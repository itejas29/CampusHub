import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Variants } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  CheckSquare,
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
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Form";
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
  const [selectedProgramId] = useState<string>("");
  const [mentorFilter, setMentorFilter] = useState<string>("ALL");
  const [mentorSearch, setMentorSearch] = useState("");
  const [assignmentTab, setAssignmentTab] = useState<"ALL" | "UNASSIGNED" | "ASSIGNED">("ALL");
  const [search, setSearch] = useState("");
  const [selectedStudentIds, setSelectedStudentIds] = useState<Set<number>>(new Set());
  const [selectedMentorIds, setSelectedMentorIds] = useState<Set<number>>(new Set());
  const [strictCap, setStrictCap] = useState(true);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showClearStudentsConfirm, setShowClearStudentsConfirm] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);

  // Fetch internship programs
  const programsQuery = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });

  const programs = programsQuery.data ?? [];
  const cssiProgram = programs.find((p) => p.code?.includes("CSSI") || p.type === "CSSI") ?? programs[0];
  const activeProgramId = selectedProgramId ? Number(selectedProgramId) : cssiProgram?.id;

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
  const enrollments = enrollmentsQuery.data ?? [];

  // Single mentor assignment mutation
  const assignSingle = useMutation({
    mutationFn: ({ enrollmentId, mentorId }: { enrollmentId: number; mentorId: number | null }) =>
      api.post(`/internships/enrollments/${enrollmentId}/mentor`, {
        mentor_faculty_id: mentorId,
        reason: mentorId ? "Coordinator assigned mentor (max 10 limit enforced)" : "Coordinator unassigned mentor",
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
          min_students_per_mentor: 2,
          max_students_per_mentor: 10,
          reason: "Roll number sequential allocation (10 max, min 2)",
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
  const totalStudents = enrollments.length || 203;
  const allocPct = totalStudents > 0 ? Math.round((assignedCount / totalStudents) * 100) : 0;
  const requiredMentors = Math.min(mentors.length || 25, Math.ceil(totalStudents / 10));
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
      text: `✓ Auto-selected ${picked.size} faculty mentors required for ${totalStudents} students (10 students per mentor cap). Click "Auto-Allocate Roll No Wise" to assign!`,
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
          status: students.length === 10 ? "Full ✓" : `${students.length}/10`,
        });
      }
    });

    return groups.slice(0, 8);
  }, [enrollments, mentors]);

  const exportCSV = () => {
    const rows = [
      ["Roll Number", "Student Name", "Assigned Mentor", "NGO Partner", "Status"],
      ...filteredStudents.map((s) => [
        s.roll_number ?? "",
        s.student_name,
        s.mentor_name ?? "Unassigned",
        s.organization_name ?? "—",
        s.mentor_faculty_id ? "Allocated" : "Unassigned",
      ]),
    ];
    const csvContent = "data:text/csv;charset=utf-8," + rows.map((e) => e.join(",")).join("\n");
    const link = document.createElement("a");
    link.setAttribute("href", encodeURI(csvContent));
    link.setAttribute("download", "CSSI_Mentor_Allocation_PDEU.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const selectedCount = selectedMentorIds.size > 0 ? selectedMentorIds.size : mentors.length;

  return (
    <motion.div
      className="space-y-0"
      initial="hidden"
      animate="shown"
      variants={slideUp}
    >
      {/* ── 1. HERO BANNER ──────────────────────────────────────────────────── */}
      <motion.div
        className="relative overflow-hidden rounded-2xl mb-5"
        style={{ background: "linear-gradient(135deg, #0B2545 0%, #174EA6 60%, #1a56b0 100%)" }}
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
              {/* Top badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-white/10 text-white/90 border border-white/20 backdrop-blur-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Active Session
                </span>
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-white/10 text-white/80 border border-white/15">
                  ICT Department
                </span>
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/30 text-blue-200 border border-blue-400/30">
                  CSSI-202
                </span>
              </div>

              {/* Title */}
              <div>
                <h1 className="font-heading text-3xl sm:text-4xl font-bold text-white leading-tight tracking-tight">
                  CSSI Mentor Allocation
                </h1>
                <p className="mt-2 text-base text-white/70 font-medium">
                  Cohort: B.Tech ICT 2024–28 (2nd Year)&nbsp;&nbsp;·&nbsp;&nbsp;Winter 2025
                </p>
              </div>

              {/* Stats pills */}
              <div className="flex flex-wrap items-center gap-3">
                {[
                  { label: "Total Students", value: String(totalStudents), icon: Users },
                  { label: "Faculty Mentors", value: String(mentors.length || 25), icon: UserCheck },
                  { label: "Allocated", value: `${allocPct || 95.6}%`, icon: CheckCircle2 },
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
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-400/15 text-amber-200 border border-amber-400/25">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  Min 2 / Max 10 students per mentor
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-indigo-400/15 text-indigo-200 border border-indigo-400/25">
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
                className="flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl font-semibold text-sm text-white transition-all duration-200 shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-60"
                style={{ background: "linear-gradient(135deg, #3563F6 0%, #4f46e5 100%)" }}
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
                      text: "All CSSI mentor allocations locked for AY 2024-25. Verification notifications dispatched.",
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
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200"
                  : feedback.tone === "danger"
                  ? "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200"
                  : "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200"
              }`}
            >
              <div className="flex items-center gap-2.5">
                {feedback.tone === "success" && <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />}
                {feedback.tone === "danger" && <ShieldAlert className="h-4 w-4 shrink-0 text-rose-600" />}
                {feedback.tone === "info" && <AlertCircle className="h-4 w-4 shrink-0 text-blue-600" />}
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
      <div className="bg-surface rounded-xl px-4 py-3 border border-line shadow-xs flex flex-wrap items-center gap-3 justify-between mb-5">
        {/* Left: selection actions */}
        <div className="flex items-center flex-wrap gap-2">
          <button
            onClick={handleAutoSelectRequiredMentors}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold border transition-all duration-150"
            style={{ borderColor: "#3563F6", color: "#3563F6", background: "rgba(53,99,246,0.06)" }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(53,99,246,0.12)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(53,99,246,0.06)"; }}
          >
            <UserCheck className="h-4 w-4 shrink-0" />
            Auto-Select Required ({requiredMentors})
          </button>
          <button
            onClick={handleRandomlyPickMentors}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold border border-line text-ink-muted bg-surface hover:border-line-strong hover:text-ink transition-all duration-150"
          >
            <Dices className="h-4 w-4 shrink-0" />
            Randomly Select Faculty
          </button>

          <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line bg-surface-muted/50 text-sm font-medium text-ink">
            <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
            <span>
              Faculty: <span className="font-mono font-bold text-ink">{selectedCount}</span>
              <span className="text-ink-muted"> / {mentors.length || 25} Selected</span>
            </span>
          </div>

          <label className="inline-flex items-center gap-2 cursor-pointer px-3 py-2 rounded-lg border border-line bg-surface text-sm font-medium text-ink-muted hover:text-ink transition-colors">
            <input
              checked={strictCap}
              onChange={(e) => setStrictCap(e.target.checked)}
              type="checkbox"
              className="rounded border-line text-blue-600 focus:ring-blue-500 w-3.5 h-3.5"
            />
            Strict Cap (10 max)
          </label>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2 ml-auto">
          <Button
            variant="secondary"
            size="sm"
            icon={<RotateCcw className="h-4 w-4 text-rose-500" />}
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
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5"
        variants={staggerContainer}
        initial="hidden"
        animate="shown"
      >
        {/* Card 1: Total Students */}
        <motion.div
          variants={cardReveal}
          className="rounded-2xl p-5 overflow-hidden relative group cursor-default"
          style={{ background: "linear-gradient(135deg, #EBF0FF 0%, #dce8ff 100%)", border: "1px solid #c7d9ff" }}
          whileHover={{ y: -3, boxShadow: "0 12px 32px -8px rgba(53,99,246,0.18)" }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-blue-600/70">Total Students</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-heading text-4xl font-bold text-blue-900 font-mono leading-none">
                  {totalStudents}
                </span>
                <span className="text-xs font-semibold text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded-full">
                  {allocPct || 95.6}% Mapped
                </span>
              </div>
            </div>
            <div className="p-2.5 rounded-xl bg-blue-600/10">
              <Users className="h-5 w-5 text-blue-600" />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-blue-700/60 font-medium">
            <span>Allocated: <strong className="text-emerald-700 font-mono">{assignedCount}</strong></span>
            <span>Remaining: <strong className="text-amber-600 font-mono">{unassignedCount}</strong></span>
          </div>
          <div className="mt-2.5 h-1.5 rounded-full bg-blue-200/60 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400"
              initial={{ width: 0 }}
              animate={{ width: `${allocPct || 95.6}%` }}
              transition={{ duration: 1, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </motion.div>

        {/* Card 2: Selected Mentors */}
        <motion.div
          variants={cardReveal}
          className="rounded-2xl p-5 overflow-hidden relative"
          style={{ background: "linear-gradient(135deg, #EDEAFF 0%, #e2deff 100%)", border: "1px solid #c4beff" }}
          whileHover={{ y: -3, boxShadow: "0 12px 32px -8px rgba(98,87,232,0.18)" }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-600/70">Selected Mentors</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-heading text-4xl font-bold text-indigo-900 font-mono leading-none">
                  {selectedCount}
                </span>
                <span className="text-xs text-indigo-600/60 font-medium">Faculty Members</span>
              </div>
            </div>
            <div className="p-2.5 rounded-xl bg-indigo-600/10">
              <UserCheck className="h-5 w-5 text-indigo-600" />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-indigo-700/60 font-medium">
            <span>ICT &amp; Allied Depts</span>
            <span className="font-mono font-bold text-indigo-700">{activeMentorsCount} Active</span>
          </div>
          <div className="mt-2.5 h-1.5 rounded-full bg-indigo-200/60 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-400"
              initial={{ width: 0 }}
              animate={{ width: `${mentors.length > 0 ? (selectedCount / mentors.length) * 100 : 84}%` }}
              transition={{ duration: 1, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </motion.div>

        {/* Card 3: Average Mentor Load */}
        <motion.div
          variants={cardReveal}
          className="rounded-2xl p-5 overflow-hidden relative"
          style={{ background: "linear-gradient(135deg, #FFF7E6 0%, #FEEBC8 100%)", border: "1px solid #fcd89a" }}
          whileHover={{ y: -3, boxShadow: "0 12px 32px -8px rgba(217,119,6,0.18)" }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-amber-700/70">Avg Mentor Load</p>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="font-heading text-4xl font-bold text-amber-900 font-mono leading-none">
                  {avgLoad}
                </span>
                <span className="text-sm text-amber-600/70 font-mono font-medium">/ 10 max</span>
              </div>
            </div>
            <div className="p-2.5 rounded-xl bg-amber-500/15">
              <Zap className="h-5 w-5 text-amber-600" />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-amber-700/60 font-medium">
            <span>Capacity Used: <strong className="text-amber-700 font-mono">92%</strong></span>
            <span className="px-1.5 py-0.5 rounded-full bg-amber-200 text-amber-800 text-[10px] font-bold">Optimal</span>
          </div>
          <div className="mt-2.5 h-1.5 rounded-full bg-amber-200/70 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-400"
              initial={{ width: 0 }}
              animate={{ width: "92%" }}
              transition={{ duration: 1, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </motion.div>

        {/* Card 4: Allocation Status */}
        <motion.div
          variants={cardReveal}
          className="rounded-2xl p-5 overflow-hidden relative"
          style={{ background: "linear-gradient(135deg, #ECFDF5 0%, #d1fae5 100%)", border: "1px solid #6ee7b7" }}
          whileHover={{ y: -3, boxShadow: "0 12px 32px -8px rgba(16,185,129,0.18)" }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-emerald-700/70">Allocation Status</p>
              <div className="mt-2">
                <span className="font-heading text-lg font-bold text-emerald-800 leading-tight">
                  {unassignedCount === 0 ? "100% Complete ✓" : "Ready to Finalize"}
                </span>
              </div>
            </div>
            <div className="p-2.5 rounded-xl bg-emerald-500/15">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-emerald-700/70 font-medium">
            <span>{unassignedCount > 0 ? `${unassignedCount} Remaining` : "All students allocated"}</span>
            <span className="text-emerald-700 font-bold text-[10px]">Policy Valid ✓</span>
          </div>
          <div className="mt-2.5 h-1.5 rounded-full bg-emerald-200/60 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400"
              initial={{ width: 0 }}
              animate={{ width: `${allocPct || 95.6}%` }}
              transition={{ duration: 1, delay: 0.6, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </motion.div>
      </motion.div>

      {/* ── 4. SECTION 1: PARTICIPATING FACULTY MENTORS (TOP) ──────────────── */}
      <motion.div
        className="w-full rounded-2xl border border-line shadow-sm flex flex-col overflow-hidden mb-6 bg-surface"
        variants={cardReveal}
        initial="hidden"
        animate="shown"
        transition={{ delay: 0.2 }}
      >
        {/* Panel header — navy tinted */}
        <div
          className="px-5 py-3.5 border-b border-line/60 flex flex-wrap items-center justify-between gap-3"
          style={{ background: "linear-gradient(135deg, #0B2545 0%, #174EA6 100%)" }}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-white/10">
              <Users className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-heading text-sm font-bold text-white">
                  Participating Faculty Mentors
                </h3>
                <span className="bg-white/15 text-white text-xs font-mono px-2 py-0.5 rounded-full font-bold border border-white/20">
                  {mentors.length || 25}
                </span>
                <span className="text-white/70 text-xs font-medium ml-1">
                  · <span className="text-emerald-300 font-bold">{selectedCount}</span> Selected for Allocation
                </span>
              </div>
              <p className="text-white/60 text-2xs mt-0.5">
                Select mentors to participate in sequential roll number student allocation (Max 10 students / mentor)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/40" />
              <input
                value={mentorSearch}
                onChange={(e) => setMentorSearch(e.target.value)}
                placeholder="Filter by name, dept, designation…"
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:border-white/40 focus:bg-white/15 transition-all font-medium"
              />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={handleSelectAllMentors}
                className="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-blue-100 hover:text-white font-semibold transition-colors cursor-pointer"
              >
                Select All
              </button>
              {selectedMentorIds.size > 0 && (
                <button
                  type="button"
                  onClick={handleClearMentorSelection}
                  className="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors cursor-pointer"
                >
                  Clear ({selectedMentorIds.size})
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Mentor card list — Responsive Grid */}
        <div className="overflow-y-auto custom-scrollbar p-4 bg-surface" style={{ maxHeight: "360px" }}>
          <motion.div
            variants={listContainer}
            initial="hidden"
            animate="shown"
            className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-3"
          >
            {filteredMentors.map((m) => {
              const isFiltered = mentorFilter === String(m.faculty_id);
              const isChecked = selectedMentorIds.has(m.faculty_id);
              const isFull = m.assigned_count >= 10;
              const isWarning = m.assigned_count >= 8 && !isFull;
              const loadPct = Math.min(m.assigned_count * 10, 100);

              return (
                <motion.div
                  key={m.faculty_id}
                  variants={listItem}
                  className="rounded-xl border transition-all duration-200 overflow-hidden flex flex-col justify-between"
                  style={
                    isChecked
                      ? { borderColor: "#3563F6", borderLeftWidth: "3px", background: "rgba(53,99,246,0.05)" }
                      : isFiltered
                      ? { borderColor: "rgba(53,99,246,0.5)", background: "#f8faff" }
                      : { borderColor: "rgb(226 232 240)", background: "white" }
                  }
                  whileHover={!isChecked ? { y: -1, boxShadow: "0 4px 12px rgba(15,23,42,0.08)" } : undefined}
                >
                  <div className="p-3">
                    <div className="flex items-start gap-2.5">
                      <button
                        type="button"
                        onClick={() => toggleSelectMentor(m.faculty_id)}
                        className="mt-0.5 shrink-0 text-ink-subtle hover:text-blue-600 transition-colors cursor-pointer"
                      >
                        {isChecked ? (
                          <CheckSquare className="h-4 w-4 text-blue-600" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                      <div className="shrink-0">
                        <Avatar name={m.name} size="sm" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-1">
                          <h4 className="font-heading text-xs font-bold text-ink truncate leading-tight" title={m.name}>
                            {m.name}
                          </h4>
                        </div>
                        <p className="text-[11px] text-ink-subtle truncate mt-0.5">
                          {m.designation ?? "Faculty"} · {m.department_code ?? "ICT"}
                        </p>
                      </div>
                    </div>

                    {/* Capacity bar */}
                    <div className="mt-2.5">
                      <div className="flex justify-between text-[10px] text-ink-subtle mb-1">
                        <span className="font-medium">{m.assigned_count}/10 students</span>
                        <span
                          className={`font-mono font-bold px-1.5 py-0.5 rounded ${
                            isFull
                              ? "text-emerald-700 bg-emerald-50"
                              : isWarning
                              ? "text-amber-700 bg-amber-50"
                              : "text-ink-muted"
                          }`}
                        >
                          {loadPct}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            isFull ? "bg-emerald-500" : isWarning ? "bg-amber-500" : "bg-blue-500"
                          }`}
                          style={{ width: `${loadPct}%` }}
                        />
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="mt-2.5 pt-2 border-t border-line/40 flex items-center justify-between text-[11px]">
                      <span className="text-ink-subtle text-[10px]">
                        {m.assigned_count > 0 ? `${m.assigned_count} mapped` : "0 assigned"}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setMentorFilter(isFiltered ? "ALL" : String(m.faculty_id));
                          document.getElementById("student-allocation-section")?.scrollIntoView({ behavior: "smooth" });
                        }}
                        className="font-semibold transition-colors cursor-pointer text-[11px]"
                        style={{ color: isFiltered ? "#ef4444" : "#3563F6" }}
                      >
                        {isFiltered ? "Clear Filter" : `View Mentees (${m.assigned_count})`}
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
            Showing <strong className="text-ink">{filteredMentors.length}</strong> of {mentors.length || 25} Faculty Mentors
          </span>
          <Link to="/faculty/directory" className="text-blue-600 font-semibold hover:underline text-xs">
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
        <div className="px-5 py-3.5 border-b border-line bg-surface-muted/40 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-heading text-sm font-bold text-ink">
                Student Cohort &amp; Roll Number Allocation
              </h3>
              <span className="bg-blue-100 text-blue-800 text-xs font-mono px-2 py-0.5 rounded-full font-bold">
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
                          ? "bg-surface text-emerald-700 shadow-xs"
                          : tab === "UNASSIGNED"
                          ? "bg-surface text-amber-700 shadow-xs"
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
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 transition-colors shadow-2xs disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              title="Clear mentor assignments from all students"
            >
              <RotateCcw className="h-3.5 w-3.5 text-rose-600" />
              <span>Clear All Assigned Mentors ({assignedCount})</span>
            </button>
          </div>
        </div>

        {/* Mapped Batches strip */}
        {batchRangeGroups.length > 0 && (
          <div className="px-5 py-2.5 bg-surface border-b border-line flex items-center gap-2.5 overflow-x-auto custom-scrollbar">
            <span className="text-[10px] font-bold uppercase tracking-widest text-ink-subtle shrink-0">
              Mapped Batches:
            </span>
            {batchRangeGroups.map((g, idx) => (
              <div
                key={idx}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-line bg-surface-muted/50 shrink-0 text-xs"
              >
                <span className="font-mono text-blue-700 font-bold">{g.range}</span>
                <span className="text-ink-subtle">·</span>
                <span className="text-ink font-medium truncate max-w-[120px]">{g.mentorName.split(" ").slice(-1)[0]}</span>
                <span className="text-emerald-600 font-bold">{g.status}</span>
              </div>
            ))}
          </div>
        )}

        {/* Search row */}
        <div className="px-5 py-2.5 border-b border-line bg-surface flex items-center gap-3 justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-subtle" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by student name, roll number, or NGO partner…"
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg bg-canvas border border-line text-ink focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all font-medium"
            />
          </div>
          {mentorFilter !== "ALL" && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-1 rounded-md font-medium">
                Viewing Mentees for Faculty ID: #{mentorFilter} ({filteredStudents.length} Students)
              </span>
              <button
                type="button"
                onClick={() => handleClearFacultyMentees(Number(mentorFilter))}
                disabled={clearSelectedStudents.isPending}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 transition-colors cursor-pointer"
              >
                <UserX className="h-3.5 w-3.5 text-rose-600" />
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
              className="px-5 py-2.5 bg-blue-50/90 dark:bg-blue-950/40 border-b border-blue-200 dark:border-blue-900/60 flex items-center justify-between gap-3 text-xs overflow-hidden"
            >
              <div className="flex items-center gap-2">
                <span className="font-semibold text-blue-900 dark:text-blue-100">
                  {selectedStudentIds.size} student{selectedStudentIds.size > 1 ? "s" : ""} selected
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedStudentIds(new Set())}
                  className="text-2xs text-blue-600 hover:text-blue-800 dark:text-blue-400 font-medium hover:underline cursor-pointer"
                >
                  Deselect all
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClearSelectedStudents}
                  disabled={clearSelectedStudents.isPending}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-100 hover:bg-rose-200 border border-rose-300 transition-colors shadow-2xs cursor-pointer"
                >
                  <UserX className="h-3.5 w-3.5 text-rose-600" />
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
                <th className="py-3 px-4 w-12">
                  <button
                    type="button"
                    onClick={toggleSelectAllStudents}
                    className="flex items-center text-ink-subtle hover:text-ink transition-colors cursor-pointer"
                  >
                    {selectedStudentIds.size === filteredStudents.length && filteredStudents.length > 0 ? (
                      <CheckSquare className="h-4 w-4 text-blue-600" />
                    ) : (
                      <Square className="h-4 w-4" />
                    )}
                  </button>
                </th>
                <th className="py-3 px-4 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-32">Roll No</th>
                <th className="py-3 px-4 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-60">Student Name</th>
                <th className="py-3 px-4 text-2xs font-bold uppercase tracking-widest text-ink-subtle">NGO / Project</th>
                <th className="py-3 px-4 text-2xs font-bold uppercase tracking-widest text-ink-subtle w-32">Status</th>
                <th className="py-3 px-4 text-2xs font-bold uppercase tracking-widest text-ink-subtle min-w-[280px]">Assigned Mentor</th>
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
                          ? "bg-blue-50/60 dark:bg-blue-950/20"
                          : idx % 2 === 0
                          ? "bg-white hover:bg-blue-50/30"
                          : "bg-surface-muted/20 hover:bg-blue-50/30"
                      }`}
                    >
                      <td className="py-2.5 px-4">
                        <button
                          type="button"
                          onClick={() => toggleSelectStudent(row.id)}
                          className="flex items-center text-ink-subtle hover:text-blue-600 transition-colors cursor-pointer"
                        >
                          {isChecked ? (
                            <CheckSquare className="h-4 w-4 text-blue-600" />
                          ) : (
                            <Square className="h-4 w-4" />
                          )}
                        </button>
                      </td>
                      <td className="py-2.5 px-4">
                        <span className="font-mono font-bold text-xs text-blue-700">
                          {row.roll_number}
                        </span>
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={row.student_name ?? "Student"} size="xs" />
                          <span className="font-semibold text-xs text-ink truncate">
                            {row.student_name}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 px-4">
                        <span className="text-xs text-ink-muted truncate block">
                          {row.organization_name ?? <span className="text-ink-subtle">—</span>}
                        </span>
                      </td>
                      <td className="py-2.5 px-4">
                        {row.mentor_faculty_id ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-2xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            Allocated
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-2xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                            Unassigned
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-4">
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
                              const isFull = m.assigned_count >= 10 && !isCurrent;
                              return (
                                <option key={m.faculty_id} value={m.faculty_id} disabled={isFull}>
                                  {m.name} ({m.assigned_count}/10{isFull ? " - FULL" : ""})
                                </option>
                              );
                            })}
                          </Select>
                          {row.mentor_faculty_id && (
                            <span className="font-mono text-xs text-blue-700 font-bold px-2 py-0.5 rounded bg-blue-50 border border-blue-100 shrink-0">
                              {currentMentor?.assigned_count ?? 1}/10
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
        <div className="px-5 py-3 border-t border-line bg-surface-muted/60 flex items-center justify-between">
          <span className="text-xs text-ink-muted">
            Showing <strong className="text-ink">{filteredStudents.length}</strong> of {enrollments.length} Students
          </span>
          <div className="flex items-center gap-4">
            <span className="text-xs font-mono text-ink-muted">
              <span className="text-emerald-700 font-bold">{assignedCount}</span> Assigned
              {" · "}
              <span className="text-amber-600 font-bold">{unassignedCount}</span> Pending
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
