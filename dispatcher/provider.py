# It simulates dialing a phone number, waits random 0.1 - 2s, then gives a random disposition
import asyncio
import random

# answered 40%, no_answer 25%, voicemail 15%, busy 10%, failed 10%.
DISPOSITIONS = ["answered", "no_answer", "voicemail", "busy", "failed"]
DISPOSITION_WEIGHTS = [0.40, 0.25, 0.15, 0.10, 0.10]

async def dispatch_call(phone_number):
    await asyncio.sleep(random.uniform(0.1, 2))
    return random.choices(DISPOSITIONS, weights=DISPOSITION_WEIGHTS, k=1)[0]

