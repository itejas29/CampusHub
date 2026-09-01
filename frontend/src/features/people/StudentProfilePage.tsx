import { useQuery } from "@tanstack/react-query";
import {
  BookOpen, Briefcase, ClipboardCheck, FileText, Lock, Mail, MapPin,
  User as UserIcon,
} from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import { api } from "@/lib/api";
import type { StudentProfile } from "@/types";

const DOC_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  VERIFIED: "success", APPROVED: "success",
  SUBMITTED: "warning", UNDER_REVIEW: "warning", REVISION_REQUESTED: "warning",
  REJECTED: "danger",
  NOT_SUBMITTED: "neutral", DRAFT: "neutral",
};

/**
 * One student, seen whole — the view faculty workflows start from.
 *
 * Which tabs appear is decided by the backend (`visible_sections`), never by
 * the role held in the browser. A section the caller may not see is absent
 * rather than empty, so a coordinator never mistakes "not allowed" for
 * "no data".
 */
export function StudentProfilePage() {
  const { studentId } = useParams<{ studentId: string }>();
  const [tab, setTab] = useState("academic");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["student-profile", studentId],
    queryFn: () => api.get<StudentProfile>(`/student-profile/${studentId}`),
    enabled: Boolean(studentId),
  });

  if (isLoading) return <LoadingState rows={6} />;
  if (error) {
    const message = (error as Error).message;
    const denied = message.toLowerCase().includes("access");
    return (
      <div>
        <PageHeader title="Student profile"
                    breadcrumbs={[{ label: "People" }, { label: "Student" }]} />
        {denied ? (
          <Alert variant="warning"
                 title="You don't have permission to view this student">
            {message}
          </Alert>
        ) : (
          <ErrorState onRetry={() => refetch()} />
        )}
      </div>
    );
  }
  if (!data) return null;

  const { personal, academic, internships, documents, evaluations, mentor } = data;
  const can = (section: string) => data.visible_sections.includes(section);
  const missingDocs = documents.filter(
    (d) => d.status === "NOT_SUBMITTED" && d.is_mandatory);

  const tabs: TabItem[] = [
    ...(can("academic") ? [{ key: "academic", label: "Academic" }] : []),
    ...(can("internship")
      ? [{ key: "internship", label: "Internship", count: internships.length }] : []),
    ...(can("documents")
      ? [{ key: "documents", label: "Documents", count: documents.length }] : []),
    ...(can("evaluation")
      ? [{ key: "evaluation", label: "Evaluation", count: evaluations.length }] : []),
    ...(can("mentor") ? [{ key: "mentor", label: "Mentor" }] : []),
  ];
  const active = tabs.some((t) => t.key === tab) ? tab : tabs[0]?.key ?? "academic";

  return (
    <div>
      <PageHeader
        title={personal.full_name}
        description={`${personal.roll_number} · ${personal.program_name ?? "—"}`}
        breadcrumbs={[{ label: "People" }, { label: personal.roll_number }]}
      />

      <Card className="mb-5">
        <CardBody className="flex flex-wrap items-center gap-2">
          <Badge tone="brand">{personal.program_code}</Badge>
          {personal.school && <Badge tone="neutral">{personal.school}</Badge>}
          <Badge tone="neutral">Semester {personal.current_semester}</Badge>
          {personal.division && (
            <Badge tone="neutral">Division {personal.division}</Badge>
          )}
          {personal.batch && <Badge tone="neutral">Batch {personal.batch}</Badge>}
          <Badge tone={personal.status === "ACTIVE" ? "success" : "neutral"}>
            {personal.status.toLowerCase()}
          </Badge>
          <span className="ml-auto flex flex-wrap items-center gap-3 text-xs text-ink-muted">
            <span className="flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" aria-hidden />{personal.email}
            </span>
            {personal.enrollment_number && (
              <span className="tabular">{personal.enrollment_number}</span>
            )}
          </span>
        </CardBody>
      </Card>

      {missingDocs.length > 0 && can("documents") && (
        <Alert variant="warning" className="mb-4"
               title={`${missingDocs.length} mandatory document(s) not submitted`}>
          {missingDocs.map((d) => d.label).join(" · ")}
        </Alert>
      )}

      {tabs.length > 0 && (
        <Tabs tabs={tabs} active={active} onChange={setTab} className="mb-4" />
      )}

      {active === "academic" && academic && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Curriculum"
                      value={academic.curriculum_version ?? "Not published"}
                      hint={academic.batch_label} />
            <StatTile label="CPI" value={academic.cpi?.toFixed(2) ?? "—"}
                      hint="Minor eligibility only" />
            <StatTile label="Backlogs" value={academic.backlog_count} />
            <StatTile label="Minor" value={academic.minor_name ?? "None"}
                      hint={academic.minor_status} />
          </div>

          {!academic.curriculum_version && (
            <Alert variant="info">
              No curriculum has been published for this student's programme and
              batch yet, so their requirements cannot be resolved.
            </Alert>
          )}

          <Card>
            <CardHeader title={`Semester ${personal.current_semester} requirements`}
                        icon={<BookOpen className="h-4 w-4" aria-hidden />} />
            <CardBody>
              {academic.current_semester_components.length === 0 ? (
                <EmptyState title="No components recorded for this semester" />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {academic.current_semester_components.map((c) => (
                    <span key={c.code}
                          className="rounded-md border border-line px-2.5 py-1.5 text-xs">
                      <span className="tabular text-ink-muted">{c.code}</span>
                      {" · "}{c.title}
                      <span className="ml-1.5 text-ink-subtle">{c.credits} cr</span>
                    </span>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Elective allocations" />
            <CardBody className="p-0">
              {academic.elective_allocations.length === 0 ? (
                <div className="p-5">
                  <EmptyState title="No electives allocated yet" />
                </div>
              ) : (
                <TableWrap>
                  <THead>
                    <TH>Component</TH><TH>Course</TH><TH>Section</TH><TH>Status</TH>
                  </THead>
                  <TBody>
                    {academic.elective_allocations.map((a, i) => (
                      <TR key={i}>
                        <TD>{a.component ?? a.component_code}</TD>
                        <TD>
                          <span className="tabular">{a.course_code}</span> · {a.course_title}
                        </TD>
                        <TD>{a.section ?? "—"}</TD>
                        <TD><Badge tone="info">{a.status.toLowerCase()}</Badge></TD>
                      </TR>
                    ))}
                  </TBody>
                </TableWrap>
              )}
            </CardBody>
          </Card>

          {academic.mooc_registrations.length > 0 && (
            <Card>
              <CardHeader title="NPTEL / MOOC" />
              <CardBody className="p-0">
                <TableWrap>
                  <THead>
                    <TH>Course</TH><TH>Platform</TH><TH>Status</TH><TH>Verification</TH>
                  </THead>
                  <TBody>
                    {academic.mooc_registrations.map((m, i) => (
                      <TR key={i}>
                        <TD>{m.course ?? "—"}</TD>
                        <TD>{m.platform}</TD>
                        <TD>{m.status.toLowerCase()}</TD>
                        <TD>
                          <Badge tone={m.verification === "VERIFIED" ? "success" : "warning"}>
                            {m.verification.toLowerCase()}
                          </Badge>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </TableWrap>
              </CardBody>
            </Card>
          )}
        </div>
      )}

      {active === "internship" && (
        <div className="space-y-4">
          {internships.length === 0 ? (
            <Card>
              <EmptyState title="No internship enrolments"
                          icon={<Briefcase className="h-5 w-5" aria-hidden />} />
            </Card>
          ) : internships.map((i) => (
            <Card key={i.enrollment_id}>
              <CardHeader
                title={i.program_name}
                description={`${i.organization ?? "No organisation recorded"} · mentor: ${i.faculty_mentor ?? "unassigned"}`}
                action={<Badge tone="info">{i.status.toLowerCase()}</Badge>}
              />
              <CardBody>
                <div className="flex items-center gap-3">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted"
                       role="progressbar" aria-valuenow={i.progress_percent}
                       aria-valuemin={0} aria-valuemax={100}
                       aria-label={`${i.program_name} progress`}>
                    <div className="h-full rounded-full bg-brand"
                         style={{ width: `${i.progress_percent}%` }} />
                  </div>
                  <span className="tabular text-xs text-ink-muted">
                    {i.completed_items}/{i.total_items} stages · {i.progress_percent}%
                  </span>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {active === "documents" && (
        <Card>
          <CardHeader title="Expected and submitted documents"
                      description="Every required artefact is listed, submitted or not."
                      icon={<FileText className="h-4 w-4" aria-hidden />} />
          <CardBody className="p-0">
            {documents.length === 0 ? (
              <div className="p-5"><EmptyState title="No documents expected yet" /></div>
            ) : (
              <TableWrap>
                <THead>
                  <TH>Group</TH><TH>Document</TH><TH>Status</TH>
                  <TH>Submitted</TH><TH>Feedback</TH>
                </THead>
                <TBody>
                  {documents.map((d, i) => (
                    <TR key={i}>
                      <TD className="text-xs text-ink-muted">{d.group ?? "—"}</TD>
                      <TD>
                        {d.file_url ? (
                          <a href={d.file_url} target="_blank" rel="noreferrer"
                             className="text-brand hover:underline">{d.label}</a>
                        ) : d.label}
                        {d.is_mandatory && d.status === "NOT_SUBMITTED" && (
                          <span className="ml-1.5 text-2xs text-warning">required</span>
                        )}
                      </TD>
                      <TD>
                        <Badge tone={DOC_TONE[d.status] ?? "neutral"}>
                          {d.status.replace(/_/g, " ").toLowerCase()}
                        </Badge>
                      </TD>
                      <TD className="text-xs text-ink-muted">
                        {d.submitted_at
                          ? new Date(d.submitted_at).toLocaleDateString() : "—"}
                      </TD>
                      <TD className="max-w-[16rem] text-xs text-ink-muted">
                        {d.reviewer_comment ?? "—"}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </TableWrap>
            )}
          </CardBody>
        </Card>
      )}

      {active === "evaluation" && (
        <div className="space-y-4">
          {evaluations.length === 0 ? (
            <Card>
              <EmptyState title="No evaluation recorded yet"
                          icon={<ClipboardCheck className="h-5 w-5" aria-hidden />} />
            </Card>
          ) : evaluations.map((e, i) => (
            <Card key={i}>
              <CardHeader
                title={e.evaluator_role.replace(/_/g, " ").toLowerCase()}
                description={e.remarks}
                action={
                  <Badge tone={e.status === "FINALISED" ? "success" : "warning"}>
                    {e.total_marks ?? "—"} / {e.max_marks ?? "—"}
                  </Badge>
                }
              />
              <CardBody className="p-0">
                <TableWrap>
                  <THead>
                    <TH>Criterion</TH><TH align="right">Marks</TH><TH>Comment</TH>
                  </THead>
                  <TBody>
                    {e.scores.map((s, j) => (
                      <TR key={j}>
                        <TD>{s.criterion ?? "—"}</TD>
                        <TD className="tabular" align="right">
                          {s.marks ?? "—"} / {s.max_marks ?? "—"}
                        </TD>
                        <TD className="text-xs text-ink-muted">{s.comment ?? "—"}</TD>
                      </TR>
                    ))}
                  </TBody>
                </TableWrap>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {active === "mentor" && (
        <Card>
          <CardHeader title="Mentor" icon={<UserIcon className="h-4 w-4" aria-hidden />} />
          <CardBody>
            {!mentor ? (
              <EmptyState title="No mentor assigned" />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
                  <span className="font-medium text-ink">{mentor.full_name}</span>
                  <span className="text-ink-muted">{mentor.designation}</span>
                  {mentor.department_code && (
                    <Badge tone="neutral">{mentor.department_code}</Badge>
                  )}
                  {mentor.email && (
                    <span className="flex items-center gap-1 text-ink-muted">
                      <Mail className="h-3.5 w-3.5" aria-hidden />{mentor.email}
                    </span>
                  )}
                  {mentor.cabin && (
                    <span className="flex items-center gap-1 text-ink-muted">
                      <MapPin className="h-3.5 w-3.5" aria-hidden />{mentor.cabin}
                    </span>
                  )}
                </div>

                {!mentor.meetings_visible ? (
                  <p className="flex items-start gap-1.5 text-xs text-ink-muted">
                    <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    Meeting history is between the student and their mentor, and is
                    not shown here.
                  </p>
                ) : mentor.recent_meetings.length === 0 ? (
                  <EmptyState title="No meetings yet" />
                ) : (
                  <TableWrap>
                    <THead>
                      <TH>Meeting</TH><TH>Requested</TH><TH>Scheduled</TH><TH>Status</TH>
                    </THead>
                    <TBody>
                      {mentor.recent_meetings.map((m, i) => (
                        <TR key={i}>
                          <TD>{m.title}</TD>
                          <TD className="text-xs text-ink-muted">
                            {m.requested_at
                              ? new Date(m.requested_at).toLocaleDateString() : "—"}
                          </TD>
                          <TD className="text-xs text-ink-muted">
                            {m.scheduled_at
                              ? new Date(m.scheduled_at).toLocaleString() : "—"}
                          </TD>
                          <TD><Badge tone="neutral">{m.status.toLowerCase()}</Badge></TD>
                        </TR>
                      ))}
                    </TBody>
                  </TableWrap>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
