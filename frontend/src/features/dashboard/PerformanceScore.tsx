import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ClipboardCheck, FileCheck2, Gauge, Info, Trophy } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { Badge, type Tone } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  DepartmentScores, FacultyScore, ScoreCategory, ScoreEntry, ScoreOutcome, ScorePolicy,
} from "@/types";

// Every figure here comes from /faculty-scores. The screen only names and
// draws them; the rules and weights live in services/faculty_scoring.py.

const BAND_TONE: Record<FacultyScore["band"], Tone> = {
  Excellent: "success", Good: "accent", "Needs attention": "warning",
  "At risk": "danger", "Not enough activity": "neutral", "Not scored yet": "neutral",
};

const BAND_RING: Record<FacultyScore["band"], string> = {
  Excellent: "text-success", Good: "text-accent", "Needs attention": "text-warning",
  "At risk": "text-danger", "Not enough activity": "text-ink-subtle",
  "Not scored yet": "text-ink-subtle",
};

const CATEGORY: Record<ScoreCategory, { label: string; icon: LucideIcon }> = {
  REVIEW: { label: "Reviews", icon: FileCheck2 },
  MARKS: { label: "Marks", icon: ClipboardCheck },
  MEETING: { label: "Meetings", icon: CalendarClock },
};

const OUTCOME: Record<ScoreOutcome, { label: string; tone: Tone }> = {
  ON_TIME: { label: "On time", tone: "success" },
  LATE: { label: "Late", tone: "warning" },
  OVERDUE: { label: "Overdue", tone: "danger" },
  MISSED: { label: "Missed", tone: "danger" },
};

const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);
const percent = (rate: number | null) => (rate === null ? "—" : `${Math.round(rate * 100)}%`);

function RateRing({ score, size = 112 }: { score: FacultyScore; size?: number }) {
  const r = 42;
  const circumference = 2 * Math.PI * r;
  const rate = score.on_time_rate ?? 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="9" className="stroke-current text-line" />
        <circle
          cx="50" cy="50" r={r} fill="none" strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - rate)}
          className={cn("stroke-current transition-[stroke-dashoffset] duration-700", BAND_RING[score.band])}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="tabular text-xl font-semibold text-ink">{percent(score.on_time_rate)}</span>
        <span className="text-2xs text-ink-subtle">on time</span>
      </div>
    </div>
  );
}

function Tally({ score }: { score: FacultyScore }) {
  const items = [
    { label: "On time", value: score.on_time, className: "text-success" },
    { label: "Late", value: score.late, className: "text-warning" },
    { label: "Overdue", value: score.overdue, className: "text-danger" },
    { label: "Missed", value: score.missed, className: "text-danger" },
    { label: "Waiting", value: score.pending, className: "text-ink-muted" },
  ];
  return (
    <dl className="grid grid-cols-5 gap-px overflow-hidden rounded-lg border border-line bg-line">
      {items.map((item) => (
        <div key={item.label} className="bg-surface px-2 py-2 text-center">
          <dd className={cn("tabular text-md font-semibold", item.value ? item.className : "text-ink-subtle")}>
            {item.value}
          </dd>
          <dt className="text-2xs text-ink-subtle">{item.label}</dt>
        </div>
      ))}
    </dl>
  );
}

function Categories({ score }: { score: FacultyScore }) {
  return (
    <ul className="grid grid-cols-3 gap-2">
      {(Object.keys(CATEGORY) as ScoreCategory[]).map((key) => {
        const { label, icon: Icon } = CATEGORY[key];
        const points = score.by_category[key] ?? 0;
        return (
          <li key={key} className="rounded-lg border border-line px-3 py-2">
            <p className="flex items-center gap-1.5 text-2xs text-ink-subtle">
              <Icon className="h-3 w-3" aria-hidden />{label}
            </p>
            <p className={cn("tabular text-md font-semibold",
              points > 0 ? "text-success" : points < 0 ? "text-danger" : "text-ink-subtle")}>
              {signed(points)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function Ledger({ entries }: { entries: ScoreEntry[] }) {
  if (entries.length === 0) {
    return <EmptyState compact title="Nothing scored yet"
                       description="Points appear as you review work, enter marks and answer meetings." />;
  }
  return (
    <ul className="divide-y divide-line">
      {entries.map((entry, i) => (
        <li key={`${entry.when}-${i}`} className="flex items-start gap-3 py-2.5">
          <span className={cn(
            "tabular mt-0.5 w-9 shrink-0 text-right text-sm font-semibold",
            entry.points > 0 ? "text-success" : entry.points < 0 ? "text-danger" : "text-ink-subtle",
          )}>
            {signed(entry.points)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm leading-snug text-ink break-anywhere">{entry.label}</p>
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-2xs text-ink-subtle">
              <Badge tone={OUTCOME[entry.outcome].tone}>{OUTCOME[entry.outcome].label}</Badge>
              <span>{CATEGORY[entry.category].label}</span>
              {entry.days !== null && <span>· {entry.days} days</span>}
              <span>· {formatDate(entry.when)}</span>
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The rules, read from the server so the screen can never disagree with the score. */
function HowItsScored({ policy }: { policy: ScorePolicy }) {
  const p = policy;
  const rows = [
    [`Review within ${p.review_fast_days} days`, p.review_fast],
    [`Review within ${p.review_ok_days} days`, p.review_ok],
    [`Review after ${p.review_ok_days} days`, p.review_late],
    [`Submission still waiting after ${p.review_ok_days} days`, p.review_overdue],
    ["Marks entered by the presentation deadline", p.marks_on_time],
    ["Marks missing at the deadline", p.marks_missed],
    [`Meeting request answered within ${p.meeting_fast_days} days`, p.meeting_fast],
    [`Meeting request unanswered after ${p.meeting_overdue_days} days`, p.meeting_overdue],
  ] as const;
  return (
    <div className="space-y-3">
      <ul className="divide-y divide-line rounded-lg border border-line">
        {rows.map(([label, points]) => (
          <li key={label} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
            <span className="text-ink">{label}</span>
            <span className={cn("tabular font-semibold", points > 0 ? "text-success" : "text-danger")}>
              {signed(points)}
            </span>
          </li>
        ))}
      </ul>
      <p className="flex gap-2 text-xs text-ink-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Covers the last {p.period_days} days. Work is credited to whoever did it; work still
        waiting counts against the student's mentor. The on-time rate compares faculty fairly
        whatever their number of students. These weights are the department's choice, not a
        PDEU rule.
      </p>
    </div>
  );
}

function NotScored() {
  return (
    <EmptyState compact title="Not scored yet"
                description="Real faculty are scored once the portal runs on real activity. Until then, any figure would come from demo data." />
  );
}

function ScoreSummary({ score }: { score: FacultyScore }) {
  if (!score.is_scored) return <NotScored />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-5">
        <RateRing score={score} />
        <div className="min-w-0 space-y-1.5">
          <Badge tone={BAND_TONE[score.band]}>{score.band}</Badge>
          <p className="tabular text-2xl font-semibold tracking-tight text-ink">
            {signed(score.points)} <span className="text-sm font-normal text-ink-muted">points</span>
          </p>
          <p className="text-xs text-ink-muted">
            {score.scored} scored item{score.scored === 1 ? "" : "s"}
          </p>
        </div>
      </div>
      <Tally score={score} />
      <Categories score={score} />
    </div>
  );
}

/** A faculty member's own score, on their dashboard. */
export function MyScoreCard() {
  const [showRules, setShowRules] = useState(false);
  const score = useQuery({ queryKey: ["faculty-scores", "me"],
                           queryFn: () => api.get<FacultyScore>("/faculty-scores/me") });
  const policy = useQuery({ queryKey: ["faculty-scores", "policy"],
                            queryFn: () => api.get<{ policy: ScorePolicy }>("/faculty-scores/policy") });
  return (
    <Card>
      <CardHeader
        title="Your performance score"
        description="How much of your student-facing work was done on time."
        icon={<Trophy className="h-4 w-4 text-warning" aria-hidden />}
        action={
          <button type="button" onClick={() => setShowRules(true)}
                  className="text-xs font-medium text-accent hover:underline">
            How it's scored
          </button>
        }
      />
      <div className="space-y-5 p-5">
        {score.isLoading ? <LoadingState rows={3} /> : score.error || !score.data ? (
          <ErrorState message={score.error instanceof Error ? score.error.message : undefined}
                      onRetry={() => score.refetch()} />
        ) : (
          <>
            <ScoreSummary score={score.data} />
            {score.data.is_scored && <div>
              <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                Recent items
              </h3>
              <div className="max-h-72 overflow-y-auto pr-1">
                <Ledger entries={score.data.entries.slice(0, 12)} />
              </div>
            </div>}
          </>
        )}
      </div>
      <Modal open={showRules} onClose={() => setShowRules(false)} title="How the score is worked out">
        {policy.data ? <HowItsScored policy={policy.data.policy} /> : <LoadingState rows={3} />}
      </Modal>
    </Card>
  );
}

function FacultyDetail({ facultyId, policy }: { facultyId: number; policy: ScorePolicy }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["faculty-scores", "faculty", facultyId],
    queryFn: () => api.get<FacultyScore>(`/faculty-scores/faculty/${facultyId}`),
  });
  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) return <ErrorState message={error instanceof Error ? error.message : undefined} />;
  return (
    <div className="space-y-5">
      <ScoreSummary score={data} />
      {data.is_scored && <Ledger entries={data.entries} />}
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-medium text-accent">How it's scored</summary>
        <div className="mt-3"><HowItsScored policy={policy} /></div>
      </details>
    </div>
  );
}

/** The HoD's view of their department: who is keeping up, and who is not. */
export function DepartmentScoresCard() {
  const [open, setOpen] = useState<FacultyScore | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["faculty-scores", "department"],
    queryFn: () => api.get<DepartmentScores>("/faculty-scores/department"),
  });
  const attention = data?.faculty.filter((f) => f.band === "At risk" || f.band === "Needs attention").length ?? 0;

  return (
    <Card>
      <CardHeader
        title="Faculty performance"
        description="On-time rate of reviews, marks and meeting replies. Select a row for the itemised record."
        icon={<Gauge className="h-4 w-4 text-ink-subtle" aria-hidden />}
        action={attention > 0 ? <Badge tone="warning">{attention} need attention</Badge> : undefined}
      />
      {isLoading ? <div className="p-5"><LoadingState rows={4} /></div> : error || !data ? (
        <div className="p-5">
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        </div>
      ) : data.faculty.length === 0 ? (
        <EmptyState compact title="No faculty in this department" />
      ) : (
        <>
        {!data.scores_real_faculty && (
          <p className="flex gap-2 border-b border-line bg-surface-muted/40 px-5 py-2.5 text-xs text-ink-muted">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Only demo accounts are scored for now. Real faculty are scored once the portal
            runs on real activity, so nobody is judged on demo data.
          </p>
        )}
        <TableWrap>
          <THead>
            <TH>Faculty</TH>
            <TH width="16%" align="right">On time</TH>
            <TH width="12%" align="right">Points</TH>
            <TH width="16%" align="right">Late / missed</TH>
            <TH width="18%">Standing</TH>
          </THead>
          <TBody>
            {data.faculty.map((row) => (
              <TR key={row.faculty_id} onClick={() => setOpen(row)}>
                <TD>
                  <p className="font-medium text-ink">{row.name}</p>
                  <p className="text-2xs text-ink-subtle">
                    {row.designation}{row.is_demo && " · Demo account"}
                  </p>
                </TD>
                {row.is_scored ? (
                  <>
                <TD align="right" className="tabular">
                  {percent(row.on_time_rate)}
                  <span className="ml-1 text-2xs text-ink-subtle">({row.on_time}/{row.scored})</span>
                </TD>
                <TD align="right" className={cn("tabular font-semibold",
                  row.points > 0 ? "text-success" : row.points < 0 ? "text-danger" : "text-ink-subtle")}>
                  {signed(row.points)}
                </TD>
                <TD align="right" className="tabular text-ink-muted">
                  {row.late + row.overdue} / {row.missed}
                </TD>
                  </>
                ) : (
                  <TD colSpan={3} align="right" className="text-2xs text-ink-subtle">—</TD>
                )}
                <TD><Badge tone={BAND_TONE[row.band]}>{row.band}</Badge></TD>
              </TR>
            ))}
          </TBody>
        </TableWrap>
        </>
      )}
      <Modal open={open !== null} onClose={() => setOpen(null)} size="lg"
             title={open?.name ?? "Faculty"} description={open?.designation ?? undefined}>
        {open && data && <FacultyDetail facultyId={open.faculty_id} policy={data.policy} />}
      </Modal>
    </Card>
  );
}
