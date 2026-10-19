"""RACE-1: N students register at the same instant for an event with K places left.
Over capacity a student is WAITLISTED by design, so the measure is REGISTERED
(confirmed) seats. Pass: confirmed seats never exceed capacity."""
import asyncio, json, sys  # no_5xx: a run with any 5xx is a FAIL

import httpx
from qa_common import BASE, burst, login_all, sql, tally

EVENT_ID, FREE, N = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])


async def main():
    taken = int(sql(f"select count(*) from event_registrations where event_id={EVENT_ID} and status <> 'CANCELLED'")[0][0])
    confirmed_before = int(sql(f"select count(*) from event_registrations where event_id={EVENT_ID} and status = 'REGISTERED'")[0][0])
    sql(f"update events set capacity={taken + FREE} where id={EVENT_ID}")
    emails = [r[0] for r in sql(
        f"select u.email from students s join users u on u.id=s.user_id where u.email like '%@campushub.example.com' "
        f"and s.id not in (select student_id from event_registrations where event_id={EVENT_ID}) order by s.id limit {N}")]
    async with httpx.AsyncClient(timeout=60) as client:
        heads = await login_all(client, emails)
        results = await burst([lambda h=h: client.post(f"{BASE}/events/{EVENT_ID}/register", headers=h, json={})
                               for h in heads])
    after = int(sql(f"select count(*) from event_registrations where event_id={EVENT_ID} and status = 'REGISTERED'")[0][0])
    waitlisted = int(sql(f"select count(*) from event_registrations where event_id={EVENT_ID} and status = 'WAITLISTED'")[0][0])
    capacity = taken + FREE
    report = {"test": "RACE-1 event capacity", "event_id": EVENT_ID, "capacity": capacity, "confirmed_before": confirmed_before,
              "concurrent_requests": N, "responses": tally(results), "confirmed_after": after, "waitlisted_after": waitlisted,
              "oversubscribed_by": max(0, after - capacity), "verdict": "PASS" if not any(not isinstance(r, Exception) and r.status_code >= 500 for r in results) and ( after <= capacity) else "FAIL"}
    print(json.dumps(report, indent=1))

asyncio.run(main())
