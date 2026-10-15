import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Award,
  BadgeCheck,
  BookOpen,
  Briefcase,
  Calendar,
  CalendarClock,
  ChevronRight,
  ClipboardCheck,
  FileText,
  GraduationCap,
  Layers,
  Megaphone,
  PlusCircle,
  Sparkles,
  UserCheck,
  Users,
  Users2,
  UserSquare2,
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
import type { Coordination, FacultyDashboard as Data } from "@/types";

function getPortfolioDetails(coord: Coordination) {
  const dept = coord.department_code || "ICT";
  switch (coord.domain) {
    case "SUMMER_INTERNSHIP":
      return {
        title: "Summer Internship Coordination",
        roleBadge: "Summer Industry Internship",
        badgeStyle:
          "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/70 dark:text-blue-300 dark:border-blue-800",
        cohortBadge: `B.Tech ${dept} — 3rd & 4th Year`,
        description:
          "Oversee summer industry internships, student registration, corporate offer letter verification, and faculty mentor assignments.",
        icon: Briefcase,
        iconBg: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400",
        stats: [
          { label: "Registered Students", value: "409", hint: "100% Cohort" },
          { label: "Mentors Assigned", value: "38", hint: "~10.8/mentor" },
          {
            label: "Allocation Status",
            value: "In Progress",
            statusColor: "text-emerald-600 dark:text-emerald-400",
          },
          { label: "Offer Letters", value: "8", hint: "Requires Action" },
        ],
        primaryAction: {
          label: "Assign Mentors",
          to: "/internships/mentor-assignment?program_id=2",
          icon: UserCheck,
        },
        secondaryAction: {
          label: "View All Students",
          to: "/internships/students?program_id=2",
        },
      };
    case "CSSI":
      return {
        title: "CSSI Coordination",
        roleBadge: "Community & Social Service Internship",
        badgeStyle:
          "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800",
        cohortBadge: `B.Tech ${dept} — 2nd Year`,
        description:
          "Community and social service internship administration, NGO organization verification desk, and faculty mentor allocation.",
        icon: Users,
        iconBg:
          "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
        stats: [
          { label: "Registered Students", value: "203", hint: "100% Cohort" },
          { label: "Mentors Assigned", value: "21", hint: "~9.6/mentor" },
          {
            label: "Allocation Status",
            value: "Completed",
            statusColor: "text-emerald-600 dark:text-emerald-400",
          },
          { label: "Pending Approvals", value: "4", hint: "NGO Check" },
        ],
        primaryAction: {
          label: "Assign Mentors",
          to: "/internships/mentor-assignment?program_id=1",
          icon: UserCheck,
        },
        secondaryAction: {
          label: "View All Students",
          to: "/internships/students?program_id=1",
        },
      };
    case "MINOR":
      return {
        title: "Minor Specialization Coordination",
        roleBadge: "Minor Track Management",
        badgeStyle:
          "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/70 dark:text-purple-300 dark:border-purple-800",
        cohortBadge: `Dept. of ${dept} • Interdisciplinary`,
        description:
          "Oversee departmental minor track offerings, review cross-department student applications, seat quotas, and prerequisite validations.",
        icon: Sparkles,
        iconBg:
          "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400",
        stats: [
          { label: "Track Status", value: "Active", hint: "Enrolling" },
          {
            label: "Applications",
            value: "Open",
            statusColor: "text-emerald-600 dark:text-emerald-400",
          },
        ],
        primaryAction: {
          label: "Review Applications",
          to: "/admin/minors",
          icon: ClipboardCheck,
        },
        secondaryAction: {
          label: "Curriculum Explorer",
          to: "/academics/curriculums",
        },
      };
    case "OPEN_ELECTIVE":
      return {
        title: "Open Electives Coordination",
        roleBadge: "University Open Electives",
        badgeStyle:
          "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800",
        cohortBadge: `Dept. of ${dept}`,
        description:
          "Manage institution-wide open elective course offerings, student preference rounds, and automated seat allocations.",
        icon: BookOpen,
        iconBg:
          "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
        stats: [
          { label: "Basket Status", value: "Active", hint: "Curriculum" },
          { label: "Registration", value: "Scheduled", hint: "Round 1" },
        ],
        primaryAction: {
          label: "Registration Rounds",
          to: "/admin/elective-rounds",
          icon: CalendarClock,
        },
        secondaryAction: {
          label: "Run Allocation",
          to: "/admin/electives",
        },
      };
    case "CORE_ELECTIVE":
      return {
        title: "Core Electives Coordination",
        roleBadge: "Department Core Electives",
        badgeStyle:
          "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/70 dark:text-indigo-300 dark:border-indigo-800",
        cohortBadge: `Dept. of ${dept}`,
        description:
          "Oversee department elective baskets, track distributions, section capacities, and student preference allocations.",
        icon: Layers,
        iconBg:
          "bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400",
        stats: [
          { label: "Baskets", value: "Defined", hint: "Syllabus" },
          { label: "Quota Allocation", value: "Ready", hint: "Pending Window" },
        ],
        primaryAction: {
          label: "Registration Rounds",
          to: "/admin/elective-rounds",
          icon: CalendarClock,
        },
        secondaryAction: {
          label: "Run Allocation",
          to: "/admin/electives",
        },
      };
    case "MOOC":
      return {
        title: "NPTEL / MOOC Coordination",
        roleBadge: "Online Learning & Equivalence",
        badgeStyle:
          "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/70 dark:text-cyan-300 dark:border-cyan-800",
        cohortBadge: `Dept. of ${dept}`,
        description:
          "Review and verify external SWAYAM/NPTEL certificates, validate course credits, and execute grade transfers.",
        icon: BadgeCheck,
        iconBg:
          "bg-cyan-50 text-cyan-600 dark:bg-cyan-950 dark:text-cyan-400",
        primaryAction: {
          label: "Verify Certificates",
          to: "/admin/nptel",
          icon: BadgeCheck,
        },
      };
    case "MENTORSHIP":
      return {
        title: "Faculty Mentorship Programme",
        roleBadge: "Student Welfare & Mentorship",
        badgeStyle:
          "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/70 dark:text-rose-300 dark:border-rose-800",
        cohortBadge: `Dept. of ${dept}`,
        description:
          "Oversee faculty mentor allocations, student counselor meetings, and semester progress tracking.",
        icon: UserSquare2,
        iconBg:
          "bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-400",
        primaryAction: {
          label: "Mentorship Desk",
          to: "/mentorship",
          icon: Users,
        },
      };
    default:
      return {
        title: `${coord.domain} Coordination`,
        roleBadge: "Department Portfolio",
        badgeStyle:
          "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800",
        cohortBadge: `Dept. of ${dept}`,
        description:
          "Institutional portfolio management and coordination responsibilities.",
        icon: Award,
        iconBg:
          "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
        primaryAction: {
          label: "Access Desk",
          to: "/",
          icon: ArrowRight,
        },
      };
  }
}

function PortfolioCard({ coord }: { coord: Coordination }) {
  const details = getPortfolioDetails(coord);
  const Icon = details.icon;
  const PrimaryIcon = details.primaryAction.icon;

  return (
    <div className="relative overflow-hidden rounded-xl border border-line bg-surface p-5 shadow-xs hover:border-line-strong hover-lift transition-all flex flex-col justify-between">
      {/* Top subtle highlight */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary to-primary/30" />

      <div>
        {/* Top Badges and Title */}
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${details.iconBg}`}
            >
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-heading text-base font-bold text-ink leading-tight">
                {details.title}
              </h3>
              <p className="text-2xs text-ink-subtle mt-0.5 font-medium">
                {details.cohortBadge}
              </p>
            </div>
          </div>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${details.badgeStyle}`}
          >
            {details.roleBadge}
          </span>
        </div>

        {/* Portfolio Description */}
        <p className="text-xs text-ink-muted leading-relaxed mb-4">
          {details.description}
        </p>

        {/* Embedded Stats Strip */}
        {details.stats && details.stats.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 py-2.5 px-3 mb-4 rounded-lg bg-surface-muted/60 border border-line/60">
            {details.stats.map((s, idx) => (
              <div key={idx} className="space-y-0.5">
                <span className="text-[10px] uppercase font-semibold text-ink-subtle tracking-wider block">
                  {s.label}
                </span>
                <div className="flex items-baseline gap-1.5">
                  <span
                    className={`font-mono text-sm font-bold ${
                      s.statusColor ?? "text-ink"
                    }`}
                  >
                    {s.value}
                  </span>
                  {s.hint && (
                    <span className="text-[10px] text-ink-subtle font-mono">
                      {s.hint}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-line/60">
        <Link
          to={details.primaryAction.to}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-xs font-semibold hover:bg-primary/90 transition-colors shadow-xs"
        >
          {PrimaryIcon && <PrimaryIcon className="h-3.5 w-3.5" />}
          <span>{details.primaryAction.label}</span>
        </Link>
        {details.secondaryAction && (
          <Link
            to={details.secondaryAction.to}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-line bg-surface hover:bg-surface-muted text-ink text-xs font-medium transition-colors"
          >
            <span>{details.secondaryAction.label}</span>
          </Link>
        )}
      </div>
    </div>
  );
}

export function FacultyDashboard() {
  const { user } = useAuth();
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

  const rawCoordinations = user?.faculty?.coordinations ?? [];
  // Deduplicate coordinations by domain to prevent redundant badges and cards
  const uniqueCoordinations = Array.from(
    new Map(rawCoordinations.map((c) => [c.domain, c])).values()
  );

  const firstName = user?.full_name ? user.full_name.split(" ")[1] ?? user.full_name : "Faculty";

  const menteesCount = data.stats.find((s) => s.key === "mentees")?.value ?? 254;
  const pendingReviewsCount = data.stats.find((s) => s.key === "pending_reviews")?.value ?? 4;

  const filteredReviews = data.pending_reviews.filter((review) => {
    if (reviewTab === "cssi") {
      return (
        review.label.toLowerCase().includes("cssi") ||
        review.link.includes("cssi") ||
        review.label.toLowerCase().includes("ngo")
      );
    }
    if (reviewTab === "summer") {
      return (
        !review.label.toLowerCase().includes("cssi") &&
        !review.link.includes("cssi")
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* 1. Page Header & Institutional Breadcrumbs */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2 border-b border-line">
        <div className="space-y-1.5">
          {/* Breadcrumb trail */}
          <nav className="flex items-center gap-1.5 text-xs text-ink-subtle">
            <Link to="/" className="hover:text-primary transition-colors">
              CampusHub
            </Link>
            <ChevronRight className="h-3 w-3 text-ink-subtle" />
            <span>Faculty Portal</span>
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
            {user?.faculty?.designation && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 text-xs font-medium">
                {user.faculty.designation}
              </span>
            )}
            {user?.faculty?.department_code && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-900 text-xs font-medium">
                Dept. of {user.faculty.department_code}
              </span>
            )}
            {uniqueCoordinations.map((c) => (
              <span
                key={c.domain}
                className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-900 dark:text-indigo-200 border border-indigo-200 dark:border-indigo-900 text-xs font-semibold"
              >
                {c.domain === "SUMMER_INTERNSHIP"
                  ? `Summer Internship Coordinator`
                  : c.domain === "CSSI"
                  ? `CSSI Coordinator`
                  : c.domain === "OPEN_ELECTIVE"
                  ? `Open Electives Coordinator`
                  : c.domain === "CORE_ELECTIVE"
                  ? `Core Electives Coordinator`
                  : c.domain === "MINOR"
                  ? `Minor Coordinator`
                  : c.domain === "MOOC"
                  ? `NPTEL / MOOC Coordinator`
                  : `${c.domain} Coordinator`}
              </span>
            ))}
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-muted text-ink-muted border border-line text-xs font-medium">
              School of Technology
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-surface-muted text-ink-subtle border border-line text-xs">
              Academic Year 2025–26
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
          <LinkButton
            to="/mentorship/mentees"
            variant="primary"
            size="sm"
            icon={<Users className="h-4 w-4" />}
          >
            My Mentees
          </LinkButton>
        </div>
      </div>

      {/* 2. APPOINTED RESPONSIBILITIES & PORTFOLIOS (If holding any coordination role) */}
      {uniqueCoordinations.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-heading text-sm sm:text-base font-bold text-ink flex items-center gap-2">
                <span>Appointed Responsibilities & Portfolios</span>
                <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-semibold">
                  {uniqueCoordinations.length} Active{" "}
                  {uniqueCoordinations.length === 1 ? "Portfolio" : "Portfolios"}
                </span>
              </h2>
              <p className="text-2xs text-ink-subtle">
                Administrative and academic portfolios entrusted to your coordination
              </p>
            </div>
          </div>

          <div
            className={`grid gap-4 ${
              uniqueCoordinations.length === 1
                ? "grid-cols-1"
                : "grid-cols-1 md:grid-cols-2"
            }`}
          >
            {uniqueCoordinations.map((coord) => (
              <PortfolioCard key={coord.domain} coord={coord} />
            ))}
          </div>
        </section>
      )}

      {/* 3. EXECUTIVE STAT TILES (Universal for all Faculty) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Tile 1: Assigned Mentees */}
        <div className="bg-surface border border-line rounded-xl p-5 shadow-xs hover-lift transition-all">
          <div className="flex items-center justify-between text-ink-muted mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">
              Assigned Mentees
            </span>
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
            <span className="text-xs font-semibold uppercase tracking-wider">
              Pending Reviews
            </span>
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
            <span className="text-xs font-semibold uppercase tracking-wider">
              Active Circulars
            </span>
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
            <span className="text-xs font-semibold uppercase tracking-wider">
              Upcoming Meetings
            </span>
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
              title={`Pending Submissions & Evaluations (${filteredReviews.length})`}
              description="Student reports and milestones awaiting faculty evaluation."
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

            {filteredReviews.length === 0 ? (
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
                    {filteredReviews.map((review) => (
                      <tr
                        key={`${review.type}-${review.id}`}
                        className="hover:bg-surface-muted/40 transition-colors"
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2.5">
                            <Avatar name={review.student} size="sm" />
                            <div>
                              <p className="font-semibold text-ink leading-tight">
                                {review.student}
                              </p>
                              <p className="font-mono text-2xs text-secondary mt-0.5">
                                {review.roll_number}
                              </p>
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
                        <Avatar
                          name={mentee.name}
                          src={mentee.avatar_url}
                          size="sm"
                        />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-ink leading-tight">
                            {mentee.name}
                          </p>
                          <p className="truncate text-2xs text-ink-subtle mt-0.5">
                            <span className="font-mono text-secondary font-semibold">
                              {mentee.roll_number}
                            </span>
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
                  <li
                    key={meeting.id}
                    className="p-3.5 hover:bg-surface-muted/30 transition-colors"
                  >
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

          {/* Quick Shortcuts & Portals */}
          <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">
              Quick Coordination & Portals
            </h3>
            <div className="space-y-2 text-xs">
              {uniqueCoordinations.some(
                (c) => c.domain === "SUMMER_INTERNSHIP"
              ) && (
                <Link
                  to="/internships/mentor-assignment?program_id=2"
                  className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
                >
                  <div className="flex items-center gap-2">
                    <UserCheck className="h-4 w-4 text-blue-600" />
                    <span>Summer Internship Mentor Allocation</span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
                </Link>
              )}
              {uniqueCoordinations.some((c) => c.domain === "CSSI") && (
                <Link
                  to="/internships/mentor-assignment?program_id=1"
                  className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
                >
                  <div className="flex items-center gap-2">
                    <UserCheck className="h-4 w-4 text-emerald-600" />
                    <span>CSSI Mentor Allocation</span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
                </Link>
              )}
              {uniqueCoordinations.some((c) => c.domain === "MINOR") && (
                <Link
                  to="/admin/minors"
                  className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-purple-600" />
                    <span>Minor Applications Desk</span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
                </Link>
              )}
              {uniqueCoordinations.some(
                (c) =>
                  c.domain === "OPEN_ELECTIVE" || c.domain === "CORE_ELECTIVE"
              ) && (
                <Link
                  to="/admin/elective-rounds"
                  className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
                >
                  <div className="flex items-center gap-2">
                    <CalendarClock className="h-4 w-4 text-amber-600" />
                    <span>Elective Registration Rounds</span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
                </Link>
              )}
              {uniqueCoordinations.some((c) => c.domain === "MOOC") && (
                <Link
                  to="/admin/nptel"
                  className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
                >
                  <div className="flex items-center gap-2">
                    <BadgeCheck className="h-4 w-4 text-cyan-600" />
                    <span>NPTEL Certificate Verification</span>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
                </Link>
              )}
              <Link
                to="/mentorship"
                className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
              >
                <div className="flex items-center gap-2">
                  <UserSquare2 className="h-4 w-4 text-primary" />
                  <span>Mentor–Mentee Management Desk</span>
                </div>
                <ArrowRight className="h-3.5 w-3.5 text-ink-subtle" />
              </Link>
              <Link
                to="/faculty"
                className="flex items-center justify-between p-2.5 rounded-lg border border-line bg-surface-muted/40 hover:bg-surface-muted transition-colors font-medium text-ink"
              >
                <div className="flex items-center gap-2">
                  <GraduationCap className="h-4 w-4 text-purple-600" />
                  <span>Faculty Directory & Roster</span>
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
                  <li
                    key={item.id}
                    className="p-3.5 hover:bg-surface-muted/30 transition-colors"
                  >
                    <p className="font-semibold text-ink leading-snug">
                      {item.title}
                    </p>
                    <p className="mt-1 line-clamp-2 text-2xs text-ink-muted">
                      {item.excerpt}
                    </p>
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

