import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const TONES = {
  accent: "text-accent",
  iris: "text-iris",
  success: "text-success-solid",
  warning: "text-warning-solid",
  neutral: "text-line-strong",
} as const;

/**
 * A progress ring. It draws only the figure it is given — the caller passes a
 * real count and its real ceiling, never a target someone typed into the UI.
 */
export function ScoreRing({
  value, max, size = 88, stroke = 8, tone = "accent", label, children, className,
}: {
  value: number; max: number; size?: number; stroke?: number;
  tone?: keyof typeof TONES;
  /** What the ring means, for screen readers: "6 of 18 credits earned". */
  label: string;
  /** Drawn in the centre — usually the figure itself. */
  children?: ReactNode;
  className?: string;
}) {
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  return (
    <div
      role="img"
      aria-label={label}
      className={cn("relative inline-flex shrink-0 items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke}
          className="stroke-surface-muted"
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke}
          stroke="currentColor" strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          className={cn("transition-[stroke-dashoffset] duration-700 ease-out motion-reduce:transition-none", TONES[tone])}
        />
      </svg>
      {children && (
        <div aria-hidden className="absolute inset-0 flex flex-col items-center justify-center text-center">
          {children}
        </div>
      )}
    </div>
  );
}
