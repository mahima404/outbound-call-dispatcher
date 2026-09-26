def connection_rate(conn, campaign_id):
    """Answered contacts / unique contacts dispatched (had at least one completed call)."""
    dispatched = conn.execute(
        "SELECT COUNT(DISTINCT contact_id) FROM call_attempts"
        " WHERE campaign_id = ? AND status = 'completed'",
        (campaign_id,),
    ).fetchone()[0]
    answered = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE campaign_id = ? AND final_status = 'answered'",
        (campaign_id,),
    ).fetchone()[0]
    rate = answered / dispatched if dispatched else 0.0
    return answered, dispatched, rate


def disposition_breakdown(conn, campaign_id):
    """Count and % of every completed attempt, per disposition."""
    rows = conn.execute(
        "SELECT disposition, COUNT(*) AS n FROM call_attempts"
        " WHERE campaign_id = ? AND status = 'completed'"
        " GROUP BY disposition ORDER BY n DESC",
        (campaign_id,),
    ).fetchall()
    total = sum(r["n"] for r in rows)
    return [(r["disposition"], r["n"], r["n"] / total) for r in rows], total


def avg_attempts_to_resolution(conn, campaign_id):
    """Average attempts for contacts that were answered or exhausted retries."""
    return conn.execute(
        "SELECT AVG(attempt_count) FROM contacts"
        " WHERE campaign_id = ? AND final_status IN ('answered', 'exhausted')",
        (campaign_id,),
    ).fetchone()[0]


def avg_time_to_first_connect(conn, campaign_id):
    """For answered contacts: when the answered call ended, minus when attempt 1 was claimed."""
    return conn.execute(
        """
        SELECT AVG(answered.ended_at - first.claimed_at)
        FROM call_attempts answered
        JOIN call_attempts first
          ON first.campaign_id = answered.campaign_id
         AND first.contact_id  = answered.contact_id
         AND first.attempt_number = 1
        WHERE answered.campaign_id = ? AND answered.disposition = 'answered'
        """,
        (campaign_id,),
    ).fetchone()[0]


def print_report(conn, campaign_id):
    answered, dispatched, rate = connection_rate(conn, campaign_id)
    breakdown, total_attempts = disposition_breakdown(conn, campaign_id)
    avg_attempts = avg_attempts_to_resolution(conn, campaign_id)
    avg_ttfc = avg_time_to_first_connect(conn, campaign_id)

    print(f"\nCampaign report: {campaign_id}")
    print(f"Connection rate: {rate:.1%} ({answered}/{dispatched} contacts)")
    print(f"Disposition breakdown ({total_attempts} attempts):")
    for disposition, count, pct in breakdown:
        print(f"  {disposition:<10} {count:>5}  {pct:.1%}")
    print(f"Avg attempts to resolution: {avg_attempts:.2f}" if avg_attempts is not None else "Avg attempts to resolution: n/a")
    print(f"Avg time to first connect: {avg_ttfc:.2f} s" if avg_ttfc is not None else "Avg time to first connect: n/a")
