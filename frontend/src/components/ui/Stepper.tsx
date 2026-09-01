import { Check, CircleDashed, Clock, Loader2, X } from "lucide-react";
import type { ReactNode } from "react";
import type { StageStatus } from "@/types";
import { cn } from "@/lib/utils";

const STATE: Record<StageStatus, {
  ring: string; dot: string; icon: ReactNode; label: string; connector: string;
}> = {
  APPROVED: {
    ring: "border-success bg-success text-success-fg", dot: "bg-success",
    icon: <Check className="h-3.5 w-3.5" aria-hidden />, label: "Approved",
    connector: "bg-success",
  },
  SKIPPED: {
    ring: "border-line-strong bg-surface-muted text-ink-subtle", dot: "bg-line-strong",
    icon: <CircleDashed className="h-3.5 w-3.5" aria-hidden />, label: "Skipped",
    connector: "bg-line-strong",
  },
  SUBMITTED: {
    ring: "border-info bg-info text-info-fg", dot: "bg-info",
    icon: <Clock className="h-3.5 w-3.5" aria-hidden />, label: "Awaiting review",
    connector: "bg-line",
  },
  IN_PROGRESS: {
    ring: "border-accent bg-accent text-white", dot: "bg-accent",
    icon: <Loader2 className="h-3.5 w-3.5" aria-hidden />, label: "In progress",
    connector: "bg-line",
  },
  REJECTED: {
    ring: "border-danger bg-danger text-danger-fg", dot: "bg-danger",
    icon: <X className="h-3.5 w-3.5" aria-hidden />, label: "Revision requested",
    connector: "bg-line",
  },
  PENDING: {
    ring: "border-line-strong bg-surface text-ink-subtle", dot: "bg-line-strong",
    icon: <span className="text-2xs font-semibold" aria-hidden />, label: "Pending",
    connector: "bg-line",
  },
  LOCKED: {
    ring: "border-line bg-surface text-ink-subtle", dot: "bg-line",
    icon: <span className="text-2xs font-semibold" aria-hidden />, label: "Locked",
    connector: "bg-line",
  },
};

export interface StepperStep {
  id: number | string;
  title: string;
  description?: string | null;
  status: StageStatus;
  meta?: ReactNode;
  isCurrent?: boolean;
  action?: ReactNode;
}

/** Vertical on small screens, horizontal from `lg` up. */
export function ProgressStepper({
  steps, className, orientation = "responsive",
}: {
  steps: StepperStep[]; className?: string;
  orientation?: "vertical" | "responsive";
}) {
  const horizontal = orientation === "responsive";
  return (
    <ol
      className={cn(
        "flex flex-col gap-0",
        horizontal && "lg:flex-row lg:gap-0",
        className,
      )}
    >
      {steps.map((step, index) => {
        const state = STATE[step.status] ?? STATE.PENDING;
        const last = index === steps.length - 1;
        return (
          <li
            key={step.id}
            className={cn(
              "relative flex gap-3 pb-6 last:pb-0",
              horizontal && "lg:flex-1 lg:flex-col lg:gap-2 lg:pb-0",
            )}
          >
            {/* connector */}
            {!last && (
              <span
                aria-hidden
                className={cn(
                  "absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-0.5 rounded",
                  state.connector,
                  horizontal && "lg:left-auto lg:top-[13px] lg:ml-7 lg:h-0.5 lg:w-[calc(100%-1.75rem)]",
                )}
              />
            )}
            <span
              className={cn(
                "relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2",
                state.ring,
                step.isCurrent && "ring-4 ring-accent/15",
              )}
            >
              {step.status === "PENDING" || step.status === "LOCKED"
                ? <span className="text-2xs font-semibold">{index + 1}</span>
                : state.icon}
            </span>
            <div className={cn("min-w-0 flex-1 pt-0.5", horizontal && "lg:pr-4 lg:pt-0")}>
              <p
                className={cn(
                  "text-sm font-medium leading-tight",
                  step.status === "PENDING" || step.status === "LOCKED"
                    ? "text-ink-muted" : "text-ink",
                )}
              >
                {step.title}
              </p>
              <p className="mt-0.5 text-xs text-ink-subtle">{state.label}</p>
              {step.description && (
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                  {step.description}
                </p>
              )}
              {step.meta && <div className="mt-1.5">{step.meta}</div>}
              {step.action && <div className="mt-2">{step.action}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Compact bar used in tables and cards. */
export function ProgressBar({
  value, max = 100, label, tone = "accent", className, showValue = true,
}: {
  value: number; max?: number; label?: string;
  tone?: "accent" | "success" | "warning" | "brand"; className?: string;
  showValue?: boolean;
}) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const fill = {
    accent: "bg-accent", success: "bg-success", warning: "bg-warning", brand: "bg-brand",
  }[tone];
  return (
    <div className={cn("min-w-0", className)}>
      {(label || showValue) && (
        <div className="mb-1 flex items-baseline justify-between gap-2">
          {label && <span className="truncate text-xs text-ink-muted">{label}</span>}
          {showValue && (
            <span className="shrink-0 text-xs font-medium tabular-nums text-ink">
              {max === 100 ? `${percent}%` : `${value}/${max}`}
            </span>
          )}
        </div>
      )}
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progress"}
      >
        <div
          className={cn("h-full rounded-full transition-all duration-500", fill)}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
