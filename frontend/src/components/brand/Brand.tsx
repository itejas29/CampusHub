import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * CampusHub's own mark — an original design, not PDEU's emblem.
 *
 * A ring left open on the right (a "C", for Campus) with three nodes on it,
 * each wired to a hub at the centre: one place every part of campus life
 * connects to. The tile's navy-to-electric gradient is the portal's brand
 * gradient. Drawn as one inline SVG, so it costs nothing to render.
 */
export function CampusHubMark({ className, title = "CampusHub" }: { className?: string; title?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 32 32" className={cn("h-8 w-8 shrink-0", className)} role="img" aria-label={title}>
      <defs>
        <linearGradient id={`chm-${id}`} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0B2545" />
          <stop offset="0.55" stopColor="#1D4ED8" />
          <stop offset="1" stopColor="#6366F1" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8.5" fill={`url(#chm-${id})`} />
      {/* spokes */}
      <g stroke="#fff" strokeOpacity="0.55" strokeWidth="1.4" strokeLinecap="round">
        <path d="M16 16V7.5M16 16H7.5M16 16v8.5" />
      </g>
      {/* the open ring — a C */}
      <path d="M22.51 10.54A8.5 8.5 0 1 0 22.51 21.46" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      {/* nodes on the ring, and the hub */}
      <g fill="#A5BEFF">
        <circle cx="16" cy="7.5" r="1.9" />
        <circle cx="7.5" cy="16" r="1.9" />
        <circle cx="16" cy="24.5" r="1.9" />
      </g>
      <circle cx="16" cy="16" r="2.7" fill="#fff" />
      <circle cx="22.51" cy="10.54" r="1.5" fill="#C4B5FD" />
    </svg>
  );
}

/**
 * The signature motif: a thin energy grid — circuit traces with nodes — for an
 * energy university. Static SVG, no animation, and pointer-events off, so it
 * adds texture without costing frames. Fades out toward its edges.
 */
export function EnergyGrid({ className, tone = "light" }: { className?: string; tone?: "light" | "dark" }) {
  const id = useId().replace(/:/g, "");
  const ink = tone === "dark" ? "rgb(255 255 255)" : "rgb(var(--c-accent))";
  return (
    <svg aria-hidden className={cn("pointer-events-none select-none", className)} viewBox="0 0 480 240" preserveAspectRatio="xMaxYMid slice">
      <defs>
        <radialGradient id={`egf-${id}`} cx="85%" cy="40%" r="75%">
          <stop offset="0" stopColor="#fff" stopOpacity="1" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
        <mask id={`egm-${id}`}><rect width="480" height="240" fill={`url(#egf-${id})`} /></mask>
      </defs>
      <g mask={`url(#egm-${id})`} stroke={ink} fill="none" strokeWidth="1" strokeOpacity={tone === "dark" ? 0.16 : 0.18} strokeLinecap="round" strokeLinejoin="round">
        <path d="M480 40H392l-24 24H296l-16-16h-64" />
        <path d="M480 96H420l-20 20h-72l-28 28H232" />
        <path d="M480 150h-44l-18-18h-58l-22 22h-84" />
        <path d="M480 200H404l-26-26h-62l-20 20h-48" />
        <path d="M392 0v40M336 64v52M300 144v56M436 150v90M368 196v44" />
        <path d="M260 0l36 48M232 144l-40 40" />
      </g>
      <g mask={`url(#egm-${id})`} fill={ink} fillOpacity={tone === "dark" ? 0.32 : 0.3}>
        {[[392, 40], [296, 64], [216, 48], [400, 116], [300, 144], [232, 144], [418, 132], [336, 154], [252, 154], [378, 174], [296, 194], [248, 194], [336, 116], [436, 150]].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="2.4" />
        ))}
      </g>
    </svg>
  );
}
