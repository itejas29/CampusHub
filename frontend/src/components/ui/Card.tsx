import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export function Card({
  children, className, as: Tag = "section",
}: { children: ReactNode; className?: string; as?: "section" | "div" | "article" }) {
  return (
    // `min-w-0` matters: as a grid/flex child the default `min-width:auto`
    // would let a wide table stretch the card instead of scrolling inside it.
    <Tag
      className={cn(
        "min-w-0 rounded-lg border border-line bg-surface shadow-xs",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title, description, action, className, icon,
}: {
  title: ReactNode; description?: ReactNode; action?: ReactNode;
  className?: string; icon?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 border-b border-line " +
        "px-5 py-3.5",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-md font-semibold text-ink">
          {icon}
          {title}
        </h2>
        {description && (
          <p className="mt-0.5 text-sm text-ink-muted">{description}</p>
        )}
      </div>
      {action && (
        <div className="flex min-w-0 flex-wrap items-center gap-2">{action}</div>
      )}
    </div>
  );
}

export function CardBody({
  children, className, flush,
}: { children: ReactNode; className?: string; flush?: boolean }) {
  return <div className={cn(!flush && "p-5", className)}>{children}</div>;
}

export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("border-t border-line bg-surface-muted/40 px-5 py-3", className)}>
      {children}
    </div>
  );
}

/**
 * The "see all" link that sits in a CardHeader's `action` slot.
 *
 * Exists mainly to guarantee the hit area. As a bare `text-xs` link this
 * rendered about 15x18px — under the 24x24 CSS px minimum in WCAG 2.2 SC 2.5.8.
 * The exception for links inline in a sentence does not apply here, because
 * these are standalone controls in a header rather than words in prose.
 *
 * The label is often just "All", which tells a screen-reader user nothing on
 * its own, so `label` supplies the accessible name while the shorter text stays
 * visible.
 */
export function CardAction({
  to, children, label, className,
}: { to: string; children: ReactNode; label?: string; className?: string }) {
  return (
    <Link
      to={to}
      aria-label={label}
      className={cn(
        "-mr-1.5 inline-flex min-h-6 items-center rounded px-1.5 text-xs text-accent",
        "transition-colors hover:bg-accent-soft hover:underline",
        className,
      )}
    >
      {children}
    </Link>
  );
}
