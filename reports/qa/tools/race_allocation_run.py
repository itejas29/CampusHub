"""RACE-5: the coordinator triggers the same real allocation run N times at once
(double-click). Pass: each covered student holds at most one seat in the slot,
section seat counters equal the seats actually held, no 5xx."""
import asyncio, json, sys

import httpx
from qa_common import BASE, burst, login, sql, tally

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
WINDOW_CODE = "OE3-2025-LOCKED"


async def main():
    window, component = sql(f"select w.id, min(o.curriculum_component_id) from elective_registration_windows w join course_offerings o "
                            f"on o.registration_window_id=w.id where w.code='{WINDOW_CODE}' group by w.id")[0]
    body = {"curriculum_component_id": int(component), "registration_window_id": int(window), "dry_run": False,
            "strategy": "preference_order"}
    async with httpx.AsyncClient(timeout=180) as client:
        head = await login(client, "vikram.joshi@campushub.example.com")
        results = await burst([lambda: client.post(f"{BASE}/electives/admin/allocate", headers=head, json=body)
                               for _ in range(N)])
    dup = sql(f"select count(*) from (select student_id from elective_allocations where curriculum_component_id={component} "
              f"group by student_id having count(*) > 1) d")[0][0]
    held = int(sql(f"select count(*) from elective_allocations where curriculum_component_id={component}")[0][0])
    drift = sql(f"select count(*) from course_sections s join course_offerings o on o.id=s.course_offering_id "
                f"where o.registration_window_id={window} and s.seats_filled <> (select count(*) from elective_allocations a where a.section_id=s.id)")[0][0]
    offering_drift = sql(f"select count(*) from course_offerings o where o.registration_window_id={window} and "
                         f"o.seats_filled <> (select count(*) from elective_allocations a where a.course_offering_id=o.id)")[0][0]
    status = sql(f"select status from elective_registration_windows where id={window}")[0][0]
    fivexx = sum(1 for r in results if not isinstance(r, Exception) and r.status_code >= 500)
    msgs = sorted({(r.json().get("error") or {}).get("message", "")[:100] for r in results
                   if not isinstance(r, Exception) and r.status_code >= 400})
    ok = int(dup) == 0 and int(drift) == 0 and int(offering_drift) == 0 and fivexx == 0
    print(json.dumps({"test": "RACE-5 concurrent allocation runs", "concurrent_requests": N, "responses": tally(results),
                      "error_messages": msgs, "seats_held": held, "students_with_two_seats": int(dup),
                      "sections_with_wrong_counter": int(drift), "offerings_with_wrong_counter": int(offering_drift),
                      "round_status_after": status, "verdict": "PASS" if ok else "FAIL"}, indent=1))

asyncio.run(main())
