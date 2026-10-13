import { GraduationCap, Sparkles, Users, CheckCircle2, ChevronRight, X, UserCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface DemoAccount {
  name: string;
  role: string;
  dept: string;
  email: string;
  domain: string;
}

const COORDINATOR_ACCOUNTS: DemoAccount[] = [
  // ICT
  { name: "Dr. Priya Nair", role: "Summer Internship Coord", dept: "ICT", email: "priya.nair@campushub.example.com", domain: "Summer Internships" },
  { name: "Prof. Sneha Iyer", role: "CSSI Coordinator", dept: "ICT", email: "sneha.iyer@campushub.example.com", domain: "Community Service" },
  { name: "Dr. Meera Krishnan", role: "NPTEL / MOOC Coord", dept: "ICT", email: "meera.krishnan@campushub.example.com", domain: "MOOC Credits" },
  { name: "Dr. Rakesh Bhatt", role: "Minor & Electives Coord", dept: "ICT", email: "rakesh.bhatt@campushub.example.com", domain: "Electives / Minors" },
  { name: "Dr. Anand Mehta", role: "Mentorship Coordinator", dept: "ICT", email: "anand.mehta@campushub.example.com", domain: "Faculty Mentor" },
  // CSE
  { name: "Dr. Kunal Shah", role: "Summer Internship Coord", dept: "CSE", email: "kunal.shah@campushub.example.com", domain: "Summer Internships" },
  { name: "Dr. Farah Ansari", role: "CSSI & MOOC Coord", dept: "CSE", email: "farah.ansari@campushub.example.com", domain: "CSSI & MOOC" },
  // Mechanical, ECE, Civil, Chemical, EE, PTE
  { name: "Dr. Suresh Pillai", role: "Summer & Minor Coord", dept: "MEC", email: "suresh.pillai@campushub.example.com", domain: "Mechanical Eng" },
  { name: "Dr. Nandita Bose", role: "Electives Coordinator", dept: "ECE", email: "nandita.bose@campushub.example.com", domain: "Electronics Eng" },
  { name: "Dr. Imran Qureshi", role: "CSSI Coordinator", dept: "ECE", email: "imran.qureshi@campushub.example.com", domain: "Community Service" },
  { name: "Dr. Sunita Rathore", role: "Summer & Minor Coord", dept: "CIV", email: "sunita.rathore@campushub.example.com", domain: "Civil Engineering" },
  { name: "Dr. Alok Ranjan", role: "Minor Coordinator", dept: "CHM", email: "alok.ranjan@campushub.example.com", domain: "Chemical Eng" },
  { name: "Dr. Rupal Vasa", role: "Electives Coordinator", dept: "EE", email: "rupal.vasa@campushub.example.com", domain: "Electrical Eng" },
  { name: "Dr. Hardik Chauhan", role: "Minor Coordinator", dept: "PTE", email: "hardik.chauhan@campushub.example.com", domain: "Petroleum Eng" },
];

const STUDENT_ACCOUNTS: DemoAccount[] = [
  { name: "Aarav Desai", role: "Student (Sem VI)", dept: "ICT", email: "aarav.desai.001@campushub.example.com", domain: "Allocated OE3 · Minor Active" },
  { name: "Ananya Menon", role: "Student (Sem IV)", dept: "ICT", email: "ananya.menon.011@campushub.example.com", domain: "OE1 Bidding Pending" },
];

const ADMIN_ACCOUNTS: DemoAccount[] = [
  { name: "Dr. Rakesh Bhatt", role: "Department Admin", dept: "ICT", email: "rakesh.bhatt@campushub.example.com", domain: "Full ICT Administration" },
  { name: "Clubs & Events Cell", role: "Club Admin", dept: "Campus", email: "clubs@campushub.example.com", domain: "Student Affairs & Events" },
  { name: "System Administrator", role: "Campus Super Admin", dept: "University", email: "admin@campushub.example.com", domain: "Root System Access" },
];

const DEMO_PASSWORD = "Campus@123";

export function LoginPage() {
  const { signIn, status } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [openDemoModal, setOpenDemoModal] = useState(false);
  const [demoCategory, setDemoCategory] = useState<"coordinators" | "students" | "admins">("coordinators");

  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!email.trim() || !password) return;
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, "network", "Could not reach the server. Is the API running?"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo(acc: DemoAccount) {
    setEmail(acc.email);
    setPassword(DEMO_PASSWORD);
    setError(null);
    setOpenDemoModal(false);
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#faf8ff] text-[#131b2e] flex flex-col lg:flex-row">
      {/* Left Hero Pane: Fixed 100vh on Desktop */}
      <section className="relative hidden lg:flex lg:w-[54%] h-full overflow-hidden bg-[#111a2e]">
        <img
          src="/pdeu_campus.jpg"
          alt="Pandit Deendayal Energy University Campus"
          className="absolute inset-0 h-full w-full object-cover object-center filter brightness-[0.88] contrast-[1.03]"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0e1626]/95 via-[#0e1626]/40 to-[#0e1626]/30" />

        {/* Top Affiliation Badge */}
        <div className="absolute top-6 left-8 z-10 flex items-center gap-2.5">
          <div className="flex items-center gap-2 rounded-full border border-white/20 bg-slate-950/70 px-3 py-1 backdrop-blur-md">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#1d4ed8] text-white">
              <GraduationCap className="h-3 w-3" />
            </span>
            <span className="text-[11px] font-semibold text-white tracking-wide">
              NAAC A++ Accredited University
            </span>
          </div>
          <div className="flex items-center rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[11px] font-medium text-white/90 backdrop-blur-md">
            <span>Gandhinagar, Gujarat</span>
          </div>
        </div>

        {/* Bottom Hero Content */}
        <div className="absolute bottom-8 left-8 right-8 z-10 flex flex-col gap-2.5 text-white">
          <div className="inline-flex items-center gap-1.5 rounded-md bg-blue-600/30 px-2.5 py-0.5 text-[11px] font-semibold text-blue-200 border border-blue-400/30 w-fit backdrop-blur-xs">
            <Sparkles className="h-3 w-3 text-blue-300" />
            <span>CampusHub — PDEU Academic Central</span>
          </div>

          <h1 className="font-display text-2xl xl:text-3xl font-bold leading-tight text-white tracking-tight">
            Pandit Deendayal Energy University
          </h1>

          <p className="max-w-lg text-xs leading-relaxed text-slate-200 opacity-90">
            Unified student and faculty command center for electives bidding, NPTEL credits transfer, internship evaluation workflows, and faculty mentorship.
          </p>

          <div className="mt-1 flex flex-wrap items-center gap-4 text-[11px] text-slate-300">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>SSO Enabled</span>
            </span>
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>Audit Logged</span>
            </span>
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span>2026 Academic Session</span>
            </span>
          </div>
        </div>
      </section>

      {/* Right Form Pane: Fixed 100vh, perfectly centered without scroll */}
      <section className="flex-1 h-full flex flex-col justify-center items-center p-4 sm:p-6 lg:p-8 overflow-y-auto lg:overflow-hidden">
        <div className="w-full max-w-[460px] bg-white rounded-2xl border border-slate-200/80 shadow-[0_8px_30px_rgb(0,0,0,0.06)] p-6 sm:p-7">
          {/* PDEU Official Logo Header */}
          <div className="flex flex-col items-center text-center pb-4 border-b border-slate-100">
            <img
              src="/pdeu_logo.png"
              alt="Pandit Deendayal Energy University Official Logo"
              className="h-10 sm:h-11 w-auto object-contain max-w-[240px]"
            />
            <h2 className="mt-2.5 text-lg font-bold text-slate-900 tracking-tight font-display">
              Student &amp; Faculty Portal
            </h2>
            <p className="text-[11px] text-slate-500">
              Sign in with your official university credentials
            </p>
          </div>

          {error && (
            <div className="mt-3">
              <Alert variant="danger">{error.message}</Alert>
            </div>
          )}

          {/* Form */}
          <form onSubmit={onSubmit} className="mt-4 space-y-3" noValidate>
            <div>
              <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                University Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@campushub.example.com"
                autoComplete="username"
                className="h-10 w-full rounded-lg border border-slate-300 bg-slate-50/50 px-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#1d4ed8] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1d4ed8]/15 transition-all"
                required
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-[11px] font-semibold text-slate-700">
                  Password
                </label>
                <span className="text-[10px] text-slate-400 font-mono">
                  Default: Campus@123
                </span>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="h-10 w-full rounded-lg border border-slate-300 bg-slate-50/50 px-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#1d4ed8] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1d4ed8]/15 transition-all"
                required
              />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting}
              className="mt-1 flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#1e3a5f] px-4 text-xs font-semibold text-white shadow-sm hover:bg-[#162c47] focus:outline-none focus:ring-2 focus:ring-[#1e3a5f]/40 active:translate-y-[1px] disabled:opacity-70 transition-all"
            >
              <span>{submitting ? "Verifying Credentials…" : "Sign In to PDEU CampusHub"}</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </form>

          {/* Divider */}
          <div className="my-3.5 flex items-center justify-center">
            <hr className="flex-1 border-slate-200" />
            <span className="px-2.5 text-[9px] font-bold uppercase tracking-wider text-slate-400 font-mono">
              OR LOGIN WITH
            </span>
            <hr className="flex-1 border-slate-200" />
          </div>

          {/* Google PDEU SSO */}
          <button
            type="button"
            onClick={() => {
              fillDemo(STUDENT_ACCOUNTS[0]);
            }}
            className="flex h-9 w-full cursor-pointer items-center justify-center gap-2.5 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:translate-y-[1px] shadow-2xs transition-all"
          >
            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.55 10.78l7.98-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            <span>Sign In with PDEU Google Workspace</span>
          </button>

          {/* 1-Click Demo Accounts Trigger Modal/Drawer */}
          <div className="mt-3.5 pt-3 border-t border-slate-100 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setOpenDemoModal(true)}
              className="flex items-center gap-1.5 text-xs font-bold text-[#1d4ed8] hover:underline"
            >
              <Users className="h-3.5 w-3.5" />
              <span>Browse All Coordinator &amp; Role Demo Accounts</span>
            </button>
            <span className="text-[10px] bg-blue-50 text-blue-700 font-semibold px-2 py-0.5 rounded border border-blue-200">
              14+ Roles
            </span>
          </div>

          {/* Quick Shortcuts */}
          <div className="mt-2.5 grid grid-cols-3 gap-1 text-[10px]">
            <button
              type="button"
              onClick={() => fillDemo(COORDINATOR_ACCOUNTS[0])}
              className="truncate rounded bg-slate-50 border border-slate-200 p-1 font-medium text-slate-700 hover:border-slate-400"
            >
              Summer Coord
            </button>
            <button
              type="button"
              onClick={() => fillDemo(COORDINATOR_ACCOUNTS[1])}
              className="truncate rounded bg-slate-50 border border-slate-200 p-1 font-medium text-slate-700 hover:border-slate-400"
            >
              CSSI Coord
            </button>
            <button
              type="button"
              onClick={() => fillDemo(COORDINATOR_ACCOUNTS[2])}
              className="truncate rounded bg-slate-50 border border-slate-200 p-1 font-medium text-slate-700 hover:border-slate-400"
            >
              MOOC Coord
            </button>
          </div>

          {/* University Portal Footer */}
          <div className="mt-4 text-center text-[10px] text-slate-400 border-t border-slate-100 pt-3">
            <p>Pandit Deendayal Energy University · Gandhinagar</p>
          </div>
        </div>
      </section>

      {/* Full Modal for All Coordinators and Roles */}
      {openDemoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-2xl max-h-[85vh] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#1e3a5f] text-white">
                  <UserCheck className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    PDEU Demo Accounts — 1-Click Autofill
                  </h3>
                  <p className="text-2xs text-slate-500">
                    Password for all accounts: <code className="font-mono font-semibold text-slate-800">{DEMO_PASSWORD}</code>
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpenDemoModal(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Category Tabs */}
            <div className="flex border-b border-slate-200 bg-white px-6 pt-2">
              <button
                type="button"
                onClick={() => setDemoCategory("coordinators")}
                className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-all ${
                  demoCategory === "coordinators"
                    ? "border-[#1d4ed8] text-[#1d4ed8]"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                Department Coordinators ({COORDINATOR_ACCOUNTS.length})
              </button>
              <button
                type="button"
                onClick={() => setDemoCategory("students")}
                className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-all ${
                  demoCategory === "students"
                    ? "border-[#1d4ed8] text-[#1d4ed8]"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                Students ({STUDENT_ACCOUNTS.length})
              </button>
              <button
                type="button"
                onClick={() => setDemoCategory("admins")}
                className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-all ${
                  demoCategory === "admins"
                    ? "border-[#1d4ed8] text-[#1d4ed8]"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                Administration ({ADMIN_ACCOUNTS.length})
              </button>
            </div>

            {/* Accounts Grid */}
            <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {(demoCategory === "coordinators"
                ? COORDINATOR_ACCOUNTS
                : demoCategory === "students"
                ? STUDENT_ACCOUNTS
                : ADMIN_ACCOUNTS
              ).map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  onClick={() => fillDemo(acc)}
                  className="group flex flex-col rounded-xl border border-slate-200 bg-white p-3 text-left hover:border-[#1d4ed8] hover:bg-blue-50/40 hover:shadow-xs transition-all"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900 group-hover:text-[#1d4ed8]">
                      {acc.name}
                    </span>
                    <span className="text-3xs font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200/60">
                      {acc.dept}
                    </span>
                  </div>
                  <span className="mt-0.5 text-2xs font-semibold text-slate-700">{acc.role}</span>
                  <span className="mt-0.5 text-3xs font-mono text-slate-400 truncate">{acc.email}</span>
                  <span className="mt-1.5 text-3xs text-slate-500 font-medium border-t border-slate-100 pt-1">
                    Scope: {acc.domain}
                  </span>
                </button>
              ))}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-2xs text-slate-500">
              <span>Click any account card to autofill and close.</span>
              <button
                type="button"
                onClick={() => setOpenDemoModal(false)}
                className="font-semibold text-slate-700 hover:underline"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
