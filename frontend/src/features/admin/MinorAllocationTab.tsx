import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListOrdered, Play, Scale } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { MinorAllocationPreview, MinorAllocationResult, MinorProgram } from "@/types";

/**
 * Minor Specialisation is the only module permitted to rank on CPI, and the
 * ranking rule is the department's, not this application's — so the screen
 * always states which criteria produced the order shown.
 */
export function MinorAllocationTab({ programs }: { programs: MinorProgram[] }) {
  const queryClient = useQueryClient();
  const [programId, setProgramId] = useState<number | null>(programs[0]?.id ?? null);
  const [confirming, setConfirming] = useState(false);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const preview = useQuery({
    queryKey: ["minor-allocation-preview", programId],
    queryFn: () =>
      api.get<MinorAllocationPreview>(`/minors/${programId}/allocation/preview`),
    enabled: programId !== null,
    retry: false,
  });

  const run = useMutation({
    mutationFn: () =>
      api.post<MinorAllocationResult>(`/minors/${programId}/allocation/run`),
    onSuccess: (result) => {
      setConfirming(false);
      setBanner({
        tone: "success",
        text: `${result.allocated} seat(s) allocated, ${result.waitlisted} waitlisted. `
            + "Every applicant has been notified.",
      });
      queryClient.invalidateQueries({ queryKey: ["minor-allocation-preview"] });
      queryClient.invalidateQueries({ queryKey: ["minor-applications"] });
      queryClient.invalidateQueries({ queryKey: ["minor-programs"] });
    },
    onError: (err) => {
      setConfirming(false);
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "The round could not be run.",
      });
    },
  });

  const data = preview.data;
  const policyMissing =
    preview.error instanceof ApiError && preview.error.status === 409;

  return (
    <div className="space-y-5">
      {banner && (
        <Alert variant={banner.tone} onDismiss={() => setBanner(null)}>{banner.text}</Alert>
      )}

      <Card>
        <CardHeader
          title="Allocation round"
          description="Rank applicants against the department's published policy, then commit seats."
          action={
            <div className="flex flex-wrap items-end gap-2">
              <FormField label="Minor programme" className="min-w-[16rem]">
                <Select
                  value={programId ?? ""}
                  onChange={(e) => setProgramId(Number(e.target.value) || null)}
                >
                  {programs.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.seats_filled}/{p.capacity} seats
                    </option>
                  ))}
                </Select>
              </FormField>
              <Button
                icon={<Play className="h-3.5 w-3.5" aria-hidden />}
                disabled={!data || data.would_allocate === 0}
                onClick={() => setConfirming(true)}
              >
                Run round
              </Button>
            </div>
          }
        />

        <CardBody>
          {programs.length === 0 ? (
            <EmptyState compact title="No minor programmes configured" />
          ) : preview.isLoading ? (
            <LoadingState label="Ranking applicants…" />
          ) : policyMissing ? (
            <Alert variant="warning">
              <p className="font-medium">No ranking policy is configured for this minor.</p>
              <p className="mt-1">
                CampusHub ships no default formula — the department states its own
                criteria (for example CPI, then fewest backlogs, then preference
                order) before a round can be run.
              </p>
            </Alert>
          ) : preview.error ? (
            <ErrorState
              message={preview.error instanceof ApiError
                ? preview.error.message
                : "The ranking could not be loaded."}
              onRetry={() => void preview.refetch()}
            />
          ) : data ? (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                <span className="flex items-center gap-1.5 text-ink-muted">
                  <Scale className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
                  Ranked by
                </span>
                <ol className="flex min-w-0 flex-wrap items-center gap-1.5">
                  {data.criteria.map((criterion, index) => (
                    <li key={criterion.field} className="flex items-center gap-1.5">
                      {index > 0 && <span className="text-ink-subtle" aria-hidden>→</span>}
                      <Badge tone="accent">
                        {criterion.label ?? criterion.field}
                        {criterion.direction === "desc" ? " ↓" : " ↑"}
                      </Badge>
                    </li>
                  ))}
                </ol>
              </div>

              <dl className="mb-4 grid gap-3 sm:grid-cols-4">
                {[
                  ["Applicants", data.applicants],
                  ["Seats available", data.seats_available],
                  ["Would allocate", data.would_allocate],
                  ["Would waitlist", data.applicants - data.would_allocate],
                ].map(([label, value]) => (
                  <div key={label as string}
                       className="min-w-0 rounded-md border border-line bg-surface-sunken p-3">
                    <dt className="text-2xs uppercase tracking-wide text-ink-subtle">
                      {label}
                    </dt>
                    <dd className="mt-0.5 font-heading text-lg font-semibold tabular-nums text-ink">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>

              <TableWrap>
                <THead>
                  <TH width="6%">Rank</TH>
                  <TH>Student</TH>
                  <TH width="12%">Department</TH>
                  <TH width="8%">CPI</TH>
                  <TH width="10%">Backlogs</TH>
                  <TH width="10%">Preference</TH>
                  <TH width="16%">Outcome</TH>
                </THead>
                <TBody>
                  {data.ranking.length === 0 ? (
                    <TableEmpty colSpan={7}>No submitted applications to rank.</TableEmpty>
                  ) : (
                    data.ranking.map((row) => (
                      <TR
                        key={row.application_id}
                        className={row.within_capacity ? undefined : "opacity-70"}
                      >
                        <TD className="tabular font-medium">{row.rank}</TD>
                        <TD>
                          <p className="font-medium text-ink">{row.student_name}</p>
                          <p className="text-2xs text-ink-subtle">
                            {row.roll_number}
                            {row.submitted_at && ` · applied ${formatDateTime(row.submitted_at)}`}
                          </p>
                        </TD>
                        <TD className="text-ink-muted">{row.department ?? "—"}</TD>
                        <TD className="tabular">{row.cpi ?? "—"}</TD>
                        <TD className="tabular">{row.backlog_count ?? "—"}</TD>
                        <TD className="tabular">{row.preference_order}</TD>
                        <TD>
                          {row.within_capacity ? (
                            <Badge tone="success">Seat</Badge>
                          ) : (
                            <Badge tone="warning">{row.note ?? "Waitlist"}</Badge>
                          )}
                        </TD>
                      </TR>
                    ))
                  )}
                </TBody>
              </TableWrap>
              <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-subtle">
                <ListOrdered className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="min-w-0">
                  This is a preview — nothing is written until you run the round.
                  CPI is used here because it is the Minor Specialisation policy;
                  elective allocation never considers it.
                </span>
              </p>
            </>
          ) : null}
        </CardBody>
      </Card>

      {confirming && data && (
        <Modal
          open onClose={() => setConfirming(false)} size="sm"
          title="Run this allocation round?"
          description={`${data.would_allocate} of ${data.applicants} applicants will `
            + `receive a seat in ${data.program_name}. The rest are waitlisted. `
            + "Every applicant is notified."}
          footer={
            <>
              <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
              <Button loading={run.isPending} onClick={() => run.mutate()}>
                Allocate {data.would_allocate} seat(s)
              </Button>
            </>
          }
        >
          <Alert variant="warning">
            Seats and application statuses are written immediately. Individual
            decisions can still be changed afterwards from the Applications tab.
          </Alert>
        </Modal>
      )}
    </div>
  );
}
