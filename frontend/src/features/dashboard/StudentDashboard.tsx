import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BookOpen, CalendarDays, Clock, GraduationCap, Mail, MapPin,
  Megaphone, Phone, Route, TrendingUp,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { LinkButton } from "@/components/ui/Button";
import { Avatar, PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deadlineLabel, formatDate, formatDateTime } from "@/lib/format";
import { roman } from "@/lib/utils";
import type { StudentDashboard as Data } from "@/types";

const STAT_ICONS = {
  semester: GraduationCap, cpi: TrendingUp, pending_electives: BookOpen,
  events: CalendarDays,
} as const;

export function StudentDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "student"],
    queryFn: () => api.get<Data>("/dashboard/student"),
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  const firstName = user?.full_name.split(" ")[0] ?? "there";

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description={
          user?.student
            ? `${user.student.program_name} · Semester ${roman(user.student.current_semester)} · Division ${user.student.division ?? "—"}`
            : undefined
        }
        meta={
          user?.student && (
            <>
              <Badge tone="brand" className="font-mono">{user.student.roll_number}</Badge>
              {user.academic_year && <Badge tone="neutral">{user.academic_year}</Badge>}
              {user.student.backlog_count > 0 && (
                <Badge tone="warning">
                  {user.student.backlog_count} backlog
                  {user.student.backlog_count > 1 ? "s" : ""}
                </Badge>
              )}
            </>
          )
        }
      />

      <StatGrid>
        {data.stats.map((stat) => {
          const Icon = STAT_ICONS[stat.key as keyof typeof STAT_ICONS];
          return (
            <StatTile
              key={stat.key}
              label={stat.label}
              value={stat.key === "semester" ? roman(stat.value) : stat.value}
              hint={stat.hint}
              icon={Icon}
              to={stat.link}
              tone={stat.key === "pending_electives" && stat.value > 0 ? "warning" : "neutral"}
            />
          );
        })}
      </StatGrid>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          {/* Action items */}
          <Card>
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
                          <Badge
                            tone={deadline.tone === "neutral" ? "neutral" : deadline.tone}
                            className="hidden sm:inline-flex"
                          >
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

          {/* This semester's curriculum */}
          {data.curriculum_semester && (
            <Card>
              <CardHeader
                title={`Semester ${roman(data.curriculum_semester.semester_number)} requirements`}
                description={`${data.curriculum_semester.total_credits} credits in this semester`}
                action={
                  <LinkButton to="/academics/curriculum" variant="secondary" size="sm"
                              iconRight={<ArrowRight className="h-3.5 w-3.5" aria-hidden />}>
                    Full curriculum
                  </LinkButton>
                }
              />
              <CardBody className="space-y-2">
                {data.curriculum_semester.components.map((component) => (
                  <div
                    key={component.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-line px-3 py-2.5"
                  >
                    <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                      {component.code}
                    </span>
                    <span className="min-w-0 flex-1 text-sm font-medium text-ink">
                      {component.title}
                    </span>
                    {component.scope_label && (
                      <span className="hidden text-xs text-ink-subtle sm:inline">
                        {component.scope_label}
                      </span>
                    )}
                    <span className="text-xs text-ink-muted">{component.credits} cr</span>
                    <StatusBadge status={component.status} />
                  </div>
                ))}
              </CardBody>
            </Card>
          )}

          {/* Progress */}
          {data.progress.length > 0 && (
            <Card>
              <CardHeader title="Programme progress" />
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
        <div className="space-y-5">
          {data.mentor && (
            <Card>
              <CardHeader title="Your faculty mentor" />
              <CardBody>
                <div className="flex items-start gap-3">
                  <Avatar name={data.mentor.name} src={data.mentor.avatar_url} size="lg" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink">{data.mentor.name}</p>
                    <p className="text-xs text-ink-muted">{data.mentor.designation}</p>
                    <p className="text-xs text-ink-subtle">{data.mentor.department}</p>
                  </div>
                </div>
                <dl className="mt-4 space-y-2 text-xs">
                  {data.mentor.cabin && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span>Cabin {data.mentor.cabin}</span>
                    </div>
                  )}
                  {data.mentor.email && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <a href={`mailto:${data.mentor.email}`} className="truncate hover:text-accent">
                        {data.mentor.email}
                      </a>
                    </div>
                  )}
                  {data.mentor.phone && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span>{data.mentor.phone}</span>
                    </div>
                  )}
                </dl>
                <LinkButton to="/mentorship" variant="secondary" size="sm" className="mt-4 w-full">
                  Request a meeting
                </LinkButton>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader
              title="Upcoming events"
              action={<Link to="/events" className="text-xs text-accent hover:underline">All events</Link>}
            />
            {data.upcoming_events.length === 0 ? (
              <EmptyState compact title="No upcoming events" icon={<CalendarDays className="h-5 w-5" aria-hidden />} />
            ) : (
              <ul className="divide-y divide-line">
                {data.upcoming_events.map((event) => (
                  <li key={event.id}>
                    <Link to={`/events/${event.id}`} className="block px-5 py-3 transition-colors hover:bg-surface-muted/60">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 text-sm font-medium leading-snug text-ink">
                          {event.title}
                        </p>
                        {event.is_registered && <Badge tone="success">Going</Badge>}
                      </div>
                      <p className="mt-1 text-xs text-ink-subtle">
                        {formatDateTime(event.start_at)}
                        {event.venue && ` · ${event.venue}`}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Announcements"
              icon={<Megaphone className="h-4 w-4 text-ink-subtle" aria-hidden />}
              action={<Link to="/announcements" className="text-xs text-accent hover:underline">All</Link>}
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
                    <p className="mt-1 text-2xs text-ink-subtle">
                      {formatDate(item.published_at)}
                    </p>
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
