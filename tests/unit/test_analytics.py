"""Each metric is correct on small hand-checked inputs, including the empty case."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ticket_pipeline import Priority, SupportTicket, summarise
from ticket_pipeline.analytics import (
    average_customer_rating,
    average_resolution_time_by_category,
    resolution_rate_by_category,
    ticket_count_by_priority,
    unresolved_ticket_count,
)

MakeTicket = Callable[..., SupportTicket]


@pytest.fixture
def tickets(make_ticket: MakeTicket) -> list[SupportTicket]:
    return [
        make_ticket(ticket_id="T-1", category="billing", priority=Priority.HIGH,
                    resolution_time_hours=1.0, customer_rating=1.0, status="resolved"),
        make_ticket(ticket_id="T-2", category="billing", priority=Priority.LOW,
                    resolution_time_hours=2.0, customer_rating=2.0, status="open"),
        make_ticket(ticket_id="T-3", category="billing", priority=Priority.HIGH,
                    resolution_time_hours=None, customer_rating=2.0, status="closed"),
        make_ticket(ticket_id="T-4", category="account", priority=Priority.UNKNOWN,
                    resolution_time_hours=4.0, customer_rating=None, status="pending"),
    ]  # fmt: skip


def test_ticket_count_by_priority_is_sorted_by_name(tickets: list[SupportTicket]) -> None:
    assert ticket_count_by_priority(tickets) == {"high": 2, "low": 1, "unknown": 1}
    assert list(ticket_count_by_priority(tickets)) == ["high", "low", "unknown"]


def test_average_resolution_time_ignores_missing_times(tickets: list[SupportTicket]) -> None:
    assert average_resolution_time_by_category(tickets) == {"account": 4.0, "billing": 1.5}


def test_average_customer_rating_is_rounded_to_two_places(tickets: list[SupportTicket]) -> None:
    assert average_customer_rating(tickets) == 1.67  # (1 + 2 + 2) / 3


def test_average_customer_rating_is_none_when_no_ratings(make_ticket: MakeTicket) -> None:
    assert average_customer_rating([make_ticket(customer_rating=None)]) is None


def test_unresolved_count_excludes_resolved_and_closed(tickets: list[SupportTicket]) -> None:
    assert unresolved_ticket_count(tickets) == 2


def test_resolution_rate_by_category(tickets: list[SupportTicket]) -> None:
    assert resolution_rate_by_category(tickets) == {"account": 0.0, "billing": 0.67}


def test_summarise_on_no_tickets_returns_empty_values() -> None:
    assert summarise([]) == {
        "ticket_count_by_priority": {},
        "average_resolution_time_hours_by_category": {},
        "average_customer_rating": None,
        "unresolved_ticket_count": 0,
        "resolution_rate_by_category": {},
    }


def test_summarise_is_deterministic(tickets: list[SupportTicket]) -> None:
    assert summarise(tickets) == summarise(list(reversed(tickets)))
