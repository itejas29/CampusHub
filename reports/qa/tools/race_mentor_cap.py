"""RACE-2: the coordinator assigns N students to one mentor at the same instant.
Pass: the mentor never ends with more students than the programme's cap."""
import asyncio, json, sys  # no_5xx: a run with any 5xx is a FAIL

import httpx
from qa_common import BASE, burst, login, sql, tally

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
PROGRAM = sql("select id from internship_programs where code='SI-2025'")[0][0]
mentor_id, mentor_user = sql("select f.id, u.email from faculty f join users u on u.id=f.user_id "
                             "where u.email='leena.nambiar@campushub.example.com'")[0]


async def main():
    sql(f"update internship_programs set config = (config::jsonb - 'mentor_allocation')::json where id={PROGRAM}")
    sql(f"update internship_enrollments set mentor_faculty_id=NULL where program_id={PROGRAM} and mentor_faculty_id={mentor_id}")
    targets = [r[0] for r in sql(f"select id from internship_enrollments where program_id={PROGRAM} order by id limit {N}")]
    sql(f"update internship_enrollments set mentor_faculty_id=NULL where id in ({','.join(targets)})")
    cap = 10
    async with httpx.AsyncClient(timeout=60) as client:
        head = await login(client, "priya.nair@campushub.example.com")
        results = await burst([lambda e=e: client.post(f"{BASE}/internships/enrollments/{e}/mentor", headers=head,
                                                       json={"mentor_faculty_id": int(mentor_id), "reason": "QA race test"})
                               for e in targets])
    after = int(sql(f"select count(*) from internship_enrollments where program_id={PROGRAM} and mentor_faculty_id={mentor_id}")[0][0])
    print(json.dumps({"test": "RACE-2 mentor cap", "cap": cap, "concurrent_requests": N, "responses": tally(results),
                      "mentor_students_after": after, "over_cap_by": max(0, after - cap),
                      "verdict": "PASS" if not any(not isinstance(r, Exception) and r.status_code >= 500 for r in results) and ( after <= cap) else "FAIL"}))

asyncio.run(main())
