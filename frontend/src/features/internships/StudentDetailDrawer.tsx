import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Save, UserCog, X } from "lucide-react";
import { useEffect, useState } from "react";
import { DocumentGroups, DocumentProgress } from "@/components/documents/DocumentGroups";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Checkbox, FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Avatar, DetailList } from "@/components/ui/Misc";
import { ProgressBar, ProgressStepper, type StepperStep } from "@/components/ui/Stepper";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { humanise, roman } from "@/lib/utils";
import type { EnrollmentDetail, MentorCapacity } from "@/types";

const TABS = [
  { key: "personal", label: "Personal" },
  { key: "organisation", label: "NGO / Organisation" },
  { key: "project", label: "Project" },
  { key: "proof", label: "Proof of Work" },
  { key: "evaluation", label: "Evaluation" },
];

export function StudentDetailDrawer({
  enrollmentId, onClose, canOverrideMentor,
}: { enrollmentId: number; onClose: () => void; canOverrideMentor?: boolean }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("personal");
  const [scores, setScores] = useState<Record<number, string>>({});
  const [absent, setAbsent] = useState(false);
  const [comments, setComments] = useState("");
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [mentorOpen, setMentorOpen] = useState(false);

  const queryKey = ["internship-record", String(enrollmentId)];
  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: () => api.get<EnrollmentDetail>(`/internships/enrollments/${enrollmentId}`),
  });

  // Seed the rubric form from any evaluation already recorded.
  useEffect(() => {
    if (!data) return;
    const existing = data.evaluations[0];
    if (existing) {
      const next: Record<number, string> = {};
      for (const score of existing.scores) {
        next[score.criteria_id] = score.marks !== null ? String(score.marks) : "";
      }
      setScores(next);
      setAbsent(existing.is_absent);
      setComments(existing.comments ?? "");
    }
  }, [data]);

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey });
    void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  const reviewStage = useMutation({
    mutationFn: ({ stageId, approve, remarks }: {
      stageId: number; approve: boolean; remarks?: string;
    }) =>
      api.post(`/internships/enrollments/${enrollmentId}/stages/review`, {
        stage_id: stageId, approve, remarks: remarks ?? null,
      }),
    onSuccess: (_r, variables) => {
      setBanner({
        tone: "success",
        text: variables.approve ? "Stage approved." : "Revision requested.",
      });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not update the stage.",
    }),
  });

  const saveEvaluation = useMutation({
    mutationFn: (finalise: boolean) =>
      api.post(`/internships/enrollments/${enrollmentId}/evaluation`, {
        scores: (data?.criteria ?? []).map((criterion) => ({
          criteria_id: criterion.id,
          marks: absent ? null : scores[criterion.id] === "" || scores[criterion.id] === undefined
            ? null : Number(scores[criterion.id]),
          is_absent: absent,
          comments: null,
        })),
        is_absent: absent,
        comments: comments || null,
        finalise,
      }),
    onSuccess: (_r, finalise) => {
      setBanner({
        tone: "success",
        text: finalise ? "Evaluation finalised and published to the student."
                       : "Evaluation saved as a draft.",
      });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not save the evaluation.",
    }),
  });

  const total = (data?.criteria ?? []).reduce((sum, criterion) => {
    const value = Number(scores[criterion.id]);
    return sum + (Number.isFinite(value) ? value * criterion.weight : 0);
  }, 0);
  const maxTotal = (data?.criteria ?? []).reduce(
    (sum, criterion) => sum + criterion.max_marks * criterion.weight, 0,
  );

  const steps: StepperStep[] = (data?.stages ?? []).map((entry) => ({
    id: entry.stage.id,
    title: entry.stage.name,
    status: entry.status,
    isCurrent: entry.is_current,
    meta: entry.submitted_at ? (
      <p className="text-2xs text-ink-subtle">Submitted {formatDate(entry.submitted_at)}</p>
    ) : undefined,
    action: entry.status === "SUBMITTED" ? (
      <div className="flex gap-1.5">
        <Button
          size="sm" variant="secondary" loading={reviewStage.isPending}
          icon={<Check className="h-3 w-3 text-success" aria-hidden />}
          onClick={() => reviewStage.mutate({ stageId: entry.stage.id, approve: true })}
        >
          Approve
        </Button>
        <Button
          size="sm" variant="ghost" className="text-danger"
          icon={<X className="h-3 w-3" aria-hidden />}
          onClick={() =>
            reviewStage.mutate({
              stageId: entry.stage.id,
              approve: false,
              remarks: "Please revise and resubmit.",
            })
          }
        >
          Request revision
        </Button>
      </div>
    ) : undefined,
  }));

  const outstandingDocs = (data?.document_groups ?? []).reduce(
    (n, group) =>
      n + group.items.filter((i) => i.is_mandatory && !i.is_satisfied).length,
    0,
  );

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={data?.student_name ?? "Student"}
      description={
        data ? `${data.roll_number} · ${data.program_code} · ${data.organization_name ?? "No organisation"}` : undefined
      }
      footer={
        tab === "evaluation" && data && data.criteria.length > 0 ? (
          <>
            <span className="mr-auto text-sm text-ink-muted">
              Total:{" "}
              <span className="font-heading text-md font-semibold tabular-nums text-ink">
                {absent ? 0 : total.toFixed(1)} / {maxTotal.toFixed(0)}
              </span>
            </span>
            <Button
              variant="secondary" size="sm" loading={saveEvaluation.isPending}
              onClick={() => saveEvaluation.mutate(false)}
              icon={<Save className="h-3.5 w-3.5" aria-hidden />}
            >
              Save draft
            </Button>
            <Button
              size="sm" loading={saveEvaluation.isPending}
              onClick={() => saveEvaluation.mutate(true)}
            >
              Finalise evaluation
            </Button>
          </>
        ) : (
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
        )
      }
    >
      {isLoading && <LoadingState rows={4} />}
      {error && <ErrorState onRetry={() => refetch()} compact />}

      {data && (
        <div>
          {banner && (
            <Alert
              variant={banner.tone === "success" ? "success" : "danger"}
              className="mb-4"
              onDismiss={() => setBanner(null)}
            >
              {banner.text}
            </Alert>
          )}

          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface-muted/40 p-3.5">
            <Avatar name={data.student_name} src={data.avatar_url} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-md font-semibold text-ink">{data.student_name}</p>
              <p className="text-xs text-ink-muted">
                <span className="tabular">{data.roll_number}</span>
                {data.semester && ` · Semester ${roman(data.semester)}`}
                {data.division && ` · Division ${data.division}`}
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <StatusBadge status={data.status} />
                {data.group_name && <Badge tone="neutral">{data.group_name}</Badge>}
                {data.mentor_name && <Badge tone="brand">{data.mentor_name}</Badge>}
              </div>
            </div>
            <div className="w-full sm:w-44">
              <ProgressBar
                value={data.progress_percent}
                label="Workflow"
                tone={data.progress_percent === 100 ? "success" : "accent"}
              />
            </div>
            {canOverrideMentor && (
              <Button
                variant="secondary" size="sm"
                icon={<UserCog className="h-3.5 w-3.5" aria-hidden />}
                onClick={() => setMentorOpen(true)}
              >
                Change mentor
              </Button>
            )}
          </div>

          <Tabs
            tabs={TABS.map((t) =>
              // Outstanding required items, so the tab itself flags missing work.
              t.key === "proof" ? { ...t, count: outstandingDocs || undefined } : t,
            )}
            active={tab}
            onChange={setTab}
            size="sm"
            className="mb-4"
          />

          {tab === "personal" && (
            <div className="space-y-5">
              <DetailList
                items={[
                  { label: "Full name", value: data.student_name },
                  { label: "Roll number", value: <span className="tabular">{data.roll_number}</span> },
                  { label: "Department", value: data.department_code },
                  { label: "Division", value: data.division },
                  { label: "Semester", value: roman(data.semester) },
                  { label: "Group", value: data.group_name },
                  { label: "Email", value: data.email },
                  { label: "Phone", value: data.phone },
                  { label: "Guardian", value: data.guardian_name },
                  { label: "Guardian phone", value: data.guardian_phone },
                ]}
              />
              <div>
                <h3 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Workflow progress
                </h3>
                <div className="rounded-lg border border-line p-4">
                  <ProgressStepper steps={steps} orientation="vertical" />
                </div>
              </div>
            </div>
          )}

          {tab === "organisation" && (
            !data.organization ? (
              <EmptyState compact title="No organisation recorded" />
            ) : (
              <div className="space-y-5">
                <DetailList
                  items={[
                    { label: "Organisation", value: data.organization.name },
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
                {(data.industry_mentor_name || data.stipend !== null) && (
                  <>
                    <hr className="border-line" />
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
                      <div className="rounded border border-line bg-surface-muted/40 p-3">
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
              </div>
            )
          )}

          {tab === "project" && (
            !data.project ? (
              <EmptyState compact title="The student has not filled in project details yet" />
            ) : (
              <div className="space-y-5">
                {data.project.title && (
                  <h3 className="font-heading text-lg font-semibold text-ink">
                    {data.project.title}
                  </h3>
                )}
                {[
                  ["Problem statement", data.project.problem_statement],
                  ["Approach of solving the problem", data.project.approach],
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
                {/* extra is a free-form JSON bag so new project fields need no migration */}
                {Object.entries(data.project.extra ?? {}).map(([key, value]) => (
                  <div key={key}>
                    <h4 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      {humanise(key)}
                    </h4>
                    <p className="mt-1 text-sm text-ink-muted">{String(value)}</p>
                  </div>
                ))}
              </div>
            )
          )}

          {tab === "proof" && (
            <div className="space-y-5">
              {data.progress && <DocumentProgress progress={data.progress} />}
              <DocumentGroups
                groups={data.document_groups}
                enrollmentId={enrollmentId}
                canReview
              />
            </div>
          )}

          {tab === "evaluation" && (
            <div className="space-y-4">
              {data.criteria.length === 0 ? (
                <EmptyState compact title="No rubric configured"
                            description="An administrator defines the evaluation criteria for this programme." />
              ) : (
                <>
                  <p className="text-sm text-ink-muted">
                    Criteria below are configured for{" "}
                    <strong>{data.program_code}</strong> — they are stored as data, not
                    fixed in the interface.
                  </p>

                  <Checkbox
                    label="Student was absent"
                    description="Records zero against every criterion."
                    checked={absent}
                    onChange={(e) => setAbsent(e.target.checked)}
                  />

                  <div className="space-y-2.5">
                    {data.criteria.map((criterion) => (
                      <div
                        key={criterion.id}
                        className="flex flex-wrap items-center gap-3 rounded-md border border-line p-3"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-ink">{criterion.name}</p>
                          {criterion.description && (
                            <p className="text-2xs text-ink-subtle">{criterion.description}</p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Input
                            type="number"
                            min={0}
                            max={criterion.max_marks}
                            step="0.5"
                            disabled={absent}
                            value={scores[criterion.id] ?? ""}
                            onChange={(e) =>
                              setScores((current) => ({
                                ...current, [criterion.id]: e.target.value,
                              }))
                            }
                            aria-label={`Marks for ${criterion.name}`}
                            className="w-20 text-right"
                          />
                          <span className="w-14 shrink-0 text-xs text-ink-subtle">
                            / {criterion.max_marks}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <FormField label="Overall comments">
                    <Textarea
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                      rows={3}
                      placeholder="Feedback the student will see alongside their marks…"
                    />
                  </FormField>

                  <Alert variant="info">
                    Marks are recorded and totalled by weight. A letter grade is not
                    derived automatically — institutional grade boundaries are applied
                    in a later phase.
                  </Alert>

                  {data.evaluations[0]?.status === "FINALISED" && (
                    <Alert variant="warning">
                      This evaluation has been finalised. Further edits are blocked by
                      the server.
                    </Alert>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {mentorOpen && data && (
        <MentorOverrideModal
          enrollmentId={enrollmentId}
          programId={data.program_id}
          currentMentorId={data.mentor_faculty_id}
          onClose={() => setMentorOpen(false)}
          onDone={() => { setMentorOpen(false); invalidate(); }}
        />
      )}
    </Modal>
  );
}

function MentorOverrideModal({
  enrollmentId, programId, currentMentorId, onClose, onDone,
}: {
  enrollmentId: number; programId: number; currentMentorId: number | null;
  onClose: () => void; onDone: () => void;
}) {
  const [facultyId, setFacultyId] = useState(String(currentMentorId ?? ""));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mentors = useQuery({
    queryKey: ["mentor-capacity", programId],
    queryFn: () => api.get<MentorCapacity[]>(`/internships/programs/${programId}/mentors-capacity`),
  });

  const override = useMutation({
    mutationFn: () =>
      api.post(`/internships/enrollments/${enrollmentId}/mentor`, {
        mentor_faculty_id: facultyId ? Number(facultyId) : null,
        reason: reason.trim() || "Coordinator assigned mentor (max 10 limit enforced)",
      }),
    onSuccess: onDone,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not change the mentor."),
  });

  return (
    <Modal
      open onClose={onClose} size="sm" title="Change faculty mentor"
      description="1 mentor has a maximum of 10 students under university academic policy."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm" loading={override.isPending}
            onClick={() => override.mutate()}
          >
            Save change
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <div className="rounded border border-primary/20 bg-primary/5 p-2.5 text-xs text-primary">
          <strong>Academic Rule:</strong> Each faculty mentor can supervise a maximum of 10 students. Faculty who already have 10 students are disabled.
        </div>

        <FormField label="Faculty mentor (Max 10 students)">
          <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}>
            <option value="">Unassigned</option>
            {(mentors.data ?? []).map((member) => {
              const isCurrent = member.faculty_id === currentMentorId;
              const isFull = member.assigned_count >= 10 && !isCurrent;
              return (
                <option key={member.faculty_id} value={member.faculty_id} disabled={isFull}>
                  {member.name} — {member.department_code ?? "Faculty"} ({member.assigned_count}/10 mentees{isFull ? " - FULL" : ""})
                </option>
              );
            })}
          </Select>
        </FormField>
        <FormField
          label="Reason for the change"
          hint="Stored with the audit entry so the change can be tracked."
        >
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
                    placeholder="e.g. Balancing group loads before the review week." />
        </FormField>
      </div>
    </Modal>
  );
}
