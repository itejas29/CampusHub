import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Tables always live inside a horizontal-scroll container so a wide table
 * never forces the page to scroll sideways on small screens.
 */
export function TableWrap({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("w-full min-w-0 overflow-x-auto", className)}>
      <table className="w-full min-w-[40rem] border-collapse text-left">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-line bg-surface-muted/60">
      <tr>{children}</tr>
    </thead>
  );
}

export function TH({
  children, className, align = "left", width,
}: {
  children?: ReactNode; className?: string;
  align?: "left" | "right" | "center"; width?: string;
}) {
  return (
    <th
      scope="col"
      style={width ? { width } : undefined}
      className={cn(
        "px-4 py-2.5 text-2xs font-semibold uppercase tracking-wide text-ink-subtle",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>;
}

export function TR({
  children, className, onClick, selected,
}: {
  children: ReactNode; className?: string; onClick?: () => void; selected?: boolean;
}) {
  return (
    <tr
      onClick={onClick}
      onKeyDown={onClick ? (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); }
      } : undefined}
      // Stays a row: `role="button"` here erased the table's row/cell structure
      // for screen readers. Focusable, with Enter/Space, is enough to operate it.
      tabIndex={onClick ? 0 : undefined}
      className={cn(
        "transition-colors duration-150",
        onClick && "cursor-pointer hover:bg-surface-muted/70 focus-visible:bg-surface-muted",
        selected && "bg-accent-soft/40",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function TD({
  children, className, align = "left", colSpan,
}: {
  children?: ReactNode; className?: string;
  align?: "left" | "right" | "center"; colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={cn(
        "px-4 py-2.5 align-middle text-sm text-ink",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function TableEmpty({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10 text-center text-sm text-ink-muted">
        {children}
      </td>
    </tr>
  );
}
