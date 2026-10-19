import { KeyRound, LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, Input } from "@/components/ui/Form";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { newPasswordError } from "@/lib/validation";

/**
 * Shown instead of the portal while a one-time password from the registrar or
 * department office is in use. The server refuses everything else until a new
 * password is chosen, so this is the only screen that could work.
 */
export function ForcePasswordChange() {
  const { user, changePassword, signOut } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const problem = newPasswordError(next, user);
  const mismatch = confirm.length > 0 && confirm !== next;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await changePassword(current, next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-4">
      <form onSubmit={submit}
            className="w-full max-w-md space-y-4 rounded-lg border border-line bg-surface p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-accent">
            <KeyRound className="h-4 w-4" aria-hidden />
          </span>
          <div>
            <h1 className="text-md font-semibold text-ink">Choose your own password</h1>
            <p className="mt-0.5 text-sm text-ink-muted">
              {user?.full_name}, you signed in with a one-time password. Set a password only you
              know to continue.
            </p>
          </div>
        </div>
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField label="One-time password" htmlFor="fp-current" required>
          <Input id="fp-current" type="password" value={current} autoComplete="current-password"
                 onChange={(e) => setCurrent(e.target.value)} />
        </FormField>
        <FormField label="New password" htmlFor="fp-next" required
                   hint={problem ? undefined : "At least 10 characters, with letters and digits."}
                   error={problem}>
          <Input id="fp-next" type="password" value={next} autoComplete="new-password"
                 onChange={(e) => setNext(e.target.value)} />
        </FormField>
        <FormField label="Confirm new password" htmlFor="fp-confirm" required
                   error={mismatch ? "Passwords do not match." : undefined}>
          <Input id="fp-confirm" type="password" value={confirm} autoComplete="new-password"
                 onChange={(e) => setConfirm(e.target.value)} />
        </FormField>
        <div className="flex items-center justify-between gap-3 pt-1">
          <Button type="button" variant="ghost" size="sm" onClick={signOut}
                  icon={<LogOut className="h-3.5 w-3.5" aria-hidden />}>
            Sign out
          </Button>
          <Button type="submit" size="sm" loading={saving}
                  disabled={!current || !next || Boolean(problem) || confirm !== next}>
            Set password and continue
          </Button>
        </div>
      </form>
    </main>
  );
}
