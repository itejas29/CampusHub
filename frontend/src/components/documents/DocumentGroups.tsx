import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Check, Clock, Eye, FileWarning, MessageSquare, Upload, X,
} from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { FormField, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/States";
import { ApiError, api, openProtectedFile } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { DocumentGroup, ExpectedDocument, InternshipProgress } from "@/types";

/** The report endpoint takes a target status where documents take an action. */
const REPORT_STATUS: Record<string, string> = {
  start_review: "UNDER_REVIEW",
  verify: "VERIFIED",
  reject: "REJECTED",
};

/** Progress derived from documents — never an arbitrary percentage. */
export function DocumentProgress({ progress }: { progress: InternshipProgress }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface-sunken p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-heading text-sm font-semibold text-ink">Progress</h3>
        <p className="text-sm tabular-nums text-ink-muted">
          <span className="font-heading text-md font-semibold text-ink">
            {progress.completed}
          </span>{" "}
          of {progress.total} stages complete
        </p>
      </div>
      <div
        className="mt-2.5 h-2 overflow-hidden rounded-full bg-line"
        role="progressbar" aria-valuenow={progress.percent}
        aria-valuemin={0} aria-valuemax={100}
        aria-label={`${progress.completed} of ${progress.total} stages complete`}
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-500"
             style={{ width: `${progress.percent}%` }} />
      </div>
      {progress.blockers.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {progress.blockers.map((blocker) => (
            <li key={blocker} className="flex items-start gap-2 text-xs text-ink-muted">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
              <span className="min-w-0">{blocker}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewTrail({ item }: { item: ExpectedDocument }) {
  if (!item.reviewed_at && !item.review_comment) return null;
  const returned = item.status === "REJECTED" || item.status === "REVISION_REQUESTED";
  return (
    <div
      className={`mt-2.5 min-w-0 rounded-md border p-2.5 text-xs ${
        returned ? "border-danger/30 bg-danger-soft" : "border-line bg-surface-sunken"
      }`}
    >
      <p className="flex items-start gap-1.5 font-medium text-ink">
        <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        <span className="min-w-0">
          {returned ? "Returned for correction" : "Reviewed"}
          {item.reviewed_by ? ` by ${item.reviewed_by}` : ""}
        </span>
      </p>
      {item.review_comment && <p className="mt-1 text-ink-muted">{item.review_comment}</p>}
      {item.reviewed_at && (
        <p className="mt-1 text-2xs text-ink-subtle">{formatDateTime(item.reviewed_at)}</p>
      )}
    </div>
  );
}

function ViewFileButton({ item }: { item: ExpectedDocument }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!item.file_url) return null;

  return (
    <>
      <Button
        size="sm" variant="secondary" loading={busy}
        icon={<Eye className="h-3.5 w-3.5" aria-hidden />}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await openProtectedFile(item.file_url as string);
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not open the file.");
          } finally {
            setBusy(false);
          }
        }}
      >
        View {item.content_type === "application/pdf" ? "PDF" : "file"}
      </Button>
      {error && <Alert variant="danger" className="mt-2">{error}</Alert>}
    </>
  );
}

function DocumentRow({
  item, enrollmentId, canReview, onUpload,
}: {
  item: ExpectedDocument; enrollmentId: number; canReview: boolean;
  onUpload?: (item: ExpectedDocument) => void;
}) {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  // `report_id` is null until the report exists, so `kind` is the discriminator.
  const isReport = item.kind === "report";
  const review = useMutation({
    // Reports and documents are reviewed through their own endpoints, but the
    // reviewer sees one consistent control either way.
    mutationFn: (body: { action: string; comment?: string }) =>
      isReport
        ? api.post(`/internships/reports/${item.report_id}/review`, {
            status: REPORT_STATUS[body.action],
            feedback: body.comment ?? null,
          })
        : api.post(`/internships/documents/${item.document_id}/review`, body),
    onSuccess: () => {
      setRejecting(false);
      setComment("");
      setError(null);
      // Same key the record page and the drawer read, so the panel, the
      // progress bar and the stage stepper all refresh together.
      queryClient.invalidateQueries({
        queryKey: ["internship-record", String(enrollmentId)],
      });
      queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save the review."),
  });

  const missing = item.status === "NOT_SUBMITTED";
  const reviewable = canReview && !missing
                     && (item.document_id !== null || item.report_id !== null);
  // A verified submission is settled; anything else the student may still replace.
  // Reports carry a written summary as well as a file, so they are composed on
  // the Reports tab — the button routes there rather than opening a file picker.
  const settled = item.status === "VERIFIED" || item.status === "APPROVED";
  const canUpload = Boolean(onUpload) && !settled;

  return (
    <li
      className={`min-w-0 rounded-md border p-3.5 ${
        missing && item.is_mandatory
          ? "border-dashed border-warning/50 bg-warning-soft/40"
          : "border-line"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm font-medium text-ink">
            <span className="min-w-0">{item.label}</span>
            {item.is_mandatory && (
              <span className="text-2xs font-normal text-ink-subtle">required</span>
            )}
            {item.revision > 1 && <Badge tone="neutral">Revision {item.revision}</Badge>}
          </p>
          <p className="mt-0.5 text-2xs text-ink-subtle">
            {missing
              ? "Not submitted yet"
              : [
                  item.file_name,
                  item.size_bytes ? formatBytes(item.size_bytes) : null,
                  item.submitted_at ? formatDateTime(item.submitted_at) : null,
                ].filter(Boolean).join(" · ")}
          </p>
        </div>
        <StatusBadge status={item.status} />
      </div>

      {/* Nothing is linked when nothing was submitted — never a placeholder link. */}
      <div className="mt-2.5 flex flex-wrap gap-2">
        <ViewFileButton item={item} />
        {canUpload && (
          <Button
            size="sm" variant={missing ? "primary" : "secondary"}
            icon={<Upload className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => onUpload?.(item)}
          >
            {isReport
              ? (missing ? `Submit week ${item.week_number ?? ""}`.trim() : "Resubmit")
              : (missing ? "Upload" : "Replace file")}
          </Button>
        )}
        {reviewable && item.status === "SUBMITTED" && (
          <Button
            size="sm" variant="ghost" loading={review.isPending}
            icon={<Clock className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => review.mutate({ action: "start_review" })}
          >
            Start review
          </Button>
        )}
        {reviewable && item.status !== "VERIFIED" && (
          <Button
            size="sm" loading={review.isPending}
            icon={<Check className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => review.mutate({ action: "verify" })}
          >
            Verify
          </Button>
        )}
        {reviewable && item.status !== "REJECTED" && (
          <Button
            size="sm" variant="ghost"
            icon={<X className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => setRejecting(true)}
          >
            Reject
          </Button>
        )}
      </div>

      <ReviewTrail item={item} />
      {error && <Alert variant="danger" className="mt-2">{error}</Alert>}

      {rejecting && (
        <Modal
          open onClose={() => setRejecting(false)} size="sm"
          title={`Reject ${item.label}`}
          description="The student sees this reason and can upload a corrected file."
          footer={
            <>
              <Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
              <Button
                variant="danger" loading={review.isPending}
                disabled={comment.trim().length === 0}
                onClick={() => review.mutate({ action: "reject", comment: comment.trim() })}
              >
                Reject document
              </Button>
            </>
          }
        >
          <FormField
            label="Reason" required
            hint="Required — a rejection with no reason leaves the student nothing to act on."
          >
            <Textarea
              rows={4} value={comment} autoFocus
              onChange={(e) => setComment(e.target.value)}
              placeholder="Explain what needs correcting…"
            />
          </FormField>
        </Modal>
      )}
    </li>
  );
}

/**
 * Renders every EXPECTED document for the programme, not merely the rows that
 * exist. A missing mandatory item stays visible as NOT_SUBMITTED so it cannot
 * be silently overlooked.
 */
export function DocumentGroups({
  groups, enrollmentId, canReview = false, onUpload,
}: {
  groups: DocumentGroup[]; enrollmentId: number; canReview?: boolean;
  onUpload?: (item: ExpectedDocument) => void;
}) {
  const populated = groups.filter((group) => group.items.length > 0);
  if (populated.length === 0) {
    return (
      <EmptyState
        compact icon={<FileWarning className="h-5 w-5" aria-hidden />}
        title="No documents are expected yet"
        description="Requirements appear here once the programme stages are configured."
      />
    );
  }
  return (
    <div className="space-y-5">
      {populated.map((group) => (
        <section key={group.title} className="min-w-0">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              {group.title}
            </h3>
            <p className="text-2xs tabular-nums text-ink-subtle">
              {group.satisfied} verified · {group.submitted} of {group.total} submitted
            </p>
          </div>
          <ul className="grid min-w-0 gap-2.5 md:grid-cols-2">
            {group.items.map((item) => (
              <DocumentRow
                key={item.key} item={item}
                enrollmentId={enrollmentId} canReview={canReview}
                onUpload={onUpload}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
