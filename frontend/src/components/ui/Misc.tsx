import { ChevronRight, Search, Upload, X } from "lucide-react";
import {
  useCallback, useEffect, useId, useRef, useState,
  type InputHTMLAttributes, type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { cn, initials } from "@/lib/utils";
import { EnergyGrid } from "@/components/brand/Brand";
import { popoverPanel } from "@/lib/motion";

export function Avatar({
  name, src, size = "md", className,
}: {
  name?: string | null; src?: string | null;
  size?: "xs" | "sm" | "md" | "lg"; className?: string;
}) {
  const sizes = {
    xs: "h-6 w-6 text-2xs", sm: "h-8 w-8 text-xs",
    md: "h-9 w-9 text-xs", lg: "h-12 w-12 text-sm",
  };
  if (src) {
    return (
      <img
        src={src}
        alt=""
        className={cn("shrink-0 rounded-full border border-line object-cover shadow-2xs", sizes[size], className)}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full border border-brand/20 bg-brand-soft font-semibold text-brand shadow-2xs",
        sizes[size], className,
      )}
    >
      {initials(name)}
    </span>
  );
}

export function Breadcrumbs({
  items,
}: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1.5 text-xs text-ink-subtle">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && <ChevronRight className="h-3 w-3 shrink-0 opacity-60" aria-hidden />}
            {item.to && index < items.length - 1 ? (
              <Link to={item.to} className="rounded transition-colors hover:text-ink font-medium">
                {item.label}
              </Link>
            ) : (
              <span className={index === items.length - 1 ? "font-semibold text-ink" : undefined}>
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({
  title, description, actions, breadcrumbs, meta, className, bordered = true,
}: {
  title: string; description?: ReactNode; actions?: ReactNode;
  breadcrumbs?: { label: string; to?: string }[]; meta?: ReactNode; className?: string;
  bordered?: boolean;
}) {
  return (
    <header
      className={cn(
        "relative mb-6",
        // The signature band: a hairline brand gradient on top and the energy
        // grid fading in on the right. Static SVG and CSS — no runtime cost.
        bordered && "overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-surface via-surface to-surface-soft px-5 pb-5 pt-5 shadow-xs sm:px-6",
        className,
      )}
    >
      {bordered && (
        <>
          <span aria-hidden className="absolute inset-x-0 top-0 h-[3px] bg-accent-gradient" />
          <EnergyGrid className="absolute inset-y-0 right-0 hidden h-full w-[58%] max-w-[34rem] sm:block" />
        </>
      )}
      <div className="relative">
      {breadcrumbs && <div className="mb-2.5"><Breadcrumbs items={breadcrumbs} /></div>}
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* A minimum basis lets the actions wrap below on a phone instead of
            squeezing the title into a narrow column beside them. */}
        <div className="min-w-0 flex-1 basis-[18rem]">
          <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl font-display">
            {title}
          </h1>
          {description && (
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-muted">{description}</p>
          )}
          {meta && <div className="mt-2.5 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2.5 pt-0.5">{actions}</div>
        )}
      </div>
      </div>
    </header>
  );
}

export function SearchInput({
  value, onChange, placeholder = "Search…", shortcut, className, ...props
}: {
  value: string; onChange: (value: string) => void; placeholder?: string;
  shortcut?: string; className?: string;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <div className={cn("relative", className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle"
        aria-hidden
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-8.5 w-full rounded-md border border-line-strong bg-surface pl-8.5 pr-8 text-xs text-ink transition-all placeholder:text-ink-subtle hover:border-ink-muted/50 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand/20"
        {...props}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 cursor-pointer items-center justify-center rounded text-ink-subtle transition-colors hover:text-ink"
        >
          <X className="h-3 w-3" aria-hidden />
        </button>
      ) : shortcut ? (
        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-line bg-surface-muted px-1.5 py-0.5 font-mono text-3xs font-medium text-ink-subtle">
          {shortcut}
        </span>
      ) : null}
    </div>
  );
}

/** Two-column definition list used across all detail views. */
export function DetailList({
  items, columns = 2, className,
}: {
  items: { label: string; value: ReactNode }[]; columns?: 1 | 2 | 3; className?: string;
}) {
  const cols = { 1: "sm:grid-cols-1", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3" }[columns];
  return (
    <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-3.5", cols, className)}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-2xs font-semibold uppercase tracking-wider text-ink-subtle font-mono">
            {item.label}
          </dt>
          <dd className="mt-0.5 break-words text-sm font-medium text-ink">
            {item.value ?? <span className="text-ink-subtle">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function FileUpload({
  onSelect, accept = ".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.ppt,.pptx",
  label = "Choose a file", hint, disabled, selectedName,
}: {
  onSelect: (file: File | null) => void; accept?: string; label?: string;
  hint?: string; disabled?: boolean; selectedName?: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled && e.dataTransfer.files?.[0]) onSelect(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border border-dashed px-4 py-7 text-center transition-all",
          dragging ? "border-brand bg-brand-soft/40 ring-2 ring-brand/10" : "border-line-strong bg-surface-muted/30 hover:bg-surface-muted/50",
          disabled && "opacity-60",
        )}
      >
        <div className="mb-2.5 flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink-subtle shadow-xs">
          <Upload className="h-4 w-4" aria-hidden />
        </div>
        {selectedName ? (
          <p className="text-sm font-medium text-ink">{selectedName}</p>
        ) : (
          <p className="text-sm text-ink-muted">
            Drag a file here, or{" "}
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="cursor-pointer rounded font-semibold text-brand underline underline-offset-2 hover:text-brand-hover disabled:cursor-not-allowed"
            >
              browse
            </button>
          </p>
        )}
        <p className="mt-1 text-xs text-ink-subtle">
          {hint ?? "PDF, image, Word or PowerPoint · up to 15 MB"}
        </p>
        {selectedName && (
          <button
            type="button"
            onClick={() => { onSelect(null); if (inputRef.current) inputRef.current.value = ""; }}
            className="mt-2.5 cursor-pointer rounded text-xs text-danger underline underline-offset-2 hover:opacity-80"
          >
            Remove file
          </button>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          disabled={disabled}
          className="sr-only"
          aria-label={label}
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </div>
    </div>
  );
}

export function Divider({ label, className }: { label?: string; className?: string }) {
  if (!label) return <hr className={cn("border-line", className)} />;
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <hr className="flex-1 border-line" />
      <span className="text-2xs font-semibold uppercase tracking-wider text-ink-subtle font-mono">
        {label}
      </span>
      <hr className="flex-1 border-line" />
    </div>
  );
}

/** Lightweight dropdown that closes on outside click and Escape. */
export function Popover({
  trigger, children, align = "right", className, panelClassName,
}: {
  trigger: (props: {
    open: boolean;
    toggle: () => void;
    triggerProps: {
      "aria-expanded": boolean;
      "aria-haspopup": "menu";
      "aria-controls": string | undefined;
    };
  }) => ReactNode;
  children: (props: { close: () => void }) => ReactNode;
  align?: "left" | "right"; className?: string; panelClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const focusTrigger = useCallback(() => {
    triggerRef.current
      ?.querySelector<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])')
      ?.focus();
  }, []);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        focusTrigger();
      }
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, focusTrigger]);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <div ref={triggerRef} className="contents">
        {trigger({
          open,
          toggle: () => setOpen((v) => !v),
          triggerProps: {
            "aria-expanded": open,
            "aria-haspopup": "menu",
            "aria-controls": open ? panelId : undefined,
          },
        })}
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            id={panelId}
            variants={popoverPanel}
            initial="hidden"
            animate="shown"
            exit="exit"
            style={{ transformOrigin: align === "right" ? "top right" : "top left" }}
            className={cn(
              "absolute z-40 mt-1.5 min-w-[15rem] rounded-xl border border-line bg-surface p-1 shadow-md",
              align === "right" ? "right-0" : "left-0",
              panelClassName,
            )}
          >
            {children({ close })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
