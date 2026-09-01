import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileStack, Info, PlayCircle } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Checkbox, FormField, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { roman } from "@/lib/utils";
import type {
  Allocation, AllocationRunResult, AllocationStrategy, Curriculum,
  CurriculumComponent, DistributeResult, Preference, Viability,
} from "@/types";

export function ElectiveAdminPage() {
  const queryClient = useQueryClient();
  const [componentId, setComponentId] = useState<string>("");
  const [tab, setTab] = useState("viability");
  const [runOpen, setRunOpen] = useState(false);
  const [result, setResult] = useState<AllocationRunResult | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const curriculums = useQuery({
    queryKey: ["curriculums"],
    queryFn: () => api.get<Curriculum[]>("/curriculum"),
  });

  // Flatten every elective slot across published curriculums.
  const components: (CurriculumComponent & { programme: string })[] =
    (curriculums.data ?? []).flatMap((curriculum) =>
      curriculum.semesters.flatMap((semester) =>
        semester.components
          .filter((component) => component.is_elective)
          .map((component) => ({
            ...component,
            programme: curriculum.program_name ?? curriculum.name,
          })),
      ),
    );

  const selected = components.find((c) => String(c.id) === componentId);

  const strategies = useQuery({
    queryKey: ["allocation-strategies"],
    queryFn: () => api.get<AllocationStrategy[]>("/electives/strategies"),
  });

  const preferences = useQuery({
    queryKey: ["component-preferences", componentId],
    queryFn: () =>
      api.get<Preference[]>(`/electives/admin/preferences?component_id=${componentId}`),
    enabled: Boolean(componentId),
  });

  const allocations = useQuery({
    queryKey: ["component-allocations", componentId],
    queryFn: () =>
      api.get<Allocation[]>(`/electives/admin/allocations?component_id=${componentId}`),
    enabled: Boolean(componentId),
  });

  // Demand is read from first preferences before allocation, and from actual
  // allocations afterwards.
  const hasAllocations = (allocations.data?.length ?? 0) > 0;
  const viability = useQuery({
    queryKey: ["component-viability", componentId, hasAllocations],
    queryFn: () =>
      api.get<Viability[]>(
        `/electives/admin/viability?component_id=${componentId}` +
        `&use_preferences=${!hasAllocations}`,
      ),
    enabled: Boolean(componentId),
  });

  const distribute = useMutation({
    mutationFn: (offeringId: number) =>
      api.post<DistributeResult>(
        `/electives/admin/offerings/${offeringId}/distribute`,
      ),
    onSuccess: (data) => {
      setBanner({
        tone: "success",
        text: `${data.assigned} student(s) placed across ${data.sections} section(s): ` +
              data.detail.map((s) => `${s.name} ${s.seats_filled}`).join(", "),
      });
      void queryClient.invalidateQueries({ queryKey: ["component-viability"] });
      void queryClient.invalidateQueries({ queryKey: ["component-allocations"] });
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not form sections.",
      }),
  });

  const run = useMutation({
    mutationFn: ({ strategy, dryRun }: { strategy: string; dryRun: boolean }) =>
      api.post<AllocationRunResult>("/electives/admin/allocate", {
        curriculum_component_id: Number(componentId),
        strategy,
        dry_run: dryRun,
      }),
    onSuccess: (data) => {
      setResult(data);
      if (!data.dry_run) {
        setRunOpen(false);
        setBanner({
          tone: "success",
          text: `Allocation complete — ${data.allocated} seat(s) assigned, ` +
                `${data.waitlisted} waitlisted.`,
        });
        void queryClient.invalidateQueries({ queryKey: ["component-allocations"] });
        void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      }
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Allocation failed.",
      }),
  });

  // Group preferences by student for a readable table.
  const byStudent = new Map<number, Preference[]>();
  for (const preference of preferences.data ?? []) {
    const key = (preference as Preference & { student_id?: number }).student_id ?? 0;
    byStudent.set(key, [...(byStudent.get(key) ?? []), preference]);
  }

  return (
    <div>
      <PageHeader
        title="Elective allocation"
        description="Review submitted preferences and run an allocation strategy. Runs default to a dry run so the outcome can be checked before anything is written."
        breadcrumbs={[{ label: "Administration" }, { label: "Elective Allocation" }]}
        actions={
          <Button
            size="sm"
            disabled={!componentId}
            onClick={() => { setResult(null); setRunOpen(true); }}
            icon={<PlayCircle className="h-3.5 w-3.5" aria-hidden />}
          >
            Run allocation
          </Button>
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <Card className="mb-5">
        <CardBody>
          <FormField
            label="Curriculum component"
            hint="Elective slots are read from the published curriculums — nothing here is hard-coded."
          >
            <Select value={componentId} onChange={(e) => setComponentId(e.target.value)}>
              <option value="">Select a component…</option>
              {components.map((component) => (
                <option key={component.id} value={component.id}>
                  {component.programme} · Sem {roman(component.semester_number)} ·{" "}
                  {component.code} — {component.title}
                </option>
              ))}
            </Select>
          </FormField>

          {selected && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone="brand" className="font-mono">{selected.code}</Badge>
              <Badge tone="neutral">Semester {roman(selected.semester_number)}</Badge>
              <Badge tone="neutral">{selected.credits} credits</Badge>
              {selected.scope_label && <Badge tone="accent">{selected.scope_label}</Badge>}
              {selected.offering_count !== null && (
                <Badge tone="neutral">{selected.offering_count} offerings</Badge>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {!componentId ? (
        <Card>
          <EmptyState
            title="Select a component"
            description="Choose an elective slot above to review its preferences and allocations."
            icon={<FileStack className="h-5 w-5" aria-hidden />}
          />
        </Card>
      ) : (
        <Card>
          <Tabs
            tabs={[
              { key: "viability", label: "Viability & sections",
                count: viability.data?.length },
              { key: "preferences", label: "Preferences", count: preferences.data?.length },
              { key: "allocations", label: "Allocations", count: allocations.data?.length },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "viability" && (
            viability.isLoading ? (
              <LoadingState rows={4} />
            ) : viability.error ? (
              <ErrorState onRetry={() => viability.refetch()} compact />
            ) : !viability.data?.length ? (
              <EmptyState compact title="No courses published for this component" />
            ) : (
              <>
                <CardBody className="border-b border-line">
                  <Alert variant="info">
                    {selected?.component_type === "OPEN_ELECTIVE" ? (
                      <>
                        <strong>Open Elective rules:</strong> a course runs with at
                        least {viability.data[0].min_students_to_run} students, and each
                        class section holds {viability.data[0].section_capacity}. There
                        is no course-wide maximum — demand above one section opens
                        another (90 → 75 + 15).
                      </>
                    ) : (
                      <>
                        <strong>Core Elective rules:</strong> the{" "}
                        {viability.data[0].min_students_to_run}-student minimum is
                        counted <em>across all participating divisions combined</em>,
                        never per division. There is no 75-student ceiling — the course
                        runs as one combined class.
                      </>
                    )}
                  </Alert>
                </CardBody>
                <TableWrap>
                  <THead>
                    <TH width="24%">Course</TH>
                    <TH width="10%" align="right">Demand</TH>
                    <TH width="18%">Runs?</TH>
                    <TH width="18%">Sections</TH>
                    <TH>Division composition</TH>
                    <TH width="12%" align="right">Actions</TH>
                  </THead>
                  <TBody>
                    {viability.data.map((row) => (
                      <TR key={row.offering_id}>
                        <TD>
                          <span className="tabular mr-2">{row.course_code}</span>
                          <span className="text-ink-muted">{row.course_title}</span>
                        </TD>
                        <TD align="right" className="tabular font-medium">
                          {row.demand}
                        </TD>
                        <TD>
                          {row.runs ? (
                            <Badge tone="success">Runs</Badge>
                          ) : (
                            <Badge tone="warning">
                              {row.shortfall} short of {row.min_students_to_run}
                            </Badge>
                          )}
                        </TD>
                        <TD>
                          {row.planned_sections.length === 0 ? (
                            <span className="text-ink-subtle">—</span>
                          ) : (
                            <span className="text-ink-muted">
                              <span className="tabular">
                                {row.planned_sections.join(" + ")}
                              </span>
                              {row.planned_sections.length > 1 && (
                                <span className="ml-1.5 text-2xs text-ink-subtle">
                                  ({row.planned_sections.length} sections)
                                </span>
                              )}
                            </span>
                          )}
                        </TD>
                        <TD>
                          {row.division_breakdown.length === 0 ? (
                            <span className="text-ink-subtle">—</span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {row.division_breakdown.map((d) => (
                                <Badge key={d.division} tone="neutral">
                                  {d.division}: {d.count}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </TD>
                        <TD align="right">
                          <Button
                            size="sm" variant="secondary" disabled={!row.runs}
                            loading={distribute.isPending}
                            onClick={() => distribute.mutate(row.offering_id)}
                          >
                            {row.existing_sections > 0 ? "Rebuild" : "Form"} sections
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </TableWrap>
              </>
            )
          )}

          {tab === "preferences" && (
            preferences.isLoading ? (
              <LoadingState rows={4} />
            ) : preferences.error ? (
              <ErrorState onRetry={() => preferences.refetch()} compact />
            ) : (
              <TableWrap>
                <THead>
                  <TH width="10%">Rank</TH>
                  <TH width="16%">Course code</TH>
                  <TH>Course</TH>
                  <TH width="16%">Submitted</TH>
                  <TH width="12%">Status</TH>
                </THead>
                <TBody>
                  {!preferences.data?.length ? (
                    <TableEmpty colSpan={5}>
                      No preferences have been submitted for this component.
                    </TableEmpty>
                  ) : (
                    preferences.data.map((preference) => (
                      <TR key={preference.id}>
                        <TD>
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-2xs font-semibold text-brand">
                            {preference.preference_order}
                          </span>
                        </TD>
                        <TD className="tabular">{preference.course_code}</TD>
                        <TD className="text-ink-muted">{preference.course_title}</TD>
                        <TD className="text-xs text-ink-subtle">
                          {formatDate(preference.submitted_at)}
                        </TD>
                        <TD><StatusBadge status={preference.status} /></TD>
                      </TR>
                    ))
                  )}
                </TBody>
              </TableWrap>
            )
          )}

          {tab === "allocations" && (
            allocations.isLoading ? (
              <LoadingState rows={4} />
            ) : allocations.error ? (
              <ErrorState onRetry={() => allocations.refetch()} compact />
            ) : (
              <TableWrap>
                <THead>
                  <TH width="20%">Student</TH>
                  <TH width="11%">Roll no.</TH>
                  <TH width="7%" align="center">Div</TH>
                  <TH>Allocated course</TH>
                  <TH width="12%">Section</TH>
                  <TH width="8%" align="center">Pref.</TH>
                  <TH width="12%">Status</TH>
                </THead>
                <TBody>
                  {!allocations.data?.length ? (
                    <TableEmpty colSpan={7}>
                      No seats have been allocated for this component yet.
                    </TableEmpty>
                  ) : (
                    allocations.data.map((allocation) => (
                      <TR key={allocation.id}>
                        <TD className="font-medium">{allocation.student_name}</TD>
                        <TD className="tabular">{allocation.roll_number}</TD>
                        <TD align="center">{allocation.division ?? "—"}</TD>
                        <TD className="text-ink-muted">
                          <span className="tabular mr-2">{allocation.course_code}</span>
                          {allocation.course_title}
                        </TD>
                        <TD>
                          {allocation.section_name ? (
                            <Badge tone="accent">{allocation.section_name}</Badge>
                          ) : (
                            <span className="text-ink-subtle">Not placed</span>
                          )}
                        </TD>
                        <TD align="center" className="tabular">
                          {allocation.preference_order_granted ?? "—"}
                        </TD>
                        <TD><StatusBadge status={allocation.status} /></TD>
                      </TR>
                    ))
                  )}
                </TBody>
              </TableWrap>
            )
          )}
        </Card>
      )}

      <RunAllocationModal
        open={runOpen}
        onClose={() => { setRunOpen(false); setResult(null); }}
        strategies={strategies.data ?? []}
        component={selected}
        result={result}
        loading={run.isPending}
        onRun={(strategy, dryRun) => run.mutate({ strategy, dryRun })}
      />
    </div>
  );
}

function RunAllocationModal({
  open, onClose, strategies, component, result, loading, onRun,
}: {
  open: boolean; onClose: () => void; strategies: AllocationStrategy[];
  component?: CurriculumComponent; result: AllocationRunResult | null;
  loading: boolean; onRun: (strategy: string, dryRun: boolean) => void;
}) {
  const [strategy, setStrategy] = useState("preference_order");
  const [dryRun, setDryRun] = useState(true);
  const chosen = strategies.find((s) => s.key === strategy);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Run allocation"
      description={component ? `${component.code} — ${component.title}` : undefined}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
          <Button
            size="sm"
            loading={loading}
            disabled={!chosen?.is_available}
            variant={dryRun ? "primary" : "danger"}
            onClick={() => onRun(strategy, dryRun)}
          >
            {dryRun ? "Preview outcome" : "Run and write allocations"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Allocation strategy">
          <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            {strategies.map((item) => (
              <option key={item.key} value={item.key} disabled={!item.is_available}>
                {item.label}{!item.is_available ? " — not configured" : ""}
              </option>
            ))}
          </Select>
        </FormField>

        {chosen && (
          <Alert variant={chosen.is_available ? "info" : "warning"}>
            {chosen.description}
          </Alert>
        )}

        <Checkbox
          label="Dry run"
          description="Preview the outcome without writing any allocation records."
          checked={dryRun}
          onChange={(e) => setDryRun(e.target.checked)}
        />

        {!dryRun && (
          <Alert variant="warning" title="This writes to the database">
            Allocation records will be created, seat counts updated and students
            notified. The run is recorded in the audit log.
          </Alert>
        )}

        {result && (
          <div className="space-y-3 rounded-lg border border-line p-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              {[
                { label: "Allocated", value: result.allocated, tone: "text-success" },
                { label: "Waitlisted", value: result.waitlisted, tone: "text-warning" },
                { label: "Unallocated", value: result.unallocated, tone: "text-ink-muted" },
              ].map((stat) => (
                <div key={stat.label}>
                  <p className={`font-heading text-2xl font-semibold tabular-nums ${stat.tone}`}>
                    {stat.value}
                  </p>
                  <p className="text-2xs text-ink-subtle">{stat.label}</p>
                </div>
              ))}
            </div>

            {result.notes.length > 0 && (
              <ul className="space-y-0.5 border-t border-line pt-3 text-xs text-ink-muted">
                {result.notes.map((note, index) => <li key={index}>{note}</li>)}
              </ul>
            )}

            {result.preview.length > 0 && (
              <div className="max-h-56 overflow-y-auto border-t border-line pt-3">
                <TableWrap>
                  <THead>
                    <TH>Student</TH>
                    <TH width="18%">Course</TH>
                    <TH width="14%" align="center">Pref.</TH>
                    <TH width="18%">Result</TH>
                  </THead>
                  <TBody>
                    {result.preview.map((row, index) => (
                      <TR key={`${row.student_id}-${index}`}>
                        <TD>
                          {row.student_name}
                          <span className="tabular ml-2 text-ink-subtle">{row.roll_number}</span>
                        </TD>
                        <TD className="tabular">{row.course_code}</TD>
                        <TD align="center" className="tabular">
                          {row.preference_order_granted ?? "—"}
                        </TD>
                        <TD><StatusBadge status={row.status} /></TD>
                      </TR>
                    ))}
                  </TBody>
                </TableWrap>
              </div>
            )}

            {result.dry_run && (
              <p className="flex items-start gap-1.5 border-t border-line pt-3 text-xs text-ink-subtle">
                <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                Nothing was written. Uncheck “Dry run” to apply this outcome.
              </p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
