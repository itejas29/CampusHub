import {
  differenceInCalendarDays, format, formatDistanceToNowStrict, isPast, parseISO,
} from "date-fns";

function toDate(value?: string | Date | null): Date | null {
  if (!value) return null;
  const date = typeof value === "string" ? parseISO(value) : value;
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value?: string | Date | null, pattern = "d MMM yyyy"): string {
  const date = toDate(value);
  return date ? format(date, pattern) : "—";
}

export function formatDateTime(value?: string | Date | null): string {
  const date = toDate(value);
  return date ? format(date, "d MMM yyyy, HH:mm") : "—";
}

export function formatTime(value?: string | Date | null): string {
  const date = toDate(value);
  return date ? format(date, "HH:mm") : "—";
}

export function relativeTime(value?: string | Date | null): string {
  const date = toDate(value);
  if (!date) return "—";
  return isPast(date)
    ? `${formatDistanceToNowStrict(date)} ago`
    : `in ${formatDistanceToNowStrict(date)}`;
}

/** Human deadline copy plus an urgency level the UI colours by. */
export function deadlineLabel(value?: string | Date | null): {
  text: string;
  tone: "neutral" | "warning" | "danger" | "success";
} {
  const date = toDate(value);
  if (!date) return { text: "No deadline set", tone: "neutral" };
  const days = differenceInCalendarDays(date, new Date());
  if (days < 0) return { text: `Closed ${formatDate(date)}`, tone: "danger" };
  if (days === 0) return { text: "Closes today", tone: "danger" };
  if (days === 1) return { text: "Closes tomorrow", tone: "warning" };
  if (days <= 7) return { text: `Closes in ${days} days`, tone: "warning" };
  return { text: `Closes ${formatDate(date)}`, tone: "neutral" };
}

export function formatNumber(value?: number | null, fallback = "—"): string {
  return value === null || value === undefined ? fallback : new Intl.NumberFormat().format(value);
}

export function formatMarks(value?: number | null, max?: number | null): string {
  if (value === null || value === undefined) return "—";
  const rounded = Number.isInteger(value) ? value : Number(value.toFixed(2));
  return max ? `${rounded} / ${max}` : String(rounded);
}

export function formatCurrency(value?: number | null): string {
  if (!value) return "Unpaid";
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(value);
}


/** Human file size for upload metadata. */
export function formatBytes(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}
