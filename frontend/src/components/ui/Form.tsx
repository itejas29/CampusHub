import { AlertCircle, Check, ChevronDown } from "lucide-react";
import {
  createContext, forwardRef, useContext, useId,
  type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

const FieldContext = createContext<{ id: string; errorId: string; hasError: boolean } | null>(null);

const CONTROL =
  "w-full rounded border bg-surface px-3 text-sm text-ink transition-colors " +
  "duration-200 placeholder:text-ink-subtle " +
  "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-subtle";

/**
 * Label is always visible (never placeholder-only) and the error message sits
 * directly beneath the control it belongs to.
 */
export function FormField({
  label, error, hint, required, children, className, htmlFor,
}: {
  label: string; error?: string; hint?: ReactNode; required?: boolean;
  children: ReactNode; className?: string; htmlFor?: string;
}) {
  const generated = useId();
  const id = htmlFor ?? generated;
  const errorId = `${id}-error`;
  return (
    <FieldContext.Provider value={{ id, errorId, hasError: Boolean(error) }}>
      <div className={cn("space-y-1.5", className)}>
        <label htmlFor={id} className="block text-sm font-medium text-ink">
          {label}
          {required && <span className="ml-0.5 text-danger" aria-hidden>*</span>}
        </label>
        {children}
        {error ? (
          <p id={errorId} className="flex items-start gap-1 text-xs text-danger">
            <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            {error}
          </p>
        ) : (
          hint && <p className="text-xs text-ink-subtle">{hint}</p>
        )}
      </div>
    </FieldContext.Provider>
  );
}

function useField() {
  return useContext(FieldContext);
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    const field = useField();
    return (
      <input
        ref={ref}
        id={props.id ?? field?.id}
        aria-invalid={field?.hasError || undefined}
        aria-describedby={field?.hasError ? field.errorId : undefined}
        className={cn(
          CONTROL, "h-9",
          field?.hasError ? "border-danger" : "border-line-strong hover:border-ink-subtle",
          className,
        )}
        {...props}
      />
    );
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, rows = 4, ...props }, ref) {
    const field = useField();
    return (
      <textarea
        ref={ref}
        rows={rows}
        id={props.id ?? field?.id}
        aria-invalid={field?.hasError || undefined}
        aria-describedby={field?.hasError ? field.errorId : undefined}
        className={cn(
          CONTROL, "py-2 leading-relaxed resize-y",
          field?.hasError ? "border-danger" : "border-line-strong hover:border-ink-subtle",
          className,
        )}
        {...props}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    const field = useField();
    return (
      <div className="relative">
        <select
          ref={ref}
          id={props.id ?? field?.id}
          aria-invalid={field?.hasError || undefined}
          aria-describedby={field?.hasError ? field.errorId : undefined}
          className={cn(
            CONTROL, "h-9 cursor-pointer appearance-none pr-9",
            field?.hasError ? "border-danger" : "border-line-strong hover:border-ink-subtle",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle"
          aria-hidden
        />
      </div>
    );
  },
);

export function Checkbox({
  label, description, className, ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; description?: string }) {
  const id = useId();
  return (
    <label
      htmlFor={props.id ?? id}
      className={cn("flex cursor-pointer items-start gap-2.5 select-none", className)}
    >
      <span className="relative mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
        <input
          type="checkbox"
          id={props.id ?? id}
          className="peer h-4 w-4 cursor-pointer appearance-none rounded-sm border border-line-strong bg-surface checked:border-accent checked:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          {...props}
        />
        <Check
          className="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100"
          aria-hidden
        />
      </span>
      <span className="min-w-0">
        <span className="block text-sm text-ink">{label}</span>
        {description && <span className="block text-xs text-ink-muted">{description}</span>}
      </span>
    </label>
  );
}

export function Radio({
  label, description, className, ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; description?: string }) {
  const id = useId();
  return (
    <label
      htmlFor={props.id ?? id}
      className={cn("flex cursor-pointer items-start gap-2.5 select-none", className)}
    >
      <input
        type="radio"
        id={props.id ?? id}
        className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-[rgb(var(--c-accent))]"
        {...props}
      />
      <span className="min-w-0">
        <span className="block text-sm text-ink">{label}</span>
        {description && <span className="block text-xs text-ink-muted">{description}</span>}
      </span>
    </label>
  );
}

export function FormActions({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center justify-end gap-2 pt-1", className)}>
      {children}
    </div>
  );
}
