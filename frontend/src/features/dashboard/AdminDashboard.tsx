import { useQuery } from "@tanstack/react-query";
import {
  Activity, ArrowRight, Building2, CalendarDays, GraduationCap, Route, School,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { AdminDashboard as Data } from "@/types";

const ICONS = {
  students: Users, faculty: GraduationCap, departments: Building2,
  clubs: School, events: CalendarDays, internship_enrollments: Route,
} as const;

export function AdminDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "admin"],
    queryFn: () => api.get<Data>("/dashboard/admin"),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  const maxSemester = Math.max(...data.students_by_semester.map((b) => b.value), 1);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administration"
        description="Live counts from the portal database — no sampled or estimated figures."
        meta={
          <>
            {user?.academic_year && <Badge tone="brand">{user.academic_year}</Badge>}
            <Badge tone="neutral">{user?.roles.map(humanise).join(" · ")}</Badge>
          </>
        }
      />

      <StatGrid columns={6}>
        {data.stats.map((stat) => (
          <StatTile
            key={stat.key} label={stat.label} value={stat.value} hint={stat.hint}
            icon={ICONS[stat.key as keyof typeof ICONS]} to={stat.link}
          />
        ))}
      </StatGrid>

      <Card>
        <CardHeader
          title="Pending actions"
          description="Queues that need an administrator or coordinator decision."
        />
        <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {data.pending_actions.map((action) => (
            <Link
              key={action.key}
              to={action.link ?? "#"}
              className="rounded-lg border border-line p-3.5 transition-colors hover:border-line-strong hover:bg-surface-muted/40"
            >
              <p className={`font-heading text-xl font-semibold tabular-nums ${
                action.value > 0 ? "text-warning" : "text-ink-subtle"
              }`}>
                {action.value}
              </p>
              <p className="mt-0.5 text-xs leading-snug text-ink-muted">{action.label}</p>
            </Link>
          ))}
        </CardBody>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Students by semester" description="Active student records" />
          <CardBody className="space-y-3">
            {data.students_by_semester.length === 0 ? (
              <EmptyState compact title="No student records" />
            ) : (
              data.students_by_semester.map((item) => (
                <div key={item.label} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 text-xs text-ink-muted">{item.label}</span>
                  <div className="h-5 flex-1 overflow-hidden rounded bg-surface-muted">
                    <div
                      className="h-full rounded bg-brand/80 transition-all duration-500"
                      style={{ width: `${(item.value / maxSemester) * 100}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right text-xs font-medium tabular-nums text-ink">
                    {item.value}
                  </span>
                </div>
              ))
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Internship completion"
                      description="Students who have completed each programme" />
          <CardBody className="space-y-4">
            {data.internship_progress.length === 0 ? (
              <EmptyState compact title="No internship enrolments" />
            ) : (
              data.internship_progress.map((item) => (
                <ProgressBar
                  key={item.label}
                  label={item.label}
                  value={item.value}
                  max={item.total ?? 1}
                  tone={item.value === item.total ? "success" : "accent"}
                />
              ))
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent activity"
            icon={<Activity className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              <Link to="/admin/audit" className="flex items-center gap-1 text-xs text-accent hover:underline">
                Full audit log <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
            }
          />
          {data.recent_activity.length === 0 ? (
            <EmptyState compact title="No recorded activity yet" />
          ) : (
            <TableWrap>
              <THead>
                <TH width="30%">Action</TH>
                <TH>Description</TH>
                <TH width="16%">Actor</TH>
                <TH width="14%" align="right">When</TH>
              </THead>
              <TBody>
                {data.recent_activity.map((item) => (
                  <TR key={item.id}>
                    <TD>
                      <Badge tone="neutral">{humanise(item.action)}</Badge>
                    </TD>
                    <TD className="text-ink-muted">{item.description ?? item.entity_type}</TD>
                    <TD className="truncate text-xs text-ink-subtle">
                      {item.actor?.split(" <")[0] ?? "system"}
                    </TD>
                    <TD align="right" className="whitespace-nowrap text-xs text-ink-subtle">
                      {relativeTime(item.created_at)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
          )}
        </Card>

        <Card>
          <CardHeader title="Upcoming events"
                      action={<Link to="/admin/events" className="text-xs text-accent hover:underline">Manage</Link>} />
          {data.upcoming_events.length === 0 ? (
            <EmptyState compact title="No upcoming events" />
          ) : (
            <ul className="divide-y divide-line">
              {data.upcoming_events.map((event) => (
                <li key={event.id} className="px-5 py-3">
                  <p className="text-sm font-medium leading-snug text-ink">{event.title}</p>
                  <p className="mt-0.5 text-xs text-ink-subtle">
                    {formatDateTime(event.start_at)}
                  </p>
                  {event.club && (
                    <p className="mt-0.5 text-2xs text-ink-subtle">{event.club}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
