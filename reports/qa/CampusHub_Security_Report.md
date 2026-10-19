# CampusHub — Security Testing Report

Scope: the API (237 routes) and its authorisation model, authentication, uploads and
downloads, input handling, response hardening. All tests were non-destructive and ran
against an isolated server on a disposable PostgreSQL database with synthetic accounts
(19 Oct 2026). Nothing was run against production. Raw results:
`reports/qa/evidence/security_*.json`; tools: `reports/qa/tools/security_probe.py`,
`horizontal_probe.py`, `timing_probe.py`.

## 1. Summary

| Severity | Found | Fixed in this cycle | Open |
|---|---:|---:|---:|
| Critical | 0 | — | — |
| High | 0 (security) | — | — |
| Medium | 3 | 2 | 1 (frontend headers) |
| Low | 3 | 3 | 0 |
| Informational | 2 | 1 | 1 |

No authorisation bypass was found: every unauthenticated call, every student call to a
permission-guarded route, and every cross-student / cross-department / cross-domain attempt
was refused.

> Note: the separate data-integrity findings (race conditions QA-01..05) and availability
> finding (QA-10) are in the defect register; they are not authorisation flaws.

## 2. Results by test

| ID | Test | Method | Result |
|---|---|---|---|
| SEC-1 | Unauthenticated access | Every non-public route (230), every method, no token | **PASS** — all 401 |
| SEC-2 | Vertical escalation | A student calls every permission-guarded route (92) with an empty body | **PASS** — no 2xx, no 5xx |
| SEC-3 | Token tampering | Modified claims with original signature; `alg=none`; expired claim; refresh token used as access token; garbage | **PASS** — all 401 |
| SEC-4 | Injection strings | 64 GET list routes × 7 payloads (SQLi, UNION, XSS, traversal, NUL, 300-char Unicode) in `q`/`search` | **FAIL → fixed**: NUL byte gave 500 on 6 endpoints (PostgreSQL rejects NUL). Now a clean 400. No SQL injection effect observed (all queries are parameterised) |
| SEC-5 | Oversized / malformed bodies | 2 MB chat message; 2,000-deep JSON; 16 MB upload (limit 15) | **PASS** — 422 / 400 / 422, no 5xx |
| SEC-6 | Response hardening | Header inspection | **FAIL → fixed for the API**: no `nosniff`, framing, CSP, referrer or HSTS headers. Frontend still open |
| SEC-7 | Horizontal & cross-scope access | 4 attackers × 11 reads/writes on one student's internship record, profile and files: another student; a faculty member with no relation; the CSE Summer Internship coordinator; the ICT **CSSI** coordinator | **PASS** — 44/44 refused (403); the owner reads her own record (200) |
| SEC-8 | Mass assignment | `PATCH /me/profile` with `email`, `roles`, `is_active`, `cpi`, `current_semester`, `must_change_password` | **PASS** — none changed |
| SEC-9 | Account enumeration by timing | Median wrong-password time, real vs unknown email | **FAIL → fixed**: 250 ms vs 34 ms (gap 215 ms) on the original code; now 252 vs 257 ms (gap 5 ms) |
| Existing | Upload & download | 16 tests in `test_file_security.py`: magic-byte check vs forged Content-Type, filename sanitising and header injection, signed-link expiry/forgery/cross-file reuse, no static `/media` mount, no storage key in responses | **PASS** (re-run on SQLite and PostgreSQL) |
| Existing | Sign-in safety | `test_account_security.py` (19): throttling, session revocation on password change, one-time passwords, demo-mode rules, privilege rules for `faculty:manage` | **PASS** |
| Existing | CSV formula injection | `test_input_validation.py` | **PASS** |
| Static | Allowed upload types | Code review of `services/files.py` | Allowlist only (PDF, JPEG/PNG/WebP, Word, PowerPoint), each checked by magic bytes; HTML/SVG cannot be uploaded |

## 3. Findings

### QA-09 · Medium · Login timing reveals registered emails — **Fixed**
- **Component:** `api/v1/auth.py _authenticate`.
- **Reproduction:** `tools/timing_probe.py` against the original code — wrong password for a
  real account 249.9 ms (bcrypt), for an unknown email 34.4 ms (hash skipped).
- **Impact:** an attacker can list which student/faculty emails have accounts, which helps
  targeted guessing and phishing.
- **Fix:** unknown emails are checked against a dummy bcrypt hash. Verified gap 5 ms.
  Regression: `test_an_unknown_email_costs_a_password_check_too`.

### QA-12 · Medium · API sent no security headers — **Fixed (API)**
- **Fix:** `app/core/hardening.py` adds `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, a deny-all
  CSP on JSON responses, and HSTS when `ENVIRONMENT=production`. Verified by SEC-6 rerun and
  `test_hardening.py`.

### QA-19 · Medium · Frontend sets no security headers — **Open**
- `frontend/vercel.json` only rewrites routes. Recommend `X-Frame-Options: DENY` (or CSP
  `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and a CSP
  after testing it against the app (fonts, inline styles from the animation library). Not
  changed here because it alters the deployed frontend and a wrong CSP breaks pages.

### QA-11 · Low · NUL byte in a search → 500 — **Fixed**
- PostgreSQL-only (the SQLite test suite could not see it). Now refused with 400 before any
  handler runs. Regression: `test_a_nul_byte_in_a_query_is_a_clean_400`.

### QA-13 · Low · Interactive API docs public in production — **Fixed**
- `/docs`, `/redoc`, `/openapi.json` are disabled when `ENVIRONMENT=production`.

### QA-10 (availability) · sign-in bursts — see Load report
- Throttling limits guessing, but a burst of *valid* sign-ins could starve the API. Mitigated
  with a sign-in queue (503 "busy" after 15 s rather than a timeout).

### Informational
- No rate limiting beyond sign-in (e.g. chatbot, uploads). Recommend a per-user limit at the
  edge or in the app before opening to the whole university.
- The development `SECRET_KEY` default is refused in production (added earlier); production
  was confirmed to use its own 64-character key without the value being printed.

## 4. Not covered (needs authorisation or an environment)

- Testing the deployed Railway/Vercel stack (TLS, platform headers, WAF) — out of scope.
- Malware scanning of uploads — no scanner is integrated (readiness gap).
- Dependency vulnerability audit (`pip-audit`, `npm audit`) — not run in this cycle.
- CSRF: the API uses bearer tokens from browser storage, not cookies, so classic CSRF does
  not apply; the trade-off is that any XSS on the frontend could read tokens — which makes
  QA-19 (frontend CSP) the more important open item.
