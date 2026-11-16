"""Logs are structured and never contain customer descriptions, at any level."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import SECRET_DESCRIPTION, CsvFactory

from ticket_pipeline import PipelineConfig, configure_logging, run_pipeline
from ticket_pipeline.logging_config import (
    REDACTED,
    KeyValueFormatter,
    RedactingFilter,
    log_event,
    redact,
)


def test_redact_masks_sensitive_keys_only() -> None:
    assert redact({"description": "secret", "ticket_id": "T-1"}) == {
        "description": REDACTED,
        "ticket_id": "T-1",
    }


def test_log_event_attaches_fields_and_redacts_at_the_source(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    log_event(logging.getLogger("demo"), logging.INFO, "saved", rows=3, description="secret")

    (record,) = caplog.records
    assert record.getMessage() == "saved"
    assert record.fields == {"rows": 3, "description": REDACTED}  # type: ignore[attr-defined]


def test_log_event_below_the_level_creates_no_record(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    log_event(logging.getLogger("demo"), logging.DEBUG, "noise", rows=1)

    assert caplog.records == []


@pytest.mark.parametrize(
    ("fields", "suffix"),
    [
        ({"stage": "load", "duration_ms": 1.5}, " stage=load duration_ms=1.5"),
        ({"records": [7, 16]}, " records=7,16"),
        ({"path": "my file.csv"}, ' path="my file.csv"'),
        ({"empty": ""}, ' empty=""'),
        ({}, ""),
    ],
)
def test_formatter_renders_key_value_pairs(fields: dict[str, object], suffix: str) -> None:
    record = logging.LogRecord("pkg.mod", logging.INFO, __file__, 1, "event", None, None)
    record.fields = fields

    line = KeyValueFormatter().format(record)

    assert line.endswith(" INFO pkg.mod event" + suffix)


def test_handler_filter_redacts_even_when_log_event_is_bypassed() -> None:
    stream = io.StringIO()
    logger = configure_logging("DEBUG", stream=stream)

    logger.info("raw_call", extra={"fields": {"description": SECRET_DESCRIPTION}})

    assert SECRET_DESCRIPTION not in stream.getvalue()
    assert f"description={REDACTED}" in stream.getvalue()


def test_redacting_filter_ignores_records_without_fields() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "plain", None, None)

    assert RedactingFilter().filter(record) is True


def test_configure_logging_twice_keeps_a_single_handler() -> None:
    configure_logging("INFO")
    logger = configure_logging("DEBUG")

    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG


def test_full_debug_run_never_logs_descriptions(
    csv_factory: CsvFactory,
    config_for: Callable[..., PipelineConfig],
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = (
        f"T-1,billing,high,{SECRET_DESCRIPTION},2,5,resolved\n"
        f"T-1,billing,urgent,{SECRET_DESCRIPTION},bad,9,open\n"  # issues trigger extra logs
    )
    caplog.set_level(logging.DEBUG)

    run_pipeline(config_for(csv_factory(rows)))

    assert caplog.records, "the run should have produced logs"
    for record in caplog.records:
        assert SECRET_DESCRIPTION not in record.getMessage()
        assert SECRET_DESCRIPTION not in str(getattr(record, "fields", ""))
    assert SECRET_DESCRIPTION not in caplog.text


def test_full_run_logs_counts_needed_for_diagnosis(
    sample_csv: Path,
    config_for: Callable[..., PipelineConfig],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    run_pipeline(config_for(sample_csv), write=False)

    events = {record.getMessage(): getattr(record, "fields", {}) for record in caplog.records}
    assert events["records_cleaned"] == {"source_rows": 5, "cleaned_rows": 3, "invalid_records": 4}
    warnings = {
        record.fields["code"]: record.fields["records"]  # type: ignore[attr-defined]
        for record in caplog.records
        if record.levelno == logging.WARNING
    }
    assert warnings == {
        "duplicate_ticket_id": [4],
        "invalid_customer_rating": [5],
        "invalid_priority": [5],
        "invalid_resolution_time_hours": [2],
        "missing_ticket_id": [3],
    }


def test_run_above_warning_level_logs_no_data_issues(
    sample_csv: Path,
    config_for: Callable[..., PipelineConfig],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    run_pipeline(config_for(sample_csv), write=False)

    assert [record for record in caplog.records if record.getMessage() == "data_issue"] == []
