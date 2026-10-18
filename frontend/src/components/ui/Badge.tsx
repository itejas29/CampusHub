import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone =
  | "neutral" | "brand" | "accent" | "success" | "warning" | "danger" | "info";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-muted text-ink-muted border-line",
  brand: "bg-brand-soft text-brand border-brand/20",
  accent: "bg-accent-soft text-accent border-accent/20",
  success: "bg-success-soft text-success border-success/20",
  warning: "bg-warning-soft text-warning border-warning/20",
  danger: "bg-danger-soft text-danger border-danger/20",
  info: "bg-info-soft text-info border-info/20",
};

export function Badge({
  tone = "neutral", children, className, icon,
}: {
  tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs " +
        "font-medium leading-tight whitespace-nowrap",
        TONES[tone], className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/**
 * Maps every backend status vocabulary to a tone, so one status never renders
 * two different colours in two different screens.
 */
const STATUS_TONES: Record<string, Tone> = {
  // generic
  ACTIVE: "success", COMPLETED: "success", APPROVED: "success", VERIFIED: "success",
  CONFIRMED: "success", ALLOCATED: "success", PUBLISHED: "success",
  REGISTERED: "info", SUBMITTED: "info", IN_PROGRESS: "info", ATTENDED: "success",
  UNDER_REVIEW: "info", UNDER_EVALUATION: "info", MENTOR_ASSIGNED: "info",
  EXAM_SCHEDULED: "info", CERTIFICATE_UPLOADED: "info", OPEN: "success",
  PENDING: "warning", WAITLISTED: "warning", DRAFT: "neutral", LOCKED: "neutral",
  REQUESTED: "warning", REVISION_REQUESTED: "warning", RESCHEDULED: "warning",
  REJECTED: "danger", CANCELLED: "danger", WITHDRAWN: "danger", DECLINED: "danger",
  DROPPED: "danger", NO_SHOW: "danger", DISCONTINUED: "danger",
  CLOSED: "neutral", ARCHIVED: "neutral", SKIPPED: "neutral",
  // A document that was never uploaded is a real state, not an absence.
  NOT_SUBMITTED: "warning",
  REGISTRATION_OPEN: "success", EVALUATION: "info", FINALISED: "success",
  GRADUATED: "neutral", ON_LEAVE: "warning",
  // priorities
  CRITICAL: "danger", HIGH: "warning", NORMAL: "neutral", LOW: "neutral",
  // student-facing computed labels
  "Action needed": "warning", Upcoming: "neutral", "Not started": "neutral",
  "Preferences submitted": "info", Core: "brand", Allocated: "success",
  Completed: "success", "Choice filling open": "success", "Interest round open": "success",
  "Final round open": "success", "Choice submitted": "info", "Choices locked": "neutral",
  "Not open yet": "neutral", Closed: "neutral",
};

export function StatusBadge({
  status, className, icon,
}: { status?: string | null; className?: string; icon?: ReactNode }) {
  if (!status) return null;
  const tone = STATUS_TONES[status] ?? "neutral";
  const label = STATUS_TONES[status] !== undefined && /[a-z]/.test(status)
    ? status
    : status.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
  return <Badge tone={tone} className={className} icon={icon}>{label}</Badge>;
}
