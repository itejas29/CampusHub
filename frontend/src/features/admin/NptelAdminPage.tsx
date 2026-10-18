import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api, qs } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { MoocRegistration } from "@/types";
import { NptelRoundsPanel } from "./NptelRoundsPanel";

export function NptelAdminPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("PENDING");
  const [review, setReview] = useState<MoocRegistration | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["mooc-admin", filter],
    queryFn: () =>
      api.get<MoocRegistration[]>(
        `/mooc/admin/registrations${qs({ verification_status: filter || undefined })}`,
      ),
  });

  const withCertificate = (data ?? []).filter((row) => row.certificate_url);

  return (
    <div>
      <PageHeader
        title="NPTEL / NCC"
        description="Run the semester's NPTEL / NCC choice, then verify the certificates students submit."
        breadcrumbs={[{ label: "Administration" }, { label: "NPTEL / NCC" }]}
      />

      <NptelRoundsPanel />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <Card>
        <Tabs
          tabs={[
            { key: "PENDING", label: "Pending" },
            { key: "VERIFIED", label: "Verified" },
            { key: "REJECTED", label: "Rejected" },
            { key: "", label: "All" },
          ]}
          active={filter}
          onChange={setFilter}
        />
        <CardHeader
          title={`${data?.length ?? 0} registration${data?.length === 1 ? "" : "s"}`}
          description={
            filter === "PENDING"
              ? `${withCertificate.length} have a certificate ready to review.`
              : undefined
          }
          icon={<BadgeCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
        />

        {isLoading ? (
          <LoadingState rows={4} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.length ? (
          <EmptyState
            title="Nothing to review"
            description="Certificates uploaded by students appear here for verification."
            icon={<BadgeCheck className="h-5 w-5" aria-hidden />}
          />
        ) : (
          <TableWrap>
            <THead>
              <TH width="20%">Student</TH>
              <TH width="12%">Roll no.</TH>
              <TH>Course</TH>
              <TH width="12%">Exam</TH>
              <TH width="12%">Status</TH>
              <TH width="14%" align="right">Actions</TH>
            </THead>
            <TBody>
              {data.length === 0 ? (
                <TableEmpty colSpan={6}>No registrations in this state.</TableEmpty>
              ) : (
                data.map((row) => (
                  <TR key={row.id}>
                    <TD className="font-medium">{row.student_name}</TD>
                    <TD className="tabular">{row.roll_number}</TD>
                    <TD className="text-ink-muted">
                      <span className="tabular mr-2">{row.course_code}</span>
                      {row.course_title}
                      <span className="mt-0.5 block text-2xs text-ink-subtle">
                        {row.platform}
                        {row.platform_registration_id && ` · ${row.platform_registration_id}`}
                      </span>
                    </TD>
                    <TD className="whitespace-nowrap text-xs text-ink-muted">
                      {row.exam_date ? formatDate(row.exam_date) : "—"}
                    </TD>
                    <TD>
                      <StatusBadge status={row.verification_status} />
                      {!row.certificate_url && (
                        <span className="mt-0.5 block text-2xs text-ink-subtle">
                          No certificate
                        </span>
                      )}
                    </TD>
                    <TD align="right">
                      <div className="flex items-center justify-end gap-2">
                        {row.certificate_url && (
                          <a href={row.certificate_url} target="_blank" rel="noreferrer"
                             className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                            View <ExternalLink className="h-3 w-3" aria-hidden />
                          </a>
                        )}
                        <Button
                          size="sm" variant="secondary" disabled={!row.certificate_url}
                          onClick={() => setReview(row)}
                        >
                          Review
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
      </Card>

      {review && (
        <ReviewModal
          registration={review}
          onClose={() => setReview(null)}
          onDone={(text) => {
            setReview(null);
            setBanner({ tone: "success", text });
            void queryClient.invalidateQueries({ queryKey: ["mooc-admin"] });
            void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          }}
        />
      )}
    </div>
  );
}

function ReviewModal({
  registration, onClose, onDone,
}: {
  registration: MoocRegistration; onClose: () => void; onDone: (text: string) => void;
}) {
  const [status, setStatus] = useState("VERIFIED");
  const [score, setScore] = useState(String(registration.final_score ?? ""));
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState<string | null>(null);

  const verify = useMutation({
    mutationFn: () =>
      api.post(`/mooc/admin/${registration.id}/verify`, {
        verification_status: status,
        final_score: score ? Number(score) : null,
        remarks: remarks || null,
      }),
    onSuccess: () =>
      onDone(status === "VERIFIED" ? "Certificate verified." : "Certificate rejected."),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not record the decision."),
  });

  return (
    <Modal
      open onClose={onClose} title="Verify certificate"
      description={`${registration.student_name} · ${registration.roll_number}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={verify.isPending} onClick={() => verify.mutate()}
                  variant={status === "VERIFIED" ? "primary" : "danger"}>
            {status === "VERIFIED" ? "Verify" : "Reject"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <DetailList
          items={[
            { label: "Course", value: registration.course_title },
            { label: "Platform", value: registration.platform },
            { label: "Registration ID", value: registration.platform_registration_id },
            { label: "Exam date", value: formatDate(registration.exam_date) },
            { label: "Exam city", value: registration.exam_city },
            {
              label: "Fee",
              value: registration.exam_fee_paid
                ? <Badge tone="success">Paid</Badge>
                : <Badge tone="warning">Not recorded</Badge>,
            },
          ]}
        />

        {registration.certificate_url && (
          <a
            href={registration.certificate_url} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
          >
            Open the uploaded certificate <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </a>
        )}

        <FormField label="Decision">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="VERIFIED">Verify — credit the course</option>
            <option value="REJECTED">Reject — certificate not acceptable</option>
          </Select>
        </FormField>

        <FormField label="Final score" hint="Optional. As printed on the certificate.">
          <Input type="number" min={0} max={100} value={score}
                 onChange={(e) => setScore(e.target.value)} />
        </FormField>

        <FormField label="Remarks" hint="Shown to the student with the decision.">
          <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={3} />
        </FormField>

        <Alert variant="info">
          A letter grade is not assigned here — institutional grade mapping for MOOC
          credit is configured in a later phase.
        </Alert>
      </div>
    </Modal>
  );
}
