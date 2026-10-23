"""Rule based memory write decisions with deterministic source attribution."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Decision:
    outcome: str
    rules: list[str]
    source_index: int | None
    link_score: int = 0


EMAIL = re.compile(r"(?<![\w.+-])[-\w.+]+@(?:[a-z0-9-]+\.)+[a-z]{2,}(?!\w)", re.I)
REF = re.compile(r"\b(?:REF[_-][a-z0-9]+|[A-Z]{2,}[-_][0-9a-f]{4,})\b", re.I)
URL = re.compile(r"\b(?:https?://|www\.)[^\s<>'\"]+", re.I)
PATH = re.compile(r"(?<!\w)(?:[A-Za-z]:\\|/)[^\s,;<>\"']+")
NUMBER = re.compile(r"(?<!\w)(?:\d[\d,.-]{2,}\d|\d{4,})(?!\w)")
ACCOUNT = re.compile(r"(?<!\w)(?:\d{8,}|\d{4}(?:[ -]\d{4}){1,3})(?!\w)")
NAME = re.compile(r"\b[A-Z][a-z]{2,}\b")
WORD = re.compile(r"\b[a-zA-Z][a-zA-Z'-]{4,}\b")
STOP = frozenset("about after again also always because before could email every first follow from have hello here into just know later notes please regards should since still their there these those today tomorrow under update when where which while would your thanks thank subject sent receive information meeting message attached original forwarded company enron".split())
IDENTIFIERS = ((EMAIL, 18), (URL, 16), (REF, 18), (PATH, 14), (ACCOUNT, 12))


def _email_text(email: dict | None) -> str:
    if not email:
        return ""
    return "\n".join(str(email.get(key, "")) for key in ("subject", "body", "from", "to", "id"))


def _identifiers(text: str) -> list[tuple[int, int, str, int]]:
    """Return complete, non-overlapping identifiers in priority order."""
    matches = []
    for pattern, weight in IDENTIFIERS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end, _, _ in matches):
                continue
            token = match.group().rstrip(".,;:!?)]}").casefold()
            if token:
                matches.append((start, end, token, weight))
    return matches


def _tokens(text: str, rare: set[str]) -> tuple[dict[str, int], set[str]]:
    found: dict[str, int] = {}
    identifiers = _identifiers(text)
    for _, _, token, weight in identifiers:
        found[token] = max(found.get(token, 0), weight)
    occupied = [(start, end) for start, end, _, _ in identifiers]
    for pattern, weight in ((NUMBER, 5), (NAME, 3)):
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            token = match.group().rstrip(".,;:!?)]}").casefold()
            found[token] = max(found.get(token, 0), weight)
    for match in WORD.finditer(text):
        if any(match.start() < end and start < match.end() for start, end in occupied):
            continue
        token = match.group().casefold()
        if token in rare and token not in STOP:
            found[token] = max(found.get(token, 0), 1)
    return found, {token for _, _, token, _ in identifiers}


def _link(note: str, inbox: list[dict]) -> tuple[int | None, int]:
    texts = [_email_text(email) for email in inbox]
    counts = Counter(word.casefold() for text in texts for word in set(WORD.findall(text)))
    rare = {word for word, count in counts.items() if count <= max(1, len(inbox) // 4)}
    note_tokens, note_identifiers = _tokens(note, rare)
    best_index, best_score = None, 0
    candidates = []
    for index, text in enumerate(texts):
        email_tokens, email_identifiers = _tokens(text, rare)
        score = sum(min(weight, email_tokens[token]) for token, weight in note_tokens.items() if token in email_tokens)
        candidates.append((index, score, bool(note_identifiers & email_identifiers)))
    decisive = any(exact for _, _, exact in candidates)
    for index, score, exact in candidates:
        if (exact or not decisive) and score > best_score:
            best_index, best_score = index, score
    return best_index, best_score


T1 = re.compile(r"<\|[^|\n]*\|>|<s>|</s>|endoftext|\[SYSTEM\b|</EMAIL>|<prompt>|###\s*NEW\s+ROLE|^\s*(?:system|assistant|user)\s*:", re.I | re.M)
T2 = re.compile(
    r"\b(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system)(?:\s+prompt)?\s+instructions\b"
    r"|\byou\s+are\s+now\s+(?:(?:an?|the)\s+)?(?:AI|assistant|email\s+assistant|system|helpful\s+bot|digital\s+secretary)\b"
    r"|\b(?:AI|assistant)\b.{0,80}\b(?:call|invoke|use)\s+(?:(?:an?|the)\s+)?(?:API|function|tool)\b"
    r"|\b(?:after|when)\s+summari[sz]ing\b.{0,160}\b(?:send|forward|email)\b"
    r"|\bsend[_-]?email\b",
    re.I | re.S,
)
T3_PIPE = re.compile(r"\b[a-z]{2,}(?:[|¦][a-z]{2,})+\b", re.I)
N3 = re.compile(r"\b(?:the\s+assistant\s+should|assistant\s+must|(?:when|after)\s+summari[sz]ing|summary\s+process|as\s+part\s+of\s+the\s+summary)\b", re.I)
N2 = re.compile(r"\b(?:always|from\s+now\s+on|whenever|every\s+time|in\s+(?:all\s+replies|every\s+reply|every\s+email|all\s+emails)|each\s+time|for\s+every|(?:for\s+)?all\s+future|permanently|permanent\s+notes|long-term\s+memory|standing\s+(?:rule|instruction)|remember|note\s+for\s+(?:the\s+)?(?:AI|assistant))\b", re.I)
ACTION_VERB = r"(?:send|sent|sending|forward(?:ed|ing)?|email(?:ed|ing)?|repl(?:y|ied|ying)|transfer(?:red|ring)?|withdraw(?:n|ing)?|pay|paid|paying|initiat(?:e|ed|ing)|delet(?:e|ed|ing)|remov(?:e|ed|ing)|mov(?:e|ed|ing)|redirect(?:ed|ing)?|shar(?:e|ed|ing)|grant(?:ed|ing)?|unlock(?:ed|ing)?|download(?:ed|ing)?|upload(?:ed|ing)?|chang(?:e|ed|ing)|updat(?:e|ed|ing)|deposit(?:ed|ing)?|buy|bought|buying|sell|sold|selling|creat(?:e|ed|ing)|giv(?:e|en|ing)|gave|us(?:e|ed|ing)|fill(?:ed|ing)?|schedul(?:e|ed|ing)|book(?:ed|ing)?|approv(?:e|ed|ing)|enabl(?:e|ed|ing)|disabl(?:e|ed|ing)|retriev(?:e|ed|ing)|fetch(?:ed|ing)?|post(?:ed|ing)?|submit(?:ted|ting)?|install(?:ed|ing)?|run|ran|running|execut(?:e|ed|ing)|set|setting|assign(?:ed|ing)?|contact(?:ed|ing)?|notif(?:y|ied|ying)|text(?:ed|ing)?|call(?:ed|ing)?|mention(?:ed|ing)?|includ(?:e|ed|ing)|cc|block(?:ed|ing)?)"
ACTION = re.compile(r"\b" + ACTION_VERB + r"\b", re.I)
REQUEST_ACTION = re.compile(r"\b(?:wants?\s+to|requested\s+(?:to\s+)?|asked\s+to|should|needs?\s+to)\s+" + ACTION_VERB + r"\b", re.I)
MONEY = re.compile(r"(?<!\w)(?:[$€£]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|GBP))(?!\w)", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-])?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?:\s*(?:ext\.?|extension|x)\s*\d+)?(?!\w)", re.I)
PHONE_LABEL = re.compile(r"\b(?:phone|fax|telephone|tel|mobile|cell|extension|ext\.?)\s*[:#-]?\s*$", re.I)
WEAK_ACTION = re.compile(r"^(?:call(?:ed|ing)?|text(?:ed|ing)?|contact(?:ed|ing)?|notif(?:y|ied|ying)|includ(?:e|ed|ing)|us(?:e|ed|ing)|set|setting|email)$", re.I)
WEAK_NOUN_NEXT = re.compile(r"^\s+(?:information|details|info|address(?:es)?|administration|from|is|was|associates|center)\b", re.I)


def _tainted_space(text: str) -> bool:
    return any(ch in "\u200b\u200c\u200d\ufeff\u2060\u3000" or (unicodedata.category(ch) == "Zs" and ch != " ") for ch in text)


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    return next((script for script in ("LATIN", "CYRILLIC", "GREEK") if script in name), None)


def _mixed_script(text: str) -> bool:
    return any(len({_script(ch) for ch in word if _script(ch)}) > 1 for word in re.findall(r"[^\W\d_]+", text, re.UNICODE))


def _targets(text: str) -> set[str]:
    values = set()
    phone_spans = [match.span() for match in PHONE.finditer(text)]
    for pattern in (EMAIL, REF, URL, PATH, ACCOUNT, MONEY):
        for match in pattern.finditer(text):
            if pattern is ACCOUNT and (
                any(match.start() < end and start < match.end() for start, end in phone_spans)
                or PHONE_LABEL.search(text[max(0, match.start() - 25):match.start()])
            ):
                continue
            values.add(match.group().strip(".,;:!?)]").casefold())
    return values


def _action_with_target(note: str, shared_targets: set[str]) -> bool:
    if not shared_targets:
        return False
    for match in ACTION.finditer(note):
        verb = match.group()
        if verb.casefold() == "pay" and note[max(0, match.start() - 3):match.start()].casefold() == "co-":
            continue
        if not WEAK_ACTION.fullmatch(verb):
            return True
        tail = note[match.end():]
        if WEAK_NOUN_NEXT.match(tail):
            continue
        for target in shared_targets:
            target_match = re.search(re.escape(target), tail, re.I)
            if target_match and target_match.start() <= 100 and not re.search(r"[.;\n]", tail[:target_match.start()]):
                return True
    return False


def check(note: str, source_email: dict | None, owner: str, trusted_senders: set[str] = frozenset(), *, inbox: list[dict] | None = None) -> Decision:
    """Check one note. The owner is accepted for API consistency; it grants no trust."""
    if not isinstance(note, str) or not isinstance(owner, str):
        raise TypeError("note and owner must be strings")
    source = _email_text(source_email)
    rules = []
    if source and T1.search(source):
        rules.append("T1")
    if source and T2.search(source):
        rules.append("T2")
    if source and (_tainted_space(source) or _mixed_script(source) or T3_PIPE.search(source)):
        rules.append("T3")
    if N3.search(note):
        rules.append("N3")
    trusted = bool(source_email and str(source_email.get("from", "")).casefold() in {sender.casefold() for sender in trusted_senders})
    if not trusted:
        source_targets = _targets(source) if source else set().union(*(_targets(_email_text(email)) for email in (inbox or [])))
        if _action_with_target(note, _targets(note) & source_targets):
            rules.append("N1")
        if N2.search(note) or (source and N2.search(source)):
            rules.append("N2")
    outcome = "block" if any(rule in rules for rule in ("T1", "T2", "T3")) else "allow_tainted" if rules else "allow"
    index = source_email.get("source_index") if source_email else None
    return Decision(outcome, rules, index if isinstance(index, int) else None)


def check_batch(notes: list[str], inbox: list[dict], owner: str, trusted_senders: set[str] = frozenset()) -> list[Decision]:
    """Attribute every note to one email, then apply the rules."""
    decisions = []
    for note in notes:
        index, score = _link(note, inbox)
        email = dict(inbox[index], source_index=index) if index is not None else None
        result = check(note, email, owner, trusted_senders, inbox=inbox if index is None else None)
        decisions.append(Decision(result.outcome, result.rules, index, score))
    return decisions


class Gate:
    check = staticmethod(check)
    check_batch = staticmethod(check_batch)
