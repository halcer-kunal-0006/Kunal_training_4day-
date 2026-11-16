"""Command-line entry point: ``ticket-pipeline`` or ``python -m ticket_pipeline``.

This is the only place in the package that catches errors. It catches
``TicketPipelineError`` alone: those are expected, user-fixable problems, so the
user gets a one-line actionable message and exit code 2. Any other exception
is a bug, and it is deliberately left to crash with a full traceback.

Exit codes: 0 success; 2 the input or output was rejected (argparse also uses 2
for invalid options).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from .config import LOG_LEVELS, DuplicatePolicy, PipelineConfig
from .errors import TicketPipelineError
from .logging_config import configure_logging, log_event
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_PIPELINE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ticket-pipeline",
        description="Clean a support-ticket CSV and report analytics and data-quality issues.",
    )
    parser.add_argument("--input", default="data/tickets.csv", help="CSV file to read")
    parser.add_argument("--output-dir", default="output", help="folder for the result files")
    parser.add_argument(
        "--duplicate-policy",
        choices=[policy.value for policy in DuplicatePolicy],
        default=DuplicatePolicy.KEEP_FIRST.value,
        help="keep_first: keep the first copy of a repeated ID; raise: stop the run",
    )
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)
    try:
        config = PipelineConfig(
            input_path=args.input,
            output_dir=args.output_dir,
            duplicate_policy=DuplicatePolicy(args.duplicate_policy),
        )
        result = run_pipeline(config)
    except TicketPipelineError as exc:
        log_event(logger, logging.ERROR, "pipeline_failed", error=type(exc).__name__)
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_PIPELINE_ERROR

    print(json.dumps(result.analytics, indent=2))
    return EXIT_OK
