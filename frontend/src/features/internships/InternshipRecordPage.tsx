import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2, FileText, Mail, MapPin, Phone,
  Send, Upload, } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { DocumentGroups, DocumentProgress } from "@/components/documents/DocumentGroups";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Avatar, DetailList, FileUpload, PageHeader } from "@/components/ui/Misc";
import { ProgressStepper, type StepperStep } from "@/components/ui/Stepper";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { API_BASE, ApiError, api, tokenStore } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { EnrollmentDetail } from "@/types";

const TABS = [
  { key: "workflow", label: "Workflow" },
  { key: "organisation", label: "Organisation" },
  { key: "project", label: "Project" },
  { key: "reports", label: "Reports" },
  { key: "documents", label: "Documents" },
  { key: "evaluation", label: "Evaluation" },
];

export function InternshipRecordPage() {
  const { enrollmentId } = useParams<{ enrollmentId: string }>();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("workflow");
  const [uploadStage, setUploadStage] = useState<{ stageId: number; type: string } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportSeq, setReportSeq] = useState(1);
  const [reportSummary, setReportSummary] = useState("");
  const [reportTasks, setReportTasks] = useState("");
  const [projectOpen, setProjectOpen] = useState(false);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const queryKey = ["internship-record", enrollmentId];
  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: () => api.get<EnrollmentDetail>(`/internships/enrollments/${enrollmentId}`),
    enabled: Boolean(enrollmentId),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey });
    void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  const submitStage = useMutation({
    mutationFn: (stageId: number) =>
      api.post(`/internships/enrollments/${enrollmentId}/stages/submit`,
               { stage_id: stageId, data: {} }),
    onSuccess: () => {
      setBanner({ tone: "success", text: "Stage submitted for your mentor's review." });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not submit this stage.",
    }),
  });

  const uploadDoc = useMutation({
    mutationFn: async ({ stageId, type, selected }: {
      stageId: number; type: string; selected: File;
    }) => {
      const form = new FormData();
      form.append("file", selected);
      form.append("document_type", type);
      form.append("stage_id", String(stageId));
      const response = await fetch(`${API_BASE}/internships/enrollments/${enrollmentId}/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokenStore.access()}` },
        body: form,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new ApiError(response.status, "upload_failed",
                           body?.error?.message ?? "Upload failed.");
      }
      return response.json();
    },
    onSuccess: (_result, variables) => {
      setUploadStage(null);
      setFile(null);
      setBanner({ tone: "success", text: "Document uploaded." });
      submitStage.mutate(variables.stageId);
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Upload failed.",
    }),
  });

  const submitReport = useMutation({
    mutationFn: () =>
      api.post(`/internships/enrollments/${enrollmentId}/reports`, {
        report_type: data?.report_schedule.length ? "WEEKLY" : "FINAL",
        sequence_number: reportSeq,
        title: `Week ${reportSeq} report`,
        summary: reportSummary,
        tasks_completed: reportTasks || null,
      }),
    onSuccess: () => {
      setReportOpen(false);
      setReportSummary("");
      setReportTasks("");
      setBanner({ tone: "success", text: "Report submitted." });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not submit the report.",
    }),
  });

  const saveProject = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.put(`/internships/enrollments/${enrollmentId}/project`, body),
    onSuccess: () => {
      setProjectOpen(false);
      setBanner({ tone: "success", text: "Project details saved." });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not save project details.",
    }),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  const outstandingDocs = data.document_groups.reduce(
    (n, group) => n + group.items.filter((i) => i.is_mandatory && !i.is_satisfied).length,
    0,
  );

  const steps: StepperStep[] = data.stages.map((entry) => ({
    id: entry.stage.id,
    title: entry.stage.name,
    description: entry.stage.description,
    status: entry.status,
    isCurrent: entry.is_current,
    meta: entry.remarks ? (
      <p className="rounded bg-surface-muted px-2 py-1 text-2xs text-ink-muted">
        Mentor: {entry.remarks}
      </p>
    ) : entry.submitted_at ? (
      <p className="text-2xs text-ink-subtle">Submitted {formatDate(entry.submitted_at)}</p>
    ) : undefined,
    action:
      (entry.status === "IN_PROGRESS" || entry.status === "REJECTED") &&
      entry.stage.owner_role === "STUDENT" ? (
        entry.stage.requires_document ? (
          <Button
            size="sm" variant="secondary"
            icon={<Upload className="h-3 w-3" aria-hidden />}
            onClick={() => {
              setUploadStage({
                stageId: entry.stage.id,
                type: entry.stage.document_type ?? "OTHER",
              });
              setFile(null);
            }}
          >
            Upload {humanise(entry.stage.document_type ?? "document").toLowerCase()}
          </Button>
        ) : (
          <Button
            size="sm" variant="secondary"
            icon={<Send className="h-3 w-3" aria-hidden />}
            loading={submitStage.isPending}
            onClick={() => submitStage.mutate(entry.stage.id)}
          >
            Mark complete
          </Button>
        )
      ) : undefined,
  }));

  const nextReportSeq = Math.max(
    1,
    ...data.reports.filter((r) => r.report_type !== "FINAL").map((r) => r.sequence_number + 1),
  );

  return (
    <div>
      <PageHeader
        title={data.program_code ?? "Internship"}
        description={data.organization_name ?? "Organisation not yet recorded"}
        breadcrumbs={[
          { label: "Internships", to: "/internships" },
          { label: data.program_code ?? "Record" },
        ]}
        meta={
          <>
            <StatusBadge status={data.status} />
            <Badge tone="neutral">
              {data.progress
                ? `${data.progress.completed}/${data.progress.total} stages`
                : `${data.progress_percent}% complete`}
            </Badge>
            {data.group_name && <Badge tone="neutral">{data.group_name}</Badge>}
            {data.final_marks !== null && (
              <Badge tone="success">Final marks {data.final_marks}</Badge>
            )}
          </>
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {data.mentor && (
        <Card className="mb-5">
          <CardBody className="flex flex-wrap items-center gap-4">
            <Avatar name={data.mentor.name} src={data.mentor.avatar_url} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                Faculty mentor
              </p>
              <p className="text-md font-semibold text-ink">{data.mentor.name}</p>
              <p className="text-xs text-ink-muted">
                {data.mentor.designation}
                {data.mentor.department && ` · ${data.mentor.department}`}
              </p>
            </div>
            <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
              {data.mentor.cabin && (
                <div className="flex items-center gap-1.5 text-ink-muted">
                  <MapPin className="h-3.5 w-3.5" aria-hidden />Cabin {data.mentor.cabin}
                </div>
              )}
              {data.mentor.email && (
                <a href={`mailto:${data.mentor.email}`}
                   className="flex items-center gap-1.5 text-ink-muted hover:text-accent">
                  <Mail className="h-3.5 w-3.5" aria-hidden />{data.mentor.email}
                </a>
              )}
              {data.mentor.phone && (
                <div className="flex items-center gap-1.5 text-ink-muted">
                  <Phone className="h-3.5 w-3.5" aria-hidden />{data.mentor.phone}
                </div>
              )}
            </dl>
          </CardBody>
        </Card>
      )}

      <Tabs
        tabs={TABS.map((t) =>
          t.key === "reports" ? { ...t, count: data.reports.length }
          : t.key === "documents" ? { ...t, count: outstandingDocs || undefined }
          : t,
        )}
        active={tab}
        onChange={setTab}
        className="mb-5"
      />

      {tab === "workflow" && (
        <Card>
          <CardHeader
            title="Workflow"
            description="Complete each stage in order. Your faculty mentor reviews every submission."
          />
          <CardBody>
            {data.progress && (
              <div className="mb-5">
                <DocumentProgress progress={data.progress} />
              </div>
            )}
            <ProgressStepper steps={steps} orientation="vertical" />
          </CardBody>
        </Card>
      )}

      {tab === "organisation" && (
        <Card>
          <CardHeader title="Host organisation"
                      icon={<Building2 className="h-4 w-4 text-ink-subtle" aria-hidden />} />
          <CardBody>
            {!data.organization ? (
              <EmptyState compact title="No organisation recorded"
                          description="Your coordinator or mentor can link an organisation to this record." />
            ) : (
              <>
                <DetailList
                  items={[
                    { label: "Name", value: data.organization.name },
                    { label: "Type", value: humanise(data.organization.type) },
                    { label: "Field of work", value: data.organization.field_of_work },
                    { label: "Contact person", value: data.organization.contact_person },
                    { label: "City", value: data.organization.city },
                    { label: "District", value: data.organization.district },
                    { label: "State", value: data.organization.state },
                    { label: "Country", value: data.organization.country },
                    { label: "Phone", value: data.organization.phone },
                    { label: "Email", value: data.organization.email },
                    { label: "Address", value: data.organization.address },
                  ]}
                />
                {(data.industry_mentor_name || data.stipend !== null || data.location) && (
                  <>
                    <hr className="my-5 border-line" />
                    <h3 className="mb-3 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      Placement details
                    </h3>
                    <DetailList
                      items={[
                        { label: "Industry mentor", value: data.industry_mentor_name },
                        { label: "Designation", value: data.industry_mentor_designation },
                        { label: "Mentor email", value: data.industry_mentor_email },
                        { label: "Location", value: data.location },
                        { label: "Stipend", value: formatCurrency(data.stipend) },
                        {
                          label: "Period",
                          value: `${formatDate(data.start_date)} – ${formatDate(data.end_date)}`,
                        },
                      ]}
                    />
                    {data.industry_mentor_feedback && (
                      <div className="mt-4 rounded border border-line bg-surface-muted/40 p-3">
                        <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                          Industry mentor feedback
                        </p>
                        <p className="mt-1 text-sm text-ink-muted">
                          {data.industry_mentor_feedback}
                        </p>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </CardBody>
        </Card>
      )}

      {tab === "project" && (
        <Card>
          <CardHeader
            title="Project details"
            description="The problem you addressed and how you approached it."
            action={
              <Button size="sm" variant="secondary" onClick={() => setProjectOpen(true)}>
                {data.project ? "Edit" : "Add details"}
              </Button>
            }
          />
          <CardBody>
            {!data.project ? (
              <EmptyState compact title="No project details yet"
                          description="Record your problem statement and approach." />
            ) : (
              <div className="space-y-5">
                {data.project.title && (
                  <h3 className="font-heading text-lg font-semibold text-ink">
                    {data.project.title}
                  </h3>
                )}
                {[
                  ["Problem statement", data.project.problem_statement],
                  ["Approach", data.project.approach],
                  ["Outcomes", data.project.outcomes],
                  ["Technologies", data.project.technologies],
                  ["Beneficiaries", data.project.beneficiaries],
                ].map(([label, value]) =>
                  value ? (
                    <div key={label as string}>
                      <h4 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                        {label}
                      </h4>
                      <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-ink-muted">
                        {value as string}
                      </p>
                    </div>
                  ) : null,
                )}
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {tab === "reports" && (
        <Card>
          <CardHeader
            title="Periodic reports"
            description={
              data.report_schedule.length
                ? `${data.reports.filter((r) => r.report_type !== "FINAL").length} of ${data.report_schedule.length} expected reports submitted`
                : "This programme does not require periodic reports."
            }
            icon={<FileText className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              data.report_schedule.length > 0 && (
                <Button size="sm" onClick={() => { setReportSeq(nextReportSeq); setReportOpen(true); }}>
                  Submit report
                </Button>
              )
            }
          />
          {data.reports.length === 0 ? (
            <EmptyState compact title="No reports submitted yet"
                        description="Submit each periodic report before its window closes." />
          ) : (
            <TableWrap>
              <THead>
                <TH width="8%">#</TH>
                <TH width="14%">Type</TH>
                <TH>Summary</TH>
                <TH width="16%">Period</TH>
                <TH width="14%">Status</TH>
              </THead>
              <TBody>
                {data.reports.map((report) => (
                  <TR key={report.id}>
                    <TD className="tabular">{report.sequence_number}</TD>
                    <TD>{humanise(report.report_type)}</TD>
                    <TD>
                      <p className="line-clamp-2 text-ink-muted">{report.summary}</p>
                      {report.feedback && (
                        <p className="mt-1 text-2xs text-success">Mentor: {report.feedback}</p>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap text-xs text-ink-subtle">
                      {formatDate(report.period_start)} – {formatDate(report.period_end)}
                    </TD>
                    <TD><StatusBadge status={report.status} /></TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
          )}
        </Card>
      )}

      {tab === "documents" && (
        <Card>
          <CardHeader
            title="Documents"
            description="Everything this programme expects from you, including what is still outstanding."
          />
          <CardBody>
            <DocumentGroups
              groups={data.document_groups}
              enrollmentId={Number(enrollmentId)}
              onUpload={(item) => {
                if (item.kind === "report") {
                  // A report needs a written summary, so it is composed on the
                  // Reports tab rather than through a bare file picker.
                  setReportSeq(item.week_number ?? 1);
                  setReportOpen(true);
                  return;
                }
                if (item.stage_id === null) return;
                setUploadStage({
                  stageId: item.stage_id,
                  type: item.document_type ?? "OTHER",
                });
              }}
            />
          </CardBody>
        </Card>
      )}

      {tab === "evaluation" && (
        <Card>
          <CardHeader
            title="Evaluation"
            description="Marks recorded by your faculty mentor against the programme rubric."
          />
          <CardBody>
            {data.evaluations.length === 0 ? (
              <>
                <EmptyState
                  compact
                  title="Not evaluated yet"
                  description="Your mentor records marks once all stages are approved."
                />
                {data.criteria.length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      You will be assessed on
                    </h4>
                    <ul className="space-y-1.5">
                      {data.criteria.map((criterion) => (
                        <li key={criterion.id}
                            className="flex items-center justify-between gap-3 rounded border border-line px-3 py-2">
                          <span className="min-w-0">
                            <span className="block text-sm text-ink">{criterion.name}</span>
                            {criterion.description && (
                              <span className="block text-2xs text-ink-subtle">
                                {criterion.description}
                              </span>
                            )}
                          </span>
                          <span className="shrink-0 text-xs font-medium tabular-nums text-ink-muted">
                            {criterion.max_marks} marks
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              data.evaluations.map((evaluation) => (
                <div key={evaluation.id} className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-line bg-surface-muted/40 p-3.5">
                    <div>
                      <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                        {humanise(evaluation.evaluator_role)}
                      </p>
                      <p className="text-sm text-ink">{evaluation.evaluator_name ?? "—"}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-heading text-2xl font-semibold tabular-nums text-ink">
                        {evaluation.total_marks ?? "—"}
                        <span className="text-sm font-normal text-ink-subtle">
                          {" / "}{evaluation.max_marks ?? "—"}
                        </span>
                      </p>
                      <StatusBadge status={evaluation.status} />
                    </div>
                  </div>

                  <TableWrap>
                    <THead>
                      <TH>Criterion</TH>
                      <TH width="14%" align="right">Marks</TH>
                      <TH width="14%" align="right">Max</TH>
                    </THead>
                    <TBody>
                      {evaluation.scores.map((score) => (
                        <TR key={score.id}>
                          <TD>
                            {score.criteria_name}
                            {score.comments && (
                              <p className="mt-0.5 text-2xs text-ink-subtle">{score.comments}</p>
                            )}
                          </TD>
                          <TD align="right" className="tabular font-medium">
                            {score.is_absent ? "Absent" : score.marks ?? "—"}
                          </TD>
                          <TD align="right" className="tabular text-ink-subtle">
                            {score.max_marks}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </TableWrap>

                  {evaluation.comments && (
                    <div className="rounded border border-line p-3.5">
                      <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                        Mentor comments
                      </p>
                      <p className="mt-1 text-sm text-ink-muted">{evaluation.comments}</p>
                    </div>
                  )}

                  <p className="text-xs text-ink-subtle">
                    A letter grade is not shown — institutional grade boundaries are
                    configured by the department in a later phase.
                  </p>
                </div>
              ))
            )}
          </CardBody>
        </Card>
      )}

      {/* Upload stage document */}
      <Modal
        open={Boolean(uploadStage)}
        onClose={() => { setUploadStage(null); setFile(null); }}
        title="Upload document"
        description={uploadStage ? humanise(uploadStage.type) : undefined}
        size="sm"
        footer={
          <>
            <Button variant="secondary" size="sm"
                    onClick={() => { setUploadStage(null); setFile(null); }}>
              Cancel
            </Button>
            <Button
              size="sm" disabled={!file} loading={uploadDoc.isPending}
              onClick={() => file && uploadStage &&
                uploadDoc.mutate({ ...uploadStage, selected: file })}
            >
              Upload &amp; submit stage
            </Button>
          </>
        }
      >
        <FileUpload onSelect={setFile} selectedName={file?.name} />
      </Modal>

      {/* Submit report */}
      <Modal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        title="Submit report"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setReportOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={reportSummary.trim().length < 10}
              loading={submitReport.isPending}
              onClick={() => submitReport.mutate()}
            >
              Submit
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <FormField label="Report number" required>
            <Input
              type="number" min={1} max={60} value={reportSeq}
              onChange={(e) => setReportSeq(Number(e.target.value))}
            />
          </FormField>
          <FormField
            label="Summary" required
            hint="At least 10 characters. What did you work on during this period?"
          >
            <Textarea
              value={reportSummary}
              onChange={(e) => setReportSummary(e.target.value)}
              rows={4}
              placeholder="This period I…"
              data-autofocus
            />
          </FormField>
          <FormField label="Tasks completed">
            <Textarea value={reportTasks} onChange={(e) => setReportTasks(e.target.value)}
                      rows={3} />
          </FormField>
        </div>
      </Modal>

      {/* Project details */}
      <ProjectModal
        open={projectOpen}
        onClose={() => setProjectOpen(false)}
        initial={data.project}
        loading={saveProject.isPending}
        onSave={(body) => saveProject.mutate(body)}
      />
    </div>
  );
}

function ProjectModal({
  open, onClose, initial, onSave, loading,
}: {
  open: boolean; onClose: () => void;
  initial: EnrollmentDetail["project"];
  onSave: (body: Record<string, unknown>) => void; loading: boolean;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [problem, setProblem] = useState(initial?.problem_statement ?? "");
  const [approach, setApproach] = useState(initial?.approach ?? "");
  const [outcomes, setOutcomes] = useState(initial?.outcomes ?? "");
  const [technologies, setTechnologies] = useState(initial?.technologies ?? "");

  return (
    <Modal
      open={open} onClose={onClose} title="Project details" size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm" loading={loading}
            onClick={() => onSave({
              title: title || null, problem_statement: problem || null,
              approach: approach || null, outcomes: outcomes || null,
              technologies: technologies || null,
            })}
          >
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Project title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} data-autofocus />
        </FormField>
        <FormField label="Problem statement"
                   hint="What problem does the organisation face?">
          <Textarea value={problem} onChange={(e) => setProblem(e.target.value)} rows={4} />
        </FormField>
        <FormField label="Approach to solving the problem">
          <Textarea value={approach} onChange={(e) => setApproach(e.target.value)} rows={4} />
        </FormField>
        <FormField label="Outcomes">
          <Textarea value={outcomes} onChange={(e) => setOutcomes(e.target.value)} rows={3} />
        </FormField>
        <FormField label="Technologies used">
          <Input value={technologies} onChange={(e) => setTechnologies(e.target.value)}
                 placeholder="Python, PostgreSQL, …" />
        </FormField>
      </div>
    </Modal>
  );
}
