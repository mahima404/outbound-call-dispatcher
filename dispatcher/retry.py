# Retry rules per disposition (see design doc 2.4):
#   answered   -> done: goal reached
#   voicemail  -> done: calling back right away would likely hit voicemail again
#   no_answer  -> retry with exponential backoff + jitter, up to max_attempts
#   failed     -> retry with exponential backoff + jitter, up to max_attempts
#   busy       -> retry ONCE after a fixed longer delay; a second busy ends the contact
import random

BACKOFF_BASE = 0.5       # seconds (would be minutes in production)
BACKOFF_CAP = 8.0        # never wait longer than this
BUSY_DELAY = 4.0         # fixed wait before the single busy retry


def backoff_delay(attempt_number):
    """Exponential backoff with full jitter: random between 0 and min(cap, base * 2^(n-1))."""
    ceiling = min(BACKOFF_CAP, BACKOFF_BASE * 2 ** (attempt_number - 1))
    return random.uniform(0, ceiling)


def next_action(disposition, attempt_number, busy_retries_used, max_attempts):
    """Returns ("done", final_status) or ("retry", delay_seconds)."""
    if disposition == "answered":
        return ("done", "answered")
    if disposition == "voicemail":
        return ("done", "voicemail")

    # no_answer / failed / busy: out of attempts?
    if attempt_number >= max_attempts:
        return ("done", "exhausted")

    if disposition == "busy":
        if busy_retries_used >= 1:
            return ("done", "exhausted")      # second busy: stop
        return ("retry", BUSY_DELAY)

    # no_answer or failed
    return ("retry", backoff_delay(attempt_number))
