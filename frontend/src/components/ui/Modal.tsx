import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "./Button";
import { cn } from "@/lib/utils";
import { dialogPanel, fade } from "@/lib/motion";

const SIZES = {
  sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl",
} as const;

/**
 * Scroll locking is reference-counted because dialogs stack — a ConfirmDialog
 * opened from inside a Modal is two locks. Without the count, closing the inner
 * one would clear `overflow` while the outer dialog is still open and let the
 * page behind it scroll.
 */
let scrollLocks = 0;

function lockScroll() {
  if (scrollLocks === 0) document.body.style.overflow = "hidden";
  scrollLocks += 1;
}

function releaseScroll() {
  scrollLocks = Math.max(0, scrollLocks - 1);
  if (scrollLocks === 0) document.body.style.overflow = "";
}

export function Modal({
  open, onClose, title, description, children, footer, size = "md", className,
}: {
  open: boolean; onClose: () => void; title: string; description?: string;
  children: ReactNode; footer?: ReactNode; size?: keyof typeof SIZES; className?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  /**
   * Held in a ref so the effect below can depend on `open` alone. Callers
   * overwhelmingly pass an inline arrow for `onClose`, which changes identity on
   * every parent render; if the effect depended on it, each keystroke in a
   * modal form would tear the effect down, run its cleanup, and hand focus back
   * to the element that opened the dialog — pulling the caret out of the field
   * being typed in.
   */
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    lockScroll();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") { onCloseRef.current(); return; }
      if (event.key !== "Tab" || !panelRef.current) return;
      // Keep focus inside the dialog.
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), ' +
          'input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    const timer = window.setTimeout(() => {
      panelRef.current
        ?.querySelector<HTMLElement>('[data-autofocus], button, input, select, textarea')
        ?.focus();
    }, 20);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      releaseScroll();
      window.clearTimeout(timer);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <motion.div
            className="absolute inset-0 bg-ink/40"
            variants={fade}
            initial="hidden"
            animate="shown"
            exit="exit"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={description ? descriptionId : undefined}
            variants={dialogPanel}
            initial="hidden"
            animate="shown"
            exit="exit"
            className={cn(
              "relative flex max-h-[92vh] w-full flex-col rounded-t-xl border border-line " +
              "bg-surface shadow-lg sm:rounded-xl",
              SIZES[size], className,
            )}
          >
            <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
              <div className="min-w-0">
                <h2 id={titleId} className="text-md font-semibold text-ink">{title}</h2>
                {description && (
                  <p id={descriptionId} className="mt-0.5 text-sm text-ink-muted">{description}</p>
                )}
              </div>
              <Button
                variant="ghost" size="icon" onClick={onClose} aria-label="Close dialog"
                className="-mr-1.5 -mt-1"
              >
                <X className="h-4 w-4" aria-hidden />
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
            {footer && (
              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-surface-muted/40 px-5 py-3">
                {footer}
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export function ConfirmDialog({
  open, onClose, onConfirm, title, message, confirmLabel = "Confirm",
  cancelLabel = "Cancel", destructive, loading,
}: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string;
  message: ReactNode; confirmLabel?: string; cancelLabel?: string;
  destructive?: boolean; loading?: boolean;
}) {
  return (
    <Modal
      open={open} onClose={onClose} title={title} size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "danger" : "primary"} size="sm"
            onClick={onConfirm} loading={loading} data-autofocus
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm text-ink-muted">{message}</div>
    </Modal>
  );
}
