import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { listContainer, listItem } from "@/lib/motion";

const TONE_STYLES = {
  neutral: {
    value: "text-ink",
    icon: "bg-surface-muted text-ink-subtle",
  },
  brand: {
    value: "text-brand",
    icon: "bg-brand-soft text-brand",
  },
  accent: {
    value: "text-accent",
    icon: "bg-accent-soft text-accent",
  },
  success: {
    value: "text-success",
    icon: "bg-success-soft text-success",
  },
  warning: {
    value: "text-warning",
    icon: "bg-warning-soft text-warning",
  },
  danger: {
    value: "text-danger",
    icon: "bg-danger-soft text-danger",
  },
};

/**
 * Premium KPI tile. Value, label, optional hint and a tonal icon.
 * Every number shown is a real query — no fake trend percentages.
 */
export function StatTile({
  label, value, hint, icon: Icon, to, tone = "neutral", className,
}: {
  label: string; value: string | number; hint?: string | null;
  icon?: LucideIcon; to?: string | null;
  tone?: keyof typeof TONE_STYLES; className?: string;
}) {
  const styles = TONE_STYLES[tone];

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-subtle leading-tight">
          {label}
        </p>
        {Icon && (
          <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", styles.icon)}>
            <Icon className="h-3.5 w-3.5" aria-hidden />
          </span>
        )}
      </div>
      <p className={cn("mt-2.5 font-heading text-[1.75rem] font-semibold leading-none tabular-nums", styles.value)}>
        {value}
      </p>
      {hint && <p className="mt-1.5 truncate text-xs text-ink-subtle">{hint}</p>}
    </>
  );

  const classes = cn(
    "block h-full rounded-xl border border-line bg-surface p-4 shadow-sm",
    "transition-all duration-200",
    to && "cursor-pointer hover:border-line-strong hover:shadow-card-hover hover:-translate-y-px",
    className,
  );

  return (
    <motion.div variants={listItem} className="h-full">
      {to ? <Link to={to} className={classes}>{body}</Link> : <div className={classes}>{body}</div>}
    </motion.div>
  );
}

export function StatGrid({
  children, columns = 4, className,
}: { children: React.ReactNode; columns?: 3 | 4 | 5 | 6; className?: string }) {
  const cols = {
    3: "sm:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
    5: "sm:grid-cols-3 lg:grid-cols-5",
    6: "sm:grid-cols-3 lg:grid-cols-6",
  }[columns];
  return (
    <motion.div
      variants={listContainer}
      initial="hidden"
      animate="shown"
      className={cn("grid grid-cols-2 gap-3", cols, className)}
    >
      {children}
    </motion.div>
  );
}
