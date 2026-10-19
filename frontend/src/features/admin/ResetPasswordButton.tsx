import { useMutation } from "@tanstack/react-query";
import { Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";

/**
 * Issue a one-time password (there is no email yet). It is shown once, here;
 * the person must replace it at their next sign-in, and every session they had
 * ends. The server decides who may do this (services/accounts.py) and refuses
 * it while demo accounts are on.
 */
export function ResetPasswordButton({ kind, id, name }: {
  kind: "students" | "faculty"; id: number; name: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const reset = useMutation({
    mutationFn: () => api.post<{ temporary_password: string; login: string }>(
      `/${kind}/${id}/reset-password`),
  });
  const close = () => { setOpen(false); setCopied(false); reset.reset(); };

  return (
    <>
      <Button variant="secondary" size="sm" className="h-7 px-2 text-xs"
              icon={<KeyRound className="h-3.5 w-3.5" aria-hidden />}
              aria-label={`Reset password for ${name}`} onClick={() => setOpen(true)}>
        Password
      </Button>
      <Modal open={open} onClose={close} title={`Reset password — ${name}`}
             description="Gives a one-time password to pass on in person or by phone."
             footer={reset.data ? (
               <Button size="sm" onClick={close}>Done</Button>
             ) : (
               <>
                 <Button variant="secondary" size="sm" onClick={close}>Cancel</Button>
                 <Button size="sm" loading={reset.isPending} onClick={() => reset.mutate()}>
                   Issue one-time password
                 </Button>
               </>
             )}>
        {reset.error ? (
          <Alert variant="danger">
            {reset.error instanceof ApiError ? reset.error.message : "Could not reset the password."}
          </Alert>
        ) : reset.data ? (
          <div className="space-y-3">
            <p className="text-sm text-ink-muted">
              Sign-in: <span className="font-medium text-ink">{reset.data.login}</span>
            </p>
            <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface-muted px-4 py-3">
              <code className="text-lg font-semibold tracking-wider text-ink">{reset.data.temporary_password}</code>
              <Button variant="secondary" size="sm" icon={<Copy className="h-3.5 w-3.5" aria-hidden />}
                      onClick={() => {
                        void navigator.clipboard?.writeText(reset.data!.temporary_password);
                        setCopied(true);
                      }}>
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <Alert variant="warning">
              Shown once. {name} must choose a new password at the next sign-in; they have been
              signed out everywhere.
            </Alert>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">
            Their current password stops working at once and they are signed out of every device.
          </p>
        )}
      </Modal>
    </>
  );
}
