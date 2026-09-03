import { BookMarked, CalendarClock, GraduationCap, ShieldCheck, TrendingUp } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/format";
import { roman } from "@/lib/utils";
import type { MinorProgram } from "@/types";

/** Collapse a value that is usually identical across programmes into one label. */
function shared<T>(programs: MinorProgram[], pick: (p: MinorProgram) => T): T[] {
  return [...new Set(programs.map(pick).filter((v) => v !== null && v !== undefined))] as T[];
}

function range(values: number[], format: (v: number) => string): string | null {
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return min === max ? format(min) : `${format(min)} – ${format(max)}`;
}

/**
 * The registration rules, stated up front rather than behind a dialog.
 *
 * Every value here is read from the programme records the API returned. Nothing
 * is restated as a literal in this file: a rule the data does not carry is a
 * rule the portal must not claim. That is also why `pro_rata`, which the
 * curriculum research marks REQUIRES_FACULTY_CONFIRMATION, is absent — it is
 * not settled policy and must not be shown as though it were.
 */
export function MinorRules({ programs }: { programs: MinorProgram[] }) {
  if (!programs.length) return null;

  const cpis = programs.map((p) => p.min_cpi).filter((v): v is number => v != null);
  const backlogs = programs.map((p) => p.max_backlogs).filter((v): v is number => v != null);
  const fromSemesters = programs.map((p) => p.eligible_from_semester);
  const continuation = shared(programs, (p) => p.continuation_rule)[0] as string | undefined;
  const source = shared(programs, (p) => p.rule_source)[0] as string | undefined;
  const sourceUrl = shared(programs, (p) => p.rule_source_url)[0] as string | undefined;
  const offered = shared(programs, (p) => p.offered_semesters.join(","))[0] as string | undefined;
  const closes = programs.map((p) => p.application_closes_at).filter(Boolean)[0];
  const open = programs.some((p) => p.window_open);

  const rules: { icon: typeof GraduationCap; label: string; value: string }[] = [];

  const from = range(fromSemesters, (v) => `Semester ${roman(v)}`);
  if (from) rules.push({ icon: GraduationCap, label: "Eligible from", value: from });

  const cpi = range(cpis, (v) => String(v));
  if (cpi) rules.push({ icon: TrendingUp, label: "Minimum CPI", value: cpi });

  if (backlogs.length) {
    const b = range(backlogs, (v) => String(v));
    rules.push({
      icon: ShieldCheck,
      label: "Backlogs allowed",
      value: b === "0" ? "None — you must have zero backlogs" : (b as string),
    });
  }

  if (offered) {
    rules.push({
      icon: BookMarked,
      label: "Courses run in",
      value: offered.split(",").map((s) => `Semester ${roman(Number(s))}`).join(" · "),
    });
  }

  if (closes) {
    rules.push({
      icon: CalendarClock,
      label: open ? "Registration closes" : "Registration closed",
      value: formatDate(closes) ?? "—",
    });
  }

  return (
    <Card className="mb-5">
      <CardHeader
        title="Registration rules"
        description="Read these before applying — they decide both whether you can register and whether you keep the minor."
        icon={<ShieldCheck className="h-4 w-4 text-accent" aria-hidden />}
        action={
          <Badge tone={open ? "success" : "neutral"}>
            {open ? "Registration open" : "Registration closed"}
          </Badge>
        }
      />
      <CardBody>
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          {rules.map(({ icon: Icon, label, value }) => (
            <div key={label} className="flex gap-2.5">
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
              <div className="min-w-0">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  {label}
                </dt>
                <dd className="mt-0.5 text-sm font-medium text-ink">{value}</dd>
              </div>
            </div>
          ))}
        </dl>

        {continuation && (
          <div className="mt-5 rounded border border-warning/40 bg-warning-soft/50 px-3.5 py-3">
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Continuing on the minor
            </p>
            <p className="mt-1 text-sm text-ink">{continuation}</p>
          </div>
        )}

        {source && (
          <p className="mt-4 text-xs text-ink-subtle">
            Source:{" "}
            {sourceUrl
              ? <a href={sourceUrl} target="_blank" rel="noreferrer"
                   className="text-accent hover:underline">{source}</a>
              : source}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
