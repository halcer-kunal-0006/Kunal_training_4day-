"""Decide whether values are valid. Deciding what to do about invalid values is cleaning's job.

Every function here is pure: text in, verdict out, no I/O and no logging.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..config import REQUIRED_COLUMNS, NumericRule
from ..errors import SchemaMismatchError
from ..models import KNOWN_PRIORITIES, Priority

# Plain decimal notation only. Rejects text that Python's float() would accept
# but which is never a real measurement: "nan", "inf", "1_000", "0x10".
_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def check_schema(
    header: Sequence[str], path: Path, required: Sequence[str] = REQUIRED_COLUMNS
) -> None:
    """Raise SchemaMismatchError unless every required column appears exactly once.

    Extra columns are allowed; they are ignored by cleaning.
    """
    missing = [column for column in required if column not in header]
    duplicated = sorted(column for column, count in Counter(header).items() if count > 1)
    if missing or duplicated:
        raise SchemaMismatchError(path, missing=missing, found=header, duplicated=duplicated)


def normalise_text(value: str | None) -> str | None:
    """Trim whitespace; an empty or whitespace-only value becomes None (missing)."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True, slots=True)
class NumberCheck:
    """The parsed value (None if missing or invalid) and whether the text was invalid."""

    value: float | None
    invalid: bool


def parse_number(text: str | None, rule: NumericRule) -> NumberCheck:
    """Parse one numeric cell.

    Empty -> missing (not invalid). Non-numeric, non-finite or out-of-range -> invalid.
    """
    cleaned = normalise_text(text)
    if cleaned is None:
        return NumberCheck(None, invalid=False)
    if not _DECIMAL.fullmatch(cleaned):
        return NumberCheck(None, invalid=True)
    number = float(cleaned)
    if not rule.accepts(number):
        return NumberCheck(None, invalid=True)
    return NumberCheck(number, invalid=False)


@dataclass(frozen=True, slots=True)
class PriorityCheck:
    value: Priority
    invalid: bool


def parse_priority(text: str | None) -> PriorityCheck:
    """Normalise case and spaces. Missing -> UNKNOWN; unrecognised -> UNKNOWN and invalid."""
    cleaned = normalise_text(text)
    if cleaned is None:
        return PriorityCheck(Priority.UNKNOWN, invalid=False)
    lowered = cleaned.lower()
    if lowered not in KNOWN_PRIORITIES:
        return PriorityCheck(Priority.UNKNOWN, invalid=True)
    return PriorityCheck(Priority(lowered), invalid=False)
