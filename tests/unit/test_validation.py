"""Validators classify single values correctly. They are pure functions, so no files are needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from ticket_pipeline import Priority, SchemaMismatchError
from ticket_pipeline.config import CUSTOMER_RATING_RULE, REQUIRED_COLUMNS, RESOLUTION_TIME_RULE
from ticket_pipeline.processing.validation import (
    check_schema,
    normalise_text,
    parse_number,
    parse_priority,
)

PATH = Path("tickets.csv")


@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
def test_check_schema_each_missing_column_is_reported_by_name(column: str) -> None:
    header = [name for name in REQUIRED_COLUMNS if name != column]

    with pytest.raises(SchemaMismatchError) as caught:
        check_schema(header, PATH)

    assert caught.value.missing == (column,)
    assert caught.value.found == tuple(header)


def test_check_schema_duplicated_column_is_rejected() -> None:
    with pytest.raises(SchemaMismatchError) as caught:
        check_schema([*REQUIRED_COLUMNS, "status"], PATH)

    assert caught.value.duplicated == ("status",)
    assert caught.value.missing == ()


def test_check_schema_extra_columns_and_any_order_are_allowed() -> None:
    check_schema(["agent", *reversed(REQUIRED_COLUMNS)], PATH)  # does not raise


@pytest.mark.parametrize(
    ("text", "expected"),
    [(None, None), ("", None), ("   ", None), ("  a b  ", "a b"), ("x", "x")],
)
def test_normalise_text_trims_and_treats_blank_as_missing(
    text: str | None, expected: str | None
) -> None:
    assert normalise_text(text) == expected


@pytest.mark.parametrize(
    ("text", "value", "invalid"),
    [
        ("2.5", 2.5, False),
        (" 3 ", 3.0, False),
        ("0", 0.0, False),
        ("1e1", 10.0, False),
        ("", None, False),  # missing is not invalid
        (None, None, False),
        ("bad", None, True),
        ("-2", None, True),  # below the minimum
        ("nan", None, True),
        ("inf", None, True),
        ("1_000", None, True),  # float() accepts this; real data never contains it
        ("0x10", None, True),
    ],
)
def test_parse_number_for_resolution_time(
    text: str | None, value: float | None, invalid: bool
) -> None:
    check = parse_number(text, RESOLUTION_TIME_RULE)

    assert (check.value, check.invalid) == (value, invalid)


@pytest.mark.parametrize(
    ("text", "value", "invalid"),
    [("1", 1.0, False), ("5", 5.0, False), ("5.01", None, True), ("0.99", None, True)],
)
def test_parse_number_for_customer_rating_boundaries(
    text: str, value: float | None, invalid: bool
) -> None:
    check = parse_number(text, CUSTOMER_RATING_RULE)

    assert (check.value, check.invalid) == (value, invalid)


@pytest.mark.parametrize(
    ("text", "priority", "invalid"),
    [
        ("high", Priority.HIGH, False),
        ("HIGH", Priority.HIGH, False),
        ("  low ", Priority.LOW, False),
        ("unknown", Priority.UNKNOWN, False),
        ("", Priority.UNKNOWN, False),  # missing: filled, not reported
        (None, Priority.UNKNOWN, False),
        ("urgent", Priority.UNKNOWN, True),  # unrecognised: filled and reported
    ],
)
def test_parse_priority(text: str | None, priority: Priority, invalid: bool) -> None:
    check = parse_priority(text)

    assert (check.value, check.invalid) == (priority, invalid)
