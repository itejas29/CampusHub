import { GraduationCap, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, Input } from "@/components/ui/Form";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Grouped so the scoped-coordinator model is visible at the door: the same
 * module has different coordinators per department, and a mentor-only faculty
 * member holds no coordination at all.
 */
const DEMO_GROUPS: { title: string; accounts: { role: string; email: string; note: string }[] }[] = [
  {
    title: "Students",
    accounts: [
      { role: "Semester VI", email: "aarav.desai.001@campushub.example.com", note: "Allocated OE3 · minor active" },
      { role: "Semester IV", email: "ananya.menon.011@campushub.example.com", note: "Open Elective 1 pending" },
    ],
  },
  {
    title: "Faculty — mentor only",
    accounts: [
      { role: "Dr. Anand Mehta", email: "anand.mehta@campushub.example.com", note: "CSSI Group 1 · no coordination" },
    ],
  },
  {
    title: "Coordinators — scoped to one module and department",
    accounts: [
      { role: "Summer Internship · ICT", email: "priya.nair@campushub.example.com", note: "Cannot touch CSSI" },
      { role: "CSSI · ICT", email: "sneha.iyer@campushub.example.com", note: "Cannot touch Summer" },
      { role: "NPTEL / MOOC · ICT", email: "meera.krishnan@campushub.example.com", note: "Not a mentor" },
      { role: "Summer Internship · CSE", email: "kunal.shah@campushub.example.com", note: "Same module, other dept" },
    ],
  },
  {
    title: "Administration",
    accounts: [
      { role: "Department Admin · ICT", email: "rakesh.bhatt@campushub.example.com", note: "Minor + electives" },
      { role: "Club Admin", email: "clubs@campushub.example.com", note: "Clubs & events" },
      { role: "Super Admin", email: "admin@campushub.example.com", note: "Full access" },
    ],
  },
];

const DEMO_PASSWORD = "Campus@123";

export function LoginPage() {
  const { signIn, status } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err
        : new ApiError(0, "network", "Could not reach the server. Is the API running?"));
    } finally {
      setSubmitting(false);
    }
  }

  function useDemo(demoEmail: string) {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError(null);
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas lg:flex-row">
      {/* Brand panel — flat institutional navy, no decorative gradient. */}
      <div className="flex flex-col justify-between bg-navy px-6 py-8 text-white sm:px-10 lg:w-[42%] lg:py-12">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded bg-white/15">
            <GraduationCap className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="font-heading text-lg font-semibold leading-tight">CampusHub</p>
            <p className="text-xs text-white/70">Pandit Deendayal Energy University</p>
          </div>
        </div>

        <div className="my-10 max-w-md lg:my-0">
          <h1 className="font-heading text-2xl font-semibold leading-snug sm:text-3xl">
            One portal for academics, internships and campus life.
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-white/75">
            Electives and NPTEL registration, minor specialisations, CSSI and summer
            internships, clubs, events and mentorship — in a single place, with your
            department's rules applied automatically.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-white/75">
            {[
              "Curriculum-driven elective eligibility",
              "End-to-end internship workflow and evaluation",
              "Mentor–mentee support and campus calendar",
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-white/60" aria-hidden />
                {line}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-white/50">
          Phase 2 preview · Demo data only
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <h2 className="font-heading text-xl font-semibold text-ink">Sign in</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Use your university account to continue.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            {error && <Alert variant="danger">{error.message}</Alert>}

            <FormField label="Email address" required error={error?.fieldError("email")}>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="name@campushub.example.com"
                required
              />
            </FormField>

            <FormField label="Password" required error={error?.fieldError("password")}>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                required
              />
            </FormField>

            <Button
              type="submit" size="lg" className="w-full" loading={submitting}
              icon={<LogIn className="h-4 w-4" aria-hidden />}
            >
              Sign in
            </Button>
          </form>

          <div className="mt-7 rounded-lg border border-line bg-surface p-4">
            <p className="text-sm font-semibold text-ink">Demo accounts</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              Every account uses the password{" "}
              <code className="rounded bg-surface-muted px-1 py-0.5 font-mono text-2xs">
                {DEMO_PASSWORD}
              </code>
            </p>
            <div className="mt-3 space-y-3">
              {DEMO_GROUPS.map((group) => (
                <div key={group.title}>
                  <p className="px-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                    {group.title}
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {group.accounts.map((account) => (
                      <li key={account.email}>
                        <button
                          type="button"
                          onClick={() => useDemo(account.email)}
                          className="flex w-full cursor-pointer items-baseline justify-between gap-3 rounded px-2 py-1.5 text-left transition-colors hover:bg-surface-muted"
                        >
                          <span className="min-w-0">
                            <span className="block text-sm font-medium text-ink">
                              {account.role}
                            </span>
                            <span className="block truncate text-2xs text-ink-subtle">
                              {account.email}
                            </span>
                          </span>
                          <span className="shrink-0 text-2xs text-ink-subtle">
                            {account.note}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
