"""RACE-6: the minor coordinator allocates N applicants at once to a minor with K
seats left. Pass: enrolments never exceed capacity and seats_filled equals the
number of active enrolments (no lost update)."""
import asyncio, json, sys  # no_5xx: a run with any 5xx is a FAIL

import httpx
from qa_common import BASE, burst, login, sql, tally

PROGRAM, FREE, N = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])


async def main():
    dept = sql(f"select department_id from minor_programs where id={PROGRAM}")[0][0]
    year = sql("select id from academic_years where is_current limit 1")[0][0]
    sql(f"delete from minor_applications where minor_program_id={PROGRAM} and remarks='QA-RACE'")
    active = int(sql(f"select count(*) from minor_enrollments where minor_program_id={PROGRAM} and status='ACTIVE'")[0][0])
    sql(f"update minor_programs set seats_filled={active}, capacity={active + FREE} where id={PROGRAM}")
    students = [r[0] for r in sql(
        f"select s.id from students s join users u on u.id=s.user_id where s.department_id<>{dept} and s.current_semester in (3, 4) "
        f"and u.email like '%@campushub.example.com' and s.id not in (select student_id from minor_enrollments) "
        f"and s.id not in (select student_id from minor_applications) order by s.id limit {N}")]
    assert students, 'no eligible synthetic students found'
    apps = []
    for sid in students:
        apps.append(sql(f"insert into minor_applications (student_id, minor_program_id, academic_year_id, preference_order, status, "
                        f"semester_at_application, submitted_at, remarks, created_at, updated_at) values ({sid}, {PROGRAM}, {year}, 1, "
                        f"'SUBMITTED', 3, now(), 'QA-RACE', now(), now()) returning id")[0][0])
    async with httpx.AsyncClient(timeout=60) as client:
        head = await login(client, "priya.nair@campushub.example.com")
        results = await burst([lambda a=a: client.post(f"{BASE}/minors/applications/{a}/decide", headers=head,
                                                       json={"status": "ALLOCATED", "remarks": "QA race"}) for a in apps])
    enrolled = int(sql(f"select count(*) from minor_enrollments where minor_program_id={PROGRAM} and status='ACTIVE'")[0][0])
    capacity, filled = map(int, sql(f"select capacity, seats_filled from minor_programs where id={PROGRAM}")[0])
    ok = enrolled <= capacity and filled == enrolled
    print(json.dumps({"test": "RACE-6 minor seats", "capacity": capacity, "free_before": FREE, "concurrent_requests": len(apps),
                      "responses": tally(results), "active_enrolments_after": enrolled, "seats_filled_counter": filled,
                      "over_capacity_by": max(0, enrolled - capacity), "counter_drift": filled - enrolled,
                      "verdict": "PASS" if not any(not isinstance(r, Exception) and r.status_code >= 500 for r in results) and ( ok) else "FAIL"}))
    # Leave no trace for the next trial.
    sql(f"delete from minor_enrollments where application_id in ({','.join(apps)})")
    sql(f"delete from minor_applications where id in ({','.join(apps)})")
    sql(f"update minor_programs set seats_filled={active} where id={PROGRAM}")

asyncio.run(main())
