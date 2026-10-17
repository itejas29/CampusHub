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
import { FormField, Input } from "@/components/ui/Form";
import { ProgramWindowStrip } from "./ProgramWindowStrip";
import { PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { humanise, roman } from "@/lib/utils";
import type { EnrollmentSummary, InternshipProgram, Organization } from "@/types";

export function InternshipsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  // A student's page is their own work: the records they upload to and
  // submit. Programme details (stages, windows, rubric — and other
  // departments' programmes) are the coordinator's; a student sees a programme
  // card only while it is one they can still register for.
  const isStudent = Boolean(user?.student);
  const [enrollIn, setEnrollIn] = useState<InternshipProgram | null>(null);
  const [organizationId, setOrganizationId] = useState<string>("");
  // A student may register an organisation that is not on the approved list
  // yet, and must name its supervisor when the programme requires one (CSSI).
  const [newOrg, setNewOrg] = useState({ name: "", city: "" });
  const [supervisor, setSupervisor] = useState({ name: "", phone: "" });
  const resetForm = () => {
    setEnrollIn(null); setOrganizationId("");
    setNewOrg({ name: "", city: "" }); setSupervisor({ name: "", phone: "" });
  };
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
        organization_id: organizationId && organizationId !== "new" ? Number(organizationId) : null,
        new_organization: organizationId === "new"
          ? { name: newOrg.name.trim(), city: newOrg.city.trim() || null,
              type: enrollIn?.allowed_organization_types[0] ?? "NGO" }
          : null,
        industry_mentor_name: supervisor.name.trim() || null,
        industry_mentor_phone: supervisor.phone.trim() || null,
      }),
    onSuccess: () => {
      resetForm();
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
  const needsSupervisor = Boolean(enrollIn?.requires_industry_mentor);
  // Named after the organisation type the programme accepts — "NGO supervisor".
  const supervisorLabel = allowedTypes.length === 1
    ? `${allowedTypes[0] === "NGO" ? "NGO" : humanise(allowedTypes[0])} supervisor`
    : "Supervisor at the organisation";
  const formReady =
    (organizationId !== "new" || newOrg.name.trim().length > 1)
    && (!needsSupervisor || (organizationId !== "" && supervisor.name.trim() && supervisor.phone.trim()));
  const filteredOrgs = (organizations.data ?? []).filter(
    (org) => allowedTypes.length === 0 || allowedTypes.includes(org.type),
  );

  const shownPrograms = isStudent
    ? (programs.data ?? []).filter((p) => p.can_enroll && !p.my_enrollment_id)
    : programs.data ?? [];

      {/* Available programmes — for a student, only one they can register for */}
  const programmesSection = !(isStudent && !programs.isLoading && !programs.error && shownPrograms.length === 0) && (
      <section className={isStudent ? "mb-6" : undefined}>
        <h2 className="mb-3 text-md font-semibold text-ink">{isStudent ? "Registration is open — fill in your details" : "Programmes"}</h2>
        {programs.isLoading ? (
          <LoadingState rows={2} />
        ) : programs.error ? (
          <ErrorState onRetry={() => programs.refetch()} compact />
        ) : !shownPrograms.length ? (
          <Card>
            <EmptyState
              title="No internship runs at your semester"
              description="CSSI runs in Semester III and the Summer Internship from Semester VI. A programme appears here once it concerns you, and your own record stays available afterwards."
              icon={<Route className="h-5 w-5" aria-hidden />}
            />
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {shownPrograms.map((program) => (
              <Card key={program.id} className={isStudent ? "border-accent/50 ring-1 ring-accent/20" : undefined}>
                <CardHeader
                  title={program.name}
                  description={isStudent
                    ? `Register with the NGO you will work with and your NGO supervisor's name and phone number.`
                    : program.description ?? undefined}
                  // A window-run programme's state lives in its windows (below);
                  // the older programme status would contradict them.
                  action={program.window_kinds.length ? undefined : <StatusBadge status={program.status} />}
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

                  {!isStudent && (
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
                  )}

                  {program.window_kinds.length > 0 && <ProgramWindowStrip programId={program.id} />}

                  {!isStudent && program.criteria.length > 0 && (
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
                      <Button size="sm" variant={isStudent ? "accent" : "primary"} onClick={() => setEnrollIn(program)}>
                        {isStudent ? "Fill in my details" : "Enrol"}
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
  );

  return (
    <div>
      <PageHeader
        title={isStudent ? "My internship" : "Internships"}
        description={isStudent
          ? "Open your internship to upload and submit each stage of the work."
          : "CSSI and Summer Internship run on the same engine — the stages, group structure, reporting cadence and evaluation rubric are configured per programme."}
        breadcrumbs={[{ label: "Internships" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {/* A student who can register sees it first: this is where the NGO and
          supervisor details are filled in once the coordinator opens it. */}
      {isStudent && programmesSection}

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
                shownPrograms.length > 0
                  ? "Register for the programme above to start the workflow."
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
              <Card key={enrollment.id} className="h-full">
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

                    {/* The deadlines that concern this student — registration,
                        posters, presentation days — and, once announced, their
                        mentor list. Not the programme's configuration. */}
                    {(programs.data ?? []).find((p) => p.id === enrollment.program_id)?.window_kinds.length
                      ? <ProgramWindowStrip programId={enrollment.program_id} />
                      : null}

                    <Link to={`/internships/record/${enrollment.id}`}
                          className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
                      Open workflow <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                  </CardBody>
                </Card>
            ))}
          </div>
        )}
      </section>

      {!isStudent && programmesSection}

      <Modal
        open={Boolean(enrollIn)}
        onClose={resetForm}
        title={`Register for ${enrollIn?.name ?? ""}`}
        description={enrollIn?.window_kinds.length
          ? "You can correct these details until the registration deadline."
          : "You can change the organisation later from your internship record."}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={resetForm}>
              Cancel
            </Button>
            <Button size="sm" variant="accent" loading={enroll.isPending}
                    disabled={!formReady}
                    onClick={() => enrollIn && enroll.mutate(enrollIn.id)}>
              Register
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
                <option value="">{needsSupervisor ? "Choose your organisation" : "Select later"}</option>
                {filteredOrgs.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name} — {org.city ?? org.state ?? org.country}
                  </option>
                ))}
                <option value="new">Not listed — add it</option>
              </select>
              {organizationId === "new" && (
                <div className="grid gap-3 pt-2 sm:grid-cols-2">
                  <FormField label="Organisation name" htmlFor="org-name" required>
                    <Input id="org-name" value={newOrg.name} maxLength={180}
                           onChange={(e) => setNewOrg((o) => ({ ...o, name: e.target.value }))} />
                  </FormField>
                  <FormField label="City" htmlFor="org-city">
                    <Input id="org-city" value={newOrg.city} maxLength={100}
                           onChange={(e) => setNewOrg((o) => ({ ...o, city: e.target.value }))} />
                  </FormField>
                </div>
              )}
              <p className="text-xs text-ink-subtle">
                <Building2 className="mr-1 inline h-3 w-3" aria-hidden />
                {allowedTypes.length
                  ? `Accepted: ${allowedTypes.map(humanise).join(", ")}`
                  : "Any approved organisation"}
              </p>
            </div>
          )}

          {needsSupervisor && (
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label={`${supervisorLabel} — name`} htmlFor="sup-name" required>
                <Input id="sup-name" value={supervisor.name} maxLength={150} autoComplete="off"
                       onChange={(e) => setSupervisor((v) => ({ ...v, name: e.target.value }))} />
              </FormField>
              <FormField label={`${supervisorLabel} — phone`} htmlFor="sup-phone" required>
                <Input id="sup-phone" type="tel" inputMode="tel" value={supervisor.phone} maxLength={20}
                       autoComplete="off"
                       onChange={(e) => setSupervisor((v) => ({ ...v, phone: e.target.value }))} />
              </FormField>
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
