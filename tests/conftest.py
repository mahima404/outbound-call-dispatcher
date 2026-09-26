# Shared test helpers. pytest loads this file automatically.
import asyncio

import pytest

import dispatcher.dispatcher as dispatcher_module
import dispatcher.retry as retry_module
from dispatcher.db import connect, create_campaign

CAMPAIGN = "c1"


class FakeProvider:
    """Stands in for dispatch_call: returns scripted dispositions and records every call."""

    def __init__(self, dispositions, latency=0.0, cycle=False):
        self.dispositions = dispositions
        self.latency = latency
        self.cycle = cycle
        self.calls = []            # phone numbers, one entry per call
        self.active = 0            # calls happening right now (counted by the provider itself)
        self.max_active = 0

    async def __call__(self, phone_number):
        i = len(self.calls)
        self.calls.append(phone_number)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.latency)
        self.active -= 1
        if self.cycle:
            return self.dispositions[i % len(self.dispositions)]
        return self.dispositions[min(i, len(self.dispositions) - 1)]   # last one repeats


@pytest.fixture
def conn():
    conn = connect(":memory:")
    create_campaign(conn, CAMPAIGN, 5, 3)
    return conn


@pytest.fixture
def fake_provider(monkeypatch):
    """Usage: provider = fake_provider(["no_answer"]) -- replaces the real dispatch_call."""
    def install(dispositions, latency=0.0, cycle=False):
        fake = FakeProvider(dispositions, latency, cycle)
        monkeypatch.setattr(dispatcher_module, "dispatch_call", fake)
        return fake
    return install


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """Shrink the backoff delays so retry tests finish in milliseconds."""
    monkeypatch.setattr(retry_module, "BACKOFF_BASE", 0.001)
    monkeypatch.setattr(retry_module, "BACKOFF_CAP", 0.004)
    monkeypatch.setattr(retry_module, "BUSY_DELAY", 0.05)


def make_contacts(n):
    return [{"contact_id": f"C{i}", "phone_number": f"+9190000{i:05d}"} for i in range(n)]
