import asyncio

from conftest import CAMPAIGN, make_contacts

from dispatcher.db import load_contacts
from dispatcher.dispatcher import run_campaign


def test_concurrency_limit_holds(conn, fake_provider):
    provider = fake_provider(["answered"], latency=0.01)
    contacts = load_contacts(conn, CAMPAIGN, make_contacts(200))

    results, stats = asyncio.run(run_campaign(contacts, 5, conn, CAMPAIGN, 3))

    assert stats["peak_in_flight"] == 5      # dispatcher's own counter
    assert provider.max_active == 5          # measured independently by the provider
    assert len(provider.calls) == 200


def test_overflow_queues_and_does_not_fail(conn, fake_provider):
    # every disposition shows up, so retries and all terminal states get exercised
    fake_provider(["answered", "no_answer", "voicemail", "busy", "failed"], cycle=True)
    contacts = load_contacts(conn, CAMPAIGN, make_contacts(100))

    results, stats = asyncio.run(run_campaign(contacts, 3, conn, CAMPAIGN, 3))

    assert stats["peak_in_flight"] <= 3
    assert all(r in ("answered", "voicemail", "exhausted") for r in results)
    pending = conn.execute("SELECT COUNT(*) FROM contacts WHERE final_status = 'pending'").fetchone()[0]
    assert pending == 0
    unfinished = conn.execute("SELECT COUNT(*) FROM call_attempts WHERE status != 'completed'").fetchone()[0]
    assert unfinished == 0
