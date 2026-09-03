import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { listContainer, listItem } from "@/lib/motion";

/**
 * Compact KPI tile. Deliberately plain: value + label + optional hint. No
 * sparklines or invented trend percentages — every number is a real query.
 */
export function StatTile({
  label, value, hint, icon: Icon, to, tone = "neutral", className,
}: {
  label: string; value: string | number; hint?: string | null;
  icon?: LucideIcon; to?: string | null;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger"; className?: string;
}) {
  const tones = {
    neutral: "text-ink", accent: "text-accent", success: "text-success",
    warning: "text-warning", danger: "text-danger",
  };
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-ink-muted">{label}</p>
        {Icon && <Icon className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />}
      </div>
      <p className={cn("mt-1.5 font-heading text-2xl font-semibold tabular-nums", tones[tone])}>
        {value}
      </p>
      {hint && <p className="mt-0.5 truncate text-xs text-ink-subtle">{hint}</p>}
    </>
  );

  const classes = cn(
    "block h-full rounded-lg border border-line bg-surface p-4 shadow-xs transition-colors duration-200",
    to && "cursor-pointer hover:border-line-strong hover:bg-surface-muted/40",
    className,
  );

  /*
   * `variants` without `initial`/`animate` means this inherits the animation
   * state of a motion parent — StatGrid below. Rendered outside one it simply
   * stays put, so a tile used on its own is never left invisible.
   */
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
    3: "sm:grid-cols-3", 4: "sm:grid-cols-2 lg:grid-cols-4",
    5: "sm:grid-cols-3 lg:grid-cols-5", 6: "sm:grid-cols-3 lg:grid-cols-6",
  }[columns];
  /*
   * The stagger lives on the container, so it stays correct no matter how many
   * tiles a dashboard renders — no per-tile delay to keep in sync.
   */
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
