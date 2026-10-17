import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight, ArrowUpRight, Award, BadgeCheck, BookOpen, Briefcase, CalendarClock,
  ClipboardCheck, Clock, FileText, Layers, Megaphone, Milestone, Sparkles, UserCheck,
  Users, Users2, UserSquare2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardHeader } from "@/components/ui/Card";
import { CountUp } from "@/components/ui/CountUp";
import { Avatar } from "@/components/ui/Misc";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { MyScoreCard } from "./PerformanceScore";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/format";

import { cn, pluralise, roman } from "@/lib/utils";
import type {
  CoordinationDomain, FacultyDashboard as Data, FacultyPortfolio, PortfolioStat,
} from "@/types";

// ── presentation metadata ──────────────────────────────────────────────────
// What each module is called, how it is drawn and where its desk lives. This is
// UI vocabulary only: every figure on the card comes from `portfolio.stats`.
type DomainMeta = {
  label: string;
  icon: LucideIcon;
  /** Icon chip + accent bar classes — tokens only, so dark mode follows. */
  chip: string;
  bar: string;
  primary: (p: FacultyPortfolio) => { label: string; to: string; icon: LucideIcon };
  secondary?: (p: FacultyPortfolio) => { label: string; to: string };
};

const internshipActions = {
  primary: (p: FacultyPortfolio) => ({
    label: "Allocate mentors",
    to: `/internships/mentor-assignment${p.program_id ? `?program_id=${p.program_id}` : ""}`,
    icon: UserCheck,
  }),
  secondary: (p: FacultyPortfolio) => ({
    label: "All students",
    to: `/internships/students${p.program_id ? `?program_id=${p.program_id}` : ""}`,
  }),
};

const DOMAIN_META: Record<CoordinationDomain, DomainMeta> = {
  CSSI: {
    label: "CSSI", icon: Users, chip: "bg-success-soft text-success",
    bar: "from-success-solid to-success-solid/40", ...internshipActions,
  },
  SUMMER_INTERNSHIP: {
    label: "Summer Internship", icon: Briefcase, chip: "bg-accent-soft text-accent",
    bar: "from-accent to-electric/50", ...internshipActions,
  },
  MINOR: {
    label: "Minor Specialisation", icon: Sparkles, chip: "bg-violet-soft text-violet",
    bar: "from-violet to-violet/40",
    primary: () => ({ label: "Review applications", to: "/admin/minors", icon: ClipboardCheck }),
  },
  OPEN_ELECTIVE: {
    label: "Open Electives", icon: BookOpen, chip: "bg-warning-soft text-warning",
    bar: "from-warning-solid to-warning-solid/40",
    primary: () => ({ label: "Registration rounds", to: "/admin/elective-rounds", icon: CalendarClock }),
    secondary: () => ({ label: "Allocation", to: "/admin/electives" }),
  },
  CORE_ELECTIVE: {
    label: "Program Core Electives", icon: Layers, chip: "bg-iris-soft text-iris",
    bar: "from-iris to-iris/40",
    primary: () => ({ label: "Registration rounds", to: "/admin/elective-rounds", icon: CalendarClock }),
    secondary: () => ({ label: "Allocation", to: "/admin/electives" }),
  },
  MOOC: {
    label: "NPTEL / MOOC", icon: BadgeCheck, chip: "bg-info-soft text-info",
    bar: "from-info to-info/40",
    primary: () => ({ label: "Verify certificates", to: "/admin/nptel", icon: BadgeCheck }),
  },
  MENTORSHIP: {
    label: "Faculty Mentorship", icon: UserSquare2, chip: "bg-danger-soft text-danger",
    bar: "from-danger to-danger/40",
    primary: () => ({ label: "Mentorship desk", to: "/mentorship", icon: Users }),
  },
};

const FALLBACK_META: DomainMeta = {
  label: "Coordination", icon: Award, chip: "bg-surface-muted text-ink-muted",
  bar: "from-line-strong to-line", primary: () => ({ label: "Open", to: "/", icon: ArrowRight }),
};

function scopeLabel(p: { department_code: string | null; is_institution_wide: boolean }) {
  if (p.is_institution_wide) return "Institution-wide";
  return p.department_code ? `Dept. of ${p.department_code}` : "Department";
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

const WINDOW_LABEL = { REGISTRATION: "Registration", PRESENTATION: "Presentations & marks" } as const;
const WINDOW_STATE = { NOT_STARTED: "Not started", SCHEDULED: "Scheduled", OPEN: "Open", CLOSED: "Closed" } as const;
const WINDOW_TONE = { NOT_STARTED: "neutral", SCHEDULED: "info", OPEN: "success", CLOSED: "neutral" } as const;

const STAT_TONE: Record<PortfolioStat["tone"], string> = {
  default: "text-ink",
  warning: "text-warning",
  success: "text-success",
};

// ── portfolio card ────────────────────────────────────────────────────────
function PortfolioCard({ portfolio }: { portfolio: FacultyPortfolio }) {
  const meta = DOMAIN_META[portfolio.domain] ?? FALLBACK_META;
  const Icon = meta.icon;
  const primary = meta.primary(portfolio);
  const secondary = meta.secondary?.(portfolio);
  const PrimaryIcon = primary.icon;

  // Internship programmes get an allocation progress bar — the one workflow a
  // coordinator returns to most. Both figures are the server's.
  const registered = portfolio.stats.find((s) => s.label === "Registered")?.value;
  const awaiting = portfolio.stats.find((s) => s.label === "Awaiting mentor")?.value;
  const showProgress = registered !== undefined && awaiting !== undefined && registered > 0;
  const allocatedPct = showProgress ? Math.round(((registered - awaiting) / registered) * 100) : 0;

  return (
    <article
      className="group relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-sm transition-[box-shadow,border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card-hover animate-in"
    >
      <div aria-hidden className={cn("h-1 bg-gradient-to-r", meta.bar)} />
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start gap-3">
          <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 group-hover:scale-105", meta.chip)}>
            <Icon className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="font-heading text-base font-semibold leading-snug text-ink">
              {meta.label} coordination
            </h3>
            <p className="mt-0.5 text-xs text-ink-subtle">
              {scopeLabel(portfolio)}
              {portfolio.program_name && (
                <>
                  <span className="mx-1.5 opacity-50">·</span>
                  <span className="break-anywhere">{portfolio.program_name}</span>
                </>
              )}
            </p>
          </div>
        </div>

        {portfolio.stats.length > 0 && (
          <dl
            className={cn(
              "mt-4 grid gap-px overflow-hidden rounded-lg border border-line bg-line",
              // Columns follow the number of figures, so no empty cell shows through.
              {
                1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-3",
              }[portfolio.stats.length] ?? "grid-cols-2 sm:grid-cols-4",
            )}
          >
            {portfolio.stats.map((s) => (
              <div key={s.label} className="min-w-0 bg-surface-sunken px-3 py-2.5">
                <dt className="text-2xs font-semibold uppercase leading-tight tracking-wide text-ink-subtle">
                  {s.label}
                </dt>
                <dd className={cn("mt-1 font-heading text-lg font-semibold leading-none tabular-nums", STAT_TONE[s.tone])}>
                  <CountUp value={s.value} />
                </dd>
                {s.hint && <dd className="mt-1 truncate text-2xs text-ink-subtle" title={s.hint}>{s.hint}</dd>}
              </div>
            ))}
          </dl>
        )}

        {showProgress && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-ink-muted">Mentor allocation</span>
              <span className="font-semibold tabular-nums text-ink">{allocatedPct}%</span>
            </div>
            <div
              className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-muted"
              role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={allocatedPct}
              aria-label="Students with a mentor"
            >
              <div
                className={cn("h-full rounded-full transition-[width] duration-700 ease-out", allocatedPct === 100 ? "bg-success-solid" : "bg-accent-gradient")}
                style={{ width: `${allocatedPct}%` }}
              />

            </div>
          </div>
        )}

        {portfolio.windows && portfolio.windows.length > 0 && (
          <div className="mt-4 rounded-lg border border-line bg-surface-sunken px-3 py-2.5">
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">Cycle</p>
            <ol className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
              {portfolio.windows.map((w, i) => (
                <li key={w.kind} className="flex items-center gap-2">
                  {i > 0 && <span aria-hidden className="text-ink-subtle">→</span>}
                  <span className="font-medium text-ink">{WINDOW_LABEL[w.kind]}</span>
                  <Badge tone={WINDOW_TONE[w.state]}>{WINDOW_STATE[w.state]}</Badge>
                </li>
              ))}
            </ol>
          </div>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2 pt-5">
          <LinkButton to={primary.to} size="sm" variant="accent" icon={<PrimaryIcon className="h-3.5 w-3.5" aria-hidden />}>
            {primary.label}
          </LinkButton>
          {secondary && (
            <LinkButton to={secondary.to} size="sm" variant="secondary">
              {secondary.label}
            </LinkButton>
          )}
          {portfolio.windows && portfolio.windows.length > 0 && portfolio.program_id && (
            <LinkButton to={`/internships/windows?program_id=${portfolio.program_id}`} size="sm" variant="ghost"
                        icon={<CalendarClock className="h-3.5 w-3.5" aria-hidden />}>
              Windows & deadlines
            </LinkButton>
          )}
        </div>
      </div>
    </article>
  );
}

// ── page ──────────────────────────────────────────────────────────────────
type ReviewFilter = "all" | "stage" | "report";

export function FacultyDashboard() {
  const { user } = useAuth();
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "faculty"],
    queryFn: () => api.get<Data>("/dashboard/faculty"),
  });

  // Oldest first: the student who has waited longest is the first to answer.
  const reviews = useMemo(
    () => [...(data?.pending_reviews ?? [])].sort(
      (a, b) => (a.submitted_at ?? "").localeCompare(b.submitted_at ?? ""),
    ),
    [data?.pending_reviews],
  );

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const stat = (key: string) => data.stats.find((s) => s.key === key);
  const reviewCount = stat("pending_reviews")?.value ?? 0;
  const counts = {
    all: reviews.length,
    stage: reviews.filter((r) => r.type === "stage").length,
    report: reviews.filter((r) => r.type === "report").length,
  };
  const shownReviews = reviewFilter === "all" ? reviews : reviews.filter((r) => r.type === reviewFilter);
  const faculty = user?.faculty;
  const openMeetings = data.upcoming_meetings.filter((m) => m.status === "REQUESTED").length;

  const STAT_ICONS: Record<string, { icon: LucideIcon; tone: "accent" | "success" | "warning" | "brand" }> = {
    mentees: { icon: Users2, tone: "accent" },
    internship_students: { icon: Briefcase, tone: "brand" },
    pending_reviews: { icon: ClipboardCheck, tone: "warning" },
    pending_evaluations: { icon: Award, tone: "success" },
  };

  return (
    <div className="space-y-6">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-2xl bg-brand-gradient text-white shadow-lg animate-in">
        <div aria-hidden className="hero-grid absolute inset-0 opacity-60" />
        <div aria-hidden className="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-electric/30 blur-3xl" />
        <div aria-hidden className="absolute -bottom-24 right-1/3 h-56 w-56 rounded-full bg-violet/25 blur-3xl" />

        <div className="relative grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/60">
              Faculty portal
              {user?.academic_year && <span> · {user.academic_year}</span>}
              {user?.current_semester_label && <span> · {user.current_semester_label}</span>}
            </p>
            <h1 className="mt-2 font-heading text-2xl font-semibold leading-tight tracking-tight text-white sm:text-3xl">
              {greeting()}, <span className="break-anywhere">{user?.full_name ?? "Faculty"}</span>
            </h1>
            <p className="mt-1.5 text-sm text-white/75">
              {[faculty?.designation, faculty?.department_code && `Department of ${faculty.department_code}`, faculty?.cabin && `Cabin ${faculty.cabin}`]
                .filter(Boolean).join(" · ") || "PDEU faculty"}
            </p>

            {data.portfolios.length > 0 && (
              <ul className="mt-4 flex flex-wrap gap-2" aria-label="Your coordination roles">
                {data.portfolios.map((p) => {
                  const meta = DOMAIN_META[p.domain] ?? FALLBACK_META;
                  return (
                    <li key={`${p.domain}-${p.program_id ?? p.department_id ?? "all"}`}
                        className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-xs font-medium text-white/90">
                      <meta.icon className="h-3.5 w-3.5 text-white/70" aria-hidden />
                      {meta.label} coordinator
                      <span className="text-white/50">· {scopeLabel(p)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Today, at a glance — two real counts and the two most used doors. */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch lg:flex-col">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 backdrop-blur-sm">
                <p className="text-2xs font-semibold uppercase tracking-wide text-white/60">To review</p>
                <p className="mt-1 font-heading text-2xl font-semibold tabular-nums"><CountUp value={reviewCount} /></p>
              </div>
              <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 backdrop-blur-sm">
                <p className="text-2xs font-semibold uppercase tracking-wide text-white/60">Meeting requests</p>
                <p className="mt-1 font-heading text-2xl font-semibold tabular-nums"><CountUp value={openMeetings} /></p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                to="/announcements"
                className="inline-flex h-9 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg bg-white px-3.5 text-sm font-semibold text-navy shadow-sm transition-all hover:-translate-y-px hover:shadow-md active:translate-y-0"
              >
                <Megaphone className="h-4 w-4" aria-hidden /> Announcements
              </Link>
              {(faculty?.is_mentor || (stat("mentees")?.value ?? 0) > 0) && (
                <Link
                  to="/mentorship/mentees"
                  className="inline-flex h-9 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-white/25 bg-white/10 px-3.5 text-sm font-semibold text-white transition-colors hover:bg-white/20"
                >
                  <Users className="h-4 w-4" aria-hidden /> My mentees
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Coordination portfolios ──────────────────────────────────────── */}
      {data.portfolios.length > 0 && (
        <section aria-labelledby="portfolios-heading" className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 id="portfolios-heading" className="font-heading text-md font-semibold text-ink">
                Your coordination portfolios
              </h2>
              <p className="text-sm text-ink-muted">
                Live figures for the modules you were appointed to run.
              </p>
            </div>
            <Badge tone="accent">{pluralise(data.portfolios.length, "portfolio")}</Badge>
          </div>
          <div className={cn("grid gap-4", data.portfolios.length > 1 && "md:grid-cols-2")}>
            {data.portfolios.map((p) => (
              <PortfolioCard key={`${p.domain}-${p.program_id ?? p.department_id ?? "all"}`} portfolio={p} />
            ))}
          </div>
        </section>
      )}

      {/* ── Your numbers ─────────────────────────────────────────────────── */}
      <StatGrid columns={4}>
        {data.stats.map((s) => (
          <StatTile
            key={s.key} label={s.label} value={s.value} hint={s.hint}
            to={s.link} icon={STAT_ICONS[s.key]?.icon} tone={s.value > 0 ? STAT_ICONS[s.key]?.tone ?? "neutral" : "neutral"}
          />
        ))}
      </StatGrid>

      <div className="grid gap-6 lg:grid-cols-12">
        {/* ── Left: the work queue ───────────────────────────────────────── */}
        <div className="min-w-0 space-y-6 lg:col-span-8">
          <Card>
            <CardHeader
              title="Review queue"
              description="Milestones and reports your students submitted, longest waiting first."
              icon={<ClipboardCheck className="h-4 w-4 text-warning" aria-hidden />}
              action={
                <div role="tablist" aria-label="Filter the review queue" className="inline-flex rounded-lg bg-surface-muted p-0.5">
                  {([["all", "All"], ["stage", "Milestones"], ["report", "Reports"]] as const).map(([key, label]) => (
                    <button
                      key={key} type="button" role="tab" aria-selected={reviewFilter === key}
                      onClick={() => setReviewFilter(key)}
                      className={cn(
                        "relative cursor-pointer whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-semibold transition-colors",
                        reviewFilter === key ? "text-ink" : "text-ink-subtle hover:text-ink",
                      )}
                    >
                      {reviewFilter === key && (
                        <span className="absolute inset-0 rounded-md bg-surface shadow-xs" aria-hidden />
                      )}
                      <span className="relative">{label} <span className="tabular-nums text-ink-subtle">{counts[key]}</span></span>
                    </button>
                  ))}
                </div>
              }
            />
            {shownReviews.length === 0 ? (
              <EmptyState
                compact
                icon={<ClipboardCheck className="h-5 w-5" aria-hidden />}
                title={reviews.length === 0 ? "You're all caught up" : "Nothing in this view"}
                description="Submissions from students you mentor appear here as they arrive."
              />
            ) : (
              <ul className="divide-y divide-line">
                {shownReviews.map((review) => {
                  const age = daysSince(review.submitted_at);
                  const overdue = age !== null && age >= 7;
                  const TypeIcon = review.type === "stage" ? Milestone : FileText;
                  return (
                    <li key={`${review.type}-${review.id}`}>
                      <Link
                        to={review.link}
                        className="group flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-surface-soft/60 focus-visible:bg-surface-soft/60"
                      >
                        <span className={cn(
                          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                          review.type === "stage" ? "bg-iris-soft text-iris" : "bg-accent-soft text-accent",
                        )}>
                          <TypeIcon className="h-4 w-4" aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-ink" title={review.label}>
                            {review.label}
                          </span>
                          <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-muted">
                            <span className="truncate" title={review.student}>{review.student}</span>
                            <span className="font-mono text-2xs text-ink-subtle">{review.roll_number}</span>
                          </span>
                        </span>
                        <span className="hidden shrink-0 flex-col items-end gap-1 sm:flex">
                          <span className={cn("inline-flex items-center gap-1 text-xs", overdue ? "font-semibold text-warning" : "text-ink-subtle")}>
                            <Clock className="h-3 w-3" aria-hidden />
                            {relativeTime(review.submitted_at)}
                          </span>
                          {overdue && <Badge tone="warning">Waiting {age} days</Badge>}
                        </span>
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-accent px-2.5 py-1.5 text-xs font-semibold text-accent-fg shadow-xs transition-all group-hover:bg-accent-hover group-hover:shadow-glow-accent">
                          Review <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" aria-hidden />
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Your mentees"
              description="Students assigned to you for academic mentoring."
              icon={<Users2 className="h-4 w-4 text-accent" aria-hidden />}
              action={data.mentees_preview.length > 0 && (
                <CardAction to="/mentorship/mentees" label="View all mentees">View all</CardAction>
              )}
            />
            {data.mentees_preview.length === 0 ? (
              <EmptyState compact title="No mentees assigned" description="Mentees appear here once your HoD's office allocates them." />
            ) : (
              <ul className="grid gap-3 p-5 sm:grid-cols-2">
                {data.mentees_preview.map((mentee) => (
                  <li key={mentee.student_id} className="min-w-0">
                    <Link
                      to={`/people/students/${mentee.student_id}`}
                      className="flex items-center gap-3 rounded-lg border border-line bg-surface p-3 transition-all hover:-translate-y-px hover:border-accent/40 hover:shadow-card-hover"
                    >
                      <Avatar name={mentee.name} src={mentee.avatar_url} size="md" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-ink" title={mentee.name}>{mentee.name}</span>
                        <span className="block truncate text-xs text-ink-subtle">
                          <span className="font-mono">{mentee.roll_number}</span> · Sem {roman(mentee.semester)}
                        </span>
                      </span>
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {data.internship_groups.length > 0 && (
            <Card>
              <CardHeader
                title="Internship groups you lead"
                icon={<Users className="h-4 w-4 text-success" aria-hidden />}
              />
              <ul className="divide-y divide-line">
                {data.internship_groups.map((g) => {
                  const pct = g.capacity > 0 ? Math.min(100, Math.round((g.member_count / g.capacity) * 100)) : 0;
                  return (
                    <li key={g.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-ink" title={g.name}>{g.name}</span>
                        {g.program && <span className="block truncate text-xs text-ink-subtle">{g.program}</span>}
                      </span>
                      {g.capacity > 0 && (
                        <span className="flex w-40 items-center gap-2">
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
                            <span className="block h-full rounded-full bg-success-solid" style={{ width: `${pct}%` }} />
                          </span>
                          <span className="text-xs tabular-nums text-ink-muted">{g.member_count}/{g.capacity}</span>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </div>

        {/* ── Right: schedule and notices ────────────────────────────────── */}
        <div className="min-w-0 space-y-6 lg:col-span-4">
          <MyScoreCard />

          <Card>
            <CardHeader
              title="Meetings"
              description="Requested and confirmed mentee meetings."
              icon={<CalendarClock className="h-4 w-4 text-iris" aria-hidden />}
              action={<CardAction to="/mentorship" label="Manage meetings">Manage</CardAction>}
            />
            {data.upcoming_meetings.length === 0 ? (
              <EmptyState compact title="No open meeting requests" />
            ) : (
              <ul className="divide-y divide-line">
                {data.upcoming_meetings.map((m) => (
                  <li key={m.id} className="flex gap-3 px-5 py-3.5">
                    <Avatar name={m.student} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 text-sm font-semibold leading-snug text-ink break-anywhere">{m.title}</p>
                        <StatusBadge status={m.status} className="shrink-0" />
                      </div>
                      <p className="mt-0.5 truncate text-xs text-ink-muted" title={m.student}>{m.student}</p>
                      <p className="mt-1 inline-flex items-center gap-1 text-xs text-ink-subtle">
                        <Clock className="h-3 w-3" aria-hidden />
                        {formatDateTime(m.scheduled_at ?? m.proposed_slot)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Announcements"
              icon={<Megaphone className="h-4 w-4 text-violet" aria-hidden />}
              action={<CardAction to="/announcements" label="All announcements">View all</CardAction>}
            />
            {data.announcements.length === 0 ? (
              <EmptyState compact title="No announcements yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.announcements.map((a) => (
                  <li key={a.id} className="px-5 py-3.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {a.priority && a.priority !== "NORMAL" && <StatusBadge status={a.priority} />}
                      {a.category && <Badge tone="neutral">{a.category.replace(/_/g, " ").toLowerCase()}</Badge>}
                      <span className="ml-auto text-2xs text-ink-subtle">{relativeTime(a.published_at)}</span>
                    </div>
                    <p className="mt-1.5 text-sm font-semibold leading-snug text-ink break-anywhere">{a.title}</p>
                    {a.excerpt && <p className="mt-1 line-clamp-2 text-xs text-ink-muted" title={a.excerpt}>{a.excerpt}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
