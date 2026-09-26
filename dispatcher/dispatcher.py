import asyncio
import time
from dispatcher.provider import dispatch_call
from dispatcher.db import claim_attempt, mark_dialing, complete_attempt, finalize_contact
from dispatcher.retry import next_action

async def dispatch_attempt(contact, attempt_number, semaphore, stats, conn, campaign_id):
    """One attempt: claim, wait for a channel, dial, record. Returns disposition, or None if duplicate."""
    attempt_id = claim_attempt(conn, campaign_id, contact["contact_id"], attempt_number)
    if attempt_id is None:
        stats["duplicates_rejected"] += 1
        return None

    async with semaphore:
        stats["in_flight"] += 1
        stats["peak_in_flight"] = max(stats["peak_in_flight"], stats["in_flight"])
        try:
            mark_dialing(conn, attempt_id)
            start = time.monotonic()
            disposition = await dispatch_call(contact["phone_number"])
            latency_ms = int((time.monotonic() - start) * 1000)
        finally:
            stats["in_flight"] -= 1

    complete_attempt(conn, attempt_id, disposition, latency_ms)
    return disposition


async def run_contact(contact, semaphore, stats, conn, campaign_id, max_attempts):
    """Keep calling one contact until the retry policy says it's done."""
    attempt_number = 1
    busy_retries_used = 0

    while True:
        disposition = await dispatch_attempt(contact, attempt_number, semaphore, stats, conn, campaign_id)
        if disposition is None:
            return None                 # another dispatch owns this attempt; stop

        action, value = next_action(disposition, attempt_number, busy_retries_used, max_attempts)

        if action == "done":
            final_status = value
            finalize_contact(conn, campaign_id, contact["contact_id"], final_status, attempt_number)
            return final_status

        # action == "retry": wait OUTSIDE the semaphore, so no channel is held
        delay_seconds = value
        if disposition == "busy":
            busy_retries_used += 1
        await asyncio.sleep(delay_seconds)
        attempt_number += 1


async def run_campaign(contacts, max_concurrency, conn, campaign_id, max_attempts):
    semaphore = asyncio.Semaphore(max_concurrency)
    stats = {"in_flight": 0, "peak_in_flight": 0, "duplicates_rejected": 0}
    results = await asyncio.gather(*(run_contact(c, semaphore, stats, conn, campaign_id, max_attempts) for c in contacts))
    return results, stats
