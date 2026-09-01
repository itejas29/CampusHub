import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { cn } from "@/lib/utils";

export function LoadingState({
  label = "Loading…", className, rows = 3,
}: { label?: string; className?: string; rows?: number }) {
  return (
    <div className={cn("space-y-2 p-5", className)} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="skeleton h-9 w-9 shrink-0 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <div className="skeleton h-3 rounded" style={{ width: `${70 - i * 12}%` }} />
            <div className="skeleton h-2.5 rounded" style={{ width: `${45 - i * 8}%` }} />
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
        <div key={i} className="rounded-lg border border-line bg-surface p-5">
          <div className="skeleton h-3.5 w-1/2 rounded" />
          <div className="skeleton mt-3 h-2.5 w-full rounded" />
          <div className="skeleton mt-2 h-2.5 w-4/5 rounded" />
          <div className="skeleton mt-5 h-7 w-24 rounded" />
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
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-surface-muted text-ink-subtle">
        {icon ?? <Inbox className="h-5 w-5" aria-hidden />}
      </div>
      <h3 className="text-md font-semibold text-ink">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p>
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
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-danger-soft text-danger">
        <AlertCircle className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="text-md font-semibold text-ink">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-ink-muted">
        {message ?? "The request could not be completed. Please try again."}
      </p>
      {onRetry && (
        <Button
          variant="secondary" size="sm" className="mt-4" onClick={onRetry}
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
