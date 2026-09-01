import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand text-brand-fg hover:bg-brand/90 active:bg-brand/95 shadow-xs " +
    "disabled:bg-brand/50",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-surface-muted " +
    "active:bg-surface-muted shadow-xs",
  ghost: "text-ink-muted hover:bg-surface-muted hover:text-ink",
  danger: "bg-danger text-danger-fg hover:bg-danger/90 shadow-xs disabled:bg-danger/50",
  subtle: "bg-accent-soft text-accent hover:bg-accent-soft/70",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
  lg: "h-11 px-5 text-base gap-2",
  // 40px hit target for icon-only controls.
  icon: "h-9 w-9 justify-center",
};

const BASE =
  "inline-flex items-center justify-center rounded font-medium whitespace-nowrap " +
  "transition-colors duration-200 cursor-pointer select-none " +
  "disabled:cursor-not-allowed disabled:opacity-60";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, iconRight, className,
    children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        icon
      )}
      {children}
      {!loading && iconRight}
    </button>
  );
});

export function LinkButton({
  to, variant = "primary", size = "md", icon, iconRight, className, children,
}: {
  to: string; variant?: Variant; size?: Size; icon?: ReactNode;
  iconRight?: ReactNode; className?: string; children: ReactNode;
}) {
  return (
    <Link to={to} className={cn(BASE, VARIANTS[variant], SIZES[size], className)}>
      {icon}
      {children}
      {iconRight}
    </Link>
  );
}
