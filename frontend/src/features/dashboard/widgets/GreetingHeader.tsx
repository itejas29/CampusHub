import { format } from "date-fns";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/**
 * The top of every role's dashboard: today's date, a greeting by name, who the
 * portal thinks you are, and the one or two doors you use most.
 */
export function GreetingHeader({
  name, context, subtitle, chips, actions,
}: {
  name: string;
  /** Follows the date: "Student portal · AY 2025-26". */
  context?: ReactNode;
  subtitle?: ReactNode;
  /** `<HeaderChip>`s — programme, semester, roles. */
  chips?: ReactNode;
  actions?: ReactNode;
}) {
  const today = new Date();
  return (
    <section
      aria-labelledby="dashboard-greeting"
      className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between"
    >
      <div className="min-w-0">
        <p className="text-xs font-medium text-ink-subtle">
          <time dateTime={format(today, "yyyy-MM-dd")}>{format(today, "EEEE, d MMMM yyyy")}</time>
          {context && <span> · {context}</span>}
        </p>
        <h1
          id="dashboard-greeting"
          className="mt-1 font-heading text-2xl font-semibold tracking-tight text-ink sm:text-[1.75rem]"
        >
          {greeting(today)}, <span className="break-anywhere text-iris">{name}</span>
        </h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
        {chips && <ul className="mt-3 flex flex-wrap gap-2">{chips}</ul>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </section>
  );
}

export function HeaderChip({
  children, icon, mono, tone = "neutral",
}: {
  children: ReactNode; icon?: ReactNode; mono?: boolean;
  tone?: "neutral" | "success" | "warning";
}) {
  return (
    <li
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium shadow-2xs",
        tone === "neutral" && "border-line bg-surface text-ink-muted",
        tone === "success" && "border-success/20 bg-success-soft text-success",
        tone === "warning" && "border-warning/25 bg-warning-soft text-warning",
        mono && "font-mono",
      )}
    >
      {icon}
      {children}
    </li>
  );
}

const BANNER_TONES = {
  iris: "border-iris/20 bg-iris-soft",
  warning: "border-warning/25 bg-warning-soft",
  success: "border-success/20 bg-success-soft",
} as const;

const BANNER_ICON_TONES = {
  iris: "text-iris", warning: "text-warning", success: "text-success",
} as const;

/**
 * The one thing most worth doing next, said plainly. Its sentence is built from
 * the dashboard's own records — it is never a slogan.
 */
export function FocusBanner({
  tone = "iris", icon, title, description, action,
}: {
  tone?: keyof typeof BANNER_TONES; icon: ReactNode; title: ReactNode;
  description?: ReactNode; action?: ReactNode;
}) {
  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-2xl border p-5 sm:flex-row sm:items-center sm:p-6",
        BANNER_TONES[tone],
      )}
    >
      <span
        className={cn(
          "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-surface shadow-xs",
          BANNER_ICON_TONES[tone],
        )}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-heading text-base font-semibold leading-snug text-ink break-anywhere">{title}</p>
        {description && <p className="mt-0.5 text-sm text-ink-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </section>
  );
}
