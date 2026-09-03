import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { transition } from "@/lib/motion";

export interface TabItem {
  key: string;
  label: string;
  count?: number;
  icon?: ReactNode;
}

/** Shared so a tab and its panel derive the same ids and can point at each other. */
const tabId = (group: string, key: string) => `${group}-tab-${key}`;
const panelId = (group: string, key: string) => `${group}-panel-${key}`;

export function Tabs({
  tabs, active, onChange, className, size = "md", group = "tabs",
  withPanels = false,
}: {
  tabs: TabItem[]; active: string; onChange: (key: string) => void;
  className?: string; size?: "sm" | "md";
  /** Distinguishes id namespaces when a page renders more than one tab set. */
  group?: string;
  /**
   * Set only when the tab content is rendered through <TabPanel> with the same
   * `group`. `aria-controls` has to point at an element that actually exists —
   * a reference to a missing id is worse than omitting it, because assistive
   * technology announces a relationship the user then cannot follow. Every
   * caller in this app currently renders its content directly rather than in a
   * TabPanel, so this stays off by default.
   */
  withPanels?: boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  /**
   * The tabs pattern expects arrow keys to move between tabs while Tab itself
   * jumps out to the panel — so only the selected tab stays in the tab order
   * (a "roving tabindex"). Without this, a keyboard user has to step through
   * every tab in the set to reach the content.
   */
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();

    const index = tabs.findIndex((t) => t.key === active);
    if (index === -1) return;

    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;

    const target = tabs[next];
    if (!target) return;
    onChange(target.key);
    listRef.current
      ?.querySelector<HTMLButtonElement>(`#${CSS.escape(tabId(group, target.key))}`)
      ?.focus();
  }

  return (
    <div className={cn("overflow-x-auto border-b border-line", className)}>
      <div
        ref={listRef}
        role="tablist"
        onKeyDown={onKeyDown}
        className="flex min-w-max gap-1"
      >
        {tabs.map((tab) => {
          const selected = tab.key === active;
          return (
            <button
              key={tab.key}
              id={tabId(group, tab.key)}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={withPanels ? panelId(group, tab.key) : undefined}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.key)}
              className={cn(
                "relative flex cursor-pointer items-center gap-1.5 whitespace-nowrap " +
                "border-b-2 border-transparent font-medium transition-colors duration-200",
                size === "sm" ? "px-3 py-2 text-xs" : "px-3.5 py-2.5 text-sm",
                selected
                  ? "text-accent"
                  : "text-ink-muted hover:border-line-strong hover:text-ink",
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
              {/*
                One underline shared across tabs via `layoutId`, so it slides
                from the old tab to the new one instead of blinking out and in.
                Rendered as a sibling of the border so the inactive hover border
                still works.
              */}
              {selected && (
                <motion.span
                  layoutId={`${group}-tab-underline`}
                  transition={transition}
                  className="absolute inset-x-0 -bottom-0.5 h-0.5 rounded-full bg-accent"
                  aria-hidden
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TabPanel({
  when, active, children, group = "tabs",
}: { when: string; active: string; children: ReactNode; group?: string }) {
  if (when !== active) return null;
  return (
    <div
      id={panelId(group, when)}
      role="tabpanel"
      aria-labelledby={tabId(group, when)}
      tabIndex={0}
      className="animate-fade-in focus-visible:outline-none"
    >
      {children}
    </div>
  );
}
