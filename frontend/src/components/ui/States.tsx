import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { cn } from "@/lib/utils";

export function LoadingState({
  label = "Loading…", className, rows = 3,
}: { label?: string; className?: string; rows?: number }) {
  return (
    <div className={cn("space-y-3 p-5", className)} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3.5">
          <div className="skeleton h-10 w-10 shrink-0 rounded-lg" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3.5 rounded-md" style={{ width: `${75 - i * 15}%` }} />
            <div className="skeleton h-2.5 rounded-md" style={{ width: `${50 - i * 10}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border border-line bg-surface p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <div className="skeleton h-4 w-1/3 rounded" />
            <div className="skeleton h-5 w-16 rounded-full" />
          </div>
          <div className="skeleton mt-4 h-3 w-full rounded" />
          <div className="skeleton mt-2 h-3 w-4/5 rounded" />
          <div className="mt-6 flex items-center justify-between pt-2">
            <div className="skeleton h-7 w-24 rounded-md" />
            <div className="skeleton h-4 w-16 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title, description, action, icon, className, compact,
}: {
  title: string; description?: string; action?: ReactNode; icon?: ReactNode;
  className?: string; compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "px-4 py-8" : "px-6 py-14",
        className,
      )}
    >
      <div className="mb-3.5 flex h-12 w-12 items-center justify-center rounded-xl border border-line/60 bg-surface-muted/60 text-ink-subtle shadow-xs">
        {icon ?? <Inbox className="h-5 w-5" aria-hidden />}
      </div>
      <h3 className="text-sm font-semibold tracking-tight text-ink">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-ink-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong", message, onRetry, className, compact,
}: {
  title?: string; message?: string; onRetry?: () => void;
  className?: string; compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "px-4 py-8" : "px-6 py-12",
        className,
      )}
      role="alert"
    >
      <div className="mb-3.5 flex h-12 w-12 items-center justify-center rounded-xl border border-danger/20 bg-danger-soft text-danger shadow-xs">
        <AlertCircle className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="text-sm font-semibold tracking-tight text-ink">{title}</h3>
      <p className="mt-1.5 max-w-md text-xs leading-relaxed text-ink-muted">
        {message ?? "The request could not be completed. Please try again."}
      </p>
      {onRetry && (
        <Button
          variant="secondary" size="sm" className="mt-4 shadow-xs" onClick={onRetry}
          icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden />}
        >
          Try again
        </Button>
      )}
    </div>
  );
}

/** Standard query-state wrapper so every list behaves identically. */
export function QueryState({
  isLoading, error, isEmpty, empty, onRetry, children, loadingRows,
}: {
  isLoading: boolean; error: unknown; isEmpty?: boolean;
  empty?: ReactNode; onRetry?: () => void; children: ReactNode; loadingRows?: number;
}) {
  if (isLoading) return <LoadingState rows={loadingRows} />;
  if (error) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={onRetry}
      />
    );
  }
  if (isEmpty) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return <>{children}</>;
}
