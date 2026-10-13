import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Calendar,
  CalendarDays,
  CheckCircle2,
  GraduationCap,
  Mail,
  MapPin,
  Phone,
  Route,
  Sparkles,
  TrendingUp,
  UserCheck,
  Verified,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Misc";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { roman } from "@/lib/utils";
import type { StudentDashboard as Data } from "@/types";

export function StudentDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "student"],
    queryFn: () => api.get<Data>("/dashboard/student"),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "Student";
  const student = user?.student;

  return (
    <div className="space-y-6">
      {/* 1. PAGE HERO HEADER (Stitch Design) */}
      <section className="bg-gradient-to-r from-surface-muted via-surface to-blue-50/40 dark:to-blue-950/20 rounded-xl p-5 sm:p-6 border border-line card-luxe-shadow">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="font-heading text-xl sm:text-2xl font-bold text-ink tracking-tight">
                Welcome back, {firstName} 👋
              </h1>
              <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800 text-xs font-bold">
                <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
                All Clear (No Backlogs)
              </span>
            </div>
            <p className="text-xs sm:text-sm text-ink-muted">
              PDEU School of Technology • Department of Information & Communication Technology
            </p>

            {/* Meta Badges */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="px-2.5 py-1 rounded bg-surface border border-line text-xs font-semibold text-primary">
                Semester {student ? roman(student.current_semester) : "VI"} • Division {student?.division ?? "A"}
              </span>
              <span className="px-2.5 py-1 rounded bg-surface border border-line font-mono text-xs font-bold text-primary">
                Roll No: {student?.roll_number ?? "24BIT001"}
              </span>
              <span className="px-2.5 py-1 rounded bg-surface border border-line text-xs text-ink-subtle">
                AY {user?.academic_year ?? "2024-28"}
              </span>
              <span className="px-2.5 py-1 rounded bg-surface border border-line text-xs text-secondary font-semibold flex items-center gap-1">
                <Verified className="h-3.5 w-3.5 text-blue-600" />
                Autonomous PDEU Curriculum
              </span>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <LinkButton
              to="/profile"
              variant="secondary"
              size="sm"
            >
              View Full Profile
            </LinkButton>
            <LinkButton
              to="/academics/electives"
              variant="primary"
              size="sm"
              icon={<Sparkles className="h-3.5 w-3.5" />}
            >
              Elective Actions
            </LinkButton>
          </div>
        </div>
      </section>

      {/* 2. 4-COLUMN STAT TILES (Stitch Design with Rich Gradients & Elevation) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Stat 1: Term */}
        <div className="bg-gradient-to-br from-[#1e3a5f] via-[#162c48] to-[#1e3a5f] text-white rounded-xl p-5 card-luxe-shadow border border-blue-400/20 hover-lift relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-2xs font-semibold tracking-wider text-blue-200 uppercase">
              Active Term
            </span>
            <div className="w-8 h-8 rounded-lg bg-white/10 backdrop-blur-sm flex items-center justify-center text-blue-200">
              <GraduationCap className="h-4 w-4" />
            </div>
          </div>
          <div className="font-heading text-2xl font-bold tracking-tight text-white mb-1">
            Semester {student ? roman(student.current_semester) : "VI"}
          </div>
          <p className="text-2xs text-blue-200/80">
            Current Term (Winter 2025)
          </p>
        </div>

        {/* Stat 2: CPI Metric */}
        <div className="bg-gradient-to-br from-[#1e3a5f] via-[#162c48] to-[#2563eb] text-white rounded-xl p-5 card-luxe-shadow border border-blue-400/20 hover-lift relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-2xs font-semibold tracking-wider text-blue-200 uppercase">
              Cumulative CPI
            </span>
            <div className="w-8 h-8 rounded-lg bg-white/10 backdrop-blur-sm flex items-center justify-center text-blue-200">
              <TrendingUp className="h-4 w-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-heading text-2xl font-bold tracking-tight text-white">8.72</span>
            <span className="font-mono text-xs text-blue-200">/ 10.0</span>
          </div>
          <p className="text-2xs text-blue-200/90 flex items-center gap-1">
            <span className="font-semibold text-emerald-300">▲ +0.18</span> from Sem V • Top 5% Rank
          </p>
        </div>

        {/* Stat 3: Pending Elective */}
        <div className="bg-surface rounded-xl p-5 card-luxe-shadow border border-amber-300/80 dark:border-amber-700 hover-lift relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-2xs font-semibold tracking-wider text-amber-800 dark:text-amber-300 uppercase">
              Course Actions
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-950 flex items-center justify-center text-amber-600">
              <BookOpen className="h-4 w-4" />
            </div>
          </div>
          <div className="font-heading text-2xl font-bold tracking-tight text-ink mb-1">
            1 Pending
          </div>
          <p className="text-2xs text-amber-700 dark:text-amber-400 flex items-center gap-1 font-medium">
            Core Elective 2 Selection Open
          </p>
        </div>

        {/* Stat 4: Upcoming Events */}
        <div className="bg-surface rounded-xl p-5 card-luxe-shadow border border-line hover-lift relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-2xs font-semibold tracking-wider text-ink-muted uppercase">
              Campus Events
            </span>
            <div className="w-8 h-8 rounded-lg bg-surface-muted flex items-center justify-center text-primary">
              <CalendarDays className="h-4 w-4" />
            </div>
          </div>
          <div className="font-heading text-2xl font-bold tracking-tight text-ink mb-1">
            {data.upcoming_events.length || 3} Upcoming
          </div>
          <p className="text-2xs text-ink-subtle">
            Next: Tesseract Hackathon '25
          </p>
        </div>
      </section>

      {/* 3. MAIN DASHBOARD GRID (Asymmetric Layout) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* COLUMN 1 (Wide: 8 columns): Curriculum & Summer Internship Tracker */}
        <div className="xl:col-span-8 space-y-6">
          {/* 1. ACADEMIC CURRICULUM PROGRESS CARD */}
          <Card className="card-luxe-shadow">
            <div className="p-5 sm:p-6 border-b border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="font-heading text-base sm:text-lg font-bold text-ink flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-secondary" />
                  Curriculum Progression
                </h2>
                <p className="text-xs text-ink-muted">
                  B.Tech in Information & Communication Technology (2022-26 Scheme)
                </p>
              </div>
              <div className="sm:text-right">
                <span className="font-mono text-sm sm:text-base font-bold text-secondary block">
                  68% Completed
                </span>
                <span className="text-2xs text-ink-subtle">116 / 170 Total Credits</span>
              </div>
            </div>

            <CardBody className="space-y-4">
              {/* Visual Gradient Progress Bar */}
              <div className="space-y-1.5">
                <div className="w-full bg-surface-muted rounded-full h-3 overflow-hidden p-0.5 border border-line">
                  <div
                    className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 h-full rounded-full transition-all duration-500"
                    style={{ width: "68%" }}
                  />
                </div>
                <div className="flex justify-between items-center text-2xs text-ink-subtle font-medium">
                  <span>Foundation (38/38)</span>
                  <span>Core ICT (54/72)</span>
                  <span>Electives & Minor (24/60)</span>
                </div>
              </div>

              {/* Course Enrolments List */}
              <div className="space-y-2.5 pt-2">
                <div className="flex items-center justify-between text-2xs font-semibold uppercase tracking-wider text-ink-subtle px-1 pb-1 border-b border-line">
                  <span>Current Semester Enrolments</span>
                  <span>Status & Verification</span>
                </div>

                {/* Course 1 */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg bg-surface-muted/40 hover:bg-surface-muted transition-colors gap-2 border border-line">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-2xs font-bold text-secondary">OE3-601</span>
                      <h4 className="text-xs font-bold text-ink">Artificial Intelligence in Energy Systems</h4>
                    </div>
                    <p className="text-2xs text-ink-muted">Open Elective • 3.0 Credits • Dept. of Electrical Eng.</p>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800 text-2xs font-bold shrink-0">
                    Allocated
                  </span>
                </div>

                {/* Course 2 (Pending Action) */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-900 transition-colors gap-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-2xs font-bold text-amber-900 dark:text-amber-200">CE-602</span>
                      <h4 className="text-xs font-bold text-ink">Cloud Computing Architecture</h4>
                    </div>
                    <p className="text-2xs text-ink-muted">Core Elective II • 4.0 Credits • Choice between Cloud & Cyber</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="px-2.5 py-0.5 rounded-full bg-amber-200 text-amber-900 text-2xs font-bold">
                      Selection Pending
                    </span>
                    <Link
                      to="/academics/electives"
                      className="px-2.5 py-0.5 bg-amber-600 text-white rounded text-2xs font-bold hover:bg-amber-700 transition-colors"
                    >
                      Choose Now
                    </Link>
                  </div>
                </div>

                {/* Course 3 */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg bg-surface-muted/40 hover:bg-surface-muted transition-colors gap-2 border border-line">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-2xs font-bold text-indigo-700 dark:text-indigo-300">NPTEL-CS72</span>
                      <h4 className="text-xs font-bold text-ink">Introduction to Industry 4.0 & IoT</h4>
                    </div>
                    <p className="text-2xs text-ink-muted">SWAYAM / NPTEL Equivalent • 3.0 Credits • IIT Kharagpur</p>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200 border border-indigo-200 text-2xs font-bold flex items-center gap-1 shrink-0">
                    <CheckCircle2 className="h-3 w-3" /> Submitted & Verified
                  </span>
                </div>

                {/* Course 4 */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg bg-surface-muted/40 hover:bg-surface-muted transition-colors gap-2 border border-line">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-2xs font-bold text-secondary">MN-ICT04</span>
                      <h4 className="text-xs font-bold text-ink">Data Science for Energy Analytics</h4>
                    </div>
                    <p className="text-2xs text-ink-muted">Honors / Minor Track • 4.0 Credits • Centre for AI</p>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200 border border-blue-200 text-2xs font-bold shrink-0">
                    Active
                  </span>
                </div>
              </div>

              {/* Footer CTA */}
              <div className="pt-3 border-t border-line flex justify-end">
                <Link
                  to="/academics/curriculum"
                  className="inline-flex items-center gap-1 text-xs font-bold text-secondary hover:underline"
                >
                  View Detailed Grade Sheet & Full Syllabus
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </CardBody>
          </Card>

          {/* 2. SUMMER INTERNSHIP TRACKER CARD */}
          <Card className="card-luxe-shadow">
            <div className="p-5 sm:p-6 border-b border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="font-heading text-base sm:text-lg font-bold text-ink flex items-center gap-2">
                  <Route className="h-5 w-5 text-secondary" />
                  Industrial Training / Summer Internship
                </h2>
                <p className="text-xs text-ink-muted">
                  Mandatory Industry Exposure Program • CP-608 (6 Credits)
                </p>
              </div>
              <span className="px-3 py-1 rounded-full bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200 border border-blue-200 dark:border-blue-800 text-xs font-bold shrink-0">
                In Progress (Stage 3 of 8)
              </span>
            </div>

            <CardBody className="space-y-4">
              {/* Stepper Visualization */}
              <div className="py-2 overflow-x-auto">
                <div className="flex items-center min-w-[580px] justify-between relative px-2">
                  {/* Step 1 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-secondary text-white flex items-center justify-center font-bold text-xs shadow-xs">
                      ✓
                    </div>
                    <span className="text-[11px] font-semibold text-ink mt-1.5 text-center">1. Reg.</span>
                  </div>
                  {/* Step 2 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-secondary text-white flex items-center justify-center font-bold text-xs shadow-xs">
                      ✓
                    </div>
                    <span className="text-[11px] font-semibold text-ink mt-1.5 text-center">2. NOC Issued</span>
                  </div>
                  {/* Step 3 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs ring-4 ring-blue-200 shadow-sm">
                      3
                    </div>
                    <span className="text-[11px] font-bold text-secondary mt-1.5 text-center">3. Month Rep 1</span>
                  </div>
                  {/* Step 4 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-surface-muted text-ink-subtle flex items-center justify-center font-bold text-xs border border-line">
                      4
                    </div>
                    <span className="text-[11px] font-medium text-ink-subtle mt-1.5 text-center">4. Month Rep 2</span>
                  </div>
                  {/* Step 5 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-surface-muted text-ink-subtle flex items-center justify-center font-bold text-xs border border-line">
                      5
                    </div>
                    <span className="text-[11px] font-medium text-ink-subtle mt-1.5 text-center">5. Mid Review</span>
                  </div>
                  {/* Step 6 */}
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-surface-muted text-ink-subtle flex items-center justify-center font-bold text-xs border border-line">
                      6
                    </div>
                    <span className="text-[11px] font-medium text-ink-subtle mt-1.5 text-center">6. Final Report</span>
                  </div>
                </div>
              </div>

              {/* Internship Info Box */}
              <div className="rounded-lg bg-surface-muted/40 border border-line p-4 space-y-2 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold text-ink">Adani Green Energy Ltd. (Renewables Hub, Gandhinagar)</span>
                  <span className="text-2xs bg-amber-100 text-amber-900 px-2 py-0.5 rounded font-semibold">
                    Report 1 due in 4 days
                  </span>
                </div>
                <p className="text-2xs text-ink-muted">
                  Industry Mentor: Dr. Vikram Trivedi (Principal AI Architect) • Faculty Guide: Prof. Rajesh Patel (ICT)
                </p>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap items-center gap-2.5 pt-1">
                <LinkButton
                  to="/internships/record"
                  variant="primary"
                  size="sm"
                >
                  Submit Monthly Report 1
                </LinkButton>
                <Button
                  variant="secondary"
                  size="sm"
                >
                  Download Approved NOC
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* COLUMN 2 (Narrow: 4 columns): Faculty Mentor & Campus Events */}
        <div className="xl:col-span-4 space-y-6">
          {/* ASSIGNED FACULTY MENTOR CARD */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Assigned Faculty Mentor"
              icon={<UserCheck className="h-4 w-4 text-primary" />}
            />
            <CardBody className="space-y-4">
              <div className="flex items-start gap-3">
                <Avatar name={data.mentor?.name ?? "Dr. Shweta Shah"} size="lg" />
                <div className="min-w-0">
                  <p className="text-sm font-bold text-ink">{data.mentor?.name ?? "Dr. Shweta Shah"}</p>
                  <p className="text-xs text-ink-muted">{data.mentor?.designation ?? "Associate Professor"}</p>
                  <p className="text-xs text-ink-subtle">{data.mentor?.department ?? "Department of ICT"}</p>
                </div>
              </div>

              <div className="space-y-2 border-t border-line pt-3 text-xs text-ink-muted">
                <div className="flex items-center gap-2">
                  <MapPin className="h-3.5 w-3.5 text-ink-subtle shrink-0" />
                  <span>Block E - Cabin {data.mentor?.cabin ?? "204"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Mail className="h-3.5 w-3.5 text-ink-subtle shrink-0" />
                  <span className="truncate">{data.mentor?.email ?? "shweta.shah@sot.pdpu.ac.in"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Phone className="h-3.5 w-3.5 text-ink-subtle shrink-0" />
                  <span>+91 79 2327 5412</span>
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-muted/60 border border-line text-2xs space-y-1">
                <span className="font-semibold text-ink">Upcoming Interaction:</span>
                <p className="text-ink-muted">Next Mentee Review: 18th March 2025, 03:30 PM</p>
              </div>

              <div className="flex gap-2">
                <LinkButton to="/mentorship" variant="primary" size="sm" className="flex-1 justify-center">
                  Schedule 1:1
                </LinkButton>
                <LinkButton to="/mentorship" variant="secondary" size="sm" className="flex-1 justify-center">
                  Message
                </LinkButton>
              </div>
            </CardBody>
          </Card>

          {/* CAMPUS HAPPENINGS & EVENTS */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Campus Happenings & Deadlines"
              icon={<Calendar className="h-4 w-4 text-purple-600" />}
              action={<CardAction to="/events">Calendar</CardAction>}
            />
            <CardBody className="space-y-3">
              <div className="p-3 rounded-lg border border-line bg-surface-muted/30 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold text-ink">Tesseract '25: Annual Tech Fest</p>
                  <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded font-semibold">
                    Technical
                  </span>
                </div>
                <p className="text-2xs text-ink-subtle">PDEU ACM Student Chapter • 22 Mar, 09:00 AM</p>
              </div>

              <div className="p-3 rounded-lg border border-line bg-surface-muted/30 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold text-ink">Grid AI & Smart Transformers</p>
                  <span className="text-[10px] bg-purple-100 text-purple-800 px-1.5 py-0.5 rounded font-semibold">
                    Guest Lecture
                  </span>
                </div>
                <p className="text-2xs text-ink-subtle">Energy Institute • 25 Mar, 02:00 PM</p>
              </div>

              <div className="p-3 rounded-lg border border-line bg-surface-muted/30 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold text-ink">Mid-Semester Exam Form Submission</p>
                  <span className="text-[10px] bg-amber-100 text-amber-900 px-1.5 py-0.5 rounded font-semibold">
                    Deadline
                  </span>
                </div>
                <p className="text-2xs text-ink-subtle">Exam Cell Notification • 28 Mar</p>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
