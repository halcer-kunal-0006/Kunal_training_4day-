"""Configuration and schema rules, each defined in exactly one place.

Everything here is immutable (tuples, frozensets, frozen dataclasses), so it is
safe to share between modules and between pipeline runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

REQUIRED_COLUMNS: tuple[str, ...] = (
    "ticket_id",
    "category",
    "priority",
    "description",
    "resolution_time_hours",
    "customer_rating",
    "status",
)
# Lower-cased on cleaning; a missing value becomes UNKNOWN.
LABEL_COLUMNS: tuple[str, ...] = ("category", "status")
RESOLVED_STATUSES: frozenset[str] = frozenset({"resolved", "closed"})
UNKNOWN = "unknown"
# Free text written by customers. It is never written to logs.
SENSITIVE_FIELDS: frozenset[str] = frozenset({"description"})
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")  # CLI choices


class DuplicatePolicy(Enum):
    KEEP_FIRST = "keep_first"  # the first row in the file wins; later copies are reported
    RAISE = "raise"  # refuse the file until duplicates are reviewed


@dataclass(frozen=True)
class NumericRule:
    """Allowed range for one numeric column (``maximum=None`` means no upper limit)."""

    column: str
    minimum: float
    maximum: float | None = None

    def accepts(self, value: float) -> bool:
        if not math.isfinite(value) or value < self.minimum:
            return False
        return self.maximum is None or value <= self.maximum

    @property
    def description(self) -> str:
        if self.maximum is None:
            return f"a finite number >= {self.minimum:g}"
        return f"a finite number between {self.minimum:g} and {self.maximum:g}"


RESOLUTION_TIME_RULE = NumericRule("resolution_time_hours", minimum=0)
CUSTOMER_RATING_RULE = NumericRule("customer_rating", minimum=1, maximum=5)
NUMERIC_RULES: tuple[NumericRule, ...] = (RESOLUTION_TIME_RULE, CUSTOMER_RATING_RULE)


@dataclass(frozen=True)
class PipelineConfig:
    """Everything one pipeline run needs. Paths are normalised to ``Path`` objects."""

    input_path: Path
    output_dir: Path
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.KEEP_FIRST

    def __post_init__(self) -> None:
        # Accept plain strings from callers, but always store Path objects.
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))

    @property
    def cleaned_csv_path(self) -> Path:
        return self.output_dir / "cleaned_tickets.csv"

    @property
    def quality_report_path(self) -> Path:
        return self.output_dir / "quality_issues.csv"

    @property
    def analytics_path(self) -> Path:
        return self.output_dir / "analytics.json"
