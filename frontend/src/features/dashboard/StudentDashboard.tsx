import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Calendar,
  CalendarDays,
  Clock,
  GraduationCap,
  Mail,
  MapPin,
  Megaphone,
  Phone,
  Route,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deadlineLabel, formatDate, formatDateTime } from "@/lib/format";
import { cn, pluralise, roman } from "@/lib/utils";
import type { StudentDashboard as Data } from "@/types";

type Component = NonNullable<Data["curriculum_semester"]>["components"][number];

/** Slots the student chooses or registers for, as opposed to compulsory ones. */
const CHOICE_TYPES = new Set(["OPEN_ELECTIVE", "PROGRAM_CORE_ELECTIVE", "MOOC"]);

const TYPE_LABELS: Record<string, string> = {
  CORE: "Core course",
  OPEN_ELECTIVE: "Open elective",
  PROGRAM_CORE_ELECTIVE: "Program elective",
  MOOC: "NPTEL / MOOC",
  MINOR: "Minor",
  INTERNSHIP: "Internship",
  PROJECT: "Project",
};

/** The screen where a slot is acted on; compulsory slots have none. */
function componentLink(component: Component): string | null {
  switch (component.component_type) {
    case "OPEN_ELECTIVE": return `/academics/open-electives/${component.id}`;
    case "PROGRAM_CORE_ELECTIVE": return `/academics/core-electives/${component.id}`;
    case "MOOC": return "/academics/nptel";
    default: return null;
  }
}

const TILE = "rounded-xl p-5 card-luxe-shadow hover-lift relative overflow-hidden";
const TILE_DARK = `${TILE} text-white border border-blue-400/20`;
const TILE_LABEL = "text-2xs font-semibold tracking-wider uppercase";
const TILE_VALUE = "font-heading text-2xl font-bold tracking-tight mb-1";
const TILE_ICON = "w-8 h-8 rounded-lg flex items-center justify-center";

export function StudentDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "student"],
    queryFn: () => api.get<Data>("/dashboard/student"),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "there";
  const student = user?.student;
  const stat = (key: string) => data.stats.find((item) => item.key === key);

  // Everything below is read from the student's own curriculum semester. A
  // semester with no elective slot (I–III in most programmes) must say so
  // rather than show "0 pending", which reads as a finished task.
  const semester = data.curriculum_semester;
  const components = semester?.components ?? [];
  const hasChoiceSlots = components.some((c) => CHOICE_TYPES.has(c.component_type));
  const pending = stat("pending_electives");
  const pendingCount = pending?.value ?? 0;
  const semesterNumber = student?.current_semester ?? stat("semester")?.value;
  const backlogs = student?.backlog_count ?? 0;
  const nextEvent = data.upcoming_events[0];
  const registeredEvents = stat("events")?.value ?? 0;

  return (
    <div className="space-y-6">
      {/* 1. PAGE HERO HEADER */}
      <section className="bg-gradient-to-r from-surface-muted via-surface to-blue-50/40 dark:to-blue-950/20 rounded-xl p-5 sm:p-6 border border-line card-luxe-shadow">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="font-heading text-xl sm:text-2xl font-bold text-ink tracking-tight">
                Welcome back, {firstName}
              </h1>
              {student && (
                backlogs === 0 ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800 text-xs font-bold">
                    <span className="w-2 h-2 rounded-full bg-emerald-600" />
                    No backlogs
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-900 dark:text-amber-200 border border-amber-300 dark:border-amber-800 text-xs font-bold">
                    <span className="w-2 h-2 rounded-full bg-amber-600" />
                    {pluralise(backlogs, "backlog")}
                  </span>
                )
              )}
            </div>
            {student?.program_name && (
              <p className="text-xs sm:text-sm text-ink-muted">{student.program_name}</p>
            )}

            {student && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="px-2.5 py-1 rounded bg-surface border border-line text-xs font-semibold text-primary">
                  Semester {roman(student.current_semester)}
                  {student.division && ` • Division ${student.division}`}
                </span>
                <span className="px-2.5 py-1 rounded bg-surface border border-line font-mono text-xs font-bold text-primary">
                  Roll No: {student.roll_number}
                </span>
                {user?.academic_year && (
                  <span className="px-2.5 py-1 rounded bg-surface border border-line text-xs text-ink-subtle">
                    AY {user.academic_year}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <LinkButton to="/profile" variant="secondary" size="sm">
              View Full Profile
            </LinkButton>
            {pendingCount > 0 && pending?.link && (
              <LinkButton
                to={pending.link}
                variant="primary"
                size="sm"
                icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
              >
                Elective Actions
              </LinkButton>
            )}
          </div>
        </div>
      </section>

      {/* 2. STAT TILES */}
      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className={cn(TILE_DARK, "bg-gradient-to-br from-[#1e3a5f] via-[#162c48] to-[#1e3a5f]")}>
          <div className="flex items-center justify-between mb-3">
            <span className={cn(TILE_LABEL, "text-blue-200")}>Active Term</span>
            <div className={cn(TILE_ICON, "bg-white/10 text-blue-200")}>
              <GraduationCap className="h-4 w-4" aria-hidden />
            </div>
          </div>
          <div className={cn(TILE_VALUE, "text-white")}>
            {semesterNumber ? `Semester ${roman(semesterNumber)}` : "—"}
          </div>
          <p className="text-2xs text-blue-200/80">
            {semester
              ? `${pluralise(components.length, "requirement")} on record`
              : "Curriculum not on record"}
          </p>
        </div>

        <div className={cn(TILE_DARK, "bg-gradient-to-br from-[#1e3a5f] via-[#162c48] to-[#2563eb]")}>
          <div className="flex items-center justify-between mb-3">
            <span className={cn(TILE_LABEL, "text-blue-200")}>Cumulative CPI</span>
            <div className={cn(TILE_ICON, "bg-white/10 text-blue-200")}>
              <TrendingUp className="h-4 w-4" aria-hidden />
            </div>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className={cn(TILE_VALUE, "text-white mb-0")}>
              {student?.cpi != null ? student.cpi.toFixed(2) : "—"}
            </span>
            {student?.cpi != null && (
              <span className="font-mono text-xs text-blue-200">/ 10.0</span>
            )}
          </div>
          <p className="text-2xs text-blue-200/90">
            {student?.cpi != null
              ? (backlogs === 0 ? "No backlogs" : pluralise(backlogs, "backlog"))
              : "Published after your first semester results"}
          </p>
        </div>

        <div
          className={cn(
            TILE, "bg-surface border",
            pendingCount > 0 ? "border-amber-300/80 dark:border-amber-700" : "border-line",
          )}
        >
          <div className="flex items-center justify-between mb-3">
            <span
              className={cn(
                TILE_LABEL,
                pendingCount > 0 ? "text-amber-800 dark:text-amber-300" : "text-ink-muted",
              )}
            >
              Elective Actions
            </span>
            <div
              className={cn(
                TILE_ICON,
                pendingCount > 0
                  ? "bg-amber-50 dark:bg-amber-950 text-amber-600"
                  : "bg-surface-muted text-primary",
              )}
            >
              <BookOpen className="h-4 w-4" aria-hidden />
            </div>
          </div>
          <div className={cn(TILE_VALUE, "text-ink")}>
            {!hasChoiceSlots ? "None" : pendingCount > 0 ? `${pendingCount} Pending` : "Up to date"}
          </div>
          <p
            className={cn(
              "text-2xs",
              pendingCount > 0 ? "text-amber-700 dark:text-amber-400 font-medium" : "text-ink-subtle",
            )}
          >
            {!semester
              ? "Curriculum not on record"
              : !hasChoiceSlots
                ? `No elective slot in Semester ${roman(semester.semester_number)}`
                : pendingCount > 0
                  ? "Waiting on your choice"
                  : "Nothing is waiting on you"}
          </p>
        </div>

        <div className={cn(TILE, "bg-surface border border-line")}>
          <div className="flex items-center justify-between mb-3">
            <span className={cn(TILE_LABEL, "text-ink-muted")}>Campus Events</span>
            <div className={cn(TILE_ICON, "bg-surface-muted text-primary")}>
              <CalendarDays className="h-4 w-4" aria-hidden />
            </div>
          </div>
          <div className={cn(TILE_VALUE, "text-ink")}>
            {data.upcoming_events.length} Upcoming
          </div>
          <p className="text-2xs text-ink-subtle truncate">
            {nextEvent
              ? `Next: ${nextEvent.title}`
              : `${registeredEvents} registered so far`}
          </p>
        </div>
      </section>

      {/* 3. MAIN GRID */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <div className="xl:col-span-8 space-y-6 min-w-0">
          {/* Action items */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Needs your attention"
              description="Open registration windows and internship steps waiting on you."
              icon={<Clock className="h-4 w-4 text-warning" aria-hidden />}
            />
            {data.action_items.length === 0 ? (
              <EmptyState
                compact
                title="Nothing pending"
                description="You have no open elective windows or internship steps right now."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.action_items.map((item, index) => {
                  const deadline = deadlineLabel(item.due_at);
                  return (
                    <li key={`${item.title}-${index}`}>
                      <Link
                        to={item.link ?? "#"}
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-muted/60"
                      >
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-surface-muted text-ink-subtle">
                          {item.kind === "internship"
                            ? <Route className="h-4 w-4" aria-hidden />
                            : <BookOpen className="h-4 w-4" aria-hidden />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-ink">{item.title}</p>
                          <p className="truncate text-xs text-ink-subtle">{item.context}</p>
                        </div>
                        {item.due_at && (
                          <Badge tone={deadline.tone} className="hidden sm:inline-flex">
                            {deadline.text}
                          </Badge>
                        )}
                        <ArrowRight className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {/* This semester, as the student's own curriculum defines it */}
          <Card className="card-luxe-shadow">
            <div className="p-5 sm:p-6 border-b border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="font-heading text-base sm:text-lg font-bold text-ink flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-secondary" aria-hidden />
                  {semester
                    ? `Semester ${roman(semester.semester_number)} Requirements`
                    : "This Semester"}
                </h2>
                {student?.program_name && (
                  <p className="text-xs text-ink-muted">{student.program_name}</p>
                )}
              </div>
              {semester && (
                <div className="sm:text-right">
                  <span className="font-mono text-sm sm:text-base font-bold text-secondary block">
                    {semester.total_credits} Credits
                  </span>
                  <span className="text-2xs text-ink-subtle">
                    {pluralise(components.length, "requirement")} on record
                  </span>
                </div>
              )}
            </div>

            {!semester ? (
              <EmptyState
                compact
                title="No curriculum on record for this semester"
                description="Your department has not published the structure for your batch yet."
              />
            ) : (
              <CardBody className="space-y-4">
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between text-2xs font-semibold uppercase tracking-wider text-ink-subtle px-1 pb-1 border-b border-line">
                    <span>Component</span>
                    <span>Status</span>
                  </div>

                  {components.map((component) => {
                    const needsAction = component.status === "Action needed"
                      || component.status === "REJECTED";
                    const link = componentLink(component);
                    return (
                      <div
                        key={component.id}
                        className={cn(
                          "flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg transition-colors gap-2 border",
                          needsAction
                            ? "bg-amber-50/70 dark:bg-amber-950/30 border-amber-200/80 dark:border-amber-900"
                            : "bg-surface-muted/40 hover:bg-surface-muted border-line",
                        )}
                      >
                        <div className="space-y-0.5 min-w-0">
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "font-mono text-2xs font-bold shrink-0",
                                needsAction ? "text-amber-900 dark:text-amber-200" : "text-secondary",
                              )}
                            >
                              {component.code}
                            </span>
                            <h3 className="text-xs font-bold text-ink truncate">{component.title}</h3>
                          </div>
                          <p className="text-2xs text-ink-muted">
                            {TYPE_LABELS[component.component_type] ?? component.component_type}
                            {" • "}{pluralise(component.credits, "credit")}
                            {component.scope_label && ` • ${component.scope_label}`}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <StatusBadge status={component.status} />
                          {needsAction && link && (
                            <Link
                              to={link}
                              className="px-2.5 py-0.5 bg-amber-600 text-white rounded text-2xs font-bold hover:bg-amber-700 transition-colors"
                            >
                              {component.component_type === "MOOC" ? "Register" : "Choose Now"}
                            </Link>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="pt-3 border-t border-line flex justify-end">
                  <Link
                    to="/academics/curriculum"
                    className="inline-flex items-center gap-1 text-xs font-bold text-secondary hover:underline"
                  >
                    View Full Curriculum
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                </div>
              </CardBody>
            )}
          </Card>

          {/* Internship / minor progress — only once the student has a record */}
          {data.progress.length > 0 && (
            <Card className="card-luxe-shadow">
              <CardHeader
                title="Programme progress"
                description="Counted from the documents you have actually submitted."
                icon={<Route className="h-4 w-4 text-secondary" aria-hidden />}
              />
              <CardBody className="space-y-4">
                {data.progress.map((item) => (
                  <Link key={item.label} to={item.link ?? "#"} className="block group">
                    <ProgressBar
                      label={item.label}
                      value={item.completed}
                      max={item.total || 1}
                      tone={item.completed >= item.total ? "success" : "accent"}
                    />
                  </Link>
                ))}
              </CardBody>
            </Card>
          )}
        </div>

        {/* Right rail */}
        <div className="xl:col-span-4 space-y-6 min-w-0">
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Assigned Faculty Mentor"
              icon={<UserCheck className="h-4 w-4 text-primary" aria-hidden />}
            />
            {!data.mentor ? (
              <EmptyState
                compact
                title="No mentor assigned yet"
                description="The department assigns a faculty mentor at the start of each academic year."
              />
            ) : (
              <CardBody className="space-y-4">
                <div className="flex items-start gap-3">
                  <Avatar name={data.mentor.name} src={data.mentor.avatar_url} size="lg" />
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-ink">{data.mentor.name}</p>
                    <p className="text-xs text-ink-muted">{data.mentor.designation}</p>
                    {data.mentor.department && (
                      <p className="text-xs text-ink-subtle">{data.mentor.department}</p>
                    )}
                  </div>
                </div>

                {(data.mentor.cabin || data.mentor.email || data.mentor.phone) && (
                  <div className="space-y-2 border-t border-line pt-3 text-xs text-ink-muted">
                    {data.mentor.cabin && (
                      <div className="flex items-center gap-2">
                        <MapPin className="h-3.5 w-3.5 text-ink-subtle shrink-0" aria-hidden />
                        <span>Cabin {data.mentor.cabin}</span>
                      </div>
                    )}
                    {data.mentor.email && (
                      <div className="flex items-center gap-2">
                        <Mail className="h-3.5 w-3.5 text-ink-subtle shrink-0" aria-hidden />
                        <a href={`mailto:${data.mentor.email}`} className="truncate hover:text-accent">
                          {data.mentor.email}
                        </a>
                      </div>
                    )}
                    {data.mentor.phone && (
                      <div className="flex items-center gap-2">
                        <Phone className="h-3.5 w-3.5 text-ink-subtle shrink-0" aria-hidden />
                        <span>{data.mentor.phone}</span>
                      </div>
                    )}
                  </div>
                )}

                <LinkButton to="/mentorship" variant="primary" size="sm" className="w-full justify-center">
                  Request a Meeting
                </LinkButton>
              </CardBody>
            )}
          </Card>

          <Card className="card-luxe-shadow">
            <CardHeader
              title="Upcoming Events"
              icon={<Calendar className="h-4 w-4 text-purple-600" aria-hidden />}
              action={<CardAction to="/events" label="All events">All</CardAction>}
            />
            {data.upcoming_events.length === 0 ? (
              <EmptyState
                compact
                title="No upcoming events"
                icon={<CalendarDays className="h-5 w-5" aria-hidden />}
              />
            ) : (
              <CardBody className="space-y-3">
                {data.upcoming_events.map((event) => (
                  <Link
                    key={event.id}
                    to={`/events/${event.id}`}
                    className="block p-3 rounded-lg border border-line bg-surface-muted/30 hover:bg-surface-muted transition-colors space-y-1"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-semibold text-ink min-w-0">{event.title}</p>
                      {event.is_registered && <Badge tone="success">Going</Badge>}
                    </div>
                    <p className="text-2xs text-ink-subtle">
                      {event.club && `${event.club} • `}
                      {formatDateTime(event.start_at)}
                      {event.venue && ` • ${event.venue}`}
                    </p>
                  </Link>
                ))}
              </CardBody>
            )}
          </Card>

          <Card className="card-luxe-shadow">
            <CardHeader
              title="Announcements"
              icon={<Megaphone className="h-4 w-4 text-ink-subtle" aria-hidden />}
              action={<CardAction to="/announcements" label="All announcements">All</CardAction>}
            />
            {data.announcements.length === 0 ? (
              <EmptyState compact title="No announcements" />
            ) : (
              <ul className="divide-y divide-line">
                {data.announcements.map((item) => (
                  <li key={item.id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 text-sm font-medium leading-snug text-ink">
                        {item.title}
                      </p>
                      {item.priority !== "NORMAL" && <StatusBadge status={item.priority} />}
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{item.excerpt}</p>
                    <p className="mt-1 text-2xs text-ink-subtle">{formatDate(item.published_at)}</p>
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
