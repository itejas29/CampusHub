"""SEC-7 horizontal and cross-scope access to one student's internship record.
Victim: a synthetic ICT Summer Internship student with a document. Every
attacker must be refused (401/403/404) on every read and write. Writes use
bodies that would succeed for the owner, so a 2xx would be a real breach."""
import asyncio, json

import httpx
from qa_common import BASE, login, sql

victim_enr, victim_student, victim_email, victim_mentor = sql(
    "select e.id, s.id, u.email, e.mentor_faculty_id from internship_enrollments e join students s on s.id=e.student_id "
    "join users u on u.id=s.user_id join internship_programs p on p.id=e.program_id "
    "where p.code='SI-2025' and e.mentor_faculty_id is not null and u.email like '%@campushub.example.com' "
    "and exists (select 1 from internship_documents d where d.enrollment_id=e.id) order by e.id limit 1")[0]
victim_file, victim_stage = sql(f"select file_id, stage_id from internship_documents where enrollment_id={victim_enr} limit 1")[0]
attacker_student = sql(f"select u.email from students s join users u on u.id=s.user_id where s.current_semester=6 "
                       f"and u.email like '%@campushub.example.com' and s.id<>{victim_student} order by s.id limit 1")[0][0]
other_mentor = sql(f"select u.email from faculty f join users u on u.id=f.user_id where f.is_demo and f.is_mentor "
                   f"and f.id<>{victim_mentor} and u.email like '%@campushub.example.com' "
                   f"and f.id not in (select faculty_id from mentor_assignments where student_id={victim_student} and is_active) "
                   f"and f.id not in (select faculty_id from faculty_role_assignments where is_active and role='COORDINATOR') "
                   f"and u.email not in ('priya.nair@campushub.example.com','admin@campushub.example.com') order by f.id limit 1")[0][0]

E = f"{BASE}/internships/enrollments/{victim_enr}"
READS = [("GET", E, None), ("GET", f"{E}/documents/expected", None), ("GET", f"{E}/progress", None),
         ("GET", f"{BASE}/student-profile/{victim_student}", None), ("GET", f"{BASE}/files/{victim_file}", None),
         ("GET", f"{BASE}/files/{victim_file}/download", None)]
WRITES = [("PATCH", E, {"industry_mentor_phone": "9876543210"}),
          ("POST", f"{E}/stages/submit", {"stage_id": int(victim_stage), "data": {}}),
          ("POST", f"{E}/stages/review", {"stage_id": int(victim_stage), "approve": True}),
          ("POST", f"{E}/evaluation", {"scores": [], "comments": "x"}),
          ("POST", f"{E}/mentor", {"mentor_faculty_id": None, "reason": "QA probe"})]
ATTACKERS = {"another student": attacker_student, "a faculty member with no relation to her (not mentor, academic mentor or coordinator)": other_mentor,
             "CSE Summer Internship coordinator": "kunal.shah@campushub.example.com",
             "ICT CSSI coordinator": "sneha.iyer@campushub.example.com"}


async def main():
    findings, table = [], {}
    async with httpx.AsyncClient(timeout=30) as client:
        owner = await login(client, victim_email)
        sanity = (await client.get(E, headers=owner)).status_code
        for who, email in ATTACKERS.items():
            head = await login(client, email)
            row = {}
            for method, url, body in READS + WRITES:
                r = await client.request(method, url, headers=head, json=body)
                row[f"{method} {url.replace(BASE, '')}"] = r.status_code
                if r.status_code < 300 or r.status_code >= 500:
                    findings.append(f"{who}: {method} {url.replace(BASE, '')} -> {r.status_code}")
            table[who] = row
    print(json.dumps({"test": "SEC-7 horizontal / cross-scope access", "owner_can_read_own_record": sanity,
                      "victim_enrollment": int(victim_enr), "results": table, "breaches_or_5xx": findings,
                      "verdict": "PASS" if not findings and sanity == 200 else "FAIL"}, indent=1))

asyncio.run(main())
