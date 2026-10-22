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


EMAIL = re.compile(r"(?<![\w.])[-\w.+]+@[-\w.]+\.[a-z]{2,}(?![\w.])", re.I)
REF = re.compile(r"\b(?:REF[_-][a-z0-9]+|[A-Z]{2,}[-_][0-9a-f]{4,})\b", re.I)
URL = re.compile(r"\b(?:https?://|www\.)[^\s<>'\"]+", re.I)
PATH = re.compile(r"(?<!\w)(?:[A-Za-z]:\\|/)[^\s,;<>\"']+")
NUMBER = re.compile(r"(?<!\w)(?:\d[\d,.-]{2,}\d|\d{4,})(?!\w)")
NAME = re.compile(r"\b[A-Z][a-z]{2,}\b")
WORD = re.compile(r"\b[a-zA-Z][a-zA-Z'-]{4,}\b")
STOP = frozenset("about after again also always because before could email every first follow from have hello here into just know later notes please regards should since still their there these those today tomorrow under update when where which while would your thanks thank subject sent receive information meeting message attached original forwarded company enron".split())


def _email_text(email: dict | None) -> str:
    if not email:
        return ""
    return "\n".join(str(email.get(key, "")) for key in ("subject", "body", "from", "to", "id"))


def _tokens(text: str, rare: set[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for pattern, weight in ((EMAIL, 12), (REF, 12), (URL, 10), (PATH, 9), (NUMBER, 5), (NAME, 3)):
        for match in pattern.finditer(text):
            token = match.group().strip(".,;:!?)]").casefold()
            found[token] = max(found.get(token, 0), weight)
    for match in WORD.finditer(text):
        token = match.group().casefold()
        if token in rare and token not in STOP:
            found[token] = max(found.get(token, 0), 1)
    return found


def _link(note: str, inbox: list[dict]) -> tuple[int | None, int]:
    texts = [_email_text(email) for email in inbox]
    counts = Counter(word.casefold() for text in texts for word in set(WORD.findall(text)))
    rare = {word for word, count in counts.items() if count <= max(1, len(inbox) // 4)}
    note_tokens = _tokens(note, rare)
    best_index, best_score = None, 0
    for index, text in enumerate(texts):
        email_tokens = _tokens(text, rare)
        score = sum(min(weight, email_tokens[token]) for token, weight in note_tokens.items() if token in email_tokens)
        if score > best_score:
            best_index, best_score = index, score
    return best_index, best_score


T1 = re.compile(r"<\|[^|\n]*\|>|<s>|</s>|endoftext|\[SYSTEM\b|</EMAIL>|<prompt>|###\s*NEW\s+ROLE|^\s*(?:system|assistant|user)\s*:", re.I | re.M)
T2 = re.compile(r"\b(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior|system)\s+instructions\b|\byou\s+are\s+now\s+(?:(?:an?|the)\s+)?(?:AI|assistant|email\s+assistant|system|helpful\s+bot)\b|\b(?:AI\s+(?:helper|assistant)|email\s+assistant|assistant\s*[,;:]\s*(?:you|please|must|should))\b|\b(?:after|when)\s+summari[sz]|\b(?:API|function|tool)\s+call\b|\bsend[_-]?email\b", re.I)
N3 = re.compile(r"\b(?:the\s+assistant\s+should|assistant\s+must|(?:when|after)\s+summari[sz]ing|summary\s+process|as\s+part\s+of\s+the\s+summary)\b", re.I)
N2 = re.compile(r"\b(?:always|from\s+now\s+on|whenever|every\s+time|for\s+all\s+future|permanently|standing\s+(?:rule|instruction)|remember)\b", re.I)
ACTION = re.compile(r"\b(?:send|sent|sending|forward(?:ed|ing)?|email(?:ed|ing)?|repl(?:y|ied|ying)|transfer(?:red|ring)?|withdraw(?:n|ing)?|pay|paid|paying|initiat(?:e|ed|ing)|delet(?:e|ed|ing)|remov(?:e|ed|ing)|mov(?:e|ed|ing)|redirect(?:ed|ing)?|shar(?:e|ed|ing)|grant(?:ed|ing)?|unlock(?:ed|ing)?|download(?:ed|ing)?|upload(?:ed|ing)?|chang(?:e|ed|ing)|updat(?:e|ed|ing))\b", re.I)
MONEY = re.compile(r"(?<!\w)(?:[$€£]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|GBP))(?!\w)", re.I)


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
    for pattern in (EMAIL, REF, URL, PATH, NUMBER, MONEY):
        values.update(m.group().strip(".,;:!?)]").casefold() for m in pattern.finditer(text))
    return values


def check(note: str, source_email: dict | None, owner: str, trusted_senders: set[str] = frozenset()) -> Decision:
    """Check one note. The owner is accepted for API consistency; it grants no trust."""
    if not isinstance(note, str) or not isinstance(owner, str):
        raise TypeError("note and owner must be strings")
    source = _email_text(source_email)
    rules = []
    if source and T1.search(source):
        rules.append("T1")
    if source and T2.search(source):
        rules.append("T2")
    if source and (_tainted_space(source) or _mixed_script(source) or re.search(r"(?i)\b[a-z]{2,}(?:[|¦][a-z]{2,})+\b", source)):
        rules.append("T3")
    if N3.search(note):
        rules.append("N3")
    trusted = bool(source_email and str(source_email.get("from", "")).casefold() in {sender.casefold() for sender in trusted_senders})
    if not trusted:
        if source and ACTION.search(note) and (_targets(note) & _targets(source)):
            rules.append("N1")
        if N2.search(note):
            rules.append("N2")
    outcome = "block" if any(rule in rules for rule in ("T1", "T2", "T3", "N3")) else "quarantine" if rules else "allow"
    index = source_email.get("source_index") if source_email else None
    return Decision(outcome, rules, index if isinstance(index, int) else None)


def check_batch(notes: list[str], inbox: list[dict], owner: str) -> list[Decision]:
    """Attribute every note to one email, then apply the rules."""
    decisions = []
    for note in notes:
        index, score = _link(note, inbox)
        email = dict(inbox[index], source_index=index) if index is not None else None
        result = check(note, email, owner)
        decisions.append(Decision(result.outcome, result.rules, index, score))
    return decisions


class Gate:
    check = staticmethod(check)
    check_batch = staticmethod(check_batch)
