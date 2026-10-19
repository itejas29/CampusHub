"""SEC sweep against the isolated QA server. Non-destructive by construction:
write routes are called only as roles that must be refused, or with bodies
that cannot validate, so nothing is created.

  SEC-1  every non-public route, unauthenticated            -> 401
  SEC-2  every permission-guarded route, as a student       -> never 2xx
  SEC-3  tampered / unsigned / expired / wrong-type tokens  -> 401
  SEC-4  injection strings in every GET `q` search          -> no 5xx
  SEC-5  oversized and deeply nested JSON                   -> no 5xx
  SEC-6  response headers                                   -> report
"""
import asyncio, base64, csv, datetime as dt, json, pathlib, re

import httpx
from qa_common import BASE, login

ROUTES = pathlib.Path(__file__).resolve().parents[1] / "evidence" / "api_routes.csv"
PUBLIC = {"/api/v1/auth/config", "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/refresh",
          "/api/v1/auth/token", "/", "/health"}
ROOT = BASE.rsplit("/api/v1", 1)[0]


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def routes():
    with ROUTES.open() as f:
        return list(csv.DictReader(f))


async def call(client, method, path, headers=None, **kw):
    try:
        return await client.request(method, ROOT + concrete(path), headers=headers, **kw)
    except Exception as exc:          # noqa: BLE001
        return exc


def code(r):
    return type(r).__name__ if isinstance(r, Exception) else r.status_code


async def main():
    out = {}
    async with httpx.AsyncClient(timeout=30) as client:
        rows = routes()
        # SEC-1
        bad = []
        for r in rows:
            if r["path"] in PUBLIC:
                continue
            res = await call(client, r["method"], r["path"], json={})
            if code(res) != 401:
                bad.append(f"{r['method']} {r['path']} -> {code(res)}")
        out["SEC-1 unauthenticated"] = {"routes_probed": sum(1 for r in rows if r["path"] not in PUBLIC),
                                         "not_401": bad, "verdict": "PASS" if not bad else "FAIL"}

        # SEC-2 (student = Ananya, Sem IV demo persona)
        student = await login(client, "ananya.menon.911@campushub.example.com")
        guarded = [r for r in rows if r["permission_dependency"]]
        leaks, fivexx = [], []
        for r in guarded:
            res = await call(client, r["method"], r["path"], headers=student, json={})
            c = code(res)
            if isinstance(c, int) and 200 <= c < 300:
                leaks.append(f"{r['method']} {r['path']} -> {c}")
            if isinstance(c, int) and c >= 500 or isinstance(c, str):
                fivexx.append(f"{r['method']} {r['path']} -> {c}")
        out["SEC-2 student vs permission-guarded routes"] = {
            "routes_probed": len(guarded), "student_got_2xx": leaks, "server_errors": fivexx,
            "verdict": "PASS" if not leaks and not fivexx else "FAIL"}

        # SEC-3 token tampering
        token = student["Authorization"].split()[1]
        head, body, sig = token.split(".")
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        def enc(obj):
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
        escalated = enc({**claims, "roles": ["SUPER_ADMIN"], "sub": "1"})
        none_alg = enc({"alg": "none", "typ": "JWT"})
        expired = enc({**claims, "exp": int(dt.datetime(2020, 1, 1).timestamp())})
        refresh = await client.post(f"{BASE}/auth/login", json={"email": "ananya.menon.911@campushub.example.com",
                                                                  "password": "Campus@123"})
        refresh_token = refresh.json()["tokens"]["refresh_token"]
        cases = {"modified claims, original signature": f"{head}.{escalated}.{sig}",
                 "alg=none, no signature": f"{none_alg}.{escalated}.",
                 "expired claim, original signature": f"{head}.{expired}.{sig}",
                 "refresh token used as access token": refresh_token,
                 "garbage": "not-a-token"}
        results = {}
        for name, tok in cases.items():
            res = await client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {tok}"})
            results[name] = code(res)
        out["SEC-3 token tampering"] = {"responses": results,
                                        "verdict": "PASS" if all(v == 401 for v in results.values()) else "FAIL"}

        # SEC-4 injection in search
        admin = await login(client, "admin@campushub.example.com")
        searchable = [r for r in rows if r["method"] == "GET" and "{" not in r["path"]]
        payloads = ["' OR '1'='1", "1; DROP TABLE users;--", "%' UNION SELECT email FROM users--",
                    "<script>alert(1)</script>", "../../etc/passwd", "\x00", "ॐ" * 300]
        errors = []
        for r in searchable:
            for p in payloads:
                res = await client.get(ROOT + r["path"], headers=admin, params={"q": p, "search": p})
                c = code(res)
                if not isinstance(c, int) or c >= 500:
                    errors.append(f"GET {r['path']} q={p[:20]!r} -> {c}")
        out["SEC-4 injection strings in search"] = {"routes": len(searchable), "payloads": len(payloads),
                                                    "server_errors": errors[:20], "verdict": "PASS" if not errors else "FAIL"}

        # SEC-5 oversized / nested payloads (validation-only: as a student on a student route)
        big = {"query": "x" * 2_000_000}
        nested = '{"curriculum_component_id": 1, "preferences": [], "x": ' + '{"x": ' * 2000 + '1' + '}' * 2001
        res_big = await client.post(f"{BASE}/chatbot/query", headers=student, json=big)
        res_nested = await client.post(f"{BASE}/electives/preferences",
                                       headers={**student, "Content-Type": "application/json"}, content=nested)
        res_upload = await client.post(f"{BASE}/files", headers=student,
                                       files={"file": ("big.pdf", b"%PDF-1.4\n" + b"0" * (16 * 1024 * 1024), "application/pdf")})
        out["SEC-5 oversized payloads"] = {"2 MB chat query": code(res_big), "2000-deep JSON": code(res_nested),
                                           "16 MB upload (limit 15)": code(res_upload),
                                           "verdict": "PASS" if all(isinstance(code(x), int) and code(x) < 500
                                                                    for x in (res_big, res_nested, res_upload)) else "FAIL"}

        # SEC-6 headers
        res = await client.get(f"{BASE}/auth/me", headers=student)
        wanted = ["strict-transport-security", "x-content-type-options", "x-frame-options",
                  "content-security-policy", "referrer-policy"]
        out["SEC-6 API response headers"] = {h: res.headers.get(h) for h in wanted}
    print(json.dumps(out, indent=1))

asyncio.run(main())
