import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Building2, CalendarDays, FileText, Route, Users,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { humanise, roman } from "@/lib/utils";
import type { EnrollmentSummary, InternshipProgram, Organization } from "@/types";

export function InternshipsPage() {
  const queryClient = useQueryClient();
  const [enrollIn, setEnrollIn] = useState<InternshipProgram | null>(null);
  const [organizationId, setOrganizationId] = useState<string>("");
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const programs = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });
  const mine = useQuery({
    queryKey: ["internship-enrollments", "me"],
    queryFn: () => api.get<EnrollmentSummary[]>("/internships/enrollments/me"),
  });
  const organizations = useQuery({
    queryKey: ["organizations", enrollIn?.id],
    queryFn: () => api.get<Organization[]>("/organizations"),
    enabled: Boolean(enrollIn?.requires_organization),
  });

  const enroll = useMutation({
    mutationFn: (programId: number) =>
      api.post(`/internships/programs/${programId}/enroll`, {
        organization_id: organizationId ? Number(organizationId) : null,
      }),
    onSuccess: () => {
      setEnrollIn(null);
      setOrganizationId("");
      setBanner({ tone: "success", text: "You are enrolled. Work through each stage in order." });
      void queryClient.invalidateQueries({ queryKey: ["internship-programs"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Enrolment failed.",
      }),
  });

  const allowedTypes = enrollIn?.allowed_organization_types ?? [];
  const filteredOrgs = (organizations.data ?? []).filter(
    (org) => allowedTypes.length === 0 || allowedTypes.includes(org.type),
  );

  return (
    <div>
      <PageHeader
        title="Internships"
        description="CSSI and Summer Internship run on the same engine — the stages, group structure, reporting cadence and evaluation rubric are configured per programme."
        breadcrumbs={[{ label: "Internships" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {/* Active enrolments */}
      <section className="mb-6">
        <h2 className="mb-3 text-md font-semibold text-ink">My internships</h2>
        {mine.isLoading ? (
          <LoadingState rows={2} />
        ) : mine.error ? (
          <ErrorState onRetry={() => mine.refetch()} compact />
        ) : !mine.data?.length ? (
          <Card>
            <EmptyState
              title="Not enrolled in an internship yet"
              description={
                (programs.data ?? []).length > 0
                  ? "Enrol in an open programme below to start the workflow."
                  // Pointing at a programme list that is empty for this
                  // semester just sends the student looking for something that
                  // is not there.
                  : "Nothing to enrol in at your current semester."
              }
              icon={<Route className="h-5 w-5" aria-hidden />}
            />
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {mine.data.map((enrollment) => (
              <Link key={enrollment.id} to={`/internships/record/${enrollment.id}`}>
                <Card className="h-full transition-colors hover:border-line-strong">
                  <CardBody>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="tabular text-ink-muted">{enrollment.program_code}</p>
                        <h3 className="mt-1 text-md font-semibold leading-snug text-ink">
                          {enrollment.organization_name ?? "Organisation not set"}
                        </h3>
                      </div>
                      <StatusBadge status={enrollment.status} />
                    </div>

                    <ProgressBar
                      className="mt-4"
                      label={enrollment.current_stage ?? "All stages complete"}
                      value={enrollment.progress_percent}
                      tone={enrollment.progress_percent === 100 ? "success" : "accent"}
                    />

                    <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                      {enrollment.mentor_name && (
                        <div>
                          <dt className="text-ink-subtle">Faculty mentor</dt>
                          <dd className="mt-0.5 text-ink">{enrollment.mentor_name}</dd>
                        </div>
                      )}
                      {enrollment.group_name && (
                        <div>
                          <dt className="text-ink-subtle">Group</dt>
                          <dd className="mt-0.5 text-ink">{enrollment.group_name}</dd>
                        </div>
                      )}
                      {enrollment.final_marks !== null && (
                        <div>
                          <dt className="text-ink-subtle">Final marks</dt>
                          <dd className="mt-0.5 font-medium text-ink">{enrollment.final_marks}</dd>
                        </div>
                      )}
                    </dl>

                    <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent">
                      Open workflow <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </span>
                  </CardBody>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Available programmes */}
      <section>
        <h2 className="mb-3 text-md font-semibold text-ink">Programmes</h2>
        {programs.isLoading ? (
          <LoadingState rows={2} />
        ) : programs.error ? (
          <ErrorState onRetry={() => programs.refetch()} compact />
        ) : !(programs.data ?? []).length ? (
          <Card>
            <EmptyState
              title="No internship runs at your semester"
              description="CSSI runs in Semester III and the Summer Internship from Semester VI. A programme appears here once it concerns you, and your own record stays available afterwards."
              icon={<Route className="h-5 w-5" aria-hidden />}
            />
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {(programs.data ?? []).map((program) => (
              <Card key={program.id}>
                <CardHeader
                  title={program.name}
                  description={program.description ?? undefined}
                  action={<StatusBadge status={program.status} />}
                />
                <CardBody>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge tone="brand" className="font-mono">{program.code}</Badge>
                    <Badge tone="neutral">{humanise(program.type)}</Badge>
                    <Badge tone="neutral">{program.credits} credits</Badge>
                    {program.target_semester && (
                      <Badge tone="neutral">From semester {roman(program.target_semester)}</Badge>
                    )}
                  </div>

                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                    <div>
                      <dt className="flex items-center gap-1 text-ink-subtle">
                        <Route className="h-3 w-3" aria-hidden /> Stages
                      </dt>
                      <dd className="mt-0.5 text-ink">{program.stages.length}</dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-1 text-ink-subtle">
                        <FileText className="h-3 w-3" aria-hidden /> Reporting
                      </dt>
                      <dd className="mt-0.5 text-ink">
                        {program.report_frequency === "NONE"
                          ? "No periodic reports"
                          : `${humanise(program.report_frequency)} × ${program.expected_report_count}`}
                      </dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-1 text-ink-subtle">
                        <Users className="h-3 w-3" aria-hidden /> Structure
                      </dt>
                      <dd className="mt-0.5 text-ink">
                        {program.requires_group
                          ? `Groups of ~${program.default_group_size}`
                          : "Individual"}
                      </dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-1 text-ink-subtle">
                        <CalendarDays className="h-3 w-3" aria-hidden /> Period
                      </dt>
                      <dd className="mt-0.5 text-ink">
                        {formatDate(program.start_date)} – {formatDate(program.end_date)}
                      </dd>
                    </div>
                  </dl>

                  {program.criteria.length > 0 && (
                    <p className="mt-3 text-xs text-ink-subtle">
                      Evaluated on {program.criteria.length} criteria ·{" "}
                      {program.criteria.reduce((sum, c) => sum + c.max_marks, 0)} marks total
                    </p>
                  )}

                  <div className="mt-4">
                    {program.my_enrollment_id ? (
                      <Link
                        to={`/internships/record/${program.my_enrollment_id}`}
                        className="inline-flex items-center gap-1 text-sm font-medium text-accent"
                      >
                        Open my record <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                      </Link>
                    ) : program.can_enroll ? (
                      <Button size="sm" onClick={() => setEnrollIn(program)}>
                        Enrol
                      </Button>
                    ) : (
                      <p className="text-xs text-ink-subtle">
                        {program.enroll_blocked_reason ?? "Not open for enrolment."}
                      </p>
                    )}
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={Boolean(enrollIn)}
        onClose={() => { setEnrollIn(null); setOrganizationId(""); }}
        title={`Enrol in ${enrollIn?.name ?? ""}`}
        description="You can change the organisation later from your internship record."
        footer={
          <>
            <Button variant="secondary" size="sm"
                    onClick={() => { setEnrollIn(null); setOrganizationId(""); }}>
              Cancel
            </Button>
            <Button size="sm" loading={enroll.isPending}
                    onClick={() => enrollIn && enroll.mutate(enrollIn.id)}>
              Confirm enrolment
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {enrollIn?.requires_group && (
            <Alert variant="info">
              You will be assigned to a faculty-supervised group automatically. Your
              mentor's contact details appear on your record once allocated.
            </Alert>
          )}

          {enrollIn?.requires_organization && (
            <div className="space-y-1.5">
              <label htmlFor="org-select" className="block text-sm font-medium text-ink">
                Host organisation
              </label>
              <select
                id="org-select"
                value={organizationId}
                onChange={(e) => setOrganizationId(e.target.value)}
                className="h-9 w-full cursor-pointer rounded border border-line-strong bg-surface px-3 text-sm text-ink"
              >
                <option value="">Select later</option>
                {filteredOrgs.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name} — {org.city ?? org.state ?? org.country}
                  </option>
                ))}
              </select>
              <p className="text-xs text-ink-subtle">
                <Building2 className="mr-1 inline h-3 w-3" aria-hidden />
                {allowedTypes.length
                  ? `Accepted: ${allowedTypes.map(humanise).join(", ")}`
                  : "Any approved organisation"}
              </p>
            </div>
          )}

          <div className="rounded border border-line bg-surface-muted/40 p-3">
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Workflow stages
            </p>
            <ol className="mt-2 space-y-1">
              {(enrollIn?.stages ?? []).map((stage, index) => (
                <li key={stage.id} className="flex items-start gap-2 text-xs text-ink-muted">
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface text-2xs font-semibold text-ink-subtle">
                    {index + 1}
                  </span>
                  {stage.name}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Modal>
    </div>
  );
}
