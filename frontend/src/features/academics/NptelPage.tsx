import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck, ExternalLink, Lock, Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Input } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { DetailList, FileUpload, PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { API_BASE, ApiError, api, tokenStore } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { roman } from "@/lib/utils";
import type {
  CourseOffering, MoocEligibility, MoocRegistration, StudentMoocStanding,
} from "@/types";
import { NptelRoundPanel, NptelStandingBanner } from "./NptelRoundPanel";

export function NptelPage() {
  const queryClient = useQueryClient();
  const [registerFor, setRegisterFor] = useState<CourseOffering | null>(null);
  const [uploadFor, setUploadFor] = useState<MoocRegistration | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const registrationIdRef = useRef<HTMLInputElement>(null);
  const examDateRef = useRef<HTMLInputElement>(null);

  // The coordinator's round, when one covers this student, replaces the free
  // catalogue below: choose from the approved list or NCC there.
  const standing = useQuery({
    queryKey: ["mooc", "round"],
    queryFn: () => api.get<StudentMoocStanding>("/mooc/rounds/mine"),
  });
  const eligibility = useQuery({
    queryKey: ["mooc", "eligibility"],
    queryFn: () => api.get<MoocEligibility>("/mooc/eligibility"),
  });
  const catalogue = useQuery({
    queryKey: ["mooc", "catalogue"],
    queryFn: () => api.get<CourseOffering[]>("/mooc/catalogue"),
    enabled: eligibility.data?.eligible === true,
  });
  const mine = useQuery({
    queryKey: ["mooc", "me"],
    queryFn: () => api.get<MoocRegistration[]>("/mooc/me"),
  });

  const register = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/mooc/register", body),
    onSuccess: () => {
      setRegisterFor(null);
      setBanner({ tone: "success", text: "Registration recorded." });
      void queryClient.invalidateQueries({ queryKey: ["mooc"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Registration failed.",
      }),
  });

  const upload = useMutation({
    mutationFn: async ({ id, selected }: { id: number; selected: File }) => {
      const form = new FormData();
      form.append("file", selected);
      const response = await fetch(`${API_BASE}/mooc/${id}/certificate`, {
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
    onSuccess: () => {
      setUploadFor(null);
      setFile(null);
      setBanner({ tone: "success", text: "Certificate uploaded and sent for verification." });
      void queryClient.invalidateQueries({ queryKey: ["mooc"] });
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Upload failed.",
      }),
  });

  if (eligibility.isLoading) return <LoadingState rows={4} />;
  if (eligibility.error) {
    return <ErrorState message={eligibility.error instanceof Error ? eligibility.error.message : undefined}
                       onRetry={() => eligibility.refetch()} />;
  }

  const component = eligibility.data?.component;
  const registeredOfferingIds = new Set((mine.data ?? []).map((r) => r.course_offering_id));

  return (
    <div>
      <PageHeader
        title="NPTEL / NCC"
        description="Your Open Elective as an NPTEL course from the department's approved list, or NCC certification. Choose in your coordinator's round, then submit the certificate here."
        breadcrumbs={[{ label: "Academics" }, { label: "NPTEL / MOOC" }]}
        meta={
          component && (
            <>
              <Badge tone="brand" className="font-mono">{component.code}</Badge>
              <Badge tone="neutral">Semester {roman(component.semester_number)}</Badge>
              <Badge tone="neutral">{component.credits} credits</Badge>
              {component.scope_label && <Badge tone="accent">{component.scope_label}</Badge>}
            </>
          )
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {standing.data && <NptelStandingBanner data={standing.data} />}
      {standing.data?.round && <NptelRoundPanel round={standing.data.round} />}

      {!eligibility.data?.eligible && !standing.data?.round && (
        <Alert
          variant={component ? "warning" : "info"}
          title={component ? "Not open for you yet" : "Not part of your curriculum"}
          className="mb-5"
        >
          <ul className="list-inside list-disc space-y-0.5">
            {(eligibility.data?.reasons ?? []).map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </Alert>
      )}

      <div className="space-y-5">
        {/* My registrations */}
        <Card>
          <CardHeader
            title="My registrations"
            description="Track exam scheduling, certificate upload and departmental verification."
            icon={<BadgeCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
          />
          {mine.isLoading ? (
            <LoadingState rows={2} />
          ) : !mine.data?.length ? (
            <EmptyState
              compact
              title="No registrations yet"
              description="Register for a course from the catalogue below, then record your platform registration ID."
              icon={<BadgeCheck className="h-5 w-5" aria-hidden />}
            />
          ) : (
            <TableWrap>
              <THead>
                <TH>Course</TH>
                <TH width="12%">Platform</TH>
                <TH width="14%">Exam</TH>
                <TH width="14%">Status</TH>
                <TH width="14%">Verification</TH>
                <TH width="12%" align="right">Actions</TH>
              </THead>
              <TBody>
                {mine.data.map((row) => (
                  <TR key={row.id}>
                    <TD>
                      <p className="font-medium text-ink">{row.course_title}</p>
                      <p className="tabular text-ink-subtle">{row.course_code}</p>
                    </TD>
                    <TD><Badge tone="neutral">{row.platform}</Badge></TD>
                    <TD className="text-ink-muted">
                      {row.exam_date ? formatDate(row.exam_date) : "Not scheduled"}
                      {row.exam_fee_paid && (
                        <span className="block text-2xs text-success">Fee paid</span>
                      )}
                    </TD>
                    <TD><StatusBadge status={row.status} /></TD>
                    <TD><StatusBadge status={row.verification_status} /></TD>
                    <TD align="right">
                      {row.certificate_url ? (
                        <a
                          href={row.certificate_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
                        >
                          Certificate <ExternalLink className="h-3 w-3" aria-hidden />
                        </a>
                      ) : (
                        <Button
                          variant="secondary" size="sm"
                          onClick={() => { setUploadFor(row); setFile(null); }}
                          icon={<Upload className="h-3 w-3" aria-hidden />}
                        >
                          Upload
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </TableWrap>
          )}
        </Card>

        {/* Catalogue — only when no round is running for this student */}
        {eligibility.data?.eligible && !standing.data?.round
          && standing.data?.standing !== "CLEARED" && standing.data?.standing !== "BACKLOG" && (
          <Card>
            <CardHeader
              title="Approved course catalogue"
              description="Courses the department has approved for this requirement."
            />
            {catalogue.isLoading ? (
              <LoadingState rows={3} />
            ) : !catalogue.data?.length ? (
              <EmptyState compact title="No approved courses published yet" />
            ) : (
              <CardBody className="grid gap-3 sm:grid-cols-2">
                {catalogue.data.map((offering) => {
                  const already = registeredOfferingIds.has(offering.id);
                  return (
                    <div key={offering.id} className="rounded-md border border-line p-3.5">
                      <div className="flex items-start justify-between gap-2">
                        <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                          {offering.course.code}
                        </span>
                        <Badge tone="neutral">{offering.course.platform}</Badge>
                      </div>
                      <p className="mt-2 text-sm font-medium leading-snug text-ink">
                        {offering.course.title}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                        <span>{offering.course.credits} credits</span>
                        {offering.course.duration_weeks && (
                          <span>{offering.course.duration_weeks} weeks</span>
                        )}
                      </div>
                      {offering.course.description && (
                        <p className="mt-2 line-clamp-2 text-xs text-ink-muted">
                          {offering.course.description}
                        </p>
                      )}
                      <div className="mt-3 flex items-center gap-2">
                        {already ? (
                          <Badge tone="success">Registered</Badge>
                        ) : (
                          <Button size="sm" onClick={() => setRegisterFor(offering)}
                                  disabled={!offering.is_open}>
                            {offering.is_open ? "Register" : "Window closed"}
                          </Button>
                        )}
                        {offering.course.provider_url && (
                          <a
                            href={offering.course.provider_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
                          >
                            Course page <ExternalLink className="h-3 w-3" aria-hidden />
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </CardBody>
            )}
          </Card>
        )}

        <Alert variant="info">
          Exam fees are paid directly on the NPTEL/SWAYAM portal. Record your
          registration ID here and upload the certificate once results are
          declared; the department then verifies it against the platform record.
        </Alert>
      </div>

      {/* Register modal */}
      <Modal
        open={Boolean(registerFor)}
        onClose={() => setRegisterFor(null)}
        title="Record NPTEL registration"
        description={registerFor?.course.title}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setRegisterFor(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={register.isPending}
              onClick={() =>
                register.mutate({
                  course_offering_id: registerFor!.id,
                  platform_registration_id: registrationIdRef.current?.value || null,
                  exam_date: examDateRef.current?.value || null,
                })
              }
            >
              Save registration
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <DetailList
            items={[
              { label: "Course", value: registerFor?.course.title },
              { label: "Platform", value: registerFor?.course.platform },
              { label: "Duration", value: registerFor?.course.duration_weeks
                  ? `${registerFor.course.duration_weeks} weeks` : "—" },
              { label: "Credits", value: registerFor?.course.credits },
            ]}
          />
          <FormField
            label="Platform registration ID"
            hint="From your NPTEL/SWAYAM confirmation email. You can add this later."
          >
            <Input ref={registrationIdRef} placeholder="NPTEL25CS123456" data-autofocus />
          </FormField>
          <FormField label="Proctored exam date" hint="Leave blank if not scheduled yet.">
            <Input ref={examDateRef} type="date" />
          </FormField>
        </div>
      </Modal>

      {/* Upload modal */}
      <Modal
        open={Boolean(uploadFor)}
        onClose={() => { setUploadFor(null); setFile(null); }}
        title="Upload certificate"
        description={uploadFor?.course_title ?? undefined}
        size="sm"
        footer={
          <>
            <Button variant="secondary" size="sm"
                    onClick={() => { setUploadFor(null); setFile(null); }}>
              Cancel
            </Button>
            <Button
              size="sm" disabled={!file} loading={upload.isPending}
              onClick={() => file && upload.mutate({ id: uploadFor!.id, selected: file })}
            >
              Upload
            </Button>
          </>
        }
      >
        <FileUpload
          onSelect={setFile}
          selectedName={file?.name}
          accept=".pdf,.jpg,.jpeg,.png"
          hint="PDF or image of your course completion certificate · up to 15 MB"
        />
        <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-subtle">
          <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          Once verified by the department, the record is locked and can no longer be edited.
        </p>
      </Modal>
    </div>
  );
}
