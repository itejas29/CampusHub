import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Calendar,
  CalendarClock,
  ChevronRight,
  ClipboardCheck,
  Download,
  FileSpreadsheet,
  FileText,
  Megaphone,
  PlusCircle,
  ShieldAlert,
  UserCheck,
  Users,
  Users2,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/format";
import { roman } from "@/lib/utils";
import type { FacultyDashboard as Data } from "@/types";

export function FacultyDashboard() {
  const { user, can, coordinates } = useAuth();
  const [reviewTab, setReviewTab] = useState<"all" | "cssi" | "summer">("all");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "faculty"],
    queryFn: () => api.get<Data>("/dashboard/faculty"),
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const isSummerCoordinator = coordinates("SUMMER_INTERNSHIP");
  const isCssiCoordinator = coordinates("CSSI");
  const isInternshipCoordinator =
    can("internships:manage") || isSummerCoordinator || isCssiCoordinator;

  const targetProgramId = isSummerCoordinator ? "2" : "1";
  const coordinations = user?.faculty?.coordinations ?? [];

  const firstName = user?.full_name ? user.full_name.split(" ")[1] ?? user.full_name : "Faculty";

  const menteesCount = data.stats.find((s) => s.key === "mentees")?.value ?? 254;
  const pendingReviewsCount = data.stats.find((s) => s.key === "pending_reviews")?.value ?? 4;

  return (
    <div className="space-y-6">
      {/* 1. Page Header & Institutional Breadcrumbs */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2 border-b border-line">
        <div className="space-y-1.5">
          {/* Breadcrumb trail */}
          <nav className="flex items-center gap-1.5 text-xs text-ink-subtle">
            <Link to="/" className="hover:text-primary transition-colors">CampusHub</Link>
            <ChevronRight className="h-3 w-3 text-ink-subtle" />
            <span>Faculty Portal</span>
            <ChevronRight className="h-3 w-3 text-ink-subtle" />
            <span className="font-medium text-ink-muted">
              {isSummerCoordinator
                ? "Summer Internship Coordination"
                : isCssiCoordinator
                ? "CSSI Coordination"
                : "Department Portal"}
            </span>
            <ChevronRight className="h-3 w-3 text-ink-subtle" />
            <span className="font-semibold text-primary">Dashboard</span>
          </nav>

          <h1 className="font-heading text-xl sm:text-2xl font-bold tracking-tight text-ink">
            Welcome back, Prof. {firstName} 👋
          </h1>

          {/* Badges Cluster */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 text-xs font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              Active Faculty
            </span>
            {coordinations.length > 0 ? (
              coordinations.map((c, i) => (
                <span
                  key={i}
                  className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950 text-blue-900 dark:text-blue-200 border border-blue-200 dark:border-blue-900 text-xs font-semibold"
                >
                  {c.domain === "SUMMER_INTERNSHIP"
                    ? `Summer Internship Coordinator — ${c.department_code ?? "ICT"}`
                    : c.domain === "CSSI"
                    ? `CSSI Coordinator — ${c.department_code ?? "ICT"}`
                    : c.domain === "OPEN_ELECTIVE"
                    ? `Open Elective Coordinator — ${c.department_code ?? "ICT"}`
                    : c.domain === "CORE_ELECTIVE"
                    ? `Core Elective Coordinator — ${c.department_code ?? "ICT"}`
                    : c.domain === "MINOR"
                    ? `Minor Coordinator — ${c.department_code ?? "ICT"}`
                    : c.domain === "MOOC"
                    ? `NPTEL / MOOC Coordinator — ${c.department_code ?? "ICT"}`
                    : `${c.domain} Coordinator — ${c.department_code ?? "ICT"}`}
                </span>
              ))
            ) : (
              user?.faculty?.designation && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950 text-blue-900 dark:text-blue-200 border border-blue-200 dark:border-blue-900 text-xs font-semibold">
                  {user.faculty.designation}
                </span>
              )
            )}
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-muted text-ink-muted border border-line text-xs font-medium">
              School of Technology
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-muted text-ink-subtle border border-line text-xs">
              Academic Year 2024–25
            </span>
            {user?.faculty?.cabin && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-muted text-ink-subtle border border-line text-xs font-mono">
                Cabin {user.faculty.cabin}
              </span>
            )}
          </div>
        </div>

        {/* Quick Top Actions */}
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          <LinkButton
            to="/announcements"
            variant="secondary"
            size="sm"
            icon={<PlusCircle className="h-4 w-4 text-primary" />}
          >
            Create Announcement
          </LinkButton>
          {isInternshipCoordinator && (
            <LinkButton
              to={`/internships/mentor-assignment?program_id=${targetProgramId}`}
              variant="primary"
              size="sm"
              icon={<UserCheck className="h-4 w-4" />}
            >
              Assign Mentors
            </LinkButton>
          )}
        </div>
      </div>

      {/* 2. COORDINATION PORTAL HERO BANNER */}
      {isInternshipCoordinator && (
        <section className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#1e3a5f] via-[#162c48] to-[#2563eb] p-6 text-white shadow-md">
          {/* Decorative Subtle Geometric Grid Pattern */}
          <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(#ffffff_1px,transparent_1px)] [background-size:16px_16px]" />
          <div className="absolute -right-16 -top-16 w-64 h-64 rounded-full bg-blue-400/20 blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="max-w-2xl space-y-2">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-white/10 backdrop-blur-md text-[11px] font-semibold tracking-wide uppercase text-blue-200">
                <ShieldAlert className="h-3.5 w-3.5" />
                {isSummerCoordinator
                  ? "B.Tech ICT — 3rd & 4th Year Cohort • Summer Internship"
                  : "B.Tech ICT — 2nd Year Cohort • CSSI"}
              </div>
              <h2 className="font-heading text-xl sm:text-2xl font-bold tracking-tight text-white">
                {isSummerCoordinator
                  ? "Summer Internship Coordination Portal — ICT"
                  : "CSSI Coordination Portal — ICT"}
              </h2>
              <p className="text-sm text-blue-100 max-w-xl leading-relaxed">
                {isSummerCoordinator
                  ? "Summer Industry Internship management, organization offer letter verification, and faculty mentor allocation workflow for 409 registered students."
                  : "Community & Social Service Internship management, NGO verification desk, and faculty mentor allocation workflow for 203 registered students."}
              </p>
            </div>

            {/* Hero Action CTAs */}
            <div className="flex flex-wrap items-center gap-3 shrink-0">
              <Link
                to={`/internships/mentor-assignment?program_id=${targetProgramId}`}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white text-[#1e3a5f] font-heading text-sm font-bold shadow-md hover:bg-slate-100 transition-all hover:scale-[1.02] active:scale-95"
              >
                <UserCheck className="h-4 w-4 text-blue-600" />
                <span>Assign Mentors</span>
              </Link>
              <Link
                to="/internships/students"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white/15 backdrop-blur-sm border border-white/20 text-white text-sm font-medium hover:bg-white/25 transition-all"
              >
                <Download className="h-4 w-4" />
                <span>Batch Download NOCs</span>
              </Link>
            </div>
          </div>

          {/* Banner Embedded Metrics Strip */}
          <div className="relative z-10 grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-5 border-t border-white/15">
            <div className="space-y-1">
              <p className="text-2xs uppercase tracking-wider text-blue-200/90 font-medium">
                Registered Students
              </p>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-2xl font-bold text-white">
                  {isSummerCoordinator ? "409" : "203"}
                </span>
                <span className="text-2xs text-emerald-300 font-semibold font-mono">100% Cohort</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-2xs uppercase tracking-wider text-blue-200/90 font-medium">
                Mentors Assigned
              </p>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-2xl font-bold text-white">
                  {isSummerCoordinator ? "38" : "21"}
                </span>
                <span className="text-2xs text-blue-200 font-mono">
                  {isSummerCoordinator ? "~10.8/mentor" : "~9.6/mentor"}
                </span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-2xs uppercase tracking-wider text-blue-200/90 font-medium">
                Allocation Status
              </p>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-2xl font-bold text-emerald-300">
                  {isSummerCoordinator ? "24" : "0"}
                </span>
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-200 text-[10px] font-bold uppercase tracking-wider">
                  {isSummerCoordinator ? "In Progress" : "All Allocated"}
                </span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-2xs uppercase tracking-wider text-blue-200/90 font-medium">
                {isSummerCoordinator ? "Pending Offer Letters" : "Pending NGO Approvals"}
              </p>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-2xl font-bold text-amber-300">
                  {isSummerCoordinator ? "8" : "4"}
                </span>
                <span className="text-2xs text-amber-200 font-mono">Requires Action</span>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 3. EXECUTIVE STAT TILES (4-Column Grid with Stitch Styling) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Tile 1: Assigned Mentees */}
        <div className="bg-surface border border-line rounded-xl p-5 shadow-xs hover-lift transition-all">
          <div className="flex items-center justify-between text-ink-muted mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Assigned Mentees</span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center text-primary">
              <Users className="h-4 w-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {menteesCount}
            </span>
            <span className="text-xs text-emerald-600 font-medium">Students</span>
          </div>
          <p className="text-2xs text-ink-subtle mt-1.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
            4 3rd Year, 8 2nd Year • All active
          </p>
        </div>

        {/* Tile 2: Pending Reviews */}
        <div className="bg-surface border border-line rounded-xl p-5 shadow-xs hover-lift transition-all ring-1 ring-amber-500/20">
          <div className="flex items-center justify-between text-ink-muted mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Pending Reviews</span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-950 flex items-center justify-center text-amber-600">
              <ClipboardCheck className="h-4 w-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-amber-600">
              {pendingReviewsCount}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 text-[10px] font-semibold">
              Action Required
            </span>
          </div>
          <p className="text-2xs text-ink-subtle mt-1.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            2 Stage-2 Reports, 2 NOC requests
          </p>
        </div>

        {/* Tile 3: Active Announcements */}
        <div className="bg-surface border border-line rounded-xl p-5 shadow-xs hover-lift transition-all">
          <div className="flex items-center justify-between text-ink-muted mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Circulars</span>
            <div className="w-8 h-8 rounded-lg bg-purple-50 dark:bg-purple-950 flex items-center justify-center text-purple-600">
              <Megaphone className="h-4 w-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {data.announcements.length || 3}
            </span>
            <span className="text-xs text-ink-muted font-medium">Notices</span>
          </div>
          <p className="text-2xs text-ink-subtle mt-1.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>
            2 ICT Dept, 1 University-wide
          </p>
        </div>

        {/* Tile 4: Upcoming Meetings */}
        <div className="bg-surface border border-line rounded-xl p-5 shadow-xs hover-lift transition-all">
          <div className="flex items-center justify-between text-ink-muted mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Upcoming Meetings</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950 flex items-center justify-center text-emerald-600">
              <Calendar className="h-4 w-4" />
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {data.upcoming_meetings.length || 2}
            </span>
            <span className="text-xs text-emerald-600 font-medium">Scheduled</span>
          </div>
          <p className="text-2xs text-ink-subtle mt-1.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            Next: Mentee Review at 03:00 PM today
          </p>
        </div>
      </section>

      {/* 4. MAIN TWO-COLUMN DASHBOARD GRID */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* LEFT COLUMN (8 cols / ~65%): Evaluation Queue & Mentees */}
        <div className="space-y-6 lg:col-span-8">
          {/* Card: Pending Reviews & Submissions */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title={`Pending Submissions & Evaluations (${data.pending_reviews.length})`}
              description="Student reports and milestones awaiting coordinator evaluation."
              icon={<ClipboardCheck className="h-4 w-4 text-amber-500" />}
              action={
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setReviewTab("all")}
                    className={`px-2.5 py-1 text-2xs font-semibold rounded ${
                      reviewTab === "all"
                        ? "bg-primary text-white"
                        : "text-ink-muted hover:bg-surface-muted"
                    }`}
                  >
                    All ({data.pending_reviews.length})
                  </button>
                  <button
                    onClick={() => setReviewTab("cssi")}
                    className={`px-2.5 py-1 text-2xs font-semibold rounded ${
                      reviewTab === "cssi"
                        ? "bg-primary text-white"
                        : "text-ink-muted hover:bg-surface-muted"
                    }`}
                  >
                    CSSI Reports
                  </button>
                  <button
                    onClick={() => setReviewTab("summer")}
                    className={`px-2.5 py-1 text-2xs font-semibold rounded ${
                      reviewTab === "summer"
                        ? "bg-primary text-white"
                        : "text-ink-muted hover:bg-surface-muted"
                    }`}
                  >
                    Summer Training
                  </button>
                </div>
              }
            />

            {data.pending_reviews.length === 0 ? (
              <EmptyState
                compact
                title="No pending reviews"
                description="Submissions from your assigned students will appear here."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-surface-muted/60 text-2xs font-semibold uppercase tracking-wider text-ink-subtle border-b border-line">
                    <tr>
                      <th className="py-2.5 px-4">Student</th>
                      <th className="py-2.5 px-3">Programme</th>
                      <th className="py-2.5 px-3">Stage / Milestone</th>
                      <th className="py-2.5 px-3">Submitted</th>
                      <th className="py-2.5 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.pending_reviews.map((review) => (
                      <tr key={`${review.type}-${review.id}`} className="hover:bg-surface-muted/40 transition-colors">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2.5">
                            <Avatar name={review.student} size="sm" />
                            <div>
                              <p className="font-semibold text-ink leading-tight">{review.student}</p>
                              <p className="font-mono text-2xs text-secondary mt-0.5">{review.roll_number}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-ink-muted">B.Tech ICT</td>
                        <td className="py-3 px-3">
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200 font-medium text-2xs">
                            <FileText className="h-3 w-3 text-blue-600" />
                            {review.label}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-ink-subtle text-2xs">
                          {relativeTime(review.submitted_at)}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Link
                            to={review.link}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-white text-2xs font-semibold hover:bg-primary/90 transition-all shadow-xs"
                          >
                            <span>Evaluate</span>
                            <ChevronRight className="h-3 w-3" />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Card: My Direct Mentees Preview */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title={`My Direct Mentees (${data.mentees_preview.length})`}
              description="Assigned mentee roster with progress tracking."
              icon={<Users2 className="h-4 w-4 text-primary" />}
              action={
                <LinkButton
                  to="/mentorship/mentees"
                  variant="secondary"
                  size="sm"
                  iconRight={<ArrowRight className="h-3.5 w-3.5" />}
                >
                  View All Mentees
                </LinkButton>
              }
            />
            {data.mentees_preview.length === 0 ? (
              <EmptyState
                compact
                title="No mentees assigned"
                description="Assigned mentees will appear here once allocated."
              />
            ) : (
              <CardBody className="grid gap-3 sm:grid-cols-2">
                {data.mentees_preview.map((mentee) => (
                  <div
                    key={mentee.student_id}
                    className="flex flex-col justify-between p-3.5 rounded-lg border border-line bg-surface hover:border-line-strong hover-lift transition-all"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <Avatar name={mentee.name} src={mentee.avatar_url} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-ink leading-tight">{mentee.name}</p>
                          <p className="truncate text-2xs text-ink-subtle mt-0.5">
                            <span className="font-mono text-secondary font-semibold">{mentee.roll_number}</span>
                            {" · "}Sem {roman(mentee.semester)}
                          </p>
                        </div>
                      </div>
                      {mentee.cpi !== null && (
                        <span className="px-1.5 py-0.5 rounded bg-surface-muted text-xs font-mono font-bold text-ink">
                          {mentee.cpi.toFixed(2)} CPI
                        </span>
                      )}
                    </div>

                    <div className="mt-3 pt-2 border-t border-line/40 flex items-center justify-between text-2xs text-ink-subtle">
                      <span>Status: Active Mentee</span>
                      <Link
                        to={`/mentorship/mentees/${mentee.student_id}`}
                        className="text-primary font-semibold hover:underline flex items-center gap-0.5"
                      >
                        Profile →
                      </Link>
                    </div>
                  </div>
                ))}
              </CardBody>
            )}
          </Card>
        </div>

        {/* RIGHT COLUMN (4 cols / ~35%): Schedule, Announcements, Shortcuts */}
        <div className="space-y-6 lg:col-span-4">
          {/* Today's Schedule & Meeting Requests */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Today's Schedule & Reviews"
              icon={<CalendarClock className="h-4 w-4 text-primary" />}
              action={<CardAction to="/mentorship" label="Manage">Manage</CardAction>}
            />
            {data.upcoming_meetings.length === 0 ? (
              <EmptyState compact title="No meetings scheduled for today" />
            ) : (
              <ul className="divide-y divide-line">
                {data.upcoming_meetings.map((meeting) => (
                  <li key={meeting.id} className="p-3.5 hover:bg-surface-muted/30 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-semibold text-ink leading-snug">
                        {meeting.title}
                      </p>
                      <StatusBadge status={meeting.status} />
                    </div>
                    <p className="mt-1 text-2xs text-ink-muted flex items-center gap-1.5">
                      <Avatar name={meeting.student} size="xs" />
                      <span>{meeting.student}</span>
                    </p>
                    <p className="mt-1 text-2xs font-mono text-secondary flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {formatDateTime(meeting.scheduled_at ?? meeting.proposed_slot)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Quick Portal Shortcuts (Stitch Design Spec) */}
          <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">
              Quick Coordination Shortcuts
            </h3>
            <div className="space-y-2 text-xs">
              <Link
                to="/internships/mentor-assignment"
                className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
              >
                <div className="flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-blue-600" />
                  <span>CSSI Mentor Allocation Engine</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
              </Link>
              <Link
                to="/internships/students"
                className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
              >
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
                  <span>CSSI Master Spreadsheet Export</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
              </Link>
              <Link
                to="/faculty/directory"
                className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
              >
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-purple-600" />
                  <span>Faculty Directory (25+ Members)</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
              </Link>
            </div>
          </div>

          {/* Department Announcements & Circulars */}
          <Card className="card-luxe-shadow">
            <CardHeader
              title="Recent Announcements"
              icon={<Megaphone className="h-4 w-4 text-purple-600" />}
              action={<CardAction to="/announcements" label="All">View All</CardAction>}
            />
            {data.announcements.length === 0 ? (
              <EmptyState compact title="No announcements posted" />
            ) : (
              <ul className="divide-y divide-line text-xs">
                {data.announcements.map((item) => (
                  <li key={item.id} className="p-3.5 hover:bg-surface-muted/30 transition-colors">
                    <p className="font-semibold text-ink leading-snug">{item.title}</p>
                    <p className="mt-1 line-clamp-2 text-2xs text-ink-muted">{item.excerpt}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
