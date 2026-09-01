import { AlertTriangle, CheckCircle2, Info, XCircle, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "info" | "success" | "warning" | "danger";

const STYLES: Record<Variant, { box: string; icon: ReactNode }> = {
  info: {
    box: "bg-info-soft/60 border-info/30 text-ink",
    icon: <Info className="h-4 w-4 text-info" aria-hidden />,
  },
  success: {
    box: "bg-success-soft/60 border-success/30 text-ink",
    icon: <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />,
  },
  warning: {
    box: "bg-warning-soft/60 border-warning/30 text-ink",
    icon: <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />,
  },
  danger: {
    box: "bg-danger-soft/60 border-danger/30 text-ink",
    icon: <XCircle className="h-4 w-4 text-danger" aria-hidden />,
  },
};

export function Alert({
  variant = "info", title, children, className, onDismiss, action,
}: {
  variant?: Variant; title?: string; children?: ReactNode; className?: string;
  onDismiss?: () => void; action?: ReactNode;
}) {
  const style = STYLES[variant];
  return (
    <div
      role={variant === "danger" ? "alert" : "status"}
      className={cn("flex gap-2.5 rounded-md border px-3.5 py-3 text-sm", style.box, className)}
    >
      <span className="mt-0.5 shrink-0">{style.icon}</span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold text-ink">{title}</p>}
        {children && <div className={cn("text-ink-muted", title && "mt-0.5")}>{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-mr-1 -mt-1 h-6 w-6 shrink-0 cursor-pointer rounded text-ink-subtle transition-colors hover:bg-black/5 hover:text-ink"
        >
          <X className="mx-auto h-3.5 w-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
