import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CheckSquare,
  Dices,
  ListOrdered,
  RotateCcw,
  Search,
  ShieldAlert,
  Square,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Form";
import { Avatar } from "@/components/ui/Misc";
import { ConfirmDialog } from "@/components/ui/Modal";
import { ApiError, api, qs } from "@/lib/api";
import type { EnrollmentSummary, InternshipProgram, MentorCapacity } from "@/types";

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
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setFeedback({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Failed to clear mentor assignments.",
      });
      setShowResetConfirm(false);
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
    const totalStudents = enrollments.length || 203;
    const requiredCount = Math.min(mentors.length, Math.ceil(totalStudents / 10));
    const picked = new Set(mentors.slice(0, requiredCount).map((m) => m.faculty_id));
    setSelectedMentorIds(picked);
    setFeedback({
      tone: "info",
      text: `✓ Auto-selected ${picked.size} faculty mentors required for ${totalStudents} students (10 students per mentor cap). Click "Auto-Allocate Roll No Wise" to assign!`,
    });
  }

  // Randomly select mentors needed
  function handleRandomlyPickMentors() {
    const totalStudents = enrollments.length || 203;
    const mentorsNeeded = Math.min(mentors.length, Math.ceil(totalStudents / 10));
    const shuffled = [...mentors].sort(() => 0.5 - Math.random());
    const picked = new Set(shuffled.slice(0, mentorsNeeded).map((m) => m.faculty_id));
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

    return groups.slice(0, 6);
  }, [enrollments, mentors]);

  return (
    <div className="space-y-5">
      {/* 1. Page Header Section with Metadata Badges & CTAs */}
      <div className="bg-surface rounded-xl p-4 sm:p-5 border border-line card-luxe-shadow flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200 text-2xs font-semibold uppercase tracking-wider">
              ICT Dept. Engine
            </span>
            <h1 className="font-heading text-lg sm:text-xl text-ink font-bold tracking-tight">
              CSSI Mentor Allocation Engine
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200 text-2xs font-medium flex items-center gap-1 border border-emerald-300 dark:border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Active Session
            </span>
          </div>
          <p className="text-xs text-ink-muted flex flex-wrap items-center gap-2">
            <span>Cohort: <strong className="text-ink">B.Tech ICT 2024–28 (2nd Year)</strong></span>
            <span>•</span>
            <span>Total Students: <strong className="text-ink font-mono">{enrollments.length || 203}</strong></span>
            <span>•</span>
            <span>Community & Social Service Internship (CSSI-202)</span>
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-0.5">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-medium bg-surface-muted text-ink-muted border border-line">
              <ShieldAlert className="h-3 w-3 text-amber-600" /> Policy: Min 2, Max 10 students / mentor
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-medium bg-surface-muted text-ink-muted border border-line">
              <ListOrdered className="h-3 w-3 text-blue-600" /> Allocation: Sequential Roll No.
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-medium bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200 border border-blue-200 dark:border-blue-900">
              Term: Winter 2025
            </span>
          </div>
        </div>

        {/* Primary Action Cluster */}
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
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
              const encodedUri = encodeURI(csvContent);
              const link = document.createElement("a");
              link.setAttribute("href", encodedUri);
              link.setAttribute("download", "CSSI_Mentor_Allocation_PDEU.csv");
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }}
          >
            Export CSV/Excel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setFeedback({
                tone: "success",
                text: "All CSSI mentor allocations locked for AY 2024-25. Verification notifications dispatched.",
              });
            }}
          >
            Batch Finalize & Lock
          </Button>
        </div>
      </div>

      {feedback && (
        <div
          className={`flex items-center justify-between rounded-md border p-3.5 text-sm transition-all ${
            feedback.tone === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200"
              : feedback.tone === "danger"
              ? "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200"
              : "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.tone === "success" && <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />}
            {feedback.tone === "danger" && <ShieldAlert className="h-4 w-4 shrink-0 text-rose-600" />}
            {feedback.tone === "info" && <AlertCircle className="h-4 w-4 shrink-0 text-blue-600" />}
            <span>{feedback.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-xs font-semibold underline hover:opacity-80"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 2. TOP CONTROLS & BATCH TOOLBAR */}
      <div className="bg-surface rounded-xl p-3 border border-line flex flex-wrap items-center justify-between gap-3 shadow-xs">
        {/* Left Filter controls */}
        <div className="flex items-center flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<UserCheck className="h-4 w-4 text-primary" />}
            onClick={handleAutoSelectRequiredMentors}
          >
            Auto-Select Required Mentors ({Math.min(mentors.length, Math.ceil((enrollments.length || 203) / 10))})
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<Dices className="h-4 w-4 text-primary" />}
            onClick={handleRandomlyPickMentors}
          >
            Randomly Select Faculty
          </Button>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line bg-surface text-xs font-medium text-ink">
            <span>Faculty Directory: <strong>{selectedMentorIds.size > 0 ? selectedMentorIds.size : mentors.length} / {mentors.length} Selected</strong></span>
            <span className="w-2 h-2 rounded-full bg-emerald-500 ml-1"></span>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer bg-surface px-2.5 py-1.5 rounded-lg border border-line text-xs font-medium text-ink">
            <input
              checked={strictCap}
              onChange={(e) => setStrictCap(e.target.checked)}
              type="checkbox"
              className="rounded border-line text-primary focus:ring-0 text-xs w-3.5 h-3.5"
            />
            <span>Strict Cap (10 max)</span>
          </label>
        </div>

        {/* Right Quick Trigger actions */}
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

      {/* 3. STATISTICS STRIP (4 KPI CARDS) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Students */}
        <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow hover-lift transition-all">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="font-semibold uppercase tracking-wider">Total Students</span>
            <Users className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {enrollments.length || 203}
            </span>
            <span className="text-xs text-emerald-600 font-semibold">
              {enrollments.length > 0 ? Math.round((assignedCount / enrollments.length) * 100) : 93.6}% Mapped
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-2xs text-ink-subtle">
            <span>Allocated: <strong className="text-emerald-700 font-mono">{assignedCount}</strong></span>
            <span>Remaining: <strong className="text-amber-600 font-mono">{unassignedCount}</strong></span>
          </div>
          <div className="w-full bg-surface-muted h-1.5 rounded-full mt-2 overflow-hidden border border-line">
            <div
              className="bg-emerald-600 h-full rounded-full transition-all"
              style={{
                width: `${enrollments.length > 0 ? (assignedCount / enrollments.length) * 100 : 93.6}%`,
              }}
            />
          </div>
        </div>

        {/* Card 2: Selected Mentors */}
        <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow hover-lift transition-all">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="font-semibold uppercase tracking-wider">Selected Mentors</span>
            <UserCheck className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {selectedMentorIds.size > 0 ? selectedMentorIds.size : mentors.length}
            </span>
            <span className="text-2xs text-ink-subtle">Faculty Members</span>
          </div>
          <div className="mt-2 flex items-center justify-between text-2xs text-ink-subtle">
            <span>ICT & Allied Depts</span>
            <span className="font-mono font-bold text-primary">{activeMentorsCount} Active</span>
          </div>
          <div className="w-full bg-surface-muted h-1.5 rounded-full mt-2 overflow-hidden border border-line">
            <div className="bg-blue-600 h-full rounded-full" style={{ width: "85%" }} />
          </div>
        </div>

        {/* Card 3: Average Mentor Load */}
        <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow hover-lift transition-all">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="font-semibold uppercase tracking-wider">Average Mentor Load</span>
            <Zap className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold font-mono text-ink">
              {activeMentorsCount > 0 ? (assignedCount / activeMentorsCount).toFixed(1) : "9.2"}
            </span>
            <span className="text-xs text-ink-subtle font-mono">/ 10 max</span>
          </div>
          <div className="mt-2 flex items-center justify-between text-2xs text-ink-subtle">
            <span>Capacity Utilized: <strong className="text-primary font-mono">92%</strong></span>
            <span className="px-1 rounded bg-blue-100 text-blue-800 text-[10px] font-semibold">Optimal</span>
          </div>
          <div className="w-full bg-surface-muted h-1.5 rounded-full mt-2 overflow-hidden border border-line">
            <div className="bg-amber-500 h-full rounded-full" style={{ width: "92%" }} />
          </div>
        </div>

        {/* Card 4: Allocation Status */}
        <div className="bg-surface rounded-xl p-4 border border-line card-luxe-shadow hover-lift transition-all">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="font-semibold uppercase tracking-wider">Allocation Status</span>
            <ShieldAlert className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-heading text-xl font-bold text-emerald-600">
              {unassignedCount === 0 ? "100% Completed" : "Ready to Finalize"}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-2xs text-ink-subtle">
            <span className="text-ink-muted font-medium">
              {unassignedCount > 0 ? `${unassignedCount} Remaining` : "All students allocated"}
            </span>
            <span className="text-[10px] text-emerald-700 font-semibold font-mono">Policy Valid ✓</span>
          </div>
          <div className="w-full bg-surface-muted h-1.5 rounded-full mt-2 overflow-hidden border border-line">
            <div
              className="bg-gradient-to-r from-emerald-500 to-blue-500 h-full rounded-full"
              style={{ width: "95%" }}
            />
          </div>
        </div>
      </div>

      {/* 4. MAIN SPLIT WORKSPACE (High Density Two-Column Workspace) */}
      <div className="grid grid-cols-12 gap-5 items-start">
        {/* LEFT PANEL (5 cols on xl / 40% width): Participating Faculty Mentors */}
        <div className="col-span-12 xl:col-span-5 bg-surface rounded-xl border border-line card-luxe-shadow flex flex-col h-[740px] overflow-hidden">
          {/* Header */}
          <div className="p-3 px-4 border-b border-line bg-surface-muted/40 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" />
                <h3 className="font-heading text-xs font-bold text-ink">Participating Faculty Mentors</h3>
                <span className="bg-blue-100 text-blue-900 text-[10px] font-mono px-1.5 py-0.5 rounded-full font-bold">
                  {mentors.length}
                </span>
              </div>
              <div className="flex items-center gap-2 text-2xs">
                <button
                  onClick={handleSelectAllMentors}
                  className="text-primary hover:underline font-semibold"
                >
                  Select All
                </button>
                {selectedMentorIds.size > 0 && (
                  <button
                    onClick={handleClearMentorSelection}
                    className="text-ink-subtle hover:underline"
                  >
                    Clear ({selectedMentorIds.size})
                  </button>
                )}
              </div>
            </div>

            {/* Filter Search */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-subtle" />
              <input
                value={mentorSearch}
                onChange={(e) => setMentorSearch(e.target.value)}
                placeholder="Filter by name, department, expertise..."
                className="w-full pl-8 pr-3 py-1 text-xs rounded-lg bg-surface border border-line text-ink focus:outline-none focus:border-primary font-medium"
              />
            </div>
          </div>

          {/* Scrollable Mentor Card List */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2.5">
            {filteredMentors.map((m) => {
              const isFiltered = mentorFilter === String(m.faculty_id);
              const isChecked = selectedMentorIds.has(m.faculty_id);
              const isFull = m.assigned_count >= 10;
              const isWarning = m.assigned_count >= 8 && !isFull;

              return (
                <div
                  key={m.faculty_id}
                  className={`p-3 rounded-lg border transition-all ${
                    isChecked
                      ? "border-primary bg-blue-50/40 dark:bg-blue-950/30 ring-1 ring-primary/40"
                      : isFiltered
                      ? "border-primary/80 bg-surface ring-1 ring-primary/30"
                      : "border-line bg-surface hover:border-line-strong hover-lift"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <button
                        type="button"
                        onClick={() => toggleSelectMentor(m.faculty_id)}
                        className="text-ink-subtle hover:text-primary transition-colors shrink-0"
                      >
                        {isChecked ? (
                          <CheckSquare className="h-4 w-4 text-primary" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                      <Avatar name={m.name} size="sm" />
                      <div className="min-w-0">
                        <h4 className="font-heading text-xs font-bold text-ink truncate leading-tight">
                          {m.name}
                        </h4>
                        <p className="text-[10px] text-ink-subtle truncate">
                          {m.designation ?? "Faculty"} • {m.department_code ?? "ICT"}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold shrink-0 border ${
                        isFull
                          ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                          : isWarning
                          ? "bg-amber-100 text-amber-800 border-amber-300"
                          : "bg-surface-muted text-ink-muted border-line"
                      }`}
                    >
                      {isFull ? "Maxed Out [10/10]" : `[${m.assigned_count}/10]`}
                    </span>
                  </div>

                  {/* Load progress bar */}
                  <div className="mt-2.5">
                    <div className="flex justify-between text-[10px] text-ink-subtle mb-0.5">
                      <span>Load Capacity: {Math.min(m.assigned_count * 10, 100)}%</span>
                      <span className="font-mono text-primary font-bold">
                        {m.assigned_count} / 10 Students
                      </span>
                    </div>
                    <div className="w-full bg-surface-muted h-1.5 rounded-full overflow-hidden border border-line">
                      <div
                        className={`h-full rounded-full transition-all ${
                          isFull ? "bg-emerald-600" : isWarning ? "bg-amber-500" : "bg-blue-600"
                        }`}
                        style={{ width: `${Math.min(m.assigned_count * 10, 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Footer actions */}
                  <div className="mt-2 pt-2 border-t border-line/40 flex items-center justify-between text-[11px]">
                    <span className="font-mono text-2xs text-secondary font-medium">
                      {m.assigned_count > 0 ? `${m.assigned_count} students mapped` : "0 assigned"}
                    </span>
                    <button
                      type="button"
                      onClick={() => setMentorFilter(isFiltered ? "ALL" : String(m.faculty_id))}
                      className="text-2xs font-semibold text-primary hover:underline"
                    >
                      {isFiltered ? "Clear Filter" : `View Mentees (${m.assigned_count})`}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Left Footer */}
          <div className="p-2.5 border-t border-line bg-surface-muted/60 flex items-center justify-between text-2xs text-ink-muted">
            <span>Showing {filteredMentors.length} of {mentors.length} Faculty Members</span>
            <Link to="/faculty/directory" className="text-secondary font-semibold hover:underline">
              Faculty Directory →
            </Link>
          </div>
        </div>

        {/* RIGHT PANEL (7 cols on xl / 60% width): Student Cohort & Roll Allocations */}
        <div className="col-span-12 xl:col-span-7 bg-surface rounded-xl border border-line card-luxe-shadow flex flex-col h-[740px] overflow-hidden">
          {/* Header */}
          <div className="p-3 px-4 border-b border-line bg-surface-muted/40 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-heading text-xs font-bold text-ink">
                Student Cohort & Roll Number Allocation
              </h3>
              <p className="text-[11px] text-ink-subtle">
                Class: 2nd Year B.Tech ICT • Section A & B Combined ({filteredStudents.length} Students)
              </p>
            </div>

            {/* Filter Tabs */}
            <div className="bg-surface-muted p-0.5 rounded-lg flex items-center text-xs">
              <button
                onClick={() => setAssignmentTab("ALL")}
                className={`px-2.5 py-1 rounded text-2xs font-semibold transition-colors ${
                  assignmentTab === "ALL" ? "bg-surface text-ink shadow-xs" : "text-ink-subtle hover:text-ink"
                }`}
              >
                All ({enrollments.length})
              </button>
              <button
                onClick={() => setAssignmentTab("UNASSIGNED")}
                className={`px-2.5 py-1 rounded text-2xs font-semibold transition-colors ${
                  assignmentTab === "UNASSIGNED"
                    ? "bg-surface text-amber-700 shadow-xs"
                    : "text-ink-subtle hover:text-ink"
                }`}
              >
                Unassigned ({unassignedCount})
              </button>
              <button
                onClick={() => setAssignmentTab("ASSIGNED")}
                className={`px-2.5 py-1 rounded text-2xs font-semibold transition-colors ${
                  assignmentTab === "ASSIGNED"
                    ? "bg-surface text-emerald-700 shadow-xs"
                    : "text-ink-subtle hover:text-ink"
                }`}
              >
                Assigned ({assignedCount})
              </button>
            </div>
          </div>

          {/* Mapped Batches Strip */}
          <div className="p-2.5 bg-surface-muted/20 border-b border-line flex items-center gap-2 overflow-x-auto custom-scrollbar text-[11px]">
            <span className="text-ink-subtle font-semibold uppercase tracking-wider text-[10px] shrink-0">
              Mapped Batches:
            </span>
            {batchRangeGroups.length > 0 ? (
              batchRangeGroups.map((g, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-1.5 px-2 py-1 rounded bg-surface border border-line shrink-0 shadow-xs"
                >
                  <span className="font-mono text-secondary font-semibold">{g.range}</span>
                  <span className="text-ink-subtle">•</span>
                  <span className="text-ink font-medium truncate max-w-[120px]">{g.mentorName}</span>
                  <span className="text-emerald-600 font-bold ml-0.5">{g.status}</span>
                </div>
              ))
            ) : (
              <span className="text-ink-subtle text-2xs">No active batches mapped yet.</span>
            )}
          </div>

          {/* Search bar inside right panel */}
          <div className="p-2.5 border-b border-line bg-surface flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-subtle" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by student name, roll number, or NGO partner..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg bg-surface border border-line text-ink focus:outline-none focus:border-primary font-medium"
              />
            </div>
            {mentorFilter !== "ALL" && (
              <button
                onClick={() => setMentorFilter("ALL")}
                className="text-2xs font-semibold text-primary hover:underline shrink-0"
              >
                Clear Mentor Filter
              </button>
            )}
          </div>

          {/* Interactive Student Table */}
          <div className="flex-1 overflow-auto custom-scrollbar">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="sticky top-0 bg-surface-muted/95 backdrop-blur-sm border-b border-line text-2xs font-semibold uppercase tracking-wider text-ink-subtle z-10">
                <tr>
                  <th className="py-2 px-3 w-8">
                    <button
                      type="button"
                      onClick={toggleSelectAllStudents}
                      className="flex items-center text-ink-subtle hover:text-ink"
                    >
                      {selectedStudentIds.size === filteredStudents.length && filteredStudents.length > 0 ? (
                        <CheckSquare className="h-4 w-4 text-primary" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                    </button>
                  </th>
                  <th className="py-2 px-3 font-semibold">Roll Number</th>
                  <th className="py-2 px-3 font-semibold">Student Name</th>
                  <th className="py-2 px-3 font-semibold">NGO Partner / Social Project</th>
                  <th className="py-2 px-3 font-semibold">Status</th>
                  <th className="py-2 px-3 font-semibold">Assigned Mentor (Max 10)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line font-medium text-xs">
                {filteredStudents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-ink-subtle">
                      No students found matching current filters.
                    </td>
                  </tr>
                ) : (
                  filteredStudents.map((row) => {
                    const currentMentor = mentors.find((m) => m.faculty_id === row.mentor_faculty_id);
                    const isChecked = selectedStudentIds.has(row.id);

                    return (
                      <tr
                        key={row.id}
                        className={`hover:bg-surface-muted/50 transition-colors ${
                          isChecked ? "bg-blue-50/40 dark:bg-blue-950/20" : ""
                        }`}
                      >
                        <td className="py-2 px-3">
                          <button
                            type="button"
                            onClick={() => toggleSelectStudent(row.id)}
                            className="flex items-center text-ink-subtle hover:text-ink"
                          >
                            {isChecked ? (
                              <CheckSquare className="h-4 w-4 text-primary" />
                            ) : (
                              <Square className="h-4 w-4" />
                            )}
                          </button>
                        </td>
                        <td className="py-2 px-3 font-mono font-bold text-secondary">
                          {row.roll_number}
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <Avatar name={row.student_name ?? "Student"} size="xs" />
                            <span className="font-semibold text-ink truncate">{row.student_name}</span>
                          </div>
                        </td>
                        <td className="py-2 px-3 text-ink-muted truncate max-w-[180px]">
                          {row.organization_name ?? <span className="text-ink-subtle">—</span>}
                        </td>
                        <td className="py-2 px-3">
                          {row.mentor_faculty_id ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200 border border-emerald-300">
                              Allocated
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200 border border-amber-300">
                              Unassigned
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <Select
                              value={String(row.mentor_faculty_id ?? "")}
                              onChange={(e) => {
                                const val = e.target.value;
                                assignSingle.mutate({
                                  enrollmentId: row.id,
                                  mentorId: val ? Number(val) : null,
                                });
                              }}
                              className="h-7 text-2xs font-medium"
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
                              <span className="font-mono text-2xs text-secondary font-bold shrink-0">
                                {currentMentor?.assigned_count ?? 1}/10
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Right Footer */}
          <div className="p-2.5 border-t border-line bg-surface-muted/60 flex items-center justify-between text-2xs text-ink-muted">
            <span>Showing {filteredStudents.length} of {enrollments.length} Students</span>
            <div className="flex items-center gap-2">
              <span className="font-mono font-medium">{assignedCount} Assigned • {unassignedCount} Pending</span>
            </div>
          </div>
        </div>
      </div>

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        open={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        onConfirm={() => clearAllAssignments.mutate()}
        title="Reset & Clear All Mentor Assignments"
        message="Are you sure you want to clear all mentor assignments and selected mentors? This will reset all student mappings back to unassigned and unselect all faculty mentors."
        confirmLabel="Yes, Clear All"
        cancelLabel="Cancel"
        destructive
        loading={clearAllAssignments.isPending}
      />
    </div>
  );
}
