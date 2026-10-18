import { CheckCircle2, CircleDashed, Clock, IndianRupee, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/Stepper";
import { formatCurrency, formatDate } from "@/lib/format";
import { cn, roman } from "@/lib/utils";
import type { MinorEnrollment, MinorPlanSemester } from "@/types";

/**
 * A minor student's programme, once they hold a seat: what they take each
 * semester, how they did, and the fee for each semester. Everything comes
 * from the server — the course list from Annexure II, results and payments
 * from the department, and a fee only once the coordinator has announced it.
 */
export function MyMinor({ enrollment }: { enrollment: MinorEnrollment }) {
  const plan = enrollment.plan ?? [];
  const current = plan.find((s) => s.when === "current");
  return (
    <div className="space-y-5">
      <Card className="border-success/40">
        <CardHeader
          title={enrollment.minor_name ?? "Your minor"}
          description={[enrollment.minor_department, enrollment.started_semester
            ? `Registered in Semester ${roman(enrollment.started_semester)}` : null].filter(Boolean).join(" · ")}
          icon={<CheckCircle2 className="h-4 w-4 text-success" aria-hidden />}
          action={<StatusBadge status={enrollment.status} />}
        />
        <CardBody className="grid gap-5 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <ProgressBar label="Credits earned" value={enrollment.credits_completed}
                         max={enrollment.total_credits ?? 1} tone="success" />
            <p className="mt-1.5 text-xs text-ink-muted">
              {enrollment.credits_completed} of {enrollment.total_credits} credits
            </p>
          </div>
          <div className="rounded-lg border border-line px-3 py-2.5">
            <p className="text-2xs uppercase tracking-wide text-ink-subtle">This semester</p>
            <p className="mt-0.5 text-sm font-semibold text-ink">
              {current ? `${current.courses.length} course${current.courses.length === 1 ? "" : "s"}`
                : "No minor course"}
            </p>
            <p className="text-xs text-ink-muted">{current?.fee ? <FeeLine semester={current} /> : "No fee announced"}</p>
          </div>
        </CardBody>
      </Card>

      <ol className="space-y-4">
        {plan.map((semester) => (
          <li key={semester.semester}>
            <Card className={cn(semester.when === "current" && "border-accent/50 ring-1 ring-accent/20",
                                semester.when === "upcoming" && "opacity-90")}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2">
                    Semester {roman(semester.semester)}
                    {semester.when === "current" && <Badge tone="accent">Now</Badge>}
                    {semester.when === "upcoming" && <Badge tone="neutral">Upcoming</Badge>}
                  </span>
                }
                description={`${semester.courses.reduce((n, c) => n + c.credits, 0)} credits`}
                action={<FeeBadge semester={semester} />}
              />
              <ul className="divide-y divide-line">
                {semester.courses.map((course) => (
                  <li key={course.minor_course_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3">
                    <ResultIcon status={course.result?.status} upcoming={semester.when === "upcoming"} />
                    <span className="tabular text-xs text-ink-muted">{course.code}</span>
                    <span className="min-w-0 flex-1 text-sm text-ink">{course.title}</span>
                    <span className="text-xs text-ink-subtle">{course.credits} cr</span>
                    <Result result={course.result} upcoming={semester.when === "upcoming"} />
                  </li>
                ))}
                {semester.courses.length === 0 && (
                  <li className="px-5 py-3 text-sm text-ink-muted">No minor course this semester.</li>
                )}
              </ul>
            </Card>
          </li>
        ))}
      </ol>
      <p className="text-xs text-ink-subtle">
        Courses follow the minor's published list. Results and fee payments are recorded by
        the offering department; ask your minor coordinator about anything missing.
      </p>
    </div>
  );
}

function ResultIcon({ status, upcoming }: { status?: string; upcoming: boolean }) {
  if (status === "PASSED") return <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden />;
  if (status === "FAILED") return <XCircle className="h-4 w-4 shrink-0 text-danger" aria-hidden />;
  if (upcoming) return <CircleDashed className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />;
  return <Clock className="h-4 w-4 shrink-0 text-accent" aria-hidden />;
}

function Result({ result, upcoming }: {
  result: MinorPlanSemester["courses"][number]["result"]; upcoming: boolean;
}): ReactNode {
  if (!result || result.status === "IN_PROGRESS") {
    return <span className="w-28 text-right text-xs text-ink-subtle">{upcoming ? "Not started" : "In progress"}</span>;
  }
  return (
    <span className="flex w-28 items-center justify-end gap-2">
      {result.marks !== null && <span className="tabular text-xs text-ink-muted">{result.marks}/100</span>}
      {result.grade && (
        <Badge tone={result.status === "PASSED" ? "success" : "danger"} className="font-mono">{result.grade}</Badge>
      )}
      {!result.grade && <StatusBadge status={result.status} />}
    </span>
  );
}

function FeeLine({ semester }: { semester: MinorPlanSemester }) {
  if (!semester.fee) return <>No fee announced</>;
  return (
    <>
      {formatCurrency(semester.fee.amount)} · {semester.payment ? "paid"
        : semester.fee.due_on ? `due ${formatDate(semester.fee.due_on)}` : "due"}
    </>
  );
}

function FeeBadge({ semester }: { semester: MinorPlanSemester }) {
  if (!semester.fee) return <Badge tone="neutral">Fee not announced</Badge>;
  const amount = formatCurrency(semester.fee.amount);
  if (semester.payment) {
    return (
      <Badge tone="success" icon={<IndianRupee className="h-3 w-3" aria-hidden />}>
        {amount} paid{semester.payment.reference ? ` · ${semester.payment.reference}` : ""}
      </Badge>
    );
  }
  return (
    <Badge tone={semester.when === "upcoming" ? "neutral" : "warning"} icon={<IndianRupee className="h-3 w-3" aria-hidden />}>
      {amount} {semester.fee.due_on ? `due ${formatDate(semester.fee.due_on)}` : "due"}
    </Badge>
  );
}
