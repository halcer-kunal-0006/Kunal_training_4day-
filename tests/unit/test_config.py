"""PipelineConfig normalises its inputs and rejects bad values; NumericRule enforces ranges."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from ticket_pipeline import DuplicatePolicy, PipelineConfig
from ticket_pipeline.config import CUSTOMER_RATING_RULE, RESOLUTION_TIME_RULE, NumericRule


def test_config_string_paths_are_stored_as_path_objects() -> None:
    config = PipelineConfig(input_path="data/t.csv", output_dir="out")  # type: ignore[arg-type]

    assert config.input_path == Path("data/t.csv")
    assert config.output_dir == Path("out")


def test_config_defaults_to_keep_first_duplicate_policy() -> None:
    config = PipelineConfig(Path("t.csv"), Path("out"))

    assert config.duplicate_policy is DuplicatePolicy.KEEP_FIRST


def test_config_output_paths_live_in_output_dir() -> None:
    config = PipelineConfig(Path("t.csv"), Path("results"))

    assert config.cleaned_csv_path == Path("results/cleaned_tickets.csv")
    assert config.quality_report_path == Path("results/quality_issues.csv")
    assert config.analytics_path == Path("results/analytics.json")


@pytest.mark.parametrize(
    ("rule", "value", "accepted"),
    [
        (RESOLUTION_TIME_RULE, 0.0, True),
        (RESOLUTION_TIME_RULE, 1e6, True),
        (RESOLUTION_TIME_RULE, -0.01, False),
        (RESOLUTION_TIME_RULE, math.inf, False),
        (RESOLUTION_TIME_RULE, math.nan, False),
        (CUSTOMER_RATING_RULE, 1.0, True),
        (CUSTOMER_RATING_RULE, 5.0, True),
        (CUSTOMER_RATING_RULE, 0.99, False),
        (CUSTOMER_RATING_RULE, 5.01, False),
    ],
)
def test_numeric_rule_accepts_only_finite_values_in_range(
    rule: NumericRule, value: float, accepted: bool
) -> None:
    assert rule.accepts(value) is accepted


@pytest.mark.parametrize(
    ("rule", "text"),
    [
        (NumericRule("x", minimum=0), "a finite number >= 0"),
        (NumericRule("x", minimum=1, maximum=5), "a finite number between 1 and 5"),
    ],
)
def test_numeric_rule_description_states_the_allowed_range(rule: NumericRule, text: str) -> None:
    assert rule.description == text
