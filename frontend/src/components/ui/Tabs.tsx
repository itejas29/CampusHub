import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  key: string;
  label: string;
  count?: number;
  icon?: ReactNode;
}

export function Tabs({
  tabs, active, onChange, className, size = "md",
}: {
  tabs: TabItem[]; active: string; onChange: (key: string) => void;
  className?: string; size?: "sm" | "md";
}) {
  return (
    <div className={cn("overflow-x-auto border-b border-line", className)}>
      <div role="tablist" className="flex min-w-max gap-1">
        {tabs.map((tab) => {
          const selected = tab.key === active;
          return (
            <button
              key={tab.key}
              role="tab"
              type="button"
              aria-selected={selected}
              onClick={() => onChange(tab.key)}
              className={cn(
                "relative flex cursor-pointer items-center gap-1.5 whitespace-nowrap " +
                "border-b-2 font-medium transition-colors duration-200",
                size === "sm" ? "px-3 py-2 text-xs" : "px-3.5 py-2.5 text-sm",
                selected
                  ? "border-accent text-accent"
                  : "border-transparent text-ink-muted hover:border-line-strong hover:text-ink",
              )}
            >
              {tab.icon}
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-2xs font-semibold tabular-nums",
                    selected ? "bg-accent-soft text-accent" : "bg-surface-muted text-ink-subtle",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TabPanel({
  when, active, children,
}: { when: string; active: string; children: ReactNode }) {
  if (when !== active) return null;
  return <div role="tabpanel" className="animate-fade-in">{children}</div>;
}
