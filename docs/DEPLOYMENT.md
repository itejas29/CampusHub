# CampusHub — AWS deployment

Target architecture, and what has to be true before CampusHub is put in front of
real students. Sections are labelled so nothing here reads as a claim that it
has been done:

- **IMPLEMENTED** — in the codebase, working.
- **VERIFIED** — exercised and observed working.
- **CONFIGURABLE** — supported, but the values are an operator decision.
- **FUTURE INFRASTRUCTURE** — deliberately not built in Phase 4.

---

## 1. Architecture

```
                    ┌──────────────┐
   students ──────► │  CloudFront  │  static frontend (S3 origin)
                    └──────┬───────┘
                           │  /api/*
                    ┌──────▼───────┐
                    │     ALB      │  TLS terminates here (ACM certificate)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │     EC2      │  uvicorn behind systemd or Docker
                    │  (private)   │  instance profile → S3, CloudWatch
                    └───┬──────┬───┘
                        │      │
            ┌───────────▼─┐  ┌─▼──────────────┐
            │ RDS Postgres│  │ S3 (documents) │  private, no public read
            │  (private)  │  └────────────────┘
            └─────────────┘
                        │
                 ┌──────▼──────┐
                 │ CloudWatch  │  logs + metrics + alarms
                 └─────────────┘
```

No Kubernetes, no microservices, no Redis. The application is one FastAPI
process and one database; adding an orchestrator would be infrastructure without
a problem to solve.

---

## 2. What the code already supports

| Concern | State | Notes |
|---|---|---|
| Storage abstraction (local ⇄ S3) | **IMPLEMENTED** | `STORAGE_BACKEND=s3` switches backends with no code change (`app/storage/`) |
| Environment-driven config | **IMPLEMENTED** | every setting in `app/core/config.py`, nothing hard-coded |
| Database migrations | **VERIFIED** | Alembic, 8 revisions, `alembic upgrade head` |
| Health endpoint | **VERIFIED** | `GET /health` — use as the ALB target-group check |
| Authorised file access | **VERIFIED** | uploads are not statically served; see [§4](#4-file-security) |
| CORS allow-list | **IMPLEMENTED** | `BACKEND_CORS_ORIGINS`, exact origins |
| Structured errors | **IMPLEMENTED** | one envelope, no stack traces to clients |
| TLS | **CONFIGURABLE** | terminate at the ALB with an ACM certificate |
| Secrets management | **CONFIGURABLE** | `SECRET_KEY`, DB password → Secrets Manager / SSM |
| Backups, PITR | **CONFIGURABLE** | RDS automated backups; set retention deliberately |
| Autoscaling | **FUTURE INFRASTRUCTURE** | single instance is right for one campus |
| Virus scanning of uploads | **FUTURE INFRASTRUCTURE** | see [§4](#4-file-security) |
| CDN cache invalidation on deploy | **CONFIGURABLE** | `aws cloudfront create-invalidation` in the deploy step |

---

## 3. Configuration

Start from [`.env.production.example`](../.env.production.example). The settings
that are not free choices:

| Setting | Required value | Why |
|---|---|---|
| `DEBUG` | `false` | debug output changes error responses |
| `SECRET_KEY` | 32 random bytes | signs access tokens **and** file download links — rotating it invalidates both |
| `BACKEND_CORS_ORIGINS` | exact origins | credentials are sent with requests; a wildcard is invalid *and* unsafe |
| `S3_PUBLIC_BASE_URL` | **empty** for documents | setting it hands out a CloudFront path instead of an authorised download, making every certificate readable by URL alone |
| `SEED_DEFAULT_PASSWORD` | unset | the demo seeder must never run against production |
| RDS `sslmode` | `require` | the database is reachable from the app subnet; encrypt it anyway |

Never commit a filled-in file. `.gitignore` already excludes `.env`.

---

## 4. File security

Uploads are **not** served as static files. That is a deliberate change made in
Phase 4: the previous arrangement mounted the upload directory at `/media`, so
every stored document — certificates, offer letters, weekly reports — was
readable by anyone who knew or guessed its object key, with no login at all.

The rules now:

1. Documents reach clients only through `GET /api/v1/files/{id}/download`, which
   authorises the caller before streaming a byte.
2. `GET /api/v1/files/{id}` authorises the same way before returning metadata.
3. The only URL ever returned is a **signed, expiring** link back to the API.
   The S3 key and the local path never cross the boundary.
4. Uploads are validated on **magic bytes**, not the browser's `Content-Type`.
5. Filenames are sanitised before storage and before being echoed in a
   `Content-Disposition` header.
6. Responses carry `X-Content-Type-Options: nosniff` and `Cache-Control:
   private, no-store`.

**The documents bucket must be private.** Block Public Access on, no bucket
policy granting `s3:GetObject` to `*`, and no CloudFront distribution in front
of it. If the bucket is public, points 1–3 are decoration.

**Virus scanning is FUTURE INFRASTRUCTURE.** Nothing scans uploaded files for
malware. The mitigations in place — type validation, no execution, no static
serving, `nosniff` — reduce but do not eliminate the risk of a user downloading
something harmful another user uploaded. Before wide rollout, add either a
GuardDuty Malware Protection for S3 scan on `PutObject`, or a Lambda-based
ClamAV scan that quarantines objects until they pass.

---

## 5. Deploying

### Database

```bash
# once, from a host that can reach RDS
alembic upgrade head
```

Migrations are additive and run inside a transaction. Take an RDS snapshot
before applying a new revision to production.

### Backend (EC2)

```bash
# on the instance
git pull && pip install -r backend/requirements.txt
alembic upgrade head
systemctl restart campushub-api
```

Run uvicorn behind the ALB. Health check: `GET /health` → `200`.

Give the instance an IAM role with exactly:
`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on
`arn:aws:s3:::campushub-prod-documents/*`, plus `logs:*` for its own log group.
No wildcard S3 access.

### Frontend (S3 + CloudFront)

```bash
cd frontend
VITE_API_BASE_URL=https://api.campushub.pdeu.ac.in/api/v1 npm run build
aws s3 sync dist/ s3://campushub-prod-web --delete
aws cloudfront create-invalidation --distribution-id EXXXXX --paths '/*'
```

`VITE_API_BASE_URL` is baked into the bundle at build time, so it has to be the
public API URL — it cannot be changed by editing a file on the server later.

Configure CloudFront to serve `index.html` for 403/404 so client-side routes
resolve.

---

## 6. Before real students use it

Not yet done, and not safe to skip:

- [ ] **Rate limiting on `/auth/login`.** Nothing currently throttles password
      attempts. Add it at the ALB (WAF rate rule) or in front of the endpoint.
      **FUTURE INFRASTRUCTURE.**
- [ ] **Upload malware scanning** (§4).
- [ ] **A real password policy and reset flow.** Seeded accounts share one
      password by design; that is a demo affordance, not a production one.
- [ ] **Backup restore rehearsal.** An untested backup is a hope.
- [ ] **CloudWatch alarms** on 5xx rate, database connections, disk, and failed
      logins.
- [ ] **A load test** at real concurrency. The dataset has been exercised at
      1,682 students, but not with hundreds of simultaneous users.
- [ ] **Institutional review** of the policies still marked *requires faculty
      confirmation* in `docs/PHASE3B-RESEARCH.md`.
