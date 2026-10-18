import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { Tabs } from "@/components/ui/Tabs";
import { MinorFeesTab, MinorGradebookTab } from "./MinorRecordsTab";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api, qs } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { roman } from "@/lib/utils";
import { MinorAllocationTab } from "./MinorAllocationTab";
import type { MinorApplication, MinorProgram } from "@/types";

export function MinorAdminPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("applications");
  const [status, setStatus] = useState("SUBMITTED");
  const [decide, setDecide] = useState<MinorApplication | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const programs = useQuery({
    queryKey: ["minor-programs"],
    queryFn: () => api.get<MinorProgram[]>("/minors"),
  });

  const applications = useQuery({
    queryKey: ["minor-applications", status],
    queryFn: () =>
      api.get<MinorApplication[]>(`/minors/applications${qs({ status: status || undefined })}`),
  });

  return (
    <div>
      <PageHeader
        title="Minor specialisation"
        description="Applications and seat configuration. Ranking is a departmental decision — the portal records it and keeps the audit trail."
        breadcrumbs={[{ label: "Administration" }, { label: "Minor Applications" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <Tabs
        tabs={[
          { key: "applications", label: "Applications", count: applications.data?.length },
          { key: "allocation", label: "Allocation round" },
          { key: "programs", label: "Minor programmes", count: programs.data?.length },
          { key: "results", label: "Results" },
          { key: "fees", label: "Fees" },
        ]}
        active={tab}
        onChange={setTab}
        className="mb-5"
      />

      {tab === "results" && <MinorGradebookTab programs={programs.data ?? []} />}
      {tab === "fees" && <MinorFeesTab programs={programs.data ?? []} />}

      {tab === "allocation" && (
        <MinorAllocationTab programs={programs.data ?? []} />
      )}

      {tab === "applications" && (
        <Card>
          <CardHeader
            title="Applications"
            icon={<Sparkles className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              <Select value={status} onChange={(e) => setStatus(e.target.value)}
                      aria-label="Filter by status" className="w-full sm:w-48">
                <option value="">All statuses</option>
                {["SUBMITTED", "UNDER_REVIEW", "ALLOCATED", "REJECTED", "WITHDRAWN"]
                  .map((value) => (
                    <option key={value} value={value}>
                      {value.replace(/_/g, " ").toLowerCase()}
                    </option>
                  ))}
              </Select>
            }
          />
          {applications.isLoading ? (
            <LoadingState rows={4} />
          ) : applications.error ? (
            <ErrorState onRetry={() => applications.refetch()} compact />
          ) : !applications.data?.length ? (
            <EmptyState title="No applications in this state"
                        icon={<Sparkles className="h-5 w-5" aria-hidden />} />
          ) : (
            <TableWrap>
              <THead>
                <TH width="18%">Student</TH>
                <TH width="11%">Roll no.</TH>
                <TH width="8%" align="center">Pref.</TH>
                <TH>Minor</TH>
                <TH width="8%" align="right">CPI</TH>
                <TH width="9%" align="right">Backlogs</TH>
                <TH width="12%">Status</TH>
                <TH width="10%" align="right">Decide</TH>
              </THead>
              <TBody>
                {applications.data.length === 0 ? (
                  <TableEmpty colSpan={8}>Nothing to review.</TableEmpty>
                ) : (
                  applications.data.map((application) => (
                    <TR key={application.id}>
                      <TD className="font-medium">{application.student_name}</TD>
                      <TD className="tabular">{application.roll_number}</TD>
                      <TD align="center">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-soft text-2xs font-semibold text-brand">
                          {application.preference_order}
                        </span>
                      </TD>
                      <TD className="text-ink-muted">
                        {application.minor_name}
                        <span className="block text-2xs text-ink-subtle">
                          {application.minor_department}
                        </span>
                      </TD>
                      <TD align="right" className="tabular font-medium">
                        {application.cpi_at_application?.toFixed(2) ?? "—"}
                      </TD>
                      <TD align="right" className="tabular">
                        {application.backlogs_at_application ?? "—"}
                      </TD>
                      <TD><StatusBadge status={application.status} /></TD>
                      <TD align="right">
                        <Button
                          size="sm" variant="secondary"
                          disabled={application.status !== "SUBMITTED"}
                          onClick={() => setDecide(application)}
                        >
                          Decide
                        </Button>
                      </TD>
                    </TR>
                  ))
                )}
              </TBody>
            </TableWrap>
          )}
        </Card>
      )}

      {tab === "programs" && (
        programs.isLoading ? (
          <LoadingState rows={4} />
        ) : !programs.data?.length ? (
          <Card><EmptyState title="No minor programmes configured" /></Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {programs.data.map((program) => (
              <Card key={program.id}>
                <CardBody>
                  <div className="flex items-start justify-between gap-2">
                    <Badge tone="brand" className="font-mono">{program.code}</Badge>
                    {!program.is_active && <Badge tone="neutral">Inactive</Badge>}
                  </div>
                  <h3 className="mt-2.5 text-md font-semibold leading-snug text-ink">
                    {program.name}
                  </h3>
                  <p className="text-xs text-ink-muted">{program.department_name}</p>

                  <ProgressBar
                    className="mt-4"
                    label="Seats filled"
                    value={program.seats_filled}
                    max={program.capacity}
                    tone={program.seats_available === 0 ? "warning" : "accent"}
                  />

                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line pt-3 text-xs">
                    {[
                      ["Credits", program.total_credits],
                      ["Opens from", `Sem ${roman(program.eligible_from_semester)}`],
                      ["Min CPI", program.min_cpi ?? "—"],
                      ["Max backlogs", program.max_backlogs ?? "—"],
                      ["Strategy", program.allocation_strategy],
                      ["Closes", formatDate(program.application_closes_at)],
                    ].map(([label, value]) => (
                      <div key={label as string}>
                        <dt className="text-ink-subtle">{label}</dt>
                        <dd className="mt-0.5 text-ink">{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </CardBody>
              </Card>
            ))}
          </div>
        )
      )}

      {decide && (
        <DecideModal
          application={decide}
          onClose={() => setDecide(null)}
          onDone={(text) => {
            setDecide(null);
            setBanner({ tone: "success", text });
            void queryClient.invalidateQueries({ queryKey: ["minor-applications"] });
            void queryClient.invalidateQueries({ queryKey: ["minor-programs"] });
            void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          }}
        />
      )}
    </div>
  );
}

function DecideModal({
  application, onClose, onDone,
}: {
  application: MinorApplication; onClose: () => void; onDone: (text: string) => void;
}) {
  const [status, setStatus] = useState("ALLOCATED");
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: () =>
      api.post(`/minors/applications/${application.id}/decide`, {
        status, remarks: remarks || null,
      }),
    onSuccess: () =>
      onDone(status === "ALLOCATED"
        ? "Seat allocated and the student notified."
        : "Decision recorded."),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not record the decision."),
  });

  return (
    <Modal
      open onClose={onClose} title="Decide application"
      description={`${application.student_name} · ${application.roll_number}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={decide.isPending} onClick={() => decide.mutate()}
                  variant={status === "REJECTED" ? "danger" : "primary"}>
            Record decision
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <DetailList
          items={[
            { label: "Minor", value: application.minor_name },
            { label: "Offering department", value: application.minor_department },
            { label: "Preference", value: `#${application.preference_order}` },
            { label: "CPI at application", value: application.cpi_at_application ?? "—" },
            { label: "Backlogs", value: application.backlogs_at_application ?? "—" },
            {
              label: "Semester",
              value: application.semester_at_application
                ? roman(application.semester_at_application) : "—",
            },
            { label: "Submitted", value: formatDate(application.submitted_at) },
          ]}
        />

        {application.motivation && (
          <div>
            <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Student's motivation
            </h3>
            <p className="mt-1 text-sm text-ink-muted">{application.motivation}</p>
          </div>
        )}

        <FormField label="Decision">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ALLOCATED">Allocate a seat</option>
            <option value="UNDER_REVIEW">Mark under review</option>
            <option value="REJECTED">Reject</option>
          </Select>
        </FormField>

        <FormField label="Remarks" hint="Shown to the student with the decision.">
          <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={3} />
        </FormField>

        <Alert variant="info">
          Allocating a seat closes this student's other pending preferences and
          decrements the minor's remaining capacity. The action is audit-logged.
        </Alert>
      </div>
    </Modal>
  );
}
