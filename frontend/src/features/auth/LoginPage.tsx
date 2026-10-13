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
  semester?: number;
  roll?: string;
}

const COORDINATOR_ACCOUNTS: DemoAccount[] = [
  // ICT
  { name: "Dr. Priya Nair", role: "Summer Internship & Minor Coord", dept: "ICT", email: "priya.nair@campushub.example.com", domain: "Summer Internships · Minors" },
  { name: "Prof. Sneha Iyer", role: "CSSI Coordinator", dept: "ICT", email: "sneha.iyer@campushub.example.com", domain: "Community Service" },
  { name: "Dr. Meera Krishnan", role: "NPTEL / MOOC Coord", dept: "ICT", email: "meera.krishnan@campushub.example.com", domain: "MOOC Credits" },
  { name: "Dr. Vikram Joshi", role: "Open Elective Coord", dept: "ICT", email: "vikram.joshi@campushub.example.com", domain: "Open Elective Rounds" },
  { name: "Prof. Leena Nambiar", role: "Core Elective Coord", dept: "ICT", email: "leena.nambiar@campushub.example.com", domain: "Core Elective Rounds" },
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
  // Full 8-Semester Spectrum (ICT Primary Cohort)
  {
    name: "Devansh Joshi",
    role: "Student (Sem I)",
    dept: "ICT",
    roll: "25BIT091",
    email: "devansh.joshi.091@campushub.example.com",
    domain: "1st Year · Induction & Core Foundation",
    semester: 1,
  },
  {
    name: "Ishaan Bhatt",
    role: "Student (Sem II)",
    dept: "ICT",
    roll: "25BIT041",
    email: "ishaan.bhatt.041@campushub.example.com",
    domain: "1st Year · CSSI Exploration Phase",
    semester: 2,
  },
  {
    name: "Riya Chauhan",
    role: "Student (Sem III)",
    dept: "ICT",
    roll: "24BIT031",
    email: "riya.chauhan.031@campushub.example.com",
    domain: "2nd Year · CSSI Live & Mentor Assigned",
    semester: 3,
  },
  {
    name: "Ananya Menon",
    role: "Student (Sem IV)",
    dept: "ICT",
    roll: "23BIT011",
    email: "ananya.menon.011@campushub.example.com",
    domain: "2nd Year · Open Elective (OE1) Bidding",
    semester: 4,
  },
  {
    name: "Kavya Patel",
    role: "Student (Sem V)",
    dept: "ICT",
    roll: "23BIT051",
    email: "kavya.patel.051@campushub.example.com",
    domain: "3rd Year · NPTEL/MOOC & Program Elective 1",
    semester: 5,
  },
  {
    name: "Aarav Desai",
    role: "Student (Sem VI)",
    dept: "ICT",
    roll: "22BIT001",
    email: "aarav.desai.001@campushub.example.com",
    domain: "3rd Year · Allocated OE3 & Minor Active",
    semester: 6,
  },
  {
    name: "Arjun Verma",
    role: "Student (Sem VII)",
    dept: "ICT",
    roll: "21BIT021",
    email: "arjun.verma.021@campushub.example.com",
    domain: "4th Year · Summer Internship & OE4",
    semester: 7,
  },
  {
    name: "Pooja Shah",
    role: "Student (Sem VIII)",
    dept: "ICT",
    roll: "21BIT081",
    email: "pooja.shah.081@campushub.example.com",
    domain: "4th Year · Capstone & Degree Completion",
    semester: 8,
  },
  // Cross-Department Representatives
  {
    name: "Rhea Kulkarni",
    role: "Student (Sem IV)",
    dept: "CSE",
    roll: "24BCE001",
    email: "rhea.kulkarni.001@campushub.example.com",
    domain: "Computer Eng · OE Bidding & Core",
    semester: 4,
  },
  {
    name: "Sameer Shah",
    role: "Student (Sem V)",
    dept: "EE",
    roll: "23BEE101",
    email: "sameer.shah.101@campushub.example.com",
    domain: "Electrical Eng · MOOC Certifications",
    semester: 5,
  },
  {
    name: "Naina Sheth",
    role: "Student (Sem VII)",
    dept: "ECE",
    roll: "22BEC001",
    email: "naina.sheth.001@campushub.example.com",
    domain: "Electronics Eng · Industry Internship",
    semester: 7,
  },
  {
    name: "Tanvi Shirke",
    role: "Student (Sem II)",
    dept: "BIO",
    roll: "25BBT001",
    email: "tanvi.shirke.001@campushub.example.com",
    domain: "Biotechnology · First Year Cohort",
    semester: 2,
  },
];

const ADMIN_ACCOUNTS: DemoAccount[] = [
  { name: "Dr. Rakesh Bhatt", role: "Head of Department", dept: "ICT", email: "rakesh.bhatt@campushub.example.com", domain: "Appoints ICT Coordinators" },
  { name: "ICT Department Office", role: "Department Admin", dept: "ICT", email: "ict.office@campushub.example.com", domain: "ICT Data Administration" },
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

          {/* 1-Click Demo Accounts Section */}
          <div className="mt-3 pt-3 border-t border-slate-100">
            {/* Quick Students by Semester */}
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-bold text-slate-700 flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-blue-600" />
                Quick Student Login (Sem 1 to 8):
              </span>
              <button
                type="button"
                onClick={() => {
                  setDemoCategory("students");
                  setOpenDemoModal(true);
                }}
                className="text-[10px] font-bold text-[#1d4ed8] hover:underline cursor-pointer"
              >
                All Details →
              </button>
            </div>

            {/* 8 Semester Student Chips */}
            <div className="grid grid-cols-4 gap-1 text-[10px]">
              {STUDENT_ACCOUNTS.slice(0, 8).map((st) => (
                <button
                  key={st.email}
                  type="button"
                  onClick={() => fillDemo(st)}
                  className="truncate rounded-md bg-blue-50/80 border border-blue-200 px-1 py-1 font-bold text-blue-800 hover:bg-blue-100 hover:border-blue-400 transition-colors cursor-pointer text-center"
                  title={`${st.name} (${st.roll}) · ${st.role} · ${st.domain}`}
                >
                  Sem {st.semester}
                </button>
              ))}
            </div>

            {/* Quick Coordinators & All Roles Trigger */}
            <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px]">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => fillDemo(COORDINATOR_ACCOUNTS[0])}
                  className="rounded bg-slate-50 border border-slate-200 px-1.5 py-0.5 font-medium text-slate-700 hover:border-slate-400 cursor-pointer"
                  title="Summer Internship Coordinator"
                >
                  Summer
                </button>
                <button
                  type="button"
                  onClick={() => fillDemo(COORDINATOR_ACCOUNTS[1])}
                  className="rounded bg-slate-50 border border-slate-200 px-1.5 py-0.5 font-medium text-slate-700 hover:border-slate-400 cursor-pointer"
                  title="CSSI Coordinator"
                >
                  CSSI
                </button>
                <button
                  type="button"
                  onClick={() => fillDemo(COORDINATOR_ACCOUNTS[2])}
                  className="rounded bg-slate-50 border border-slate-200 px-1.5 py-0.5 font-medium text-slate-700 hover:border-slate-400 cursor-pointer"
                  title="MOOC Coordinator"
                >
                  MOOC
                </button>
              </div>

              <button
                type="button"
                onClick={() => setOpenDemoModal(true)}
                className="font-bold text-[#1d4ed8] hover:underline cursor-pointer"
              >
                Browse All ({COORDINATOR_ACCOUNTS.length + STUDENT_ACCOUNTS.length + ADMIN_ACCOUNTS.length}) →
              </button>
            </div>
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
                  <div className="flex items-center justify-between gap-1">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-bold text-xs text-slate-900 group-hover:text-[#1d4ed8] truncate">
                        {acc.name}
                      </span>
                      {acc.semester && (
                        <span className="text-3xs font-mono font-bold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-800 shrink-0">
                          Sem {acc.semester}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {acc.roll && (
                        <span className="text-3xs font-mono font-semibold text-slate-500 bg-slate-50 px-1 py-0.5 rounded border border-slate-200/50">
                          {acc.roll}
                        </span>
                      )}
                      <span className="text-3xs font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200/60">
                        {acc.dept}
                      </span>
                    </div>
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
