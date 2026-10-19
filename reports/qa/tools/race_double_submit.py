"""RACE-3: one student sends the same request N times at once (double-click).
Pass: exactly one record exists afterwards and no request fails with a 5xx."""
import asyncio, json, sys

import httpx
from qa_common import BASE, burst, login, sql, tally

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
EMAIL = "meera.joshi.004@campushub.example.com"


async def main():
    student = sql(f"select s.id from students s join users u on u.id=s.user_id where u.email='{EMAIL}'")[0][0]
    program = sql("select id from internship_programs where code='SI-2025'")[0][0]
    sql(f"delete from enrollment_stage_progress where enrollment_id in (select id from internship_enrollments where student_id={student} and program_id={program})")
    sql(f"delete from internship_enrollments where student_id={student} and program_id={program}")
    body = {"new_organization": {"name": "Zenith Data Labs", "type": "COMPANY", "city": "Ahmedabad"},
            "industry_mentor_name": "Kiran Mehta", "industry_mentor_phone": "9825012345"}
    async with httpx.AsyncClient(timeout=60) as client:
        head = await login(client, EMAIL)
        results = await burst([lambda: client.post(f"{BASE}/internships/programs/{program}/enroll", headers=head, json=body)
                               for _ in range(N)])
    rows = int(sql(f"select count(*) from internship_enrollments where student_id={student} and program_id={program}")[0][0])
    orgs = int(sql("select count(*) from organizations where name='Zenith Data Labs'")[0][0])
    progress = int(sql(f"select count(*) from enrollment_stage_progress where enrollment_id in (select id from internship_enrollments where student_id={student} and program_id={program})")[0][0])
    fivexx = sum(1 for r in results if not isinstance(r, Exception) and r.status_code >= 500)
    errors = sorted({r.json().get("error", {}).get("message", "")[:90] for r in results
                     if not isinstance(r, Exception) and r.status_code >= 400})
    print(json.dumps({"test": "RACE-3 double-submit enrolment", "concurrent_requests": N, "responses": tally(results),
                      "enrolments_after": rows, "stage_rows": progress, "organisations_named_Zenith": orgs,
                      "error_messages": errors, "verdict": "PASS" if rows == 1 and fivexx == 0 else "FAIL"}, indent=1))

asyncio.run(main())
