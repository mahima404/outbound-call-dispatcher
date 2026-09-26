import pytest
from conftest import CAMPAIGN

from dispatcher.analytics import (
    avg_attempts_to_resolution,
    avg_time_to_first_connect,
    connection_rate,
    disposition_breakdown,
)
from dispatcher.db import load_contacts


def add_contact(conn, contact_id, final_status, attempts):
    """Insert a contact plus its attempts by hand. attempts = [(disposition, claimed_at, ended_at), ...]"""
    load_contacts(conn, CAMPAIGN, [{"contact_id": contact_id, "phone_number": "+91" + contact_id}])
    for n, (disposition, claimed_at, ended_at) in enumerate(attempts, start=1):
        conn.execute(
            "INSERT INTO call_attempts (campaign_id, contact_id, attempt_number, status, disposition,"
            " claimed_at, started_at, ended_at, latency_ms) VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, 0)",
            (CAMPAIGN, contact_id, n, disposition, claimed_at, claimed_at, ended_at),
        )
    conn.execute(
        "UPDATE contacts SET final_status = ?, attempt_count = ? WHERE contact_id = ?",
        (final_status, len(attempts), contact_id),
    )


@pytest.fixture
def campaign(conn):
    add_contact(conn, "A", "answered", [("answered", 100.0, 102.0)])                             # 2 s to connect
    add_contact(conn, "B", "answered", [("no_answer", 100.0, 101.0), ("answered", 105.0, 110.0)])  # 10 s
    add_contact(conn, "C", "exhausted", [("no_answer", 0, 1), ("failed", 2, 3), ("no_answer", 4, 5)])
    add_contact(conn, "D", "voicemail", [("voicemail", 0, 1)])
    return conn


def test_connection_rate(campaign):
    answered, dispatched, rate = connection_rate(campaign, CAMPAIGN)
    assert (answered, dispatched) == (2, 4)
    assert rate == pytest.approx(0.5)


def test_disposition_breakdown(campaign):
    breakdown, total = disposition_breakdown(campaign, CAMPAIGN)
    counts = {d: n for d, n, _ in breakdown}
    assert total == 7
    assert counts == {"no_answer": 3, "answered": 2, "failed": 1, "voicemail": 1}
    pct = {d: p for d, _, p in breakdown}
    assert pct["no_answer"] == pytest.approx(3 / 7)


def test_avg_attempts_to_resolution(campaign):
    # answered A=1, B=2; exhausted C=3; voicemail D excluded -> (1 + 2 + 3) / 3
    assert avg_attempts_to_resolution(campaign, CAMPAIGN) == pytest.approx(2.0)


def test_avg_time_to_first_connect(campaign):
    # A: 102 - 100 = 2 s, B: 110 - 100 = 10 s -> 6 s
    assert avg_time_to_first_connect(campaign, CAMPAIGN) == pytest.approx(6.0)
