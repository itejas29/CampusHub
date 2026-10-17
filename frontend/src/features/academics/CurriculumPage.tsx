import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, CircleDot, Lock } from "lucide-react";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/Misc";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { cn, roman } from "@/lib/utils";
import type { Curriculum } from "@/types";

/** One colour per kind of requirement, used as a dot and a label. */
const TYPE_STYLE: Record<string, { dot: string; label: string }> = {
  CORE: { dot: "bg-brand", label: "Core" },
  OPEN_ELECTIVE: { dot: "bg-accent", label: "Open elective" },
  PROGRAM_CORE_ELECTIVE: { dot: "bg-iris", label: "Program elective" },
  MOOC: { dot: "bg-warning-solid", label: "NPTEL / MOOC" },
  MINOR: { dot: "bg-success-solid", label: "Minor" },
  INTERNSHIP: { dot: "bg-violet", label: "Internship" },
  PROJECT: { dot: "bg-info", label: "Project" },
};

export function CurriculumPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["curriculum", "me"],
    queryFn: () => api.get<Curriculum>("/curriculum/me"),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        title="Curriculum unavailable"
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const total = data.total_credits ?? data.semesters.reduce((n, s) => n + s.total_credits, 0);
  const earned = data.semesters.filter((s) => s.is_completed).reduce((n, s) => n + s.total_credits, 0);
  const pct = total > 0 ? Math.round((earned / total) * 100) : 0;
  const types = Array.from(new Set(data.semesters.flatMap((s) => s.components.map((c) => c.component_type))));

  return (
    <div className="space-y-5">
      <PageHeader
        title="Curriculum"
        description="Your programme, semester by semester, as published by the department. Elective slots and their source rules come from the curriculum itself."
        breadcrumbs={[{ label: "Academics" }, { label: "Curriculum" }]}
        meta={
          <>
            <Badge tone="brand">{data.program_name}</Badge>
            <Badge tone="neutral">Scheme {data.version}</Badge>
            {total > 0 && <Badge tone="neutral">{total} credits</Badge>}
          </>
        }
      />

      {/* ── The journey ───────────────────────────────────────────────── */}
      <section aria-label="Programme progress" className="rounded-2xl border border-line bg-surface p-5 shadow-xs">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">Credits completed</p>
            <p className="mt-1 font-heading text-2xl font-semibold tabular-nums text-ink">
              {earned}<span className="text-base font-medium text-ink-subtle"> / {total}</span>
            </p>
          </div>
          <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-muted">
            {types.map((t) => (
              <li key={t} className="flex items-center gap-1.5">
                <span className={cn("h-2 w-2 rounded-full", TYPE_STYLE[t]?.dot ?? "bg-line-strong")} />
                {TYPE_STYLE[t]?.label ?? t}
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-muted" role="progressbar"
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Credits completed">
          <div className="h-full rounded-full bg-accent-gradient" style={{ width: `${pct}%` }} />
        </div>
        <ol className="mt-5 grid grid-cols-4 gap-2 sm:grid-cols-8">
          {data.semesters.map((s) => (
            <li key={s.semester_number}>
              <a
                href={`#semester-${s.semester_number}`}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-xl border px-2 py-2.5 text-center transition-colors",
                  s.is_current
                    ? "border-accent bg-accent-soft text-accent"
                    : s.is_completed
                      ? "border-success/25 bg-success-soft/60 text-success hover:border-success/50"
                      : "border-line text-ink-subtle hover:border-line-strong hover:text-ink",
                )}
              >
                <span className="font-heading text-sm font-semibold">{roman(s.semester_number)}</span>
                <span className="text-2xs tabular-nums">{s.total_credits} cr</span>
              </a>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Semesters ─────────────────────────────────────────────────── */}
      <div className="space-y-3">
        {data.semesters.map((semester) => (
          <details
            key={semester.semester_number}
            id={`semester-${semester.semester_number}`}
            open={semester.is_current || undefined}
            className={cn(
              "group scroll-mt-20 overflow-hidden rounded-2xl border bg-surface shadow-xs",
              semester.is_current ? "border-accent/50 ring-1 ring-accent/15" : "border-line",
            )}
          >
            <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4 [&::-webkit-details-marker]:hidden">
              <span className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                semester.is_completed ? "bg-success-soft text-success"
                  : semester.is_current ? "bg-accent-soft text-accent" : "bg-surface-muted text-ink-subtle",
              )}>
                {semester.is_completed ? <CheckCircle2 className="h-4.5 w-4.5" aria-hidden />
                  : semester.is_current ? <CircleDot className="h-4.5 w-4.5" aria-hidden />
                    : <Lock className="h-4 w-4" aria-hidden />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-heading text-md font-semibold text-ink">{semester.label}</span>
                  {semester.is_current && <Badge tone="accent">Current</Badge>}
                  {semester.is_completed && <Badge tone="success">Completed</Badge>}
                </span>
                <span className="block text-xs text-ink-muted">
                  {semester.components.length} requirement{semester.components.length === 1 ? "" : "s"} · {semester.total_credits} credits
                </span>
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-ink-subtle transition-transform group-open:rotate-180" aria-hidden />
            </summary>

            <ul className="divide-y divide-line border-t border-line">
              {semester.components.map((c) => {
                const style = TYPE_STYLE[c.component_type];
                const locked = c.is_unlocked === false;
                return (
                  <li key={c.id} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-3", locked && "bg-surface-sunken")}>
                    <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", style?.dot ?? "bg-line-strong")}
                          title={style?.label} aria-hidden />
                    <div className="min-w-0 flex-1 basis-60">
                      <p className="text-sm font-medium leading-snug text-ink">{c.title}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-subtle">
                        <span>{style?.label ?? c.component_type}</span>
                        {c.scope_label && <span>· {c.scope_label}</span>}
                        {c.is_elective && (c.offering_count ?? 0) > 0 && <span>· {c.offering_count} options</span>}
                        <span className="hidden font-mono text-2xs text-ink-subtle/80 md:inline">· {c.code}</span>
                      </p>
                      {c.allocated_course && (
                        <p className="mt-1.5 inline-flex rounded-md bg-success-soft/60 px-2 py-1 text-xs text-ink">
                          <span className="font-semibold">Allocated:</span>&nbsp;{c.allocated_course}
                        </p>
                      )}
                    </div>
                    <span className="w-14 shrink-0 text-right font-heading text-sm font-semibold tabular-nums text-ink">
                      {c.credits}<span className="text-xs font-normal text-ink-subtle"> cr</span>
                    </span>
                    {/* A core course's status is just "Core" — the dot already says so. */}
                    <span className="w-28 shrink-0 text-right">
                      {c.status_label && c.status_label.toLowerCase() !== (style?.label ?? "").toLowerCase()
                        && <StatusBadge status={c.status_label} />}
                    </span>
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>
    </div>
  );
}
