import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id     TEXT PRIMARY KEY,
  max_concurrency INTEGER NOT NULL,
  max_attempts    INTEGER NOT NULL,
  created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
  campaign_id   TEXT NOT NULL,
  contact_id    TEXT NOT NULL,
  phone_number  TEXT NOT NULL,
  final_status  TEXT NOT NULL DEFAULT 'pending'
                CHECK (final_status IN ('pending', 'answered', 'voicemail', 'exhausted')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (campaign_id, contact_id)
);

CREATE TABLE IF NOT EXISTS call_attempts (
  attempt_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id    TEXT NOT NULL,
  contact_id     TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  status         TEXT NOT NULL
                 CHECK (status IN ('claimed', 'dialing', 'completed')),
  disposition    TEXT             -- null until completed
                 CHECK (disposition IN ('answered', 'no_answer', 'voicemail', 'busy', 'failed')),
  claimed_at     REAL NOT NULL,   -- epoch seconds
  started_at     REAL,
  ended_at       REAL,
  latency_ms     INTEGER,
  UNIQUE (campaign_id, contact_id, attempt_number)
);
"""


def connect(path="campaign.db"):
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def create_campaign(conn, campaign_id, max_concurrency, max_attempts):
    conn.execute(
        "INSERT INTO campaigns (campaign_id, max_concurrency, max_attempts, created_at) VALUES (?, ?, ?, ?)",
        (campaign_id, max_concurrency, max_attempts, time.time()),
    )


def load_contacts(conn, campaign_id, contacts):
    """Insert contacts, skipping duplicates. Returns only the ones actually inserted."""
    inserted = []
    for c in contacts:
        cur = conn.execute(
            "INSERT OR IGNORE INTO contacts (campaign_id, contact_id, phone_number) VALUES (?, ?, ?)",
            (campaign_id, c["contact_id"], c["phone_number"]),
        )
        if cur.rowcount == 1: 
            inserted.append(c)
    return inserted


def claim_attempt(conn, campaign_id, contact_id, attempt_number):
    """Reserve an attempt. Returns its attempt_id, or None if someone already claimed it."""
    try:
        cur = conn.execute(
            "INSERT INTO call_attempts (campaign_id, contact_id, attempt_number, status, claimed_at)"
            " VALUES (?, ?, ?, 'claimed', ?)",
            (campaign_id, contact_id, attempt_number, time.time()),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:     # UNIQUE (campaign_id, contact_id, attempt_number) violated
        return None


def mark_dialing(conn, attempt_id):
    conn.execute(
        "UPDATE call_attempts SET status = 'dialing', started_at = ? WHERE attempt_id = ?",
        (time.time(), attempt_id),
    )


def complete_attempt(conn, attempt_id, disposition, latency_ms):
    conn.execute(
        "UPDATE call_attempts SET status = 'completed', disposition = ?, ended_at = ?, latency_ms = ?"
        " WHERE attempt_id = ?",
        (disposition, time.time(), latency_ms, attempt_id),
    )


def finalize_contact(conn, campaign_id, contact_id, final_status, attempt_count):
    conn.execute(
        "UPDATE contacts SET final_status = ?, attempt_count = ? WHERE campaign_id = ? AND contact_id = ?",
        (final_status, attempt_count, campaign_id, contact_id),
    )
