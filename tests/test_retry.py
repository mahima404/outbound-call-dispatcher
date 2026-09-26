import asyncio

import pytest
from conftest import CAMPAIGN, make_contacts

import dispatcher.retry as retry_module
from dispatcher.db import load_contacts
from dispatcher.dispatcher import run
from dispatcher.retry import backoff_delay


def run_one_contact(conn, max_attempts=3):
    """Runs a single contact; returns its contacts row and its attempt rows."""
    contacts = load_contacts(conn, CAMPAIGN, make_contacts(1))
    asyncio.run(run(contacts, 5, conn, CAMPAIGN, max_attempts))
    contact = conn.execute("SELECT final_status, attempt_count FROM contacts").fetchone()
    attempts = conn.execute("SELECT * FROM call_attempts ORDER BY attempt_number").fetchall()
    return contact, attempts


def test_retry_cap(conn, fake_provider):
    provider = fake_provider(["no_answer"])            # never answers

    contact, attempts = run_one_contact(conn, max_attempts=3)

    assert len(provider.calls) == 3
    assert [a["attempt_number"] for a in attempts] == [1, 2, 3]
    assert contact["final_status"] == "exhausted"
    assert contact["attempt_count"] == 3


def test_busy_handled_once(conn, fake_provider):
    provider = fake_provider(["busy", "busy"])

    contact, attempts = run_one_contact(conn, max_attempts=3)

    assert len(provider.calls) == 2                    # one retry only, even though 3 are allowed
    assert contact["final_status"] == "exhausted"
    gap = attempts[1]["claimed_at"] - attempts[0]["ended_at"]
    assert gap >= retry_module.BUSY_DELAY * 0.9        # waited the busy delay (small clock tolerance)


@pytest.mark.parametrize("disposition", ["answered", "voicemail"])
def test_terminal_dispositions_not_retried(conn, fake_provider, disposition):
    provider = fake_provider([disposition, "answered"])

    contact, attempts = run_one_contact(conn)

    assert len(provider.calls) == 1
    assert contact["final_status"] == disposition
    assert contact["attempt_count"] == 1


def test_backoff_bounds():
    for attempt in range(1, 6):
        ceiling = min(retry_module.BACKOFF_CAP, retry_module.BACKOFF_BASE * 2 ** (attempt - 1))
        for _ in range(1000):
            assert 0 <= backoff_delay(attempt) <= ceiling
