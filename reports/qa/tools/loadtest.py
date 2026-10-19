"""PERF-L: concurrent virtual users against the ISOLATED QA server.

    python loadtest.py --users 50 --duration 60 --think 1.0 --label ramp-50 [--server-pid PID]

Each virtual user signs in once (as a person does), then loops realistic
journeys with think time between requests. Mix: 85% students, 10% mentors,
4% coordinators, 1% registrar. ~8% of student iterations write (preferences,
event registration). Latency is recorded per endpoint; server CPU/RSS and
PostgreSQL activity are sampled alongside. Synthetic accounts only.
"""
from __future__ import annotations

import argparse, asyncio, json, random, statistics, subprocess, time
from collections import defaultdict

import httpx
from qa_common import BASE, PASSWORD, PG_CONTAINER, sql

ap = argparse.ArgumentParser()
ap.add_argument("--users", type=int, default=10)
ap.add_argument("--duration", type=int, default=60)
ap.add_argument("--think", type=float, default=1.0, help="mean seconds between a user's requests")
ap.add_argument("--ramp", type=float, default=10.0, help="seconds over which users arrive")
ap.add_argument("--label", default="run")
ap.add_argument("--server-pid", type=int)
ap.add_argument("--db", default="campushub_qa_10k")
ap.add_argument("--out", default="../evidence/load")
args = ap.parse_args()

import qa_common  # noqa: E402
qa_common.PG_DB = args.db

STUDENTS = [r[0] for r in sql("select u.email from users u join students s on s.user_id=u.id "
                              "where u.email like '%campushub.example.com' and u.is_active order by random() limit 3000")]
SEM4 = [r[0] for r in sql("select u.email from users u join students s on s.user_id=u.id where s.current_semester=4 "
                          "and u.email like '%campushub.example.com' order by random() limit 1500")]
MENTORS = [r[0] for r in sql("select distinct u.email from faculty f join users u on u.id=f.user_id "
                             "join internship_enrollments e on e.mentor_faculty_id=f.id where f.is_demo")]
COORDS = ["priya.nair@campushub.example.com", "sneha.iyer@campushub.example.com",
          "vikram.joshi@campushub.example.com", "leena.nambiar@campushub.example.com"]
OE1 = sql("select min(o.curriculum_component_id) from course_offerings o join elective_registration_windows w "
          "on w.id=o.registration_window_id where w.code='OE1-2025-LIVE'")[0][0]
OE1_OFFERS = [int(r[0]) for r in sql("select o.id from course_offerings o join elective_registration_windows w "
                                     "on w.id=o.registration_window_id where w.code='OE1-2025-LIVE' order by o.id")][:5]
EVENTS = [int(r[0]) for r in sql("select id from events where registration_required and status='PUBLISHED' "
                                 "and registration_deadline > now()")]

samples: dict[str, list[float]] = defaultdict(list)
statuses: dict[str, dict] = defaultdict(lambda: defaultdict(int))
business = defaultdict(int)
stop_at = 0.0


async def req(client, name, method, path, headers=None, **kw):
    t = time.perf_counter()
    try:
        r = await client.request(method, BASE + path, headers=headers, **kw)
        code = r.status_code
    except Exception as exc:          # noqa: BLE001 — a timeout is a result
        r, code = None, type(exc).__name__
    samples[name].append((time.perf_counter() - t) * 1000)
    statuses[name][code] += 1
    return r


async def think():
    await asyncio.sleep(random.expovariate(1 / args.think) if args.think > 0 else 0)


async def student(client, email, sem4):
    r = await req(client, "login", "POST", "/auth/login", json={"email": email, "password": PASSWORD})
    if not r or r.status_code != 200:
        return
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    while time.time() < stop_at:
        await req(client, "student dashboard", "GET", "/dashboard/student", h); await think()
        await req(client, "notifications", "GET", "/notifications", h); await think()
        page = random.choice([("announcements", "/announcements"), ("internships", "/internships/programs"),
                              ("my internship", "/internships/enrollments/me"), ("events", "/events"),
                              ("my electives", "/electives/allocations/me"), ("mentor meetings", "/mentorship/meetings")])
        await req(client, page[0], "GET", page[1], h); await think()
        roll = random.random()
        if sem4 and roll < 0.05:
            prefs = [{"course_offering_id": o, "preference_order": i + 1}
                     for i, o in enumerate(random.sample(OE1_OFFERS, len(OE1_OFFERS)))]
            r = await req(client, "WRITE elective preferences", "POST", "/electives/preferences", h,
                          json={"curriculum_component_id": int(OE1), "preferences": prefs})
            if r is not None and r.status_code == 200:
                business["preference lists saved"] += 1
            await think()
        elif roll < 0.08 and EVENTS:
            r = await req(client, "WRITE event registration", "POST", f"/events/{random.choice(EVENTS)}/register", h, json={})
            if r is not None and r.status_code == 200:
                business["event registrations"] += 1
            await think()


async def staff(client, email, kind):
    r = await req(client, "login", "POST", "/auth/login", json={"email": email, "password": PASSWORD})
    if not r or r.status_code != 200:
        return
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    while time.time() < stop_at:
        if kind == "mentor":
            await req(client, "faculty dashboard", "GET", "/dashboard/faculty", h); await think()
            await req(client, "my internship students", "GET", "/internships/enrollments?mine=true", h); await think()
            await req(client, "faculty score", "GET", "/faculty-scores/me", h); await think()
        elif kind == "coordinator":
            await req(client, "faculty dashboard", "GET", "/dashboard/faculty", h); await think()
            await req(client, "all internship students (coordinator)", "GET", "/internships/enrollments", h); await think()
            await req(client, "elective rounds (coordinator)", "GET", "/electives/admin/windows", h); await think()
        else:
            await req(client, "admin dashboard", "GET", "/dashboard/admin", h); await think()
            await req(client, "students page", "GET", "/students?page=1&size=50", h); await think()
            await req(client, "department scores", "GET", "/faculty-scores/department", h); await think()


async def sampler(out: list):
    while time.time() < stop_at:
        row = {"t": round(time.time(), 1)}
        if args.server_pid:
            ps = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", str(args.server_pid)], capture_output=True, text=True).stdout.split()
            if len(ps) == 2:
                row["server_cpu_pct"], row["server_rss_mb"] = float(ps[0]), round(int(ps[1]) / 1024, 1)
        try:
            q = subprocess.run(["docker", "exec", PG_CONTAINER, "psql", "-U", "qa", "-d", args.db, "-tA", "-F", ",", "-c",
                                "select count(*) filter (where state='active'), count(*) filter (where state like 'idle in%'), "
                                "count(*), count(*) filter (where wait_event_type='Lock') from pg_stat_activity "
                                f"where datname='{args.db}'"], capture_output=True, text=True, timeout=5).stdout.strip().split(",")
            row.update(pg_active=int(q[0]), pg_idle_in_tx=int(q[1]), pg_connections=int(q[2]), pg_lock_waits=int(q[3]))
        except Exception:                 # noqa: BLE001
            pass
        out.append(row)
        await asyncio.sleep(2)


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p / 100 * len(xs)))], 1) if xs else None


async def main():
    global stop_at
    limits = httpx.Limits(max_connections=args.users + 20, max_keepalive_connections=args.users + 20)
    resource: list = []
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        start = time.time()
        stop_at = start + args.ramp + args.duration
        tasks = [asyncio.create_task(sampler(resource))]
        for i in range(args.users):
            roll = random.random()
            if roll < 0.85:
                use4 = random.random() < 0.3 and SEM4
                email = random.choice(SEM4) if use4 else random.choice(STUDENTS)
                coro = student(client, email, bool(use4))
            elif roll < 0.95 and MENTORS:
                coro = staff(client, random.choice(MENTORS), "mentor")
            elif roll < 0.99:
                coro = staff(client, random.choice(COORDS), "coordinator")
            else:
                coro = staff(client, "admin@campushub.example.com", "registrar")
            tasks.append(asyncio.create_task(coro))
            await asyncio.sleep(args.ramp / max(args.users, 1))
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
    total = sum(len(v) for v in samples.values())
    errors = {k: {str(c): n for c, n in v.items() if not (isinstance(c, int) and c < 400)} for k, v in statuses.items()}
    errors = {k: v for k, v in errors.items() if v}
    every = [x for v in samples.values() for x in v]
    non_login = [x for k, v in samples.items() if k != "login" for x in v]
    summary = {
        "label": args.label, "virtual_users": args.users, "duration_s": args.duration, "ramp_s": args.ramp,
        "think_time_mean_s": args.think, "elapsed_s": round(elapsed, 1), "requests": total,
        "throughput_rps": round(total / elapsed, 1),
        "error_rate_pct": round(100 * sum(sum(v.values()) for v in errors.values()) / max(total, 1), 2),
        "latency_ms_all": {"p50": pct(every, 50), "p90": pct(every, 90), "p95": pct(every, 95), "p99": pct(every, 99),
                           "max": round(max(every), 1) if every else None},
        "latency_ms_excluding_login": {"p50": pct(non_login, 50), "p95": pct(non_login, 95), "p99": pct(non_login, 99)},
        "per_endpoint": {k: {"n": len(v), "p50": pct(v, 50), "p95": pct(v, 95), "p99": pct(v, 99),
                             "mean": round(statistics.mean(v), 1)} for k, v in sorted(samples.items())},
        "errors": errors, "business_operations": dict(business),
        "resources": {
            "server_cpu_pct_max": max((r.get("server_cpu_pct", 0) for r in resource), default=None),
            "server_rss_mb_max": max((r.get("server_rss_mb", 0) for r in resource), default=None),
            "pg_connections_max": max((r.get("pg_connections", 0) for r in resource), default=None),
            "pg_active_max": max((r.get("pg_active", 0) for r in resource), default=None),
            "pg_lock_waits_max": max((r.get("pg_lock_waits", 0) for r in resource), default=None),
            "samples": resource},
    }
    import pathlib
    pathlib.Path(args.out).mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(f"{args.out}/{args.label}.json", "w"), indent=1)
    s = summary
    print(f"{args.label:14} VU={args.users:4} req={s['requests']:6} rps={s['throughput_rps']:7} err={s['error_rate_pct']:5}% "
          f"p50={s['latency_ms_all']['p50']} p95={s['latency_ms_all']['p95']} p99={s['latency_ms_all']['p99']} "
          f"(non-login p95={s['latency_ms_excluding_login']['p95']}) cpu_max={s['resources']['server_cpu_pct_max']} "
          f"rss={s['resources']['server_rss_mb_max']}MB pg_conn={s['resources']['pg_connections_max']} "
          f"locks={s['resources']['pg_lock_waits_max']} ops={dict(business)}")

asyncio.run(main())
