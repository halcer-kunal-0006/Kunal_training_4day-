"""Decorators that add logging at stage boundaries without touching the stage's logic."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .logging_config import log_event

P = ParamSpec("P")
R = TypeVar("R")


def log_stage(stage: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log when a pipeline stage starts, finishes (with its duration) or fails.

    The wrapped function keeps its name, docstring and full type signature
    (``functools.wraps`` plus ``ParamSpec``). Exceptions are logged and then
    re-raised unchanged: the decorator never hides a failure.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        logger = logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            log_event(logger, logging.INFO, "stage_started", stage=stage)
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "stage_failed",
                    stage=stage,
                    error=type(exc).__name__,
                    duration_ms=_elapsed_ms(start),
                )
                raise
            log_event(
                logger, logging.INFO, "stage_finished", stage=stage, duration_ms=_elapsed_ms(start)
            )
            return result

        return wrapper

    return decorator


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
