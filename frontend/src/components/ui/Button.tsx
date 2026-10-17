import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

type Variant = "primary" | "accent" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand text-brand-fg hover:bg-brand-hover shadow-sm " +
    "disabled:bg-brand/50 disabled:shadow-none",
  // The interactive blue, for the one action a screen is about.
  accent:
    "bg-accent text-accent-fg hover:bg-accent-hover hover:shadow-glow-accent shadow-sm " +
    "disabled:bg-accent/50 disabled:shadow-none",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-surface-muted " +
    "active:bg-surface-muted shadow-xs disabled:shadow-none",
  ghost: "text-ink-muted hover:bg-surface-muted hover:text-ink active:bg-surface-muted/80",
  danger:
    "bg-danger text-danger-fg hover:bg-danger/90 shadow-sm disabled:bg-danger/50 disabled:shadow-none",
  subtle: "bg-accent-soft text-accent hover:bg-accent-soft/70 active:bg-accent-soft/60",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5 rounded-md",
  md: "h-9 px-3.5 text-sm gap-2 rounded-md",
  lg: "h-10 px-5 text-sm gap-2 rounded-lg",
  // 36px hit target for icon-only controls.
  icon: "h-9 w-9 justify-center rounded-md",
};

const BASE =
  "inline-flex items-center justify-center font-medium whitespace-nowrap " +
  "transition-[background-color,box-shadow,color,transform] duration-150 cursor-pointer select-none " +
  "active:scale-[0.98] disabled:active:scale-100 " +
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
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
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
