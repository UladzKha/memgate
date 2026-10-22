"""Tagged memory entries produced by the deterministic write gate."""

from __future__ import annotations

from dataclasses import dataclass

from .gate import check_batch, _targets


@dataclass(frozen=True)
class MemoryEntry:
    text: str
    outcome: str
    rules: list[str]
    source_sender: str | None
    source_trusted: bool
    targets: list[str]


def write_memory(notes: list[str], inbox: list[dict], owner: str,
                 trusted_senders: set[str] = frozenset()) -> list[MemoryEntry]:
    """Keep allow and allow_tainted notes with provenance; drop blocks."""
    trusted = {sender.casefold() for sender in trusted_senders}
    entries = []
    for note, decision in zip(notes, check_batch(notes, inbox, owner, trusted_senders)):
        if decision.outcome == "block":
            continue
        source = inbox[decision.source_index] if decision.source_index is not None else None
        sender = str(source.get("from", "")) if source else None
        entries.append(MemoryEntry(
            text=note, outcome=decision.outcome, rules=list(decision.rules),
            source_sender=sender, source_trusted=bool(sender and sender.casefold() in trusted),
            targets=sorted(_targets(note)),
        ))
    return entries
