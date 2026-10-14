import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Download, Layers, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { api, downloadProtectedFile } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { humanise, roman } from "@/lib/utils";
import type { InternshipGroup, InternshipProgram } from "@/types";

export function ProgramsAdminPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });

  return (
    <div>
      <PageHeader
        title="Internship programmes"
        description="One engine, configured per programme: stages, group structure, reporting cadence and rubric are all data."
        breadcrumbs={[{ label: "Internships" }, { label: "Programmes" }]}
        actions={
          <Link to="/internships/students"
                className="inline-flex h-9 items-center rounded border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink transition-colors hover:bg-surface-muted">
            All students
          </Link>
        }
      />

      {isLoading && <LoadingState rows={4} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No internship programmes configured"
                      icon={<ClipboardList className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      <div className="space-y-5">
        {(data ?? []).map((program) => (
          <ProgramCard key={program.id} program={program} />
        ))}
      </div>
    </div>
  );
}

function ProgramCard({ program }: { program: InternshipProgram }) {
  const groups = useQuery({
    queryKey: ["internship-groups", program.id],
    queryFn: () => api.get<InternshipGroup[]>(`/internships/programs/${program.id}/groups`),
    enabled: program.requires_group,
  });

  return (
    <Card>
      <CardHeader
        title={program.name}
        description={program.description ?? undefined}
        action={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void downloadProtectedFile(`/internships/programs/${program.id}/export`)}
              icon={<Download className="h-3.5 w-3.5" aria-hidden />}
            >
              Export Grades CSV
            </Button>
            <StatusBadge status={program.status} />
          </div>
        }
      />
      <CardBody className="space-y-5">
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="brand" className="font-mono">{program.code}</Badge>
          <Badge tone="neutral">{humanise(program.type)}</Badge>
          <Badge tone="neutral">{program.credits} credits</Badge>
          {program.target_semester && (
            <Badge tone="neutral">From semester {roman(program.target_semester)}</Badge>
          )}
          <Badge tone="neutral">
            {formatDate(program.start_date)} – {formatDate(program.end_date)}
          </Badge>
          {program.coordinator_name && (
            <Badge tone="accent">Coordinator: {program.coordinator_name}</Badge>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Enrolled", value: program.enrolled_count },
            { label: "Completed", value: program.completed_count },
            { label: "Stages", value: program.stages.length },
            { label: "Rubric criteria", value: program.criteria.length },
          ].map((stat) => (
            <div key={stat.label} className="rounded border border-line p-3">
              <p className="font-heading text-xl font-semibold tabular-nums text-ink">
                {stat.value}
              </p>
              <p className="text-xs text-ink-subtle">{stat.label}</p>
            </div>
          ))}
        </div>

        <ProgressBar
          label="Completion"
          value={program.completed_count}
          max={program.enrolled_count || 1}
          tone={program.completed_count === program.enrolled_count ? "success" : "accent"}
        />

        <div className="grid gap-5 lg:grid-cols-2">
          <div className="min-w-0">
            <h3 className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              <Layers className="h-3 w-3" aria-hidden /> Configured stages
            </h3>
            <ol className="space-y-1">
              {program.stages.map((stage, index) => (
                <li key={stage.id}
                    className="flex items-start gap-2 rounded border border-line px-2.5 py-1.5">
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-muted text-2xs font-semibold text-ink-subtle">
                    {index + 1}
                  </span>
                  <span className="min-w-0 flex-1 text-sm text-ink">{stage.name}</span>
                  <span className="shrink-0 text-2xs text-ink-subtle">
                    {stage.owner_role.toLowerCase()}
                    {stage.requires_document && " · doc"}
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div className="min-w-0">
            <h3 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Evaluation rubric
            </h3>
            <TableWrap className="rounded border border-line">
              <THead>
                <TH>Criterion</TH>
                <TH width="20%" align="right">Max</TH>
                <TH width="20%" align="right">Weight</TH>
              </THead>
              <TBody>
                {program.criteria.map((criterion) => (
                  <TR key={criterion.id}>
                    <TD>{criterion.name}</TD>
                    <TD align="right" className="tabular">{criterion.max_marks}</TD>
                    <TD align="right" className="tabular text-ink-subtle">
                      ×{criterion.weight}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
            <p className="mt-2 text-2xs text-ink-subtle">
              Reporting:{" "}
              {program.report_frequency === "NONE"
                ? "no periodic reports"
                : `${humanise(program.report_frequency).toLowerCase()}, ${program.expected_report_count} expected`}
              {program.requires_industry_mentor && " · industry mentor required"}
            </p>
          </div>
        </div>

        {program.requires_group && (
          <div>
            <h3 className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              <Users className="h-3 w-3" aria-hidden /> Faculty groups
            </h3>
            {groups.isLoading ? (
              <LoadingState rows={2} />
            ) : !groups.data?.length ? (
              <p className="text-sm text-ink-muted">No groups have been created yet.</p>
            ) : (
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {groups.data.map((group) => (
                  <div key={group.id} className="rounded border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-ink">{group.name}</p>
                      <Badge tone="neutral">
                        {group.member_count}/{group.capacity}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-ink-muted">
                      {group.faculty_name ?? "No faculty assigned"}
                    </p>
                    {group.faculty_cabin && (
                      <p className="text-2xs text-ink-subtle">
                        Cabin {group.faculty_cabin}
                      </p>
                    )}
                    {group.meeting_schedule && (
                      <p className="mt-1 text-2xs text-ink-subtle">
                        {group.meeting_schedule}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
