import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Variants } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  Dices,
  Download,
  ListOrdered,
  Lock,
  RotateCcw,
  Search,
  ShieldAlert,
  Square,
  UserCheck,
  Users,
  UserX,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { CountUp } from "@/components/ui/CountUp";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Form";
import { Avatar } from "@/components/ui/Misc";
import { ConfirmDialog } from "@/components/ui/Modal";
import { ApiError, api, qs } from "@/lib/api";
import { listContainer, listItem, slideUp } from "@/lib/motion";
import type { EnrollmentSummary, InternshipProgram, MentorCapacity } from "@/types";

// ─── Animation helpers ────────────────────────────────────────────────────────
const EASE = [0.16, 1, 0.3, 1] as const;

const staggerContainer: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};
const cardReveal: Variants = {
  hidden: { opacity: 0, y: 14, scale: 0.98 },
  shown: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.28, ease: EASE } },
};
const heroReveal: Variants = {
  hidden: { opacity: 0, y: 20 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
};

export function MentorAssignmentPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  // The URL is the only source of truth for the programme, so a dashboard link
  // to another programme switches this screen even while it is open.
  const queryProgramId = searchParams.get("program_id");
  const [mentorFilter, setMentorFilter] = useState<string>("ALL");
  const [mentorSearch, setMentorSearch] = useState("");
  const [assignmentTab, setAssignmentTab] = useState<"ALL" | "UNASSIGNED" | "ASSIGNED">("ALL");
  const [search, setSearch] = useState("");
  const [selectedStudentIds, setSelectedStudentIds] = useState<Set<number>>(new Set());
  const [selectedMentorIds, setSelectedMentorIds] = useState<Set<number>>(new Set());
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showClearStudentsConfirm, setShowClearStudentsConfirm] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);

  // Fetch internship programs
  const programsQuery = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });

  const programs = programsQuery.data ?? [];

  const isSuperAdmin = user?.roles.includes("SUPER_ADMIN");

  // Filter programs strictly based on coordinator permissions and department
  const availablePrograms = useMemo(() => {
    if (isSuperAdmin) return programs;

    const myCoordinations = user?.faculty?.coordinations ?? [];
    return programs.filter((p) => {
      // Check if user has an active coordination matching this program's domain and department
      const matchesCoordination = myCoordinations.some((c) => {
        const domainMatches =
          (p.type === "CSSI" && c.domain === "CSSI") ||
          (p.type === "SUMMER" && c.domain === "SUMMER_INTERNSHIP");
        const deptMatches = c.department_id == null || c.department_id === p.department_id;
        return domainMatches && deptMatches;
      });

      // Access is the scoped grant alone. A name match ("Shah" inside "Shah
      // Patel") is not a grant; the server would refuse those writes anyway.
      return matchesCoordination;
    });
  }, [programs, isSuperAdmin, user]);

  // Determine active program: explicit state > search param > user's coordinated program
  const activeProgram = useMemo(() => {
    if (queryProgramId) {
      const match = availablePrograms.find((p) => String(p.id) === queryProgramId);
      if (match) return match;
    }
    return availablePrograms[0] ?? (isSuperAdmin ? programs[0] : null);
  }, [availablePrograms, programs, queryProgramId, isSuperAdmin]);

  const activeProgramId = activeProgram?.id;

  const handleProgramChange = (newId: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("program_id", newId);
      return next;
    });
    setSelectedMentorIds(new Set());
    setSelectedStudentIds(new Set());
    setFeedback(null);
  };

  // Fetch mentor capacities
  const mentorsQuery = useQuery({
    queryKey: ["mentor-capacity", activeProgramId],
    queryFn: () => api.get<MentorCapacity[]>(`/internships/programs/${activeProgramId}/mentors-capacity`),
    enabled: !!activeProgramId,
  });

  // Fetch all enrollments
  const enrollmentsQuery = useQuery({
    queryKey: ["internship-enrollments", "all", activeProgramId],
    queryFn: () =>
      api.get<EnrollmentSummary[]>(
        `/internships/enrollments${qs({
          program_id: activeProgramId || undefined,
        })}`,
      ),
    enabled: !!activeProgramId,
  });

  const mentors = mentorsQuery.data ?? [];
  // Until both lists arrive, "0 students" would be a claim, not a fact.
  const loadingData = mentorsQuery.isLoading || enrollmentsQuery.isLoading;
  const enrollments = enrollmentsQuery.data ?? [];

  // Single mentor assignment mutation
  const assignSingle = useMutation({
    mutationFn: ({ enrollmentId, mentorId }: { enrollmentId: number; mentorId: number | null }) =>
      api.post(`/internships/enrollments/${enrollmentId}/mentor`, {
        mentor_faculty_id: mentorId,
        reason: mentorId ? "Coordinator assigned mentor" : "Coordinator unassigned mentor",
      }),
    onSuccess: () => {
      setFeedback({ tone: "success", text: "Mentor assignment updated successfully." });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setFeedback({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Failed to assign mentor. Please check capacity.",
      });
    },
  });

  // Roll Number Wise Allocation Mutation
  const allocateByRollNo = useMutation({
    mutationFn: (facultyIds?: number[]) =>
      api.post<{ assigned_count: number; message: string }>(
        `/internships/programs/${activeProgramId}/assign-mentors`,
        {
          allocate_by_roll_no: true,
          faculty_ids: facultyIds && facultyIds.length > 0 ? facultyIds : undefined,
          reason: "Roll-number allocation",
        },
      ),
    onSuccess: (res) => {
      setFeedback({ tone: "success", text: res.message });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setFeedback({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Failed to allocate students.",
      });
    },
  });

  // Clear all mentor assignments and selected mentors
  const clearAllAssignments = useMutation({
    mutationFn: () =>
      api.post<{ assigned_count: number; message: string }>(
        `/internships/programs/${activeProgramId}/assign-mentors`,
        {
          clear_all: true,
          reason: "Coordinator cleared all mentor assignments and allocations",
        },
      ),
    onSuccess: (res) => {
      setFeedback({
        tone: "info",
        text: res.message || "All mentor assignments and faculty selections have been cleared.",
      });
      setSelectedMentorIds(new Set());
      setSelectedStudentIds(new Set());
      setShowResetConfirm(false);
      setShowClearStudentsConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setFeedback({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Failed to clear mentor assignments.",
      });
      setShowResetConfirm(false);
      setShowClearStudentsConfirm(false);
    },
  });

  // Clear mentors for a list of student enrollments
  const clearSelectedStudents = useMutation({
    mutationFn: (studentIds: number[]) =>
      api.post<{ assigned_count: number; message: string }>(
        `/internships/programs/${activeProgramId}/assign-mentors`,
        {
          assignments: studentIds.map((id) => ({
            enrollment_id: id,
            mentor_faculty_id: null,
          })),
          reason: "Coordinator cleared mentors for selected students",
        },
      ),
    onSuccess: (res) => {
      setFeedback({
        tone: "success",
        text: res.message || "Cleared mentor assignments for selected students.",
      });
      setSelectedStudentIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setFeedback({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Failed to clear mentors for selected students.",
      });
    },
  });

  // Filtered mentors list
  const filteredMentors = useMemo(() => {
    let list = [...mentors];
    const q = mentorSearch.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          (m.department_code ?? "").toLowerCase().includes(q) ||
          (m.designation ?? "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [mentors, mentorSearch]);

  // Filtered student list sorted by Roll Number
  const filteredStudents = useMemo(() => {
    let list = [...enrollments];

    if (assignmentTab === "UNASSIGNED") {
      list = list.filter((e) => !e.mentor_faculty_id);
    } else if (assignmentTab === "ASSIGNED") {
      list = list.filter((e) => !!e.mentor_faculty_id);
    }

    if (mentorFilter !== "ALL") {
      if (mentorFilter === "UNASSIGNED") {
        list = list.filter((e) => !e.mentor_faculty_id);
      } else {
        const fId = Number(mentorFilter);
        list = list.filter((e) => e.mentor_faculty_id === fId);
      }
    }

    const needle = search.trim().toLowerCase();
    if (needle) {
      list = list.filter(
        (e) =>
          `${e.student_name} ${e.roll_number} ${e.organization_name ?? ""}`.toLowerCase().includes(needle),
      );
    }

    list.sort((a, b) =>
      (a.roll_number ?? "").localeCompare(b.roll_number ?? "", undefined, { numeric: true }),
    );

    return list;
  }, [enrollments, assignmentTab, mentorFilter, search]);

  const unassignedCount = enrollments.filter((e) => !e.mentor_faculty_id).length;
  const assignedCount = enrollments.filter((e) => !!e.mentor_faculty_id).length;
  const activeMentorsCount = mentors.filter((m) => m.assigned_count > 0).length;
  const totalStudents = enrollments.length;
  const allocPct = totalStudents > 0 ? Math.round((assignedCount / totalStudents) * 100) : 0;
  // The per-mentor cap is programme configuration, reported by the server.
  const cap = mentors[0]?.max_capacity ?? null;
  const requiredMentors = cap ? Math.min(mentors.length, Math.ceil(totalStudents / cap)) : 0;
  const capacityUsedPct = cap && activeMentorsCount > 0
    ? Math.round((assignedCount / (activeMentorsCount * cap)) * 100) : 0;
  const avgLoad = activeMentorsCount > 0 ? (assignedCount / activeMentorsCount).toFixed(1) : "—";

  // Toggle student selection
  function toggleSelectStudent(id: number) {
    setSelectedStudentIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllStudents() {
    if (selectedStudentIds.size === filteredStudents.length && filteredStudents.length > 0) {
      setSelectedStudentIds(new Set());
    } else {
      setSelectedStudentIds(new Set(filteredStudents.map((s) => s.id)));
    }
  }

  // Toggle mentor selection
  function toggleSelectMentor(facultyId: number) {
    setSelectedMentorIds((prev) => {
      const next = new Set(prev);
      if (next.has(facultyId)) next.delete(facultyId);
      else next.add(facultyId);
      return next;
    });
  }

  // Auto-select required amount of mentors based on enrolled students
  function handleAutoSelectRequiredMentors() {
    const picked = new Set(mentors.slice(0, requiredMentors).map((m) => m.faculty_id));
    setSelectedMentorIds(picked);
    setFeedback({
      tone: "info",
      text: `✓ Auto-selected ${picked.size} faculty mentors required for ${totalStudents} students (${cap ?? "—"} per mentor). Click "Auto-Allocate Roll No Wise" to assign!`,
    });
  }

  // Randomly select mentors needed
  function handleRandomlyPickMentors() {
    const shuffled = [...mentors].sort(() => 0.5 - Math.random());
    const picked = new Set(shuffled.slice(0, requiredMentors).map((m) => m.faculty_id));
    setSelectedMentorIds(picked);
    setFeedback({
      tone: "info",
      text: `🎲 Randomly selected ${picked.size} faculty mentors from ${mentors.length} available faculties. Click "Auto-Allocate Roll No Wise" to assign!`,
    });
  }

  function handleSelectAllMentors() {
    setSelectedMentorIds(new Set(mentors.map((m) => m.faculty_id)));
  }

  function handleClearMentorSelection() {
    setSelectedMentorIds(new Set());
  }

  // Clear assigned mentors for all currently selected students
  function handleClearSelectedStudents() {
    const idsWithMentors = Array.from(selectedStudentIds).filter((id) => {
      const student = enrollments.find((e) => e.id === id);
      return student && student.mentor_faculty_id != null;
    });

    if (idsWithMentors.length === 0) {
      setFeedback({
        tone: "info",
        text: "None of the selected students currently have an assigned mentor to clear.",
      });
      return;
    }

    clearSelectedStudents.mutate(idsWithMentors);
  }

  // Clear all mentees for a specific faculty member
  function handleClearFacultyMentees(facultyId: number) {
    const studentsToClear = enrollments
      .filter((e) => e.mentor_faculty_id === facultyId)
      .map((e) => e.id);
    if (studentsToClear.length === 0) return;
    clearSelectedStudents.mutate(studentsToClear);
  }

  // Batch Range groups preview
  const batchRangeGroups = useMemo(() => {
    const groups: { mentorName: string; range: string; count: number; status: string }[] = [];
    const mentorMap = new Map<number, { name: string; students: EnrollmentSummary[] }>();

    for (const s of enrollments) {
      if (s.mentor_faculty_id) {
        if (!mentorMap.has(s.mentor_faculty_id)) {
          const mentor = mentors.find((m) => m.faculty_id === s.mentor_faculty_id);
          mentorMap.set(s.mentor_faculty_id, {
            name: mentor?.name ?? s.mentor_name ?? "Mentor",
            students: [],
          });
        }
        mentorMap.get(s.mentor_faculty_id)!.students.push(s);
      }
    }

    mentorMap.forEach(({ name, students }) => {
      if (students.length > 0) {
        const sorted = [...students].sort((a, b) =>
          (a.roll_number ?? "").localeCompare(b.roll_number ?? "", undefined, { numeric: true }),
        );
        const first = sorted[0].roll_number ?? "";
        const last = sorted[sorted.length - 1].roll_number ?? "";
        groups.push({
          mentorName: name,
          range: first === last ? first : `${first}–${last.slice(-3)}`,
          count: students.length,
          status: cap && students.length >= cap ? "Full" : `${students.length}/${cap ?? "—"}`,
        });
      }
    });

    return groups.slice(0, 8);
  }, [enrollments, mentors, cap]);

  const exportCSV = () => {
    // Quote every field, double embedded quotes, and neutralise a leading
    // = + - @ so a student-entered organisation name can't run as a formula.
    const cell = (raw: string | null) => {
      const value = raw ?? "";
      const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
      return `"${safe.replace(/"/g, '""')}"`;
    };
    const rows = [
      ["Roll Number", "Student Name", "Assigned Mentor", "Organisation / NGO", "Status"],
      ...filteredStudents.map((s) => [
        s.roll_number ?? "",
        s.student_name,
        s.mentor_name ?? "Unassigned",
        s.organization_name ?? "",
        s.mentor_faculty_id ? "Allocated" : "Unassigned",
      ]),
    ];
    // BOM so Excel reads names with accents as UTF-8.
    const csv = "\uFEFF" + rows.map((r) => r.map(cell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(activeProgram?.code ?? "Internship").replace(/[^a-zA-Z0-9_-]/g, "_")}_Mentor_Allocation_PDEU.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  const selectedCount = selectedMentorIds.size > 0 ? selectedMentorIds.size : mentors.length;

  return (
    <motion.div
      className="space-y-0 pb-12"
      initial="hidden"
      animate="shown"
      variants={slideUp}
    >
      {/* ── 1. HERO BANNER ──────────────────────────────────────────────────── */}
      <motion.div
        className="relative overflow-hidden rounded-2xl mb-7 shadow-sm bg-brand-gradient"
        variants={heroReveal}
      >
        {/* Decorative geometry */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle at 80% 50%, rgba(53,99,246,0.18) 0%, transparent 60%), " +
              "radial-gradient(circle at 95% 10%, rgba(98,87,232,0.22) 0%, transparent 45%)",
          }}
        />
        {/* Grid lines decoration (right side) */}
        <svg
          className="absolute right-0 top-0 h-full w-1/3 opacity-[0.06]"
          viewBox="0 0 400 300"
          fill="none"
          aria-hidden
        >
          {Array.from({ length: 10 }).map((_, i) => (
            <line key={`v${i}`} x1={i * 44} y1="0" x2={i * 44} y2="300" stroke="white" strokeWidth="1" />
          ))}
          {Array.from({ length: 8 }).map((_, i) => (
            <line key={`h${i}`} x1="0" y1={i * 40} x2="400" y2={i * 40} stroke="white" strokeWidth="1" />
          ))}
          <circle cx="320" cy="150" r="80" stroke="white" strokeWidth="1.5" fill="none" />
          <circle cx="320" cy="150" r="50" stroke="white" strokeWidth="1" fill="none" />
          <circle cx="320" cy="150" r="20" stroke="white" strokeWidth="1" fill="none" />
        </svg>

        <div className="relative z-10 px-6 py-10 sm:px-8 sm:py-12">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-8">
            {/* Left: title + meta */}
            <div className="space-y-4 max-w-2xl">
              {/* Top badges + Program Switcher */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-white/10 text-white/90 border border-white/20 backdrop-blur-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-success-solid animate-pulse" />
                  Active Session
                </span>
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-white/10 text-white/80 border border-white/15">
                  {user?.faculty?.department_code ? `${user.faculty.department_code} Department` : "ICT Department"}
                </span>

                {/* Program Switcher */}
                {availablePrograms.length > 1 ? (
                  <div className="relative inline-flex items-center">
                    <select
                      value={activeProgram?.id ?? ""}
                      onChange={(e) => handleProgramChange(e.target.value)}
                      className="appearance-none bg-accent/30 hover:bg-accent/40 text-blue-100 font-semibold text-xs rounded-full pl-3 pr-7 py-1 border border-accent/60 backdrop-blur-sm cursor-pointer transition focus:outline-none focus:ring-1 focus:ring-white/40"
                    >
                      {availablePrograms.map((p) => (
                        <option key={p.id} value={p.id} className="text-ink bg-white font-medium">
                          {p.name} ({p.code})
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-2 h-3.5 w-3.5 text-blue-200 pointer-events-none" />
                  </div>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-accent/30 text-blue-200 border border-accent/60">
                    {activeProgram?.code ?? "CSSI-202"}
                  </span>
                )}
              </div>

              {/* Title */}
              <div>
                <h1 className="font-heading text-3xl sm:text-4xl font-bold text-white leading-tight tracking-tight">
                  {activeProgram ? `${activeProgram.name} Mentor Allocation` : "Mentor Allocation"}
                </h1>
                <p className="mt-2 text-base text-white/70 font-medium">
                  {activeProgram?.type === "SUMMER"
                    ? "Summer Industry Internship"
                    : "Community & Social Service Internship"}
                  &nbsp;&nbsp;·&nbsp;&nbsp;{activeProgram?.target_semester ? `Target Semester ${activeProgram.target_semester}` : "Cohort Year"}
                  &nbsp;&nbsp;·&nbsp;&nbsp;Code: {activeProgram?.code ?? "—"}
                </p>
              </div>

              {/* Stats pills */}
              <div className="flex flex-wrap items-center gap-3">
                {[
                  { label: "Total Students", value: String(totalStudents), icon: Users },
                  { label: "Faculty Mentors", value: String(mentors.length), icon: UserCheck },
                  { label: "Allocated", value: `${allocPct}%`, icon: CheckCircle2 },
                ].map(({ label, value, icon: Icon }) => (
                  <div
                    key={label}
                    className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/10 border border-white/15 backdrop-blur-sm"
                  >
                    <Icon className="h-4 w-4 text-white/70 shrink-0" />
                    <div>
                      <div className="text-lg font-bold font-mono text-white leading-none">{value}</div>
                      <div className="text-[10px] text-white/60 font-medium mt-0.5">{label}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Policy badges */}
              <div className="flex flex-wrap gap-2 pt-1">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-warning-solid/15 text-amber-200 border border-warning/60">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  Up to {cap ?? "—"} students per mentor
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-iris/15 text-indigo-200 border border-iris/60">
                  <ListOrdered className="h-3.5 w-3.5" />
                  Sequential Roll No. Allocation
                </span>
              </div>
            </div>

            {/* Right: primary CTAs */}
            <div className="flex flex-col gap-3 shrink-0">
              <button
                onClick={() =>
                  allocateByRollNo.mutate(
                    selectedMentorIds.size > 0 ? Array.from(selectedMentorIds) : undefined,
                  )
                }
                disabled={allocateByRollNo.isPending}
                className="flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl font-semibold text-sm text-white bg-accent-gradient transition-all duration-200 shadow-lg hover:shadow-glow-accent hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-60"
              >
                <Zap className="h-4.5 w-4.5 shrink-0" />
                {allocateByRollNo.isPending ? "Allocating…" : "Auto-Allocate Roll No Wise"}
              </button>
              <div className="flex gap-2">
                <button
                  onClick={exportCSV}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white/90 border border-white/25 bg-white/10 hover:bg-white/20 transition-all duration-200"
                >
                  <Download className="h-4 w-4" />
                  Export CSV
                </button>
                <button
                  onClick={() => {
                    setFeedback({
                      tone: "success",
                      text: `All ${activeProgram?.name ?? "internship"} mentor allocations locked for AY 2024-25. Verification notifications dispatched.`,
                    });
                  }}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white/90 border border-white/25 bg-white/10 hover:bg-white/20 transition-all duration-200"
                >
                  <Lock className="h-4 w-4" />
                  Finalize &amp; Lock
                </button>
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {activeProgram && !activeProgram.mentor_capacity_confirmed && (
        <MentorCapNotice program={activeProgram} />
      )}

      {/* ── Feedback Banner ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {feedback && (
          <motion.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div
              className={`flex items-center justify-between rounded-xl border px-4 py-3 text-sm mb-5 ${
                feedback.tone === "success"
                  ? "border-success/25 bg-success-soft text-success"
                  : feedback.tone === "danger"
                  ? "border-danger/25 bg-danger-soft text-danger"
                  : "border-accent/25 bg-accent-soft text-accent"
              }`}
            >
              <div className="flex items-center gap-2.5">
                {feedback.tone === "success" && <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />}
                {feedback.tone === "danger" && <ShieldAlert className="h-4 w-4 shrink-0 text-danger" />}
                {feedback.tone === "info" && <AlertCircle className="h-4 w-4 shrink-0 text-accent" />}
                <span className="font-medium">{feedback.text}</span>
              </div>
              <button
                type="button"
                onClick={() => setFeedback(null)}
                className="text-xs font-semibold opacity-60 hover:opacity-100 transition-opacity ml-4 shrink-0"
              >
                Dismiss
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── 2. ACTION TOOLBAR ────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-2xl px-5 py-3.5 border border-line shadow-xs flex flex-wrap items-center gap-3.5 justify-between mb-7">
        {/* Left: selection actions */}
        <div className="flex items-center flex-wrap gap-2.5">
          <button
            onClick={handleAutoSelectRequiredMentors}
            className="inline-flex cursor-pointer items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold border border-accent text-accent bg-accent/5 hover:bg-accent/10 transition-colors duration-150"
          >
            <UserCheck className="h-4 w-4 shrink-0" />
            Auto-Select Required ({requiredMentors})
          </button>
          <button
            onClick={handleRandomlyPickMentors}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold border border-line text-ink-muted bg-surface hover:border-line-strong hover:text-ink transition-all duration-150 cursor-pointer"
          >
            <Dices className="h-4 w-4 shrink-0" />
            Randomly Select Faculty
          </button>

          <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line bg-surface-muted/50 text-sm font-medium text-ink">
            <span className="w-2 h-2 rounded-full bg-success-solid shrink-0" />
            <span>
              Faculty: <span className="font-mono font-bold text-ink">{selectedCount}</span>
              <span className="text-ink-muted"> / {mentors.length} selected</span>
            </span>
          </div>

        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2.5 ml-auto">
          <Button
            variant="secondary"
            size="sm"
            icon={<RotateCcw className="h-4 w-4 text-danger" />}
            loading={clearAllAssignments.isPending}
            onClick={() => setShowResetConfirm(true)}
          >
            Reset
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Zap className="h-4 w-4" />}
            loading={allocateByRollNo.isPending}
            onClick={() =>
              allocateByRollNo.mutate(
                selectedMentorIds.size > 0 ? Array.from(selectedMentorIds) : undefined,
              )
            }
          >
            Auto-Allocate Roll No Wise
          </Button>
        </div>
      </div>

      {/* ── 3. METRICS STRIP ─────────────────────────────────────────────────── */}
      <motion.div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8"
        variants={staggerContainer}
        initial="hidden"
        animate="shown"
      >
        {[
          {
            key: "students", label: "Students", icon: Users,
            chip: "bg-accent-soft text-accent", bar: "bg-success-solid",
            value: totalStudents,
            badge: totalStudents > 0 ? `${allocPct}% have a mentor` : null,
            left: <>With mentor <strong className="font-mono text-ink">{assignedCount}</strong></>,
            right: <>Waiting <strong className={cn("font-mono", unassignedCount ? "text-warning" : "text-ink")}>{unassignedCount}</strong></>,
            pct: allocPct,
          },
          {
            key: "mentors", label: "Mentors in this run", icon: UserCheck,
            chip: "bg-iris-soft text-iris", bar: "bg-iris",
            value: selectedCount,
            badge: selectedMentorIds.size === 0 ? "All eligible" : `of ${mentors.length} eligible`,
            left: <>From the programme's department</>,
            right: <><strong className="font-mono text-ink">{activeMentorsCount}</strong> carrying students</>,
            pct: mentors.length > 0 ? (selectedCount / mentors.length) * 100 : 0,
          },
          {
            key: "load", label: "Average load", icon: Zap,
            chip: "bg-warning-soft text-warning", bar: "bg-warning-solid",
            value: avgLoad,
            badge: cap ? `cap ${cap} per mentor` : null,
            left: <>Capacity used <strong className="font-mono text-ink">{capacityUsedPct}%</strong></>,
            right: null,
            pct: capacityUsedPct,
          },
          {
            key: "status", label: "Allocation", icon: CheckCircle2,
            chip: unassignedCount === 0 && totalStudents > 0 ? "bg-success-soft text-success" : "bg-surface-muted text-ink-muted",
            bar: "bg-success-solid",
            value: totalStudents === 0 ? "No students" : unassignedCount === 0 ? "Complete" : "In progress",
            badge: null,
            left: <>{totalStudents === 0 ? "Nobody has registered yet" : unassignedCount > 0 ? `${unassignedCount} still need a mentor` : "Every student has a mentor"}</>,
            right: null,
            pct: allocPct,
          },
        ].map((k) => (
          <motion.div
            key={k.key}
            variants={cardReveal}
            className="group relative min-w-0 overflow-hidden rounded-2xl border border-line bg-surface p-5 shadow-sm transition-[box-shadow,transform,border-color] duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card-hover"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">{k.label}</p>
                <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  {loadingData ? (
                    <span className="skeleton inline-block h-8 w-24 rounded-md" aria-label="Loading" />
                  ) : (
                    <>
                      <span className="font-heading text-3xl font-semibold leading-none text-ink tabular-nums">
                        {typeof k.value === "number" ? <CountUp value={k.value} /> : k.value}
                      </span>
                      {k.badge && <span className="text-xs font-medium text-ink-muted">{k.badge}</span>}
                    </>
                  )}
                </div>
              </div>
              <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-105", k.chip)}>
                <k.icon className="h-5 w-5" aria-hidden />
              </span>
            </div>
            <div className={cn("mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-ink-muted", loadingData && "invisible")}>
              <span>{k.left}</span>
              {k.right && <span>{k.right}</span>}
            </div>
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-muted">
              <motion.div
                className={cn("h-full rounded-full", k.bar)}
                initial={{ width: 0 }}
                animate={{ width: `${loadingData ? 0 : Math.min(100, Math.max(0, k.pct))}%` }}
                transition={{ duration: 0.9, delay: 0.25, ease: EASE }}
              />
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* ── 4. SECTION 1: PARTICIPATING FACULTY MENTORS (TOP) ──────────────── */}
      <motion.div
        className="w-full rounded-2xl border border-line shadow-sm flex flex-col overflow-hidden mb-8 bg-surface"
        variants={cardReveal}
        initial="hidden"
        animate="shown"
        transition={{ delay: 0.2 }}
      >
        {/* Panel header — navy tinted */}
        <div
          className="px-6 py-4 border-b border-line/60 flex flex-wrap items-center justify-between gap-4 bg-gradient-to-br from-navy to-navy-light"
        >
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-white/10">
              <Users className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="font-heading text-base font-bold text-white">
                  Participating Faculty Mentors
                </h3>
                <span className="bg-white/15 text-white text-xs font-mono px-2.5 py-0.5 rounded-full font-bold border border-white/20">
                  {mentors.length}
                </span>
                <span className="text-white/70 text-xs font-medium ml-1">
                  · <span className="text-emerald-300 font-bold">{selectedCount}</span> Selected for Allocation
                </span>
              </div>
              <p className="text-white/70 text-xs mt-0.5">
                Select mentors to participate in sequential roll number student allocation (up to {cap ?? "—"} students each)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/40" />
              <input
                value={mentorSearch}
                onChange={(e) => setMentorSearch(e.target.value)}
                placeholder="Filter by name, dept, designation…"
                className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl bg-white/10 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:border-white/50 focus:bg-white/15 transition-all font-medium"
              />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={handleSelectAllMentors}
                className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-blue-100 hover:text-white font-semibold transition-colors cursor-pointer"
              >
                Select All
              </button>
              {selectedMentorIds.size > 0 && (
                <button
                  type="button"
                  onClick={handleClearMentorSelection}
                  className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors cursor-pointer"
                >
                  Clear ({selectedMentorIds.size})
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Mentor card list — Spacious Responsive Grid */}
        <div className="overflow-y-auto custom-scrollbar p-6 bg-surface-muted/20" style={{ maxHeight: "500px" }}>
          <motion.div
            variants={listContainer}
            initial="hidden"
            animate="shown"
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
          >
            {filteredMentors.map((m) => {
              const isFiltered = mentorFilter === String(m.faculty_id);
              const isChecked = selectedMentorIds.has(m.faculty_id);
              const isFull = m.is_full;
              const isWarning = !isFull && m.remaining_capacity <= 2;
              const loadPct = m.max_capacity > 0 ? Math.min((m.assigned_count / m.max_capacity) * 100, 100) : 0;

              return (
                <motion.div
                  key={m.faculty_id}
                  variants={listItem}
                  className={cn(
                    "min-w-0 rounded-2xl border transition-[box-shadow,border-color,background-color] duration-200 overflow-hidden flex flex-col justify-between shadow-2xs hover:shadow-md",
                    isChecked
                      ? "border-accent ring-1 ring-accent bg-accent/[0.03]"
                      : isFiltered
                      ? "border-accent/60 ring-1 ring-accent/40 bg-surface-soft"
                      : "border-line bg-surface",
                  )}
                  whileHover={{ y: -2 }}
                >
                  <div className="p-4 sm:p-5">
                    {/* Header: Checkbox + Avatar + Name + Load Tag */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <button
                          type="button"
                          onClick={() => toggleSelectMentor(m.faculty_id)}
                          className="mt-0.5 shrink-0 text-ink-subtle hover:text-accent transition-colors cursor-pointer"
                          title={isChecked ? "Deselect faculty mentor" : "Select faculty mentor"}
                        >
                          {isChecked ? (
                            <CheckSquare className="h-4.5 w-4.5 text-accent" />
                          ) : (
                            <Square className="h-4.5 w-4.5" />
                          )}
                        </button>
                        <div className="shrink-0">
                          <Avatar name={m.name} size="sm" />
                        </div>
                        <div className="min-w-0">
                          <h4 className="font-heading text-sm font-bold text-ink truncate leading-snug" title={m.name}>
                            {m.name}
                          </h4>
                          <p className="text-xs text-ink-subtle truncate mt-0.5">
                            {m.designation ?? "Faculty"} · <span className="font-semibold text-ink-muted">{m.department_code ?? "ICT"}</span>
                          </p>
                        </div>
                      </div>

                      <span
                        className={`text-2xs font-mono px-2 py-0.5 rounded-full font-bold shrink-0 border ${
                          isFull
                            ? "bg-success-soft text-success border-success/25"
                            : isWarning
                            ? "bg-warning-soft text-warning border-warning/25"
                            : "bg-surface-muted text-ink-muted border-line"
                        }`}
                      >
                        {isFull ? `Full ${m.assigned_count}/${m.max_capacity}` : `${m.assigned_count}/${m.max_capacity}`}
                      </span>
                    </div>

                    {/* Capacity bar section */}
                    <div className="mt-4 pt-3.5 border-t border-line/40">
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="font-medium text-ink">
                          {m.assigned_count} <span className="font-normal text-ink-subtle">/ {m.max_capacity} students</span>
                        </span>
                        <span
                          className={`font-mono text-2xs font-bold px-2 py-0.5 rounded ${
                            isFull
                              ? "text-success bg-success-soft font-bold"
                              : isWarning
                              ? "text-warning bg-warning-soft font-bold"
                              : "text-ink-subtle font-medium"
                          }`}
                        >
                          {loadPct}% Capacity
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-surface-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            isFull ? "bg-success-solid" : isWarning ? "bg-warning-solid" : "bg-accent"
                          }`}
                          style={{ width: `${loadPct}%` }}
                        />
                      </div>
                    </div>

                    {/* Footer: status & action button */}
                    <div className="mt-4 pt-3 border-t border-line/40 flex items-center justify-between">
                      <span className="text-xs text-ink-subtle">
                        {m.assigned_count > 0 ? (
                          <span className="text-success font-semibold">{m.assigned_count} assigned</span>
                        ) : (
                          <span className="text-ink-subtle">0 assigned</span>
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setMentorFilter(isFiltered ? "ALL" : String(m.faculty_id));
                          document.getElementById("student-allocation-section")?.scrollIntoView({ behavior: "smooth" });
                        }}
                        className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer border ${
                          isFiltered
                            ? "bg-danger-soft text-danger border-danger/25 hover:bg-danger-soft"
                            : "bg-accent-soft/80 text-accent border-accent/25 hover:bg-accent-soft"
                        }`}
                      >
                        {isFiltered ? "✕ Clear Filter" : `View Mentees (${m.assigned_count}) →`}
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </div>

        {/* Section 1 footer */}
        <div className="px-5 py-2.5 border-t border-line bg-surface-muted/60 flex items-center justify-between text-xs text-ink-muted">
          <span>
            Showing <strong className="text-ink">{filteredMentors.length}</strong> of {mentors.length} Faculty Mentors
          </span>
          <Link to="/faculty/directory" className="text-accent font-semibold hover:underline text-xs">
            Faculty Directory →
          </Link>
        </div>
      </motion.div>

      {/* ── 5. SECTION 2: STUDENT COHORT ALLOCATION (BOTTOM) ──────────────── */}
      <motion.div
        id="student-allocation-section"
        className="w-full rounded-2xl border border-line shadow-sm flex flex-col overflow-hidden bg-surface"
        variants={cardReveal}
        initial="hidden"
        animate="shown"
        transition={{ delay: 0.3 }}
      >
        {/* Panel header */}
        <div className="px-6 py-4 border-b border-line bg-surface-muted/40 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="font-heading text-base font-bold text-ink">
                Student Cohort &amp; Roll Number Allocation
              </h3>
              <span className="bg-accent-soft text-accent text-xs font-mono px-2.5 py-0.5 rounded-full font-bold">
                {enrollments.length} Students
              </span>
            </div>
            <p className="text-xs text-ink-subtle mt-0.5">
              2nd Year B.Tech ICT · Sections A &amp; B · Roll Number Wise Mentor Allocation Table
            </p>
          </div>

          <div className="flex items-center flex-wrap gap-2.5">
            {/* Filter tabs */}
            <div className="flex items-center bg-surface-muted/80 rounded-lg p-0.5 border border-line text-xs">
              {(["ALL", "UNASSIGNED", "ASSIGNED"] as const).map((tab) => {
                const label =
                  tab === "ALL"
                    ? `All (${enrollments.length})`
                    : tab === "UNASSIGNED"
                    ? `Unassigned (${unassignedCount})`
                    : `Assigned (${assignedCount})`;
                const isActive = assignmentTab === tab;
                return (
                  <button
                    key={tab}
                    onClick={() => setAssignmentTab(tab)}
                    className={`px-3 py-1.5 rounded-md font-semibold transition-all duration-150 cursor-pointer ${
                      isActive
                        ? tab === "ASSIGNED"
                          ? "bg-surface text-success shadow-xs"
                          : tab === "UNASSIGNED"
                          ? "bg-surface text-warning shadow-xs"
                          : "bg-surface text-ink shadow-xs"
                        : "text-ink-subtle hover:text-ink"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            {/* Clear All Assigned Mentors Button */}
            <button
              type="button"
              onClick={() => setShowClearStudentsConfirm(true)}
              disabled={assignedCount === 0 || clearAllAssignments.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-danger hover:text-danger bg-danger-soft hover:bg-danger-soft border border-danger/25 transition-colors shadow-2xs disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              title="Clear mentor assignments from all students"
            >
              <RotateCcw className="h-3.5 w-3.5 text-danger" />
              <span>Clear All Assigned Mentors ({assignedCount})</span>
            </button>
          </div>
        </div>

        {/* Mapped Batches strip */}
        {batchRangeGroups.length > 0 && (
          <div className="px-6 py-3 bg-surface border-b border-line flex items-center gap-3 overflow-x-auto custom-scrollbar">
            <span className="text-[10px] font-bold uppercase tracking-widest text-ink-subtle shrink-0">
              Mapped Batches:
            </span>
            {batchRangeGroups.map((g, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-line bg-surface-muted/50 shrink-0 text-xs shadow-2xs"
              >
                <span className="font-mono text-accent font-bold">{g.range}</span>
                <span className="text-ink-subtle">·</span>
                <span className="text-ink font-medium truncate max-w-[140px]">{g.mentorName.split(" ").slice(-1)[0]}</span>
                <span className="text-success font-bold">{g.status}</span>
              </div>
            ))}
          </div>
        )}

        {/* Search row */}
        <div className="px-6 py-3.5 border-b border-line bg-surface flex items-center gap-4 justify-between">
          <div className="relative flex-1 max-w-lg">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by student name, roll number, or NGO partner…"
              className="w-full pl-9 pr-3.5 py-2 text-xs rounded-xl bg-canvas border border-line text-ink focus:outline-none focus:border-accent/60 focus:ring-2 focus:ring-blue-100 transition-all font-medium"
            />
          </div>
          {mentorFilter !== "ALL" && (
            <div className="flex items-center gap-2.5 shrink-0">
              <span className="text-xs text-accent bg-accent-soft border border-accent/25 px-3 py-1.5 rounded-lg font-medium">
                Viewing Mentees for Faculty ID: #{mentorFilter} ({filteredStudents.length} Students)
              </span>
              <button
                type="button"
                onClick={() => handleClearFacultyMentees(Number(mentorFilter))}
                disabled={clearSelectedStudents.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-danger bg-danger-soft hover:bg-danger-soft border border-danger/25 transition-colors cursor-pointer"
              >
                <UserX className="h-3.5 w-3.5 text-danger" />
                Unassign This Faculty&apos;s Students
              </button>
              <button
                onClick={() => setMentorFilter("ALL")}
                className="text-xs font-semibold text-ink-muted hover:text-ink hover:underline shrink-0 cursor-pointer"
              >
                ✕ Clear Filter
              </button>
            </div>
          )}
        </div>

        {/* Selected students action bar */}
        <AnimatePresence>
          {selectedStudentIds.size > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="px-6 py-3 bg-accent-soft/90 border-b border-accent/25 flex items-center justify-between gap-3 text-xs overflow-hidden"
            >
              <div className="flex items-center gap-2.5">
                <span className="font-semibold text-accent">
                  {selectedStudentIds.size} student{selectedStudentIds.size > 1 ? "s" : ""} selected
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedStudentIds(new Set())}
                  className="text-2xs text-accent hover:text-accent font-medium hover:underline cursor-pointer"
                >
                  Deselect all
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClearSelectedStudents}
                  disabled={clearSelectedStudents.isPending}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-danger hover:text-danger bg-danger-soft hover:bg-danger-soft border border-danger/25 transition-colors shadow-2xs cursor-pointer"
                >
                  <UserX className="h-3.5 w-3.5 text-danger" />
                  <span>Clear Mentors for Selected ({selectedStudentIds.size})</span>
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Table */}
        <div className="overflow-auto custom-scrollbar" style={{ maxHeight: "620px" }}>
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 z-10 bg-surface-muted/95 backdrop-blur-sm border-b border-line">
              <tr>
                <th className="py-3.5 px-5 w-12">
                  <button
                    type="button"
                    onClick={toggleSelectAllStudents}
                    className="flex items-center text-ink-subtle hover:text-ink transition-colors cursor-pointer"
                  >
                    {selectedStudentIds.size === filteredStudents.length && filteredStudents.length > 0 ? (
                      <CheckSquare className="h-4.5 w-4.5 text-accent" />
                    ) : (
                      <Square className="h-4.5 w-4.5" />
                    )}
                  </button>
                </th>
                <th className="py-3.5 px-5 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-32">Roll No</th>
                <th className="py-3.5 px-5 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-60">Student Name</th>
                <th className="py-3.5 px-5 text-2xs font-bold uppercase tracking-widest text-ink-subtle">NGO / Project</th>
                <th className="py-3.5 px-5 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-32">Status</th>
                <th className="py-3.5 px-5 text-2xs font-bold uppercase tracking-widest text-ink-subtle min-w-[280px]">Assigned Mentor</th>
              </tr>
            </thead>
            <tbody>
              {filteredStudents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-ink-subtle text-sm">
                    <div className="flex flex-col items-center gap-2">
                      <Users className="h-8 w-8 text-ink-subtle/40" />
                      <span>No students found matching current filters.</span>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredStudents.map((row, idx) => {
                  const currentMentor = mentors.find((m) => m.faculty_id === row.mentor_faculty_id);
                  const isChecked = selectedStudentIds.has(row.id);

                  return (
                    <motion.tr
                      key={row.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: Math.min(idx * 0.005, 0.2) }}
                      className={`border-b border-line/50 transition-colors duration-100 ${
                        isChecked
                          ? "bg-accent-soft/60"
                          : idx % 2 === 0
                          ? "bg-surface hover:bg-accent-soft/30"
                          : "bg-surface-muted/20 hover:bg-accent-soft/30"
                      }`}
                    >
                      <td className="py-3.5 px-5">
                        <button
                          type="button"
                          onClick={() => toggleSelectStudent(row.id)}
                          className="flex items-center text-ink-subtle hover:text-accent transition-colors cursor-pointer"
                        >
                          {isChecked ? (
                            <CheckSquare className="h-4.5 w-4.5 text-accent" />
                          ) : (
                            <Square className="h-4.5 w-4.5" />
                          )}
                        </button>
                      </td>
                      <td className="py-3.5 px-5">
                        <span className="font-mono font-bold text-xs text-accent">
                          {row.roll_number}
                        </span>
                      </td>
                      <td className="py-3.5 px-5">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={row.student_name ?? "Student"} size="xs" />
                          <span className="font-semibold text-xs text-ink truncate">
                            {row.student_name}
                          </span>
                        </div>
                      </td>
                      <td className="py-3.5 px-5">
                        <span className="text-xs text-ink-muted truncate block">
                          {row.organization_name ?? <span className="text-ink-subtle">—</span>}
                        </span>
                      </td>
                      <td className="py-3.5 px-5">
                        {row.mentor_faculty_id ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-2xs font-bold bg-success-soft text-success border border-success/25">
                            <span className="w-1.5 h-1.5 rounded-full bg-success-solid" />
                            Allocated
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-2xs font-bold bg-warning-soft text-warning border border-warning/25">
                            <span className="w-1.5 h-1.5 rounded-full bg-warning-solid" />
                            Unassigned
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-5">
                        <div className="flex items-center gap-2 max-w-sm">
                          <Select
                            value={String(row.mentor_faculty_id ?? "")}
                            onChange={(e) => {
                              const val = e.target.value;
                              assignSingle.mutate({
                                enrollmentId: row.id,
                                mentorId: val ? Number(val) : null,
                              });
                            }}
                            className="h-8 text-xs font-medium flex-1"
                          >
                            <option value="">— Unassigned —</option>
                            {mentors.map((m) => {
                              const isCurrent = m.faculty_id === row.mentor_faculty_id;
                              const isFull = m.is_full && !isCurrent;
                              return (
                                <option key={m.faculty_id} value={m.faculty_id} disabled={isFull}>
                                  {m.name} ({m.assigned_count}/{m.max_capacity}{isFull ? " · full" : ""})
                                </option>
                              );
                            })}
                          </Select>
                          {row.mentor_faculty_id && (
                            <span className="font-mono text-xs text-accent font-bold px-2 py-0.5 rounded bg-accent-soft border border-accent/25 shrink-0">
                              {currentMentor?.assigned_count ?? 1}/{currentMentor?.max_capacity ?? cap ?? "—"}
                            </span>
                          )}
                        </div>
                      </td>
                    </motion.tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Section 2 footer */}
        <div className="px-6 py-3.5 border-t border-line bg-surface-muted/60 flex items-center justify-between">
          <span className="text-xs text-ink-muted">
            Showing <strong className="text-ink">{filteredStudents.length}</strong> of {enrollments.length} Students
          </span>
          <div className="flex items-center gap-4">
            <span className="text-xs font-mono text-ink-muted">
              <span className="text-success font-bold">{assignedCount}</span> Assigned
              {" · "}
              <span className="text-warning font-bold">{unassignedCount}</span> Pending
            </span>
          </div>
        </div>
      </motion.div>

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        open={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        onConfirm={() => clearAllAssignments.mutate()}
        title="Reset &amp; Clear All Mentor Assignments"
        message="Are you sure you want to clear all mentor assignments and selected mentors? This will reset all student mappings back to unassigned and unselect all faculty mentors."
        confirmLabel="Yes, Clear All"
        cancelLabel="Cancel"
        destructive
        loading={clearAllAssignments.isPending}
      />

      {/* Clear All Student Mentor Assignments Confirmation */}
      <ConfirmDialog
        open={showClearStudentsConfirm}
        onClose={() => setShowClearStudentsConfirm(false)}
        onConfirm={() => clearAllAssignments.mutate()}
        title="Clear All Assigned Mentors"
        message={`Are you sure you want to clear assigned mentors from all ${assignedCount} students? All students will be reset to Unassigned.`}
        confirmLabel="Yes, Clear All Student Mentors"
        cancelLabel="Cancel"
        destructive
        loading={clearAllAssignments.isPending}
      />

    </motion.div>
  );
}

/**
 * Shown while a programme's cap is the portal default. Ten per mentor is not a
 * written PDEU rule, so the screen says so and lets the coordinator record the
 * figure their department actually uses. Saving it is the confirmation.
 */
function MentorCapNotice({ program }: { program: InternshipProgram }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(String(program.mentor_capacity));
  const save = useMutation({
    mutationFn: (cap: number) =>
      api.patch<InternshipProgram>(`/internships/programs/${program.id}`, { mentor_capacity: cap }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["internship-programs"] });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const cap = Number(value);
  const valid = Number.isInteger(cap) && cap >= 1 && cap <= 60;

  return (
    <div className="mb-5 flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3.5 sm:flex-row sm:items-center">
      <ShieldAlert className="hidden h-5 w-5 shrink-0 text-warning sm:block" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-ink">
          The cap of {program.mentor_capacity} students per mentor is not confirmed
        </p>
        <p className="mt-0.5 text-ink-muted">
          It is the portal's default, not a PDEU rule. Confirm the figure your department uses —
          allocation and the capacity checks will follow it.
        </p>
        {save.isError && (
          <p className="mt-1 font-medium text-danger" role="alert">
            {save.error instanceof ApiError ? save.error.message : "Could not save the cap."}
          </p>
        )}
      </div>
      <form
        className="flex shrink-0 items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate(cap);
        }}
      >
        <label htmlFor="mentor-cap" className="sr-only">Students per mentor</label>
        <Input
          id="mentor-cap" type="number" min={1} max={60} inputMode="numeric"
          value={value} onChange={(e) => setValue(e.target.value)}
          className="h-9 w-20 text-center" aria-invalid={!valid || undefined}
        />
        <Button type="submit" size="sm" variant="accent" loading={save.isPending} disabled={!valid}>
          Confirm cap
        </Button>
      </form>
    </div>
  );
}
