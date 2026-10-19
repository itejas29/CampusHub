"""Build CampusHub_Test_Case_Matrix.csv from the final JUnit results (both
databases) plus the QA probes. Counts are executed tests, not test functions."""
import collections, csv, json, pathlib, xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"

MODULES = {
    "Authentication, sessions & accounts": ["test_security", "test_account_security", "test_rbac", "test_cors", "test_hardening"],
    "Authorisation & scope (HoD, coordinators, departments)": ["test_scope", "test_hod", "test_hod_view", "test_divisions_and_scope", "test_api_security", "test_minor_scope"],
    "Input validation & CSV safety": ["test_input_validation"],
    "Uploads, downloads & documents": ["test_file_security", "test_documents", "test_progress"],
    "Curriculum (data-driven, batch-scoped)": ["test_curriculum_import", "test_curriculum_versioning", "test_curriculum_lifecycle", "test_program_curricula", "test_semester_requirements", "test_eligibility", "test_student_visibility"],
    "Electives: rounds, preferences, allocation, sections": ["test_registration_windows", "test_registration_rounds_api", "test_round_allocation", "test_round_deletion", "test_two_stage_rounds", "test_allocation", "test_sections", "test_exports_and_allocations_view"],
    "NPTEL / NCC": ["test_nptel_rounds"],
    "Minor specialisation": ["test_minor_ranking", "test_minor_portal"],
    "Internship engine (CSSI, Summer, projects)": ["test_internship_engine", "test_internship_windows", "test_program_phase", "test_project_modules", "test_coordinator_tools", "test_registration_stage", "test_module_audit_fixes"],
    "Mentor allocation & mentoring": ["test_mentor_allocation", "test_mentor_allocation_lock"],
    "Faculty performance score": ["test_faculty_scoring", "test_real_faculty_roster"],
    "Dashboards, profiles, announcements, chatbot": ["test_student_dashboard", "test_student_profile", "test_announcement_audience", "test_chatbot", "test_chatbot_answers"],
    "Cross-module journeys": ["test_e2e_scenarios", "test_academic_tracks_e2e"],
    "Performance regressions (query counts)": ["test_query_counts"],
    "Concurrency (PostgreSQL only)": ["test_pg_concurrency"],
}


def junit(name):
    r = ET.parse(EV / f"{name}_junit.xml").getroot()
    out = collections.defaultdict(lambda: collections.Counter())
    for case in r.iter("testcase"):
        mod = case.get("classname", "").split(".")
        file = next((m for m in mod if m.startswith("test_")), "?")
        status = ("failed" if case.find("failure") is not None or case.find("error") is not None
                  else "skipped" if case.find("skipped") is not None else "passed")
        out[file][status] += 1
    return out


sq, pg = junit("final_backend_sqlite"), junit("final_backend_pg")
mapped = {f for files in MODULES.values() for f in files}
unmapped = sorted(set(sq) - mapped)
if unmapped:
    MODULES["Other"] = unmapped

probes = {
    "Electives: rounds, preferences, allocation, sections": "RACE-4 preferences 30/30; RACE-5 allocation runs PASS; query profile",
    "Minor specialisation": "RACE-6 minor seats 6/6 after fix (6/6 failed before)",
    "Internship engine (CSSI, Summer, projects)": "RACE-2 mentor cap 6/6 after fix; RACE-3 double submit PASS; SEC-7 horizontal 44/44 refused; browser side-by-side SI demo",
    "Authentication, sessions & accounts": "SEC-1/3/9; spike & stress load",
    "Authorisation & scope (HoD, coordinators, departments)": "SEC-1 230 routes; SEC-2 92 routes; SEC-7; SEC-8",
    "Mentor allocation & mentoring": "Query profile: my-mentees 4,676 → 24 queries",
    "Faculty performance score": "Query profile: 276 → 19 queries",
    "Dashboards, profiles, announcements, chatbot": "Browser crawl 200 pages desktop + 67 pages at 390 px; load journeys",
}
rows = []
for module, files in MODULES.items():
    s = sum((sq.get(f, collections.Counter()) for f in files), collections.Counter())
    p = sum((pg.get(f, collections.Counter()) for f in files), collections.Counter())
    status = "FAIL" if s["failed"] or p["failed"] else ("PASS" if (s["passed"] or p["passed"]) else "NOT RUN")
    rows.append({"module": module, "test_files": " ".join(files),
                 "sqlite_passed": s["passed"], "sqlite_failed": s["failed"], "sqlite_skipped": s["skipped"],
                 "postgresql_passed": p["passed"], "postgresql_failed": p["failed"], "postgresql_skipped": p["skipped"],
                 "additional_qa_evidence": probes.get(module, ""), "status": status})
with open(ROOT / "CampusHub_Test_Case_Matrix.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
totals = {k: sum(r[k] for r in rows) for k in rows[0] if k.endswith(("passed", "failed", "skipped"))}
print(json.dumps(totals))
