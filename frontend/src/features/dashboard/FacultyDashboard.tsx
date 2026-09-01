import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, CalendarClock, ClipboardCheck, FileText, Route, Users, Users2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar, PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/format";
import { roman } from "@/lib/utils";
import type { FacultyDashboard as Data } from "@/types";

const ICONS = {
  mentees: Users, internship_students: Route,
  pending_reviews: ClipboardCheck, pending_evaluations: FileText,
} as const;

export function FacultyDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "faculty"],
    queryFn: () => api.get<Data>("/dashboard/faculty"),
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={user?.full_name ?? "Faculty dashboard"}
        description={
          user?.faculty
            ? `${user.faculty.designation} · ${user.faculty.department_code ?? ""}`
            : undefined
        }
        meta={
          user?.faculty && (
            <>
              <Badge tone="brand" className="font-mono">{user.faculty.employee_code}</Badge>
              {user.faculty.cabin && <Badge tone="neutral">Cabin {user.faculty.cabin}</Badge>}
              {user.academic_year && <Badge tone="neutral">{user.academic_year}</Badge>}
            </>
          )
        }
        actions={
          <LinkButton to="/announcements" variant="secondary" size="sm">
            Post announcement
          </LinkButton>
        }
      />

      <StatGrid>
        {data.stats.map((stat) => (
          <StatTile
            key={stat.key}
            label={stat.label}
            value={stat.value}
            hint={stat.hint}
            icon={ICONS[stat.key as keyof typeof ICONS]}
            to={stat.link}
            tone={
              (stat.key === "pending_reviews" || stat.key === "pending_evaluations")
                && stat.value > 0 ? "warning" : "neutral"
            }
          />
        ))}
      </StatGrid>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          <Card>
            <CardHeader
              title="Awaiting your review"
              description="Internship stages and reports your students have submitted."
              icon={<ClipboardCheck className="h-4 w-4 text-warning" aria-hidden />}
            />
            {data.pending_reviews.length === 0 ? (
              <EmptyState
                compact
                title="Nothing to review"
                description="Submissions from your assigned students will appear here."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.pending_reviews.map((review) => (
                  <li key={`${review.type}-${review.id}`}>
                    <Link
                      to={review.link}
                      className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-muted/60"
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-surface-muted text-ink-subtle">
                        {review.type === "report"
                          ? <FileText className="h-4 w-4" aria-hidden />
                          : <Route className="h-4 w-4" aria-hidden />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{review.label}</p>
                        <p className="truncate text-xs text-ink-subtle">
                          <span className="font-mono">{review.roll_number}</span> · {review.student}
                        </p>
                      </div>
                      <span className="hidden shrink-0 text-xs text-ink-subtle sm:block">
                        {relativeTime(review.submitted_at)}
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="My mentees"
              icon={<Users2 className="h-4 w-4 text-ink-subtle" aria-hidden />}
              action={
                <LinkButton to="/mentorship/mentees" variant="secondary" size="sm"
                            iconRight={<ArrowRight className="h-3.5 w-3.5" aria-hidden />}>
                  View all
                </LinkButton>
              }
            />
            {data.mentees_preview.length === 0 ? (
              <EmptyState compact title="No mentees assigned"
                          description="The department administrator assigns mentees each academic year." />
            ) : (
              <CardBody className="grid gap-2 sm:grid-cols-2">
                {data.mentees_preview.map((mentee) => (
                  <div
                    key={mentee.student_id}
                    className="flex items-center gap-2.5 rounded border border-line px-3 py-2"
                  >
                    <Avatar name={mentee.name} src={mentee.avatar_url} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{mentee.name}</p>
                      <p className="truncate text-2xs text-ink-subtle">
                        <span className="font-mono">{mentee.roll_number}</span>
                        {" · "}Sem {roman(mentee.semester)}
                      </p>
                    </div>
                    {mentee.cpi !== null && (
                      <span className="shrink-0 text-xs font-medium tabular-nums text-ink-muted">
                        {mentee.cpi.toFixed(2)}
                      </span>
                    )}
                  </div>
                ))}
              </CardBody>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Meeting requests"
              icon={<CalendarClock className="h-4 w-4 text-ink-subtle" aria-hidden />}
              action={<Link to="/mentorship" className="text-xs text-accent hover:underline">Manage</Link>}
            />
            {data.upcoming_meetings.length === 0 ? (
              <EmptyState compact title="No open requests" />
            ) : (
              <ul className="divide-y divide-line">
                {data.upcoming_meetings.map((meeting) => (
                  <li key={meeting.id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 text-sm font-medium leading-snug text-ink">
                        {meeting.title}
                      </p>
                      <StatusBadge status={meeting.status} />
                    </div>
                    <p className="mt-0.5 text-xs text-ink-muted">{meeting.student}</p>
                    <p className="mt-0.5 text-2xs text-ink-subtle">
                      {formatDateTime(meeting.scheduled_at ?? meeting.proposed_slot)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {data.internship_groups.length > 0 && (
            <Card>
              <CardHeader title="My internship groups" />
              <CardBody className="space-y-4">
                {data.internship_groups.map((group) => (
                  <div key={group.id}>
                    <ProgressBar
                      label={`${group.name} · ${group.program ?? ""}`}
                      value={group.member_count}
                      max={group.capacity}
                      tone="brand"
                    />
                  </div>
                ))}
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Announcements"
                        action={<Link to="/announcements" className="text-xs text-accent hover:underline">All</Link>} />
            {data.announcements.length === 0 ? (
              <EmptyState compact title="No announcements" />
            ) : (
              <ul className="divide-y divide-line">
                {data.announcements.map((item) => (
                  <li key={item.id} className="px-5 py-3">
                    <p className="text-sm font-medium leading-snug text-ink">{item.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{item.excerpt}</p>
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
