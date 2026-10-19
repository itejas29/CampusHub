"""PERF-Q: database round trips and time per endpoint, in process, on PostgreSQL.

    DATABASE_URL=postgresql://… PYTHONPATH=backend python query_profile.py out.json

Counts every statement SQLAlchemy sends per request. Run it at two dataset sizes:
an endpoint whose count grows with the rows has an N+1.
"""
import json, os, sys, time

assert "railway" not in os.environ.get("DATABASE_URL", ""), "refusing to profile production"

from fastapi.testclient import TestClient   # noqa: E402
from sqlalchemy import event                 # noqa: E402

from app.db.session import engine            # noqa: E402
from app.main import app                     # noqa: E402

COUNT = [0]


@event.listens_for(engine, "before_cursor_execute")
def _count(*_):
    COUNT[0] += 1


client = TestClient(app)
PASSWORD = "Campus@123"


def head(email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


ROLES = {
    "student (Sem VI)": ("aarav.desai.001@campushub.example.com",
                         ["/api/v1/dashboard/student", "/api/v1/internships/programs", "/api/v1/internships/enrollments/me",
                          "/api/v1/electives/allocations/me", "/api/v1/notifications", "/api/v1/announcements",
                          "/api/v1/events", "/api/v1/clubs", "/api/v1/mentorship/meetings", "/api/v1/minors/workspace"]),
    "SI coordinator": ("priya.nair@campushub.example.com",
                       ["/api/v1/dashboard/faculty", "/api/v1/internships/enrollments", "/api/v1/internships/programs",
                        "/api/v1/internships/programs/2/windows", "/api/v1/internships/programs/2/mentor-capacity",
                        "/api/v1/mentorship/my-mentees", "/api/v1/minors"]),
    "mentor": ("anand.mehta@campushub.example.com",
               ["/api/v1/dashboard/faculty", "/api/v1/internships/enrollments?mine=true", "/api/v1/faculty-scores/me"]),
    "OE coordinator": ("vikram.joshi@campushub.example.com",
                       ["/api/v1/electives/admin/windows", "/api/v1/electives/admin/allocations?curriculum_component_id=503"]),
    "registrar": ("admin@campushub.example.com",
                  ["/api/v1/dashboard/admin", "/api/v1/students?page=1&size=50", "/api/v1/faculty",
                   "/api/v1/faculty-scores/department", "/api/v1/dashboard/hod?department_code=ICT", "/api/v1/admin/audit-logs"]),
}

rows = []
for role, (email, paths) in ROLES.items():
    h = head(email)
    for path in paths:
        client.get(path, headers=h)                     # warm
        COUNT[0] = 0
        t = time.perf_counter()
        r = client.get(path, headers=h)
        ms = (time.perf_counter() - t) * 1000
        size = len(r.content)
        rows.append({"role": role, "path": path, "status": r.status_code, "queries": COUNT[0],
                     "ms": round(ms, 1), "bytes": size})
        print(f"{role:18} {path:62} {r.status_code} q={COUNT[0]:5} {ms:8.1f} ms {size/1024:8.1f} KB", flush=True)

json.dump(rows, open(sys.argv[1], "w"), indent=1)
