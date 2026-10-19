"""Combine every QA report into one printable HTML (then PDF via render_pdf.mjs).

    python build_pdf.py            -> reports/qa/CampusHub_QA_Report.html

Markdown is converted by a small converter covering what the reports use:
headings, paragraphs, lists, tables, fenced code, quotes, emphasis, links.
CSVs become tables; the defect register is a summary table plus one detail
block per defect (13 columns do not fit a page).
"""
from __future__ import annotations

import csv
import html
import json
import pathlib
import re

QA = pathlib.Path(__file__).resolve().parents[1]


# ── markdown ──────────────────────────────────────────────────────────────
def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    # Code first, held aside, so `*.json` inside it is never read as emphasis.
    codes: list[str] = []

    def hold(m):
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", hold, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    for mark, cls in (("✅", "ok"), ("🟡", "part"), ("❌", "no"), ("⛔", "blocked")):
        text = text.replace(mark, f'<span class="mark {cls}">{mark}</span>')
    return text


def table(lines: list[str]) -> str:
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    head, body = rows[0], [r for r in rows[2:]]
    aligns = []
    for spec in rows[1]:
        aligns.append("right" if spec.endswith(":") and not spec.startswith(":") else "left")
    th = "".join(f"<th>{inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(
        f'<td class="num">{inline(c)}</td>' if i < len(aligns) and aligns[i] == "right" else f"<td>{inline(c)}</td>"
        for i, c in enumerate(r)) + "</tr>" for r in body)
    cls = " class='wide'" if len(head) >= 10 else (" class='compact'" if len(head) >= 7 else "")
    return f"<table{cls}><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def md(text: str, shift: int = 0) -> str:
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = min(6, len(m.group(1)) + shift)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(table(lines[i:j]))
            i = j
            continue
        if line.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            out.append("<blockquote>" + md("\n".join(l.lstrip("> ").rstrip() for l in lines[i:j])) + "</blockquote>")
            i = j
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            j, items = i, []
            ordered = bool(re.match(r"^\s*\d+\.", line))
            while j < len(lines) and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]) or (lines[j].startswith("  ") and lines[j].strip())):
                if re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]) and not lines[j].startswith("   "):
                    items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[j]))
                else:
                    items[-1] += " " + lines[j].strip()
                j += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            i = j
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#|\||>|```|\s*([-*]|\d+\.)\s)", lines[j]):
            j += 1
        out.append("<p>" + inline(" ".join(l.strip() for l in lines[i:j])) + "</p>")
        i = max(j, i + 1)
    return "\n".join(out)


# ── csv sections ──────────────────────────────────────────────────────────
SEV = {"Critical": "crit", "High": "high", "Medium": "med", "Low": "low", "Info": "info"}


def badge(sev: str) -> str:
    return f'<span class="sev {SEV.get(sev, "info")}">{html.escape(sev)}</span>'


def status_badge(status: str) -> str:
    s = status.lower()
    cls = "st-ok" if s.startswith("fixed") else "st-mit" if s.startswith("mitigated") else \
          "st-open" if s.startswith("open") else "st-info"
    return f'<span class="st {cls}">{html.escape(status)}</span>'


def defects() -> str:
    rows = list(csv.DictReader(open(QA / "CampusHub_Defect_Register.csv")))
    counts = {}
    for r in rows:
        key = r["status"].split(" —")[0].split(" (")[0]
        counts[key] = counts.get(key, 0) + 1
    summary = "".join(f"<tr><td>{html.escape(k)}</td><td class='num'>{v}</td></tr>" for k, v in counts.items())
    head = ("<table class='compact'><thead><tr><th>ID</th><th>Severity</th><th>Module</th><th>Title</th><th>Status</th>"
            "</tr></thead><tbody>" + "".join(
                f"<tr><td class='nowrap'><strong>{r['id']}</strong></td><td>{badge(r['severity'])}</td>"
                f"<td>{html.escape(r['module'])}</td><td>{html.escape(r['title'])}</td><td>{status_badge(r['status'])}</td></tr>"
                for r in rows) + "</tbody></table>")
    details = []
    for r in rows:
        fields = [("Category", r["category"]), ("Affected roles", r["affected_roles"]), ("Priority", r["priority"]),
                  ("Root cause", r["root_cause"]), ("Reproduction", r["reproduction"]), ("Evidence", r["evidence"]),
                  ("Fix", r["fix"]), ("Regression test", r["regression_test"])]
        dl = "".join(f"<tr><th>{k}</th><td>{inline(v)}</td></tr>" for k, v in fields if v and v != "—")
        details.append(f"<div class='defect'><h3>{r['id']} · {html.escape(r['title'])}</h3>"
                       f"<p>{badge(r['severity'])} {status_badge(r['status'])} <span class='muted'>{html.escape(r['module'])}</span></p>"
                       f"<table class='kv'>{dl}</table></div>")
    return (f"<h2>Summary by status</h2><table class='narrow'><thead><tr><th>Status</th><th>Count</th></tr></thead>"
            f"<tbody>{summary}<tr><td><strong>Total</strong></td><td class='num'><strong>{len(rows)}</strong></td></tr>"
            f"</tbody></table><h2>All findings</h2>{head}<h2>Details</h2>" + "".join(details))


def matrix() -> str:
    rows = list(csv.DictReader(open(QA / "CampusHub_Test_Case_Matrix.csv")))
    num = ["sqlite_passed", "sqlite_failed", "sqlite_skipped", "postgresql_passed", "postgresql_failed", "postgresql_skipped"]
    tot = {k: sum(int(r[k]) for r in rows) for k in num}
    body = "".join(
        f"<tr><td>{html.escape(r['module'])}</td>" + "".join(f"<td class='num'>{r[k]}</td>" for k in num) +
        f"<td><span class='st st-ok'>{html.escape(r['status'])}</span></td>"
        f"<td class='small'>{html.escape(r['additional_qa_evidence'])}</td></tr>" for r in rows)
    foot = "<tr class='total'><td>Total</td>" + "".join(f"<td class='num'>{tot[k]}</td>" for k in num) + "<td></td><td></td></tr>"
    files = "".join(f"<tr><td>{html.escape(r['module'])}</td><td class='small'><code>{html.escape(r['test_files'])}</code></td></tr>" for r in rows)
    return ("<p>Executed tests per module from the final JUnit results of both runs (each parametrised case counts once). "
            "The two SQLite skips are the PostgreSQL-only concurrency tests.</p>"
            "<table class='compact'><thead><tr><th rowspan='2'>Module</th><th colspan='3'>SQLite</th><th colspan='3'>PostgreSQL 16</th>"
            "<th rowspan='2'>Status</th><th rowspan='2'>Additional QA evidence</th></tr>"
            "<tr><th>Pass</th><th>Fail</th><th>Skip</th><th>Pass</th><th>Fail</th><th>Skip</th></tr></thead>"
            f"<tbody>{body}{foot}</tbody></table><h2>Test files per module</h2><table class='compact'><thead><tr><th>Module</th>"
            f"<th>Test files</th></tr></thead><tbody>{files}</tbody></table>")


# ── assemble ──────────────────────────────────────────────────────────────
def section(sid: str, title: str, body: str) -> str:
    return f"<section id='{sid}'><h1>{html.escape(title)}</h1>{body}</section>"


def strip_title(text: str) -> str:
    return re.sub(r"^# .*\n", "", text, count=1)


summary = json.load(open(QA / "qa_summary.json"))
SECTIONS = [
    ("exec", "1. Executive report", md(strip_title((QA / "CampusHub_QA_Executive_Report.md").read_text()))),
    ("ready", "2. Production readiness checklist", md(strip_title((QA / "CampusHub_Production_Readiness_Checklist.md").read_text()))),
    ("defects", "3. Defect register", defects()),
    ("matrix", "4. Test case matrix", matrix()),
    ("load", "5. Load, concurrency and database performance", md(strip_title((QA / "CampusHub_Load_Test_Report.md").read_text()))),
    ("security", "6. Security testing", md(strip_title((QA / "CampusHub_Security_Report.md").read_text()))),
]

t = summary["tests"]
cover = f"""
<section class="cover">
  <div class="brand">CampusHub · PDEU student portal</div>
  <h1 class="title">Quality Assurance, Production Readiness &amp; Stress Testing Report</h1>
  <p class="subtitle">Functional, PostgreSQL, concurrency, security and load testing</p>
  <table class="kv cover-kv">
    <tr><th>Testing date</th><td>19 October 2026</td></tr>
    <tr><th>Code under test</th><td>baseline <code>{summary['baseline_commit']}</code> → fixes on branch <code>{summary['branch_with_fixes']}</code> (not deployed)</td></tr>
    <tr><th>Environment</th><td>{summary['environment']['host']}; {summary['environment']['database']}; API {summary['environment']['api']}; 10,000 synthetic students</td></tr>
    <tr><th>Overall status</th><td><strong>{summary['overall_status']}</strong></td></tr>
    <tr><th>Recommendation</th><td><span class="rec">{summary['recommendation']}</span></td></tr>
  </table>
  <div class="tiles">
    <div><b>{t['backend_postgresql']['final']['passed']:,}</b><span>backend tests passing on PostgreSQL</span></div>
    <div><b>{t['backend_sqlite']['final']['passed']:,}</b><span>passing on SQLite (+2 PostgreSQL-only)</span></div>
    <div><b>{t['e2e_playwright']['final']['passed']}/15</b><span>browser journeys</span></div>
    <div><b>{summary['defects']['total']}</b><span>findings · 13 fixed</span></div>
  </div>
  <p class="note">Production was not touched: no deployment, no live data changes, no load or security tests against the live site.
  All QA data was synthetic.</p>
</section>"""
toc = "<section class='toc'><h1>Contents</h1><ol>" + "".join(
    f"<li><a href='#{sid}'>{html.escape(title.split('. ', 1)[1])}</a></li>" for sid, title, _ in SECTIONS) + "</ol></section>"

CSS = """
@page { size: A4; margin: 18mm 15mm 18mm 15mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1f2937; }
h1 { font-size: 19pt; color: #0f2a4a; border-bottom: 2.5px solid #2563eb; padding-bottom: 5px; margin: 0 0 12px; }
h2 { font-size: 13pt; color: #0f2a4a; margin: 18px 0 8px; }
h3 { font-size: 11pt; color: #1e3a8a; margin: 14px 0 6px; }
h4 { font-size: 10pt; margin: 10px 0 4px; }
section { page-break-before: always; }
section.cover { page-break-before: auto; }
p { margin: 5px 0 8px; }
ul, ol { margin: 4px 0 8px 18px; padding: 0; } li { margin: 2px 0; }
code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 8.5pt; background: #f1f5f9; padding: 0 3px; border-radius: 3px; word-break: break-word; }
pre { font-family: 'SF Mono', Menlo, monospace; font-size: 8pt; background: #0f172a; color: #e2e8f0; padding: 9px 11px; border-radius: 5px; white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
blockquote { margin: 8px 0; padding: 6px 12px; border-left: 3px solid #f59e0b; background: #fffbeb; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 8.6pt; page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 4px 6px; vertical-align: top; text-align: left;
         word-break: normal; overflow-wrap: normal; hyphens: none; }
td.num { text-align: right; white-space: nowrap; }
td code, li code, p code { overflow-wrap: anywhere; }
table.wide { font-size: 7.4pt; } table.wide th, table.wide td { padding: 3px 4px; }
h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
h2 + table, h3 + table, h2 + p, h3 + p { break-before: avoid; }

thead th { background: #1e3a8a; color: #fff; font-weight: 600; }
tbody tr:nth-child(even) td { background: #f8fafc; }
table.compact { font-size: 8.2pt; } table.narrow { width: 45%; }
table.kv th { width: 24%; background: #eef2ff; color: #1e3a8a; font-weight: 600; }
table.kv td { background: #fff !important; }
tr.total td { font-weight: 700; background: #e0e7ff !important; }
.small { font-size: 7.8pt; } .nowrap { white-space: nowrap; } .muted { color: #64748b; font-size: 8.5pt; }
.sev, .st { display: inline-block; padding: 1px 6px; border-radius: 9px; font-size: 7.8pt; font-weight: 600; white-space: nowrap; }
.sev.crit { background: #7f1d1d; color: #fff; } .sev.high { background: #fee2e2; color: #991b1b; }
.sev.med { background: #ffedd5; color: #9a3412; } .sev.low { background: #fef9c3; color: #854d0e; } .sev.info { background: #e2e8f0; color: #334155; }
.st { white-space: normal; } .st-ok { background: #dcfce7; color: #166534; } .st-mit { background: #fef3c7; color: #92400e; }
.st-open { background: #fee2e2; color: #991b1b; } .st-info { background: #e2e8f0; color: #334155; }
.mark { font-size: 9pt; }
.defect { page-break-inside: avoid; border: 1px solid #e2e8f0; border-radius: 6px; padding: 2px 10px 6px; margin: 0 0 10px; }
.defect h3 { margin-top: 8px; }
.cover { padding-top: 40mm; }
.cover .brand { color: #2563eb; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: 9.5pt; }
.cover .title { font-size: 26pt; border: none; line-height: 1.15; margin: 10px 0 6px; }
.cover .subtitle { font-size: 12pt; color: #475569; margin-bottom: 22px; }
.cover-kv { width: 100%; font-size: 10pt; } .cover-kv th { width: 28%; }
.rec { background: #dcfce7; color: #166534; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 18px 0; }
.tiles div { border: 1px solid #c7d2fe; border-radius: 8px; padding: 10px; background: #eef2ff; }
.tiles b { display: block; font-size: 18pt; color: #1e3a8a; } .tiles span { font-size: 8.5pt; color: #334155; }
.note { font-size: 8.8pt; color: #475569; border-top: 1px solid #e2e8f0; padding-top: 8px; margin-top: 20px; }
.toc ol { font-size: 12pt; line-height: 2; } .toc a { color: #1e3a8a; text-decoration: none; }
a { color: #1d4ed8; text-decoration: none; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 12px 0; }
"""
doc = (f"<!doctype html><html><head><meta charset='utf-8'><title>CampusHub QA Report</title><style>{CSS}</style></head><body>"
       + cover + toc + "".join(section(sid, title, body) for sid, title, body in SECTIONS) + "</body></html>")
(QA / "CampusHub_QA_Report.html").write_text(doc, encoding="utf-8")
print("wrote", QA / "CampusHub_QA_Report.html", f"{len(doc) // 1024} KB")
