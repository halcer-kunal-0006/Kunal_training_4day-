"""Metrics over cleaned tickets. Pure functions: tickets in, numbers out, no I/O.

Averages and rates are rounded to 2 decimal places. Results are sorted by key,
so output is identical on every run.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from statistics import fmean
from typing import Any

from .models import SupportTicket


def ticket_count_by_priority(tickets: Sequence[SupportTicket]) -> dict[str, int]:
    counts = Counter(ticket.priority.value for ticket in tickets)
    return dict(sorted(counts.items()))


def average_resolution_time_by_category(tickets: Sequence[SupportTicket]) -> dict[str, float]:
    """Mean resolution time per category, using only tickets that have a valid time."""
    times: dict[str, list[float]] = defaultdict(list)
    for ticket in tickets:
        if ticket.resolution_time_hours is not None:
            times[ticket.category].append(ticket.resolution_time_hours)
    return {category: round(fmean(values), 2) for category, values in sorted(times.items())}


def average_customer_rating(tickets: Sequence[SupportTicket]) -> float | None:
    """Mean of the valid ratings, or None when no ticket has one."""
    ratings = [ticket.customer_rating for ticket in tickets if ticket.customer_rating is not None]
    return round(fmean(ratings), 2) if ratings else None


def unresolved_ticket_count(tickets: Sequence[SupportTicket]) -> int:
    return sum(not ticket.is_resolved for ticket in tickets)


def resolution_rate_by_category(tickets: Sequence[SupportTicket]) -> dict[str, float]:
    """Share of each category's tickets that are resolved or closed, from 0 to 1."""
    totals: Counter[str] = Counter()
    resolved: Counter[str] = Counter()
    for ticket in tickets:
        totals[ticket.category] += 1
        resolved[ticket.category] += ticket.is_resolved
    return {
        category: round(resolved[category] / total, 2) for category, total in sorted(totals.items())
    }


def summarise(tickets: Sequence[SupportTicket]) -> dict[str, Any]:
    """All metrics, keyed by the names used in the analytics output."""
    return {
        "ticket_count_by_priority": ticket_count_by_priority(tickets),
        "average_resolution_time_hours_by_category": average_resolution_time_by_category(tickets),
        "average_customer_rating": average_customer_rating(tickets),
        "unresolved_ticket_count": unresolved_ticket_count(tickets),
        "resolution_rate_by_category": resolution_rate_by_category(tickets),
    }
