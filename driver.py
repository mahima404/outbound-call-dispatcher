# Driver: plays the client. Builds a synthetic cohort, runs the campaign,
# and prints the analytics.
#
# Run from the project root:
#   python3 -m driver --contacts 300 --concurrency 20
import argparse
import os
import random
import asyncio

from dispatcher.db import connect, create_campaign, load_contacts
from dispatcher.dispatcher import run_campaign
from dispatcher.analytics import print_report


NAMES = ["Aarav", "Diya", "Kabir", "Ananya", "Rohan", "Isha", "Vikram", "Meera", "Arjun", "Sara"]

def generate_cohort(n):
    contacts = []
    for i in range(1, n+1):
        contacts.append({
            "contact_id": f"C{i:04d}",
            "phone_number": f"+91{random.randint(6000000000, 9999999999)}",
            # per-contact variables the voice agent would use to personalise the call;
            # the dispatcher itself only needs contact_id and phone_number
            "name": random.choice(NAMES),
            "account_ref": f"LN{random.randint(100000, 999999)}",
        })
    return contacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contacts", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--db", default="campaign.db")
    args = parser.parse_args()

    if os.path.exists(args.db):
        os.remove(args.db)
    conn = connect(args.db)

    cohort = generate_cohort(args.contacts)
    print(f"Generated {len(cohort)} contacts")
    for c in cohort[:3]:
        print(c)

    campaign_id = "campaign-1"
    create_campaign(conn, campaign_id, args.concurrency, args.max_attempts)
    contacts = load_contacts(conn, campaign_id, cohort)
    results, stats = asyncio.run(run_campaign(contacts, args.concurrency, conn, campaign_id, args.max_attempts))
    # results holds each contact's final status (None if its lifecycle was a duplicate)
    finished = [r for r in results if r is not None]
    print(f"Contacts finished: {len(finished)}")
    print(f"Duplicates rejected: {stats['duplicates_rejected']}")
    print(f"Peak in-flight: {stats['peak_in_flight']} (limit {args.concurrency})")
    print_report(conn, campaign_id)

if __name__ == "__main__":
    main()
