"""RACE-4: a student submits two different preference lists at the same instant.
Pass: afterwards the student holds exactly one complete list (one of the two),
ranks 1..n with no gaps or duplicates, and no request fails with a 5xx."""
import asyncio, json, sys

import httpx
from qa_common import BASE, burst, login, sql, tally

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 10


async def main():
    window, component = sql("select w.id, min(o.curriculum_component_id) from elective_registration_windows w "
                            "join course_offerings o on o.registration_window_id=w.id where w.code='OE1-2025-LIVE' group by w.id")[0]
    offerings = [int(r[0]) for r in sql(f"select id from course_offerings where registration_window_id={window} order by id")][:5]   # the round allows 3..5
    email = sql("select u.email from students s join users u on u.id=s.user_id where s.current_semester=4 "
                "and u.email like '%@campushub.example.com' order by s.id limit 1")[0][0]
    student = sql(f"select s.id from students s join users u on u.id=s.user_id where u.email='{email}'")[0][0]
    a = [{"course_offering_id": o, "preference_order": i + 1} for i, o in enumerate(offerings)]
    b = [{"course_offering_id": o, "preference_order": i + 1} for i, o in enumerate(reversed(offerings))]
    outcomes = []
    async with httpx.AsyncClient(timeout=60) as client:
        head = await login(client, email)
        for t in range(TRIALS):
            results = await burst([lambda p=p: client.post(f"{BASE}/electives/preferences", headers=head,
                                                           json={"curriculum_component_id": int(component), "preferences": p})
                                   for p in (a, b, a, b)])
            rows = sql(f"select course_offering_id, preference_order from elective_preferences "
                       f"where student_id={student} and curriculum_component_id={component} order by preference_order")
            got = [{"course_offering_id": int(o), "preference_order": int(r)} for o, r in rows]
            ok = got in (a, b) and not any(not isinstance(r, Exception) and r.status_code >= 500 for r in results)
            outcomes.append({"trial": t + 1, "responses": tally(results), "rows": len(got),
                             "matches_a_submitted_list": got in (a, b), "verdict": "PASS" if ok else "FAIL"})
    print(json.dumps({"test": "RACE-4 concurrent preference lists", "student": email.split("@")[0],
                      "offerings": len(offerings), "trials": outcomes,
                      "verdict": "PASS" if all(o["verdict"] == "PASS" for o in outcomes) else "FAIL"}, indent=1))

asyncio.run(main())
