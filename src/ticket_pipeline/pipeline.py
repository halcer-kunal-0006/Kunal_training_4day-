"""Connect the stages. The pipeline holds no cleaning rules or metric logic of its own.

    open_ticket_csv -> clean_records -> summarise -> writers

Each stage is wrapped in ``@log_stage``, so every run logs where time was
spent and which stage failed, without logging code inside the stages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analytics import summarise
from .config import PipelineConfig
from .decorators import log_stage
from .logging_config import log_event
from .processing.cleaning import CleaningResult, clean_records
from .processing.loader import open_ticket_csv
from .processing.writers import write_cleaned_csv, write_json, write_quality_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    cleaned: CleaningResult
    analytics: dict[str, Any]  # metrics followed by the data-quality fields
    outputs: dict[str, Path] = field(default_factory=dict)  # empty when write=False


def run_pipeline(config: PipelineConfig, *, write: bool = True) -> PipelineResult:
    """Run every stage for ``config``; with ``write=False`` nothing is saved to disk."""
    log_event(
        logger,
        logging.INFO,
        "pipeline_started",
        input=config.input_path.name,
        duplicate_policy=config.duplicate_policy.value,
    )
    cleaned = _load_and_clean(config)
    analytics = _analyse(cleaned)
    outputs = _write_outputs(config, cleaned, analytics) if write else {}
    log_event(
        logger,
        logging.INFO,
        "pipeline_finished",
        tickets=cleaned.report.cleaned_rows,
        invalid_records=cleaned.report.invalid_record_count,
        outputs=len(outputs),
    )
    return PipelineResult(cleaned, analytics, outputs)


@log_stage("load_and_clean")
def _load_and_clean(config: PipelineConfig) -> CleaningResult:
    # Records stream from the file straight into cleaning, so loading and
    # cleaning are one stage; the file is closed when the `with` block ends.
    with open_ticket_csv(config.input_path) as reader:
        return clean_records(reader, config.duplicate_policy)


@log_stage("analyse")
def _analyse(cleaned: CleaningResult) -> dict[str, Any]:
    return {**summarise(cleaned.tickets), **cleaned.report.quality_summary()}


@log_stage("write")
def _write_outputs(
    config: PipelineConfig, cleaned: CleaningResult, analytics: dict[str, Any]
) -> dict[str, Path]:
    protected = [config.input_path]
    return {
        "cleaned_csv": write_cleaned_csv(cleaned.tickets, config.cleaned_csv_path, protected),
        "quality_report": write_quality_report(
            cleaned.report, config.quality_report_path, protected
        ),
        "analytics": write_json(analytics, config.analytics_path, protected),
    }
