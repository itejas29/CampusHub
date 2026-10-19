"""SEC-9: does a wrong password take as long for an unknown email as for a real one?
A large difference tells an attacker which addresses have accounts.
Warm-up first; then alternating samples (two real accounts, 4 each, under the
5-per-account lock)."""
import json, statistics, sys, time, httpx
from qa_common import BASE, sql
reals = [r[0] for r in sql("select u.email from users u join students s on s.user_id=u.id "
                           "where u.email like '%campushub.example.com' order by random() limit 2")]
def t(email):
    s = time.perf_counter(); httpx.post(f"{BASE}/auth/login", json={"email": email, "password": "wrong-pass-1"}, timeout=30)
    return (time.perf_counter() - s) * 1000
t("warm.up.only@campushub.example.com")
real, fake = [], []
for i in range(8):
    real.append(t(reals[i % 2])); fake.append(t(f"nobody.{i}.{int(time.time())}@campushub.example.com"))
gap = abs(statistics.median(real) - statistics.median(fake))
print(json.dumps({"test": "SEC-9 login timing", "label": sys.argv[1] if len(sys.argv) > 1 else "",
                  "existing_account_median_ms": round(statistics.median(real), 1),
                  "unknown_email_median_ms": round(statistics.median(fake), 1), "gap_ms": round(gap, 1),
                  "verdict": "PASS" if gap < 50 else "FAIL"}))
