"""Shared fixtures. Every file a test creates lives in pytest's per-test ``tmp_path``,
so tests never share state and can run alone or in any order."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import pytest

from ticket_pipeline import PipelineConfig, Priority, SupportTicket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEADER = "ticket_id,category,priority,description,resolution_time_hours,customer_rating,status\n"
# A small file that exercises every cleaning rule once.
SAMPLE_ROWS = (
    "T-1,Billing,HIGH,Charged twice,2.5,5,resolved\n"
    "t-2 , technical ,medium,App crash,bad,4,open\n"  # lower-case ID, spaces, bad number
    ",billing,low,No identifier,1,3,closed\n"  # missing ID -> dropped
    "T-1,billing,low,Duplicate of T-1,1,1,open\n"  # duplicate -> dropped
    "T-3,,urgent,,4,9,\n"  # missing labels, bad priority, rating out of range
)
SECRET_DESCRIPTION = "Customer card ending 4242 was charged twice"


class CsvFactory(Protocol):
    def __call__(self, body: str, *, name: str = ..., header: str = ...) -> Path: ...


@pytest.fixture
def csv_factory(tmp_path: Path) -> CsvFactory:
    """Write ``header + body`` to a file in tmp_path and return its path."""

    def make(body: str, *, name: str = "tickets.csv", header: str = HEADER) -> Path:
        path = tmp_path / name
        path.write_text(header + body, encoding="utf-8", newline="")
        return path

    return make


@pytest.fixture
def sample_csv(csv_factory: CsvFactory) -> Path:
    return csv_factory(SAMPLE_ROWS)


@pytest.fixture
def real_sample_csv(tmp_path: Path) -> Path:
    """A private copy of data/tickets.csv, so no test can modify the real file."""
    copy = tmp_path / "tickets.csv"
    copy.write_bytes((PROJECT_ROOT / "data" / "tickets.csv").read_bytes())
    return copy


@pytest.fixture
def config_for(tmp_path: Path) -> Callable[..., PipelineConfig]:
    """Build a PipelineConfig whose outputs go to tmp_path/output."""

    def make(input_path: Path, **overrides: Any) -> PipelineConfig:
        return PipelineConfig(input_path=input_path, output_dir=tmp_path / "output", **overrides)

    return make


@pytest.fixture
def make_ticket() -> Callable[..., SupportTicket]:
    """Build a valid SupportTicket; keyword arguments override single fields."""

    def make(**overrides: Any) -> SupportTicket:
        fields: dict[str, Any] = {
            "ticket_id": "T-1",
            "category": "billing",
            "priority": Priority.HIGH,
            "description": "Charged twice",
            "resolution_time_hours": 2.0,
            "customer_rating": 4.0,
            "status": "resolved",
        }
        fields.update(overrides)
        return SupportTicket(**fields)

    return make


@pytest.fixture(autouse=True)
def _isolate_package_logger() -> Iterator[None]:
    """Undo any handler/level/propagation change a test (e.g. the CLI) makes to the logger."""
    logger = logging.getLogger("ticket_pipeline")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    yield
    for handler in logger.handlers:
        if handler not in saved[0]:
            handler.close()
    logger.handlers, logger.level, logger.propagate = saved
