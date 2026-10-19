import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, BookOpen, CalendarClock, GraduationCap, Megaphone, ShieldCheck,
  UserCog, Users,
} from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { HodDashboard as Data } from "@/types";
import { DepartmentScoresCard } from "./PerformanceScore";

const STAT_ICONS = {
  faculty: GraduationCap, students: Users, uncovered: AlertTriangle,
  open_rounds: CalendarClock,
} as const;

/**
 * The Head of Department's home. Built around the one thing they do — appoint
 * the people who run each module — and what they oversee. It has no mentee list
 * and no review queue on purpose: an HoD has neither.
 */
export function HodDashboard({ departmentCode }: { departmentCode?: string }) {
  const { user } = useAuth();
  // `departmentCode`: the registrar opening a department's Head-of-Department
  // view (the HoD is a real person who cannot sign in to the demo).
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "hod", departmentCode ?? "own"],
    queryFn: () => api.get<Data>(departmentCode
      ? `/dashboard/hod?department_code=${encodeURIComponent(departmentCode)}` : "/dashboard/hod"),
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

  return (
    <div className="space-y-6">
      {departmentCode && (
        <Alert variant="info">
          You are seeing what the Head of Department of {data.department.name} sees. As
          registrar you may also appoint here; the Head can only read their department and
          appoint into it.
        </Alert>
      )}
      <PageHeader
        title={(departmentCode ? data.hod_name : user?.full_name) ?? "Head of Department"}

        description={`Head of Department · ${data.department.name}`}
        meta={
          <>
            <Badge tone="brand" className="font-mono">{data.department.code}</Badge>
            {user?.academic_year && <Badge tone="neutral">{user.academic_year}</Badge>}
          </>
        }
        actions={
          <LinkButton to="/admin/roles" size="sm"
                      icon={<UserCog className="h-3.5 w-3.5" aria-hidden />}>
            Manage coordinators
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
            icon={STAT_ICONS[stat.key as keyof typeof STAT_ICONS]}
            to={stat.link}
            tone={stat.key === "uncovered" && stat.value > 0 ? "warning" : "neutral"}
          />
        ))}
      </StatGrid>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          <Card>
            <CardHeader
              title="Who runs each module"
              description="You appoint these. A module with mentors but no coordinator is still uncovered."
              icon={<ShieldCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
              action={<CardAction to="/admin/roles" label="Manage coordinators">Manage</CardAction>}
            />
            <TableWrap>
              <THead>
                <TH width="34%">Module</TH>
                <TH>Coordinator</TH>
                <TH width="14%" align="right">Mentors</TH>
              </THead>
              <TBody>
                {data.modules.map((module) => (
                  <TR key={module.domain}>
                    <TD className="font-medium text-ink">{module.label}</TD>
                    <TD>
                      {module.is_covered ? (
                        <ul className="space-y-0.5">
                          {module.coordinators.map((person) => (
                            <li key={person.assignment_id}>
                              <span className="text-ink">{person.name}</span>
                              <span className="ml-1.5 text-xs text-ink-subtle">
                                {person.designation}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <Badge tone="warning">No coordinator</Badge>
                      )}
                    </TD>
                    <TD align="right" className="tabular">
                      {module.mentor_count || <span className="text-ink-subtle">—</span>}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
          </Card>

          <DepartmentScoresCard />

          <Card>
            <CardHeader
              title="Elective registration rounds"
              description="Opened, extended and locked by the module's coordinator. You can see them; you cannot change them."
              icon={<BookOpen className="h-4 w-4 text-ink-subtle" aria-hidden />}
            />
            {data.rounds.length === 0 ? (
              <EmptyState compact title="No rounds yet"
                          description="Rounds appear here once a coordinator creates one." />
            ) : (
              <TableWrap>
                <THead>
                  <TH>Round</TH>
                  <TH width="18%">Family</TH>
                  <TH width="20%">Closes</TH>
                  <TH width="12%" align="right">Students</TH>
                  <TH width="14%">Status</TH>
                </THead>
                <TBody>
                  {data.rounds.map((round) => (
                    <TR key={round.id}>
                      <TD>
                        <p className="font-medium text-ink">{round.title}</p>
                        <p className="font-mono text-2xs text-ink-subtle">{round.code}</p>
                      </TD>
                      <TD className="text-xs text-ink-muted">
                        {humanise(round.component_type)}
                      </TD>
                      <TD className="text-xs text-ink-muted">
                        {formatDateTime(round.closes_at)}
                      </TD>
                      <TD align="right" className="tabular">
                        {round.eligible_student_count}
                      </TD>
                      <TD><StatusBadge status={round.status} /></TD>
                    </TR>
                  ))}
                </TBody>
              </TableWrap>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
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
