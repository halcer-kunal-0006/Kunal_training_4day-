"""Structured, privacy-safe logging.

Library modules only call ``logging.getLogger(__name__)`` and ``log_event``.
Handlers are configured once, by the application entry point (``cli.main``),
through ``configure_logging``. A library that configures logging itself would
override the choices of whoever imports it.

Log line format::

    2026-11-04 10:15:02 INFO ticket_pipeline.pipeline stage_finished stage=clean duration_ms=3.1
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, TextIO

from .config import SENSITIVE_FIELDS

PACKAGE_LOGGER = "ticket_pipeline"
REDACTED = "[REDACTED]"
_FIELDS_ATTR = "fields"  # LogRecord attribute that holds the event's key=value context


def redact(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``fields`` with every sensitive key masked."""
    return {key: REDACTED if key in SENSITIVE_FIELDS else value for key, value in fields.items()}


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Log a named event with key=value context, redacting sensitive keys at the source."""
    if logger.isEnabledFor(level):
        logger.log(level, event, extra={_FIELDS_ATTR: redact(fields)}, stacklevel=2)


def _format_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set, frozenset)):
        value = ",".join(str(item) for item in value)
    text = str(value)
    return f'"{text}"' if (" " in text or not text) else text


class KeyValueFormatter(logging.Formatter):
    """Render ``event key=value ...``; values that contain spaces are quoted."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields: Mapping[str, Any] = getattr(record, _FIELDS_ATTR, {})
        if fields:
            line += " " + " ".join(f"{key}={_format_value(val)}" for key, val in fields.items())
        return line


class RedactingFilter(logging.Filter):
    """Safety net on the handler: masks sensitive keys even if a caller bypassed log_event."""

    def filter(self, record: logging.LogRecord) -> bool:
        fields = getattr(record, _FIELDS_ATTR, None)
        if isinstance(fields, Mapping):
            setattr(record, _FIELDS_ATTR, redact(fields))
        return True


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> logging.Logger:
    """Send the package's logs to ``stream`` (stderr by default) at ``level``.

    Calling it again replaces the previous handler instead of adding a second one,
    so repeated runs never print every line twice.
    """
    logger = logging.getLogger(PACKAGE_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KeyValueFormatter())
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
