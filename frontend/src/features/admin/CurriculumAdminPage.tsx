import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Archive, CheckCircle2, ExternalLink, FileText, Undo2, Upload,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { api } from "@/lib/api";
import type { Curriculum, Program, ProgramDivision } from "@/types";

const STATUS_TONE = {
  PUBLISHED: "success", DRAFT: "warning", ARCHIVED: "neutral",
} as const;

const CONFIDENCE_TONE: Record<string, "success" | "warning"> = {
  CONFIRMED_OFFICIAL_SOURCE: "success",
  PARTIAL_SOURCE: "warning",
  DERIVED_FROM_INTAKE: "warning",
  REQUIRES_FACULTY_CONFIRMATION: "warning",
};

/**
 * Curriculum version management.
 *
 * The lifecycle is the point: a published version is what students are actually
 * served, so it cannot be edited in place — the way forward is a revision, which
 * closes the previous batch window and leaves the old structure intact for the
 * cohort still studying under it.
 */
export function CurriculumAdminPage() {
  const queryClient = useQueryClient();
  const [programFilter, setProgramFilter] = useState<string>("");
  const [message, setMessage] = useState<{ variant: "success" | "danger"; text: string } | null>(null);

  const programs = useQuery({
    queryKey: ["curriculum-programs"],
    queryFn: () => api.get<Program[]>("/curriculum/programs"),
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["curriculum-versions"],
    queryFn: () => api.get<Curriculum[]>("/curriculum?include_semesters=false"),
  });

  const [divisionProgram, setDivisionProgram] = useState<string>("");
  const divisions = useQuery({
    queryKey: ["program-divisions", divisionProgram],
    queryFn: () =>
      api.get<ProgramDivision[]>(`/curriculum/programs/${divisionProgram}/divisions`),
    enabled: Boolean(divisionProgram),
  });

  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      api.post<Curriculum>(`/curriculum/${id}/${action}`, {}),
    onSuccess: (result) => {
      setMessage({ variant: "success", text: `${result.name} is now ${result.status.toLowerCase()}.` });
      queryClient.invalidateQueries({ queryKey: ["curriculum-versions"] });
      queryClient.invalidateQueries({ queryKey: ["curriculums"] });
    },
    onError: (e: Error) => setMessage({ variant: "danger", text: e.message }),
  });

  const rows = useMemo(() => {
    const items = data ?? [];
    const filtered = programFilter
      ? items.filter((c) => String(c.program_id) === programFilter)
      : items;
    return [...filtered].sort((a, b) =>
      (a.program_code ?? "").localeCompare(b.program_code ?? "") ||
      b.effective_from_year - a.effective_from_year);
  }, [data, programFilter]);

  const flaggedTotal = (data ?? []).reduce((n, c) => n + c.flagged_component_count, 0);
  const drafts = (data ?? []).filter((c) => c.status === "DRAFT").length;

  return (
    <div>
      <PageHeader
        title="Curriculum management"
        description="Versions are scoped to admission batches. Publishing is the review step made explicit; a published version is never edited in place."
        breadcrumbs={[{ label: "Administration" }, { label: "Curriculum" }]}
        actions={
          programs.data && (
            <Select
              value={programFilter}
              onChange={(e) => setProgramFilter(e.target.value)}
              aria-label="Filter by programme"
              className="w-full sm:w-72"
            >
              <option value="">All programmes</option>
              {programs.data.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
          )
        }
      />

      {message && (
        <Alert variant={message.variant} className="mb-4" onDismiss={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      {(drafts > 0 || flaggedTotal > 0) && (
        <Alert variant="info" className="mb-4">
          {drafts > 0 && <>{drafts} version(s) awaiting review. </>}
          {flaggedTotal > 0 && (
            <>
              {flaggedTotal} component(s) across all programmes are flagged as needing
              faculty confirmation. Publishing is blocked until each is confirmed —
              an unconfirmed reading of a curriculum document must not become a rule
              students are held to.
            </>
          )}
        </Alert>
      )}

      {isLoading && <LoadingState rows={6} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No curriculum versions"
                      icon={<FileText className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      {rows.length > 0 && (
        <Card className="mb-5">
          <CardHeader title="Versions"
                      description="Historical versions are kept, never deleted — a cohort part-way through its degree keeps the structure it was admitted under." />
          <CardBody className="overflow-x-auto p-0">
            <TableWrap>
              <THead>
                <TH>Programme</TH><TH>Version</TH><TH>Batches</TH>
                <TH>Status</TH><TH>Components</TH><TH>Source</TH><TH>Actions</TH>
              </THead>

              <TBody>
                {rows.map((c) => (
                  <TR key={c.id}>
                    <TD>
                      <p className="font-medium text-ink">{c.program_name}</p>
                      <p className="text-2xs text-ink-subtle">
                        {c.school} · {c.department_code}
                      </p>
                    </TD>
                    <TD className="tabular">{c.version}</TD>
                    <TD className="text-xs">{c.batch_label}</TD>
                    <TD>
                      <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>
                        {c.status.toLowerCase()}
                      </Badge>
                    </TD>
                    <TD className="tabular text-xs">
                      {c.component_count}
                      {c.flagged_component_count > 0 && (
                        <span className="ml-1.5 inline-flex items-center gap-1 text-warning">
                          <AlertTriangle className="h-3 w-3" aria-hidden />
                          {c.flagged_component_count}
                        </span>
                      )}
                    </TD>
                    <TD className="max-w-[18rem] text-xs">
                      {c.source ? (
                        <>
                          {c.source.confidence && (
                            <Badge tone={CONFIDENCE_TONE[c.source.confidence] ?? "neutral"}>
                              {c.source.confidence.replace(/_/g, " ").toLowerCase()}
                            </Badge>
                          )}
                          {c.source.url && (
                            <a href={c.source.url} target="_blank" rel="noreferrer"
                               className="mt-1 flex items-center gap-1 text-brand hover:underline">
                              <span className="truncate">{c.source.title ?? "Official document"}</span>
                              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                            </a>
                          )}
                          {c.source.review_notes && (
                            <p className="mt-1 text-2xs text-warning">{c.source.review_notes}</p>
                          )}
                        </>
                      ) : (
                        <span className="text-ink-subtle">No source recorded</span>
                      )}
                    </TD>
                    <TD>
                      <div className="flex flex-wrap gap-1.5">
                        {c.status !== "PUBLISHED" && (
                          <Button size="sm" variant="secondary"
                                  icon={<Upload className="h-3.5 w-3.5" aria-hidden />}
                                  disabled={act.isPending || c.flagged_component_count > 0}
                                  title={c.flagged_component_count > 0
                                    ? "Confirm the flagged components first"
                                    : undefined}
                                  onClick={() => act.mutate({ id: c.id, action: "publish" })}>
                            Publish
                          </Button>
                        )}
                        {c.status === "PUBLISHED" && (
                          <>
                            <Button size="sm" variant="ghost" disabled={act.isPending}
                                    icon={<Undo2 className="h-3.5 w-3.5" aria-hidden />}
                                    onClick={() => act.mutate({ id: c.id, action: "unpublish" })}>
                              Unpublish
                            </Button>
                            <Button size="sm" variant="ghost" disabled={act.isPending}
                                    icon={<Archive className="h-3.5 w-3.5" aria-hidden />}
                                    onClick={() => act.mutate({ id: c.id, action: "archive" })}>
                              Archive
                            </Button>
                          </>
                        )}
                        {c.status === "PUBLISHED" && c.flagged_component_count === 0 && (
                          <span className="inline-flex items-center gap-1 text-2xs text-success">
                            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                            live
                          </span>
                        )}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Divisions"
          description="Programme × batch, not a fixed A/B/C/D. The Core Elective allocator reads these rows."
          action={
            programs.data && (
              <Select value={divisionProgram}
                      onChange={(e) => setDivisionProgram(e.target.value)}
                      aria-label="Programme divisions" className="w-full sm:w-64">
                <option value="">Select a programme…</option>
                {programs.data.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </Select>
            )
          }
        />
        <CardBody>
          {!divisionProgram && (
            <p className="text-sm text-ink-muted">
              Choose a programme to see the divisions configured for each batch.
            </p>
          )}
          {divisionProgram && divisions.isLoading && <LoadingState rows={2} />}
          {divisionProgram && divisions.data?.length === 0 && (
            <p className="text-sm text-ink-muted">
              No divisions configured. The allocator treats this as “no division
              restriction” rather than assuming four.
            </p>
          )}
          {divisions.data && divisions.data.length > 0 && (
            <div className="space-y-3">
              {[...new Set(divisions.data.map((d) => d.admission_year))]
                .sort((a, b) => b - a)
                .map((yearGroup) => (
                  <div key={yearGroup} className="flex flex-wrap items-center gap-2">
                    <span className="tabular text-xs text-ink-muted">{yearGroup} batch</span>
                    {divisions.data!
                      .filter((d) => d.admission_year === yearGroup)
                      .map((d) => (
                        <Badge key={d.id} tone="neutral">
                          {d.name}
                          {d.student_count > 0 && ` · ${d.student_count}`}
                        </Badge>
                      ))}
                  </div>
                ))}
              {divisions.data[0]?.notes && (
                <p className="pt-1 text-2xs text-ink-subtle">{divisions.data[0].notes}</p>
              )}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
