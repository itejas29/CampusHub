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
        "min-w-0 rounded-xl border border-line bg-surface shadow-sm",
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
        "flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-md font-semibold tracking-tight text-ink">
          {icon}
          {title}
        </h2>
        {description && (
          <p className="mt-0.5 text-sm text-ink-muted leading-snug">{description}</p>
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
    <div className={cn("border-t border-line bg-surface-muted/30 px-5 py-3 rounded-b-xl", className)}>
      {children}
    </div>
  );
}

/**
 * The "see all" link that sits in a CardHeader's `action` slot.
 */
export function CardAction({
  to, children, label, className,
}: { to: string; children: ReactNode; label?: string; className?: string }) {
  return (
    <Link
      to={to}
      aria-label={label}
      className={cn(
        "-mr-1 inline-flex min-h-6 items-center rounded-md px-2 py-0.5 text-xs font-medium text-accent",
        "transition-colors hover:bg-accent-soft hover:text-accent",
        className,
      )}
    >
      {children}
    </Link>
  );
}

/**
 * Clickable card variant — used on event cards, club cards, etc.
 * Has a subtle hover lift for a premium feel.
 */
export function ClickCard({
  children, className, as: Tag = "div", onClick,
}: {
  children: ReactNode; className?: string;
  as?: "div" | "article";
  onClick?: () => void;
}) {
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "min-w-0 rounded-xl border border-line bg-surface shadow-sm",
        "cursor-pointer transition-all duration-200",
        "hover:border-line-strong hover:shadow-card-hover hover:-translate-y-px",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
