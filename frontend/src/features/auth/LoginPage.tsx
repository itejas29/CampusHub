import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight, BookOpen, Briefcase, Eye, EyeOff, GraduationCap, ShieldCheck, Sparkles,
  UserCheck, Users,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { roman } from "@/lib/utils";

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
  { name: "ICT Department Office", role: "Department Admin", dept: "ICT", email: "ict.office@campushub.example.com", domain: "ICT Data Administration" },
  { name: "Clubs & Events Cell", role: "Club Admin", dept: "Campus", email: "clubs@campushub.example.com", domain: "Student Affairs & Events" },
  { name: "System Administrator", role: "Campus Super Admin", dept: "University", email: "admin@campushub.example.com", domain: "Root System Access" },
];

const DEMO_PASSWORD = "Campus@123";

/**
 * Demo sign-in shortcuts are for evaluation builds only. They show in local
 * development, or when a deployment opts in with VITE_DEMO_MODE=true — never
 * by default on a production build, where they would publish working
 * credentials on the login screen.
 */
const DEMO_MODE = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === "true";

type DemoCategory = "coordinators" | "students" | "admins";
const DEMO_GROUPS: Record<DemoCategory, { label: string; accounts: DemoAccount[] }> = {
  coordinators: { label: "Coordinators", accounts: COORDINATOR_ACCOUNTS },
  students: { label: "Students", accounts: STUDENT_ACCOUNTS },
  admins: { label: "Administration", accounts: ADMIN_ACCOUNTS },
};

const inputClass =
  "h-11 w-full rounded-lg border border-line-strong bg-surface px-3.5 text-base text-ink sm:text-sm " +
  "placeholder:text-ink-subtle transition-[border-color,box-shadow] duration-150 " +
  "hover:border-ink-subtle/60 focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/15";

export function LoginPage() {
  const { signIn, status } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [openDemoModal, setOpenDemoModal] = useState(false);
  const [demoCategory, setDemoCategory] = useState<DemoCategory>("coordinators");

  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError(new ApiError(0, "validation", "Enter your university email and password."));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, "network", "Could not reach the server. Check your connection and try again."),
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
    <div className="flex min-h-dvh flex-col bg-canvas text-ink lg:flex-row">
      {/* ── Hero: the campus, the university, what the portal does ───────── */}
      <section className="relative hidden overflow-hidden bg-navy lg:flex lg:w-[54%] lg:min-h-dvh">
        <img
          src="/pdeu_campus.jpg"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-center"
        />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-navy-deep via-navy/70 to-navy/30" />
        <div aria-hidden className="hero-grid absolute inset-0 opacity-30" />
        <div aria-hidden className="absolute -left-24 bottom-10 h-72 w-72 rounded-full bg-electric/30 blur-3xl" />

        <div className="relative z-10 flex w-full flex-col justify-between p-10 xl:p-12">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-gradient text-white shadow-glow-accent">
              <GraduationCap className="h-5 w-5" aria-hidden />
            </span>
            <span>
              <span className="block font-heading text-base font-semibold leading-tight text-white">CampusHub</span>
              <span className="block text-2xs font-semibold uppercase tracking-[0.14em] text-white/60">Gandhinagar, Gujarat</span>
            </span>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="max-w-xl text-white"
          >
            <p className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold text-white/90 backdrop-blur-sm">
              <Sparkles className="h-3.5 w-3.5 text-electric" aria-hidden />
              One portal for every academic workflow
            </p>
            <h1 className="mt-4 font-heading text-3xl font-semibold leading-tight tracking-tight xl:text-4xl">
              Pandit Deendayal Energy University
            </h1>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-white/75">
              Elective registration, NPTEL credit transfer, CSSI and internship evaluation,
              mentoring and campus life — for students, faculty and administration.
            </p>
            <ul className="mt-6 grid max-w-lg grid-cols-2 gap-2.5">
              {[
                [BookOpen, "Electives & minors"],
                [Briefcase, "Internships & CSSI"],
                [Users, "Mentor–mentee"],
                [ShieldCheck, "Every action audited"],
              ].map(([Icon, label]) => {
                const I = Icon as typeof BookOpen;
                return (
                  <li key={label as string} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 py-2 text-xs font-medium text-white/85 backdrop-blur-sm">
                    <I className="h-4 w-4 shrink-0 text-electric" aria-hidden />
                    {label as string}
                  </li>
                );
              })}
            </ul>
          </motion.div>
        </div>
      </section>

      {/* ── Sign-in form ─────────────────────────────────────────────────── */}
      <main className="relative flex flex-1 items-center justify-center px-4 py-10 sm:px-6 lg:py-8">
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-surface-soft to-transparent lg:hidden" />
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-full max-w-[440px] rounded-2xl border border-line bg-surface p-6 shadow-lg sm:p-8"
        >
          <div className="flex flex-col items-center text-center">
            {/* The official logo's lettering is white — it needs the navy behind it,
                or only the emblem shows on a white card. */}
            <div className="relative flex w-full justify-center overflow-hidden rounded-xl bg-brand-gradient px-5 py-4">
              <div aria-hidden className="hero-grid absolute inset-0 opacity-40" />
              <img
                src="/pdeu_logo.png"
                alt="Pandit Deendayal Energy University"
                className="relative h-12 w-auto max-w-full object-contain"
              />
            </div>
            <h2 className="mt-4 font-heading text-xl font-semibold tracking-tight text-ink">
              Sign in to CampusHub
            </h2>
            <p className="mt-1 text-sm text-ink-muted">Use your university email and password.</p>
          </div>

          <AnimatePresence initial={false}>
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="pt-5">
                  <Alert variant="danger">{error.message}</Alert>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium text-ink">
                University email
              </label>
              <input
                id="login-email"
                type="email"
                inputMode="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Your university email"
                autoComplete="username"
                className={inputClass}
                required
                aria-invalid={error?.code === "validation" && !email.trim() ? true : undefined}
              />
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-sm font-medium text-ink">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className={`${inputClass} pr-11`}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 flex w-11 cursor-pointer items-center justify-center rounded-r-lg text-ink-subtle transition-colors hover:text-ink"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                </button>
              </div>
            </div>

            <Button type="submit" variant="accent" size="lg" loading={submitting} className="w-full" iconRight={!submitting && <ArrowRight className="h-4 w-4" aria-hidden />}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {DEMO_MODE && (
            <div className="mt-6 border-t border-line pt-5">
              <div className="flex items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                  <UserCheck className="h-3.5 w-3.5 text-accent" aria-hidden />
                  Demo accounts
                  <span className="font-normal text-ink-subtle">· password {DEMO_PASSWORD}</span>
                </p>
                <button
                  type="button"
                  onClick={() => setOpenDemoModal(true)}
                  className="cursor-pointer whitespace-nowrap rounded text-xs font-semibold text-accent hover:underline"
                >
                  Browse all
                </button>
              </div>
              <p className="mt-3 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">Students by semester</p>
              <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                {STUDENT_ACCOUNTS.slice(0, 8).map((st) => (
                  <button
                    key={st.email}
                    type="button"
                    onClick={() => fillDemo(st)}
                    className="cursor-pointer rounded-md border border-accent/20 bg-accent-soft px-1 py-1.5 text-center text-xs font-semibold text-accent transition-colors hover:border-accent/50"
                    title={`${st.name} (${st.roll}) · ${st.domain}`}
                  >
                    Sem {roman(st.semester)}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">Coordinators</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {COORDINATOR_ACCOUNTS.slice(0, 3).map((acc) => (
                  <button
                    key={acc.email}
                    type="button"
                    onClick={() => fillDemo(acc)}
                    className="cursor-pointer rounded-md border border-line bg-surface-muted px-2 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
                    title={`${acc.name} · ${acc.role}`}
                  >
                    {acc.role}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="mt-6 text-center text-xs text-ink-subtle">
            Pandit Deendayal Energy University · Gandhinagar
          </p>
        </motion.div>
      </main>

      {DEMO_MODE && (
        <Modal
          open={openDemoModal}
          onClose={() => setOpenDemoModal(false)}
          title="Demo accounts"
          description={`Choose an account to fill the form. Every account uses the password ${DEMO_PASSWORD}.`}
          size="lg"
        >
          <div role="tablist" aria-label="Account type" className="-mt-1 mb-4 inline-flex rounded-lg bg-surface-muted p-0.5">
            {(Object.keys(DEMO_GROUPS) as DemoCategory[]).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={demoCategory === key}
                onClick={() => setDemoCategory(key)}
                className={`cursor-pointer rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  demoCategory === key ? "bg-surface text-ink shadow-xs" : "text-ink-subtle hover:text-ink"
                }`}
              >
                {DEMO_GROUPS[key].label} <span className="tabular-nums text-ink-subtle">{DEMO_GROUPS[key].accounts.length}</span>
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {DEMO_GROUPS[demoCategory].accounts.map((acc) => (
              <button
                key={acc.email}
                type="button"
                onClick={() => fillDemo(acc)}
                className="group flex min-w-0 cursor-pointer flex-col rounded-xl border border-line bg-surface p-3 text-left transition-all hover:-translate-y-px hover:border-accent/50 hover:shadow-card-hover"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-semibold text-ink group-hover:text-accent" title={acc.name}>
                    {acc.name}
                  </span>
                  <span className="shrink-0 rounded border border-line bg-surface-muted px-1.5 py-0.5 text-2xs font-semibold text-ink-muted">
                    {acc.semester ? `Sem ${roman(acc.semester)}` : acc.dept}
                  </span>
                </span>
                <span className="mt-0.5 text-xs font-medium text-ink-muted">{acc.role}</span>
                <span className="mt-0.5 truncate font-mono text-2xs text-ink-subtle" title={acc.email}>{acc.email}</span>
                <span className="mt-2 border-t border-line pt-1.5 text-2xs text-ink-subtle">{acc.domain}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
