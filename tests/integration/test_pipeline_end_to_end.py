"""The whole pipeline on the real sample file, through real files on disk.

Expected values were counted by hand from data/tickets.csv and match the Day 2
reference output (Day 2 sample_analytics_output.json), so Day 3's rewrite is
checked against an independent result, not against itself.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ticket_pipeline import (
    DuplicatePolicy,
    DuplicateTicketError,
    MalformedFileError,
    PipelineConfig,
    run_pipeline,
)

pytestmark = pytest.mark.integration

ConfigFor = Callable[..., PipelineConfig]

EXPECTED_ANALYTICS: dict[str, Any] = {
    "ticket_count_by_priority": {"high": 7, "low": 7, "medium": 8, "unknown": 1},
    "average_resolution_time_hours_by_category": {
        "account": 1.8, "billing": 3.4, "shipping": 5.3, "technical": 8.0, "unknown": 3.0,
    },
    "average_customer_rating": 4.0,
    "unresolved_ticket_count": 10,
    "resolution_rate_by_category": {
        "account": 0.8, "billing": 0.67, "shipping": 0.6, "technical": 0.33, "unknown": 0.0,
    },
    "missing_values_after_cleaning": {
        "ticket_id": 0, "category": 0, "priority": 0, "description": 0,
        "resolution_time_hours": 2, "customer_rating": 3, "status": 0,
    },
    "missing_values_before_cleaning": {
        "ticket_id": 1, "category": 1, "priority": 1, "description": 1,
        "resolution_time_hours": 0, "customer_rating": 2, "status": 1,
    },
    "invalid_numeric_values": {"resolution_time_hours": 2, "customer_rating": 1},
    "invalid_record_count": 5,
    "duplicate_ticket_ids": ["T-002"],
    "rows_dropped_missing_ticket_id": 1,
}  # fmt: skip


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sample_file_produces_the_reference_analytics(
    real_sample_csv: Path, config_for: ConfigFor
) -> None:
    result = run_pipeline(config_for(real_sample_csv))

    assert result.analytics == EXPECTED_ANALYTICS
    assert list(result.analytics) == list(EXPECTED_ANALYTICS)  # key order is stable too
    assert len(result.cleaned.tickets) == 23


def test_sample_run_writes_all_outputs_and_leaves_the_input_unchanged(
    real_sample_csv: Path, config_for: ConfigFor
) -> None:
    before = sha256(real_sample_csv)
    config = config_for(real_sample_csv)

    result = run_pipeline(config)

    assert sha256(real_sample_csv) == before
    assert set(result.outputs) == {"cleaned_csv", "quality_report", "analytics"}
    assert json.loads(config.analytics_path.read_text(encoding="utf-8")) == EXPECTED_ANALYTICS
    with config.cleaned_csv_path.open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 23
    assert config.quality_report_path.read_text(encoding="utf-8").splitlines() == [
        "source_record_number,issues",
        "7,invalid_resolution_time_hours",
        "16,invalid_resolution_time_hours",
        "17,invalid_customer_rating",
        "22,missing_ticket_id",
        "23,duplicate_ticket_id",
    ]


def test_cleaned_output_can_be_fed_back_in_without_new_issues(
    real_sample_csv: Path, config_for: ConfigFor, tmp_path: Path
) -> None:
    first = config_for(real_sample_csv)
    run_pipeline(first)
    second = PipelineConfig(first.cleaned_csv_path, tmp_path / "second")

    result = run_pipeline(second, write=False)

    assert result.cleaned.report.issues == ()
    assert result.cleaned.tickets == run_pipeline(first, write=False).cleaned.tickets


def test_write_false_creates_no_files(real_sample_csv: Path, config_for: ConfigFor) -> None:
    config = config_for(real_sample_csv)

    result = run_pipeline(config, write=False)

    assert result.outputs == {}
    assert not config.output_dir.exists()


def test_raise_policy_rejects_the_sample_duplicate(
    real_sample_csv: Path, config_for: ConfigFor
) -> None:
    config = config_for(real_sample_csv, duplicate_policy=DuplicatePolicy.RAISE)

    with pytest.raises(DuplicateTicketError) as caught:
        run_pipeline(config)

    assert (caught.value.ticket_id, caught.value.first_record, caught.value.duplicate_record) == (
        "T-002",
        2,
        23,
    )
    assert not config.output_dir.exists()  # nothing is written for a rejected file


def test_stages_are_logged_in_order(
    real_sample_csv: Path, config_for: ConfigFor, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    run_pipeline(config_for(real_sample_csv))

    stages = [
        (record.getMessage(), record.fields["stage"])  # type: ignore[attr-defined]
        for record in caplog.records
        if record.getMessage().startswith("stage_")
    ]
    assert stages == [
        ("stage_started", "load_and_clean"),
        ("stage_finished", "load_and_clean"),
        ("stage_started", "analyse"),
        ("stage_finished", "analyse"),
        ("stage_started", "write"),
        ("stage_finished", "write"),
    ]


def test_failure_logs_the_failing_stage_and_propagates(
    csv_factory: Callable[..., Path], config_for: ConfigFor, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    with pytest.raises(MalformedFileError):
        run_pipeline(config_for(csv_factory("T-1,too,few\n")))

    last = caplog.records[-1]
    assert (last.levelno, last.getMessage()) == (logging.ERROR, "stage_failed")
    assert last.fields == {  # type: ignore[attr-defined]
        "stage": "load_and_clean",
        "error": "MalformedFileError",
        "duration_ms": last.fields["duration_ms"],  # type: ignore[attr-defined]
    }
