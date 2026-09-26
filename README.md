# Outbound Call Dispatcher

A simplified outbound voice campaign dispatcher. It calls a cohort of contacts through a mock telephony provider, never exceeding a concurrent-channel limit, never placing the same call twice, retrying some outcomes with backoff, storing every attempt in SQLite, and reporting campaign analytics.

There is no real telephony: the mock provider simulates call latency and outcomes.

## Running it

Requires Python 3.9+. The dispatcher itself uses only the standard library; `pytest` is needed for the tests.

```bash
# run a simulated campaign (from the project root)
python3 driver.py --contacts 300 --concurrency 20 --max-attempts 3

# run the tests
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Driver options:

| Option | Default | Meaning |
|---|---|---|
| `--contacts` | 300 | number of synthetic contacts in the cohort |
| `--concurrency` | 20 | max calls in flight at once (the provider's channel limit) |
| `--max-attempts` | 3 | max calls per contact, including the first |
| `--db` | `campaign.db` | SQLite file, recreated on every run |

The driver prints the peak in-flight count, the number of rejected duplicates, and the analytics report. All attempts stay in the SQLite file afterwards, so they can be queried directly:

```bash
sqlite3 campaign.db "SELECT disposition, COUNT(*) FROM call_attempts GROUP BY disposition;"
```

## Project layout

```
driver.py                 builds the cohort, runs the campaign, prints the report
dispatcher/
  provider.py             mock dispatch_call(phone_number)
  db.py                   schema + claim / dialing / complete / finalize helpers
  retry.py                retry rules and backoff per disposition
  dispatcher.py           concurrency limit and per-contact lifecycle
  analytics.py            SQL for the four metrics
tests/                    concurrency, idempotency, retry and analytics tests
```

## Mock provider

`dispatch_call(phone_number)` waits a random 0.1–2.0 s, then returns a disposition with this distribution:

| Disposition | Probability |
|---|---|
| answered | 40% |
| no_answer | 25% |
| voicemail | 15% |
| busy | 10% |
| failed | 10% |

Most first attempts do not connect, which is roughly what outbound calling looks like. It also means every retry path gets exercised in a run.

## How it works

### Concurrency limit

The dispatcher uses asyncio, with one coroutine per contact and an `asyncio.Semaphore(N)` held only around the provider call. Contacts beyond N wait at the semaphore instead of failing. A channel is freed the moment a call returns, so channels are never left idle while contacts are waiting. Backoff sleeps happen outside the semaphore, so a contact waiting to retry holds no channel.

### Idempotency

Before dialing, the dispatcher inserts a `call_attempts` row with status `claimed`. The table has `UNIQUE (campaign_id, contact_id, attempt_number)`, so the database lets exactly one insert succeed. Any duplicate dispatch of the same attempt fails with `IntegrityError` and is skipped without calling the provider, and before it takes a channel. A retry uses the next attempt number, so it is allowed. Duplicate contacts in the cohort are dropped on load with `INSERT OR IGNORE`.

### Retry rules

| Disposition | Handling |
|---|---|
| answered | done |
| voicemail | done: an immediate retry would almost always hit voicemail again |
| no_answer | retry with exponential backoff + full jitter, up to `max_attempts` |
| failed | retry with exponential backoff + full jitter, up to `max_attempts` |
| busy | one retry after a fixed 4 s delay; a second busy ends the contact as exhausted |

Backoff: `delay = random.uniform(0, min(8, 0.5 × 2^(attempt − 1)))` seconds. The exponential growth spaces out repeated failures, and the jitter stops contacts that failed together from retrying together. Delays are in seconds so a simulation finishes quickly; in production they would be minutes to hours.

### Contact lifecycle

1. Contact loaded with `final_status = 'pending'`
2. Claim attempt (`claimed`); stop if it is a duplicate
3. Wait for a channel, then dial (`dialing`)
4. Record disposition, end time and latency (`completed`)
5. Retry policy decides: finish, or sleep and go back to step 2 with the next attempt number
6. Write `final_status` (`answered` / `voicemail` / `exhausted`) and `attempt_count`

## Analytics

| Metric | Definition |
|---|---|
| Connection rate | answered contacts / unique contacts with at least one completed call |
| Disposition breakdown | count and % of all completed attempts, per disposition |
| Avg attempts to resolution | mean `attempt_count` over contacts that ended answered or exhausted |
| Avg time to first connect | for answered contacts: `ended_at` of the answered call minus `claimed_at` of attempt 1, so it includes queueing and backoff |

## Known limitations

- **Single process only.** The semaphore and pending retries live in one process's memory.
- **Pending retries are lost on a crash**, and a crash mid-call leaves an attempt in `dialing` with an unknown outcome.
- **No compliance rules:** no calling-hour windows, DND checks or cross-campaign contact limits.
- **Simplified failures.** The mock provider does not separate retryable failures from permanent ones such as an invalid number.
