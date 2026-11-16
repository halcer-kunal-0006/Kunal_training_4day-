"""@log_stage logs stage boundaries with a duration, preserves the wrapped function,
and never swallows exceptions. The clock is patched so durations are exact."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import pytest

from ticket_pipeline.decorators import log_stage


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every call to perf_counter advances exactly 0.25 seconds."""
    ticks: Iterator[float] = iter([10.0, 10.25, 10.5, 10.75])
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))


@log_stage("double")
def double(value: int) -> int:
    """Return twice the value."""
    return value * 2


@log_stage("explode")
def explode() -> None:
    raise KeyError("boom")


def stage_events(caplog: pytest.LogCaptureFixture) -> list[tuple[str, dict[str, object]]]:
    return [(record.getMessage(), getattr(record, "fields", {})) for record in caplog.records]


def test_decorator_preserves_name_docstring_and_result() -> None:
    assert double.__name__ == "double"
    assert double.__doc__ == "Return twice the value."
    assert double(21) == 42


@pytest.mark.usefixtures("fake_clock")
def test_successful_stage_logs_start_and_finish_with_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    double(1)

    assert stage_events(caplog) == [
        ("stage_started", {"stage": "double"}),
        ("stage_finished", {"stage": "double", "duration_ms": 250.0}),
    ]


@pytest.mark.usefixtures("fake_clock")
def test_failing_stage_logs_error_and_reraises_the_same_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    with pytest.raises(KeyError, match="boom"):
        explode()

    failed = caplog.records[-1]
    assert failed.levelno == logging.ERROR
    assert stage_events(caplog)[-1] == (
        "stage_failed",
        {"stage": "explode", "error": "KeyError", "duration_ms": 250.0},
    )
