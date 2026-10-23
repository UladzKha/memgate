"""Pure action-time guard for identifiers learned from untrusted memory."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .gate import ACCOUNT, EMAIL, MONEY, PATH, REF, URL, _targets


class GuardResult(str):
    """A string outcome with a machine-readable explanation."""

    reason: str | None
    identifier: str | None

    def __new__(cls, outcome: str, reason: str | None = None, identifier: str | None = None):
        result = str.__new__(cls, outcome)
        result.reason = reason
        result.identifier = identifier
        return result


def _amount(value: str) -> str:
    digits = re.sub(r"[^0-9.]", "", value)
    try:
        return format(Decimal(digits).normalize(), "f")
    except InvalidOperation:
        return digits


def _canonical(target: str) -> str:
    value = target.strip().casefold()
    if MONEY.fullmatch(value):
        return "amount:" + _amount(value)
    if EMAIL.fullmatch(value):
        relay = re.fullmatch(r"(c_[0-9a-f]+)@relay\.example\.[a-z]+", value)
        if relay:
            return "email:" + relay[1] + "@relay.example.*"
        return "email:" + value
    if REF.fullmatch(value):
        return "ref:" + value
    if URL.fullmatch(value):
        return "url:" + value.rstrip(".,;:!?)")
    if PATH.fullmatch(value):
        return "path:" + value
    if ACCOUNT.fullmatch(value):
        return "account:" + re.sub(r"\D", "", value)
    return value


def _arg_targets(value: Any, key: str = "") -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_arg_targets(item, str(name)) for name, item in value.items()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_arg_targets(item, key) for item in value))
    if value is None or isinstance(value, bool):
        return set()
    text = str(value)
    result = {_canonical(target) for target in _targets(text)}
    if key.casefold() in {"amount", "price", "sum"} and isinstance(value, (int, float, str)):
        number = _amount(text)
        if number:
            result.add("amount:" + number)
    return result


def guard(tool_name: str, args: dict, memory: list, trusted: set[str], user_text: str,
          policy: str = "strict") -> GuardResult:
    """Deny targets from memory according to the selected pure guard policy."""
    if policy not in ("strict", "tainted_only"):
        raise ValueError(f"Unknown action-guard policy: {policy}")
    action_targets = _arg_targets(args)
    trusted_targets = {_canonical(target) for value in trusted for target in (_targets(value) or {value})}
    user_targets = {_canonical(target) for target in _targets(user_text)}
    for entry in memory:
        source_trusted = entry.source_trusted if hasattr(entry, "source_trusted") else entry["source_trusted"]
        if source_trusted:
            continue
        outcome = entry.outcome if hasattr(entry, "outcome") else entry["outcome"]
        if policy == "tainted_only" and outcome != "allow_tainted":
            continue
        targets = entry.targets if hasattr(entry, "targets") else entry["targets"]
        for target in targets:
            canonical = _canonical(target)
            if canonical in action_targets and canonical not in trusted_targets and canonical not in user_targets:
                return GuardResult("deny", f"{tool_name} uses {target} from untrusted memory; ask the user before acting", target)
    return GuardResult("allow")


def guard_strict(tool_name: str, args: dict, memory: list, trusted: set[str],
                 user_text: str) -> GuardResult:
    """Deny targets from any memory entry with an untrusted source sender."""
    return guard(tool_name, args, memory, trusted, user_text, policy="strict")


def guard_tainted_only(tool_name: str, args: dict, memory: list, trusted: set[str],
                       user_text: str) -> GuardResult:
    """Deny targets only from untrusted allow_tainted memory entries."""
    return guard(tool_name, args, memory, trusted, user_text, policy="tainted_only")
