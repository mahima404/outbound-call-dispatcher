import asyncio

from conftest import CAMPAIGN, make_contacts

from dispatcher.db import load_contacts
from dispatcher.dispatcher import dispatch_attempt, run_campaign


def test_concurrent_duplicate_dispatch_calls_provider_once(conn, fake_provider):
    provider = fake_provider(["answered"], latency=0.05)
    contact = load_contacts(conn, CAMPAIGN, make_contacts(1))[0]
    stats = {"in_flight": 0, "peak_in_flight": 0, "duplicates_rejected": 0}

    async def five_at_once():
        semaphore = asyncio.Semaphore(10)
        return await asyncio.gather(
            *(dispatch_attempt(contact, 1, semaphore, stats, conn, CAMPAIGN) for _ in range(5))
        )

    results = asyncio.run(five_at_once())

    assert len(provider.calls) == 1                      # only one call went out
    assert results.count(None) == 4                      # the other four were rejected
    assert stats["duplicates_rejected"] == 4
    rows = conn.execute("SELECT COUNT(*) FROM call_attempts").fetchone()[0]
    assert rows == 1


def test_next_attempt_is_not_blocked(conn, fake_provider):
    # a business retry (attempt 2) must still go through
    provider = fake_provider(["no_answer"])
    contact = load_contacts(conn, CAMPAIGN, make_contacts(1))[0]
    stats = {"in_flight": 0, "peak_in_flight": 0, "duplicates_rejected": 0}

    async def two_attempts():
        semaphore = asyncio.Semaphore(1)
        first = await dispatch_attempt(contact, 1, semaphore, stats, conn, CAMPAIGN)
        second = await dispatch_attempt(contact, 2, semaphore, stats, conn, CAMPAIGN)
        return first, second

    assert asyncio.run(two_attempts()) == ("no_answer", "no_answer")
    assert len(provider.calls) == 2


def test_duplicate_contact_in_cohort_runs_once(conn, fake_provider):
    provider = fake_provider(["answered"])
    cohort = make_contacts(1) * 2                        # same contact listed twice

    contacts = load_contacts(conn, CAMPAIGN, cohort)
    asyncio.run(run_campaign(contacts, 5, conn, CAMPAIGN, 3))

    assert len(contacts) == 1
    assert len(provider.calls) == 1
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1
