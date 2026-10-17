import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock, Check, Download, Eraser, Filter, ListOrdered, Lock, LockOpen, Plus,
  Repeat2, RotateCcw, Search, ShieldAlert, Trash2, UserCheck, Users, UserX, X,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Form";
import { Avatar, PageHeader } from "@/components/ui/Misc";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { StatGrid, StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { EnrollmentSummary, InternshipProgram, MentorCapacity, ProgramWindows } from "@/types";

/**
 * Mentor allocation for an internship programme (CSSI, Summer Internship).
 *
 * Laid out the way a coordinator works: who is available to mentor (left), how
 * the next roll-number run will split the cohort (top right), and every
 * student with their mentor (below). The server enforces every rule shown
 * here — department-only mentors, no HoD, the per-mentor cap, and (for a
 * window-run programme) that registration has started.
 */

/** A real checkbox with an accessible name, styled to the design system. */
function Tick({
  checked, onChange, label, indeterminate,
}: { checked: boolean; onChange: () => void; label: string; indeterminate?: boolean }) {
  return (
    <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
      <input
        type="checkbox" checked={checked} onChange={onChange} aria-label={label}
        ref={(el) => { if (el) el.indeterminate = Boolean(indeterminate); }}
        className="peer h-4 w-4 cursor-pointer appearance-none rounded-sm border border-line-strong bg-surface checked:border-accent checked:bg-accent indeterminate:border-accent indeterminate:bg-accent"
        onClick={(e) => e.stopPropagation()}
      />
      <Check className="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100" aria-hidden />
    </span>
  );
}

function LoadBar({ count, cap }: { count: number; cap: number }) {
  const pct = cap > 0 ? Math.min(100, (count / cap) * 100) : 0;
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
      <span
        className={cn("block h-full rounded-full transition-[width] duration-300",
          count >= cap ? "bg-warning-solid" : count > 0 ? "bg-accent" : "bg-transparent")}
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

function PanelHeader({ title, meta, children }: { title: string; meta?: ReactNode; children?: ReactNode }) {
  return (
    <div className="border-b border-line px-4 py-3.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-heading text-md font-semibold text-ink">{title}</h2>
        {meta}
      </div>
      {children}
    </div>
  );
}

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
  const [lockDialog, setLockDialog] = useState<"lock" | "unlock" | null>(null);
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
        // The server names the role that runs each programme, so a new
        // programme type needs no change here.
        const domainMatches = c.domain === p.coordination_domain;
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

  // A window-run programme (CSSI) allocates only once registration has started.
  const windowsQuery = useQuery({
    queryKey: ["internship-windows", activeProgramId],
    queryFn: () => api.get<ProgramWindows>(`/internships/programs/${activeProgramId}/windows`),
    enabled: Boolean(activeProgramId && activeProgram?.window_kinds?.length),
  });
  const registrationWindow = windowsQuery.data?.windows.find((w) => w.kind === "REGISTRATION");
  const allocationLocked = Boolean(
    activeProgram?.window_kinds?.includes("REGISTRATION")
      && windowsQuery.isSuccess
      && (!registrationWindow || registrationWindow.state === "SCHEDULED"),
  );

  const mentors = mentorsQuery.data ?? [];
  const isLocked = Boolean(activeProgram?.mentor_allocation_locked_at);
  // While locked, a student can only be moved to a mentor in the allocation.
  const assignable = isLocked ? mentors.filter((m) => m.in_allocation) : mentors;
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

  // Lock, unlock and the one-step changes a locked allocation allows. The
  // server holds every rule (who may, the cap, the allocation's members).
  const allocationChange = useMutation({
    mutationFn: ({ method, path, body }: { method: "post" | "put" | "delete"; path: string; body?: unknown }) => {
      const url = `/internships/programs/${activeProgramId}/mentor-allocation${path}`;
      return method === "delete" ? api.delete<{ message?: string }>(url)
        : method === "put" ? api.put<{ message?: string }>(url, body)
          : api.post<{ message?: string }>(url, body);
    },
    onSuccess: (res, vars) => {
      const text = vars.path === "/lock" ? "Allocation locked. Change it one mentor at a time from here."
        : vars.path === "/unlock" ? "Allocation unlocked. Runs and resets are available again."
          : res?.message ?? "Updated.";
      setFeedback({ tone: "success", text });
      setLockDialog(null);
      setSelectedMentorIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ["internship-programs"] });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      void queryClient.invalidateQueries({ queryKey: ["internship-enrollments"] });
    },
    onError: (err) => {
      setLockDialog(null);
      setFeedback({ tone: "danger", text: err instanceof ApiError ? err.message : "That change could not be made." });
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
      text: `✓ Auto-selected ${picked.size} faculty mentors required for ${totalStudents} students (${cap ?? "—"} per mentor). Click Auto-allocate to assign them.`,
    });
  }

  // One click: with no mentors ticked, take the ones the cohort needs — the
  // same name-ordered pool the server would use — tick them so the panel shows
  // who was picked, and run the roll-number allocation with exactly those.
  function handleAutoAllocate() {
    const ids = selectedMentorIds.size > 0
      ? Array.from(selectedMentorIds)
      : mentors.slice(0, runUsed).map((m) => m.faculty_id);
    if (selectedMentorIds.size === 0) setSelectedMentorIds(new Set(ids));
    allocateByRollNo.mutate(ids);
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


  // ── derived view data ─────────────────────────────────────────────────
  // Each mentor's current roll-number block, shown beside their load.
  const rangesByMentor = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const e of enrollments) {
      if (!e.mentor_faculty_id || !e.roll_number) continue;
      const list = map.get(e.mentor_faculty_id) ?? [];
      list.push(e.roll_number);
      map.set(e.mentor_faculty_id, list);
    }
    const out = new Map<number, string>();
    map.forEach((rolls, id) => {
      rolls.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
      out.set(id, rolls.length === 1 ? rolls[0] : `${rolls[0]} – ${rolls[rolls.length - 1]}`);
    });
    return out;
  }, [enrollments]);

  // What the next roll-number run will do — the same arithmetic the server uses.
  const runMentors = selectedMentorIds.size > 0 ? selectedMentorIds.size : mentors.length;
  const runUsed = cap ? Math.min(runMentors, Math.ceil(totalStudents / cap)) : 0;
  const runSeated = cap ? Math.min(totalStudents, runUsed * cap) : 0;
  const runLeft = totalStudents - runSeated;
  const filteredMentorName = mentorFilter !== "ALL" && mentorFilter !== "UNASSIGNED"
    ? mentors.find((m) => String(m.faculty_id) === mentorFilter)?.name : null;
  const allVisibleSelected = filteredStudents.length > 0
    && filteredStudents.every((s) => selectedStudentIds.has(s.id));
  const someVisibleSelected = filteredStudents.some((s) => selectedStudentIds.has(s.id));

  if (programsQuery.isLoading) return <LoadingState rows={4} />;
  if (programsQuery.error) return <ErrorState onRetry={() => programsQuery.refetch()} />;
  if (!activeProgram) {
    return (
      <Card>
        <EmptyState title="No programme to allocate"
          description="You coordinate no CSSI or Summer Internship programme. Your HoD appoints coordinators." />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Mentor allocation"
        description={`${activeProgram.name} · ${activeProgram.code}${activeProgram.target_semester ? ` · Semester ${activeProgram.target_semester}` : ""}`}
        breadcrumbs={[{ label: "Internships", to: "/internships" }, { label: "Mentor allocation" }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {availablePrograms.length > 1 && (
              <Select aria-label="Programme" value={String(activeProgram.id)}
                      onChange={(e) => handleProgramChange(e.target.value)} className="h-9 w-60">
                {availablePrograms.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}</option>)}
              </Select>
            )}
            {activeProgram.window_kinds?.length > 0 && (
              <LinkButton to={`/internships/windows?program_id=${activeProgram.id}`} variant="secondary" size="sm"
                          icon={<CalendarClock className="h-3.5 w-3.5" aria-hidden />}>
                Windows &amp; deadlines
              </LinkButton>
            )}
            <Button variant="secondary" size="sm" onClick={exportCSV} disabled={!enrollments.length}
                    icon={<Download className="h-3.5 w-3.5" aria-hidden />}>
              Export CSV
            </Button>
          </div>
        }
      />

      {allocationLocked && (
        <Alert variant="info" title="Allocation opens once registration starts"
               action={<LinkButton to={`/internships/windows?program_id=${activeProgram.id}`} size="sm" variant="accent">Open registration</LinkButton>}>
          Students register their organisation first; then you allocate mentors.
        </Alert>
      )}
      {!activeProgram.mentor_capacity_confirmed && <MentorCapNotice program={activeProgram} />}
      {feedback && (
        <Alert variant={feedback.tone === "danger" ? "danger" : feedback.tone === "success" ? "success" : "info"}
               onDismiss={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <StatGrid columns={4}>
        <StatTile label="Students" value={loadingData ? "—" : totalStudents} icon={Users} tone="neutral"
                  hint={`Registered for ${activeProgram.code}`} />
        <StatTile label="With a mentor" value={loadingData ? "—" : assignedCount} icon={UserCheck}
                  tone={assignedCount && !unassignedCount ? "success" : "accent"} hint={loadingData ? null : `${allocPct}% of the cohort`} />
        <StatTile label="Awaiting a mentor" value={loadingData ? "—" : unassignedCount} icon={UserX}
                  tone={unassignedCount ? "warning" : "neutral"}
                  hint={unassignedCount ? "Auto-allocate or assign below" : "Everyone is allocated"} />
        <StatTile label="Average load" value={loadingData ? "—" : avgLoad} icon={ListOrdered} tone="neutral"
                  hint={cap ? `Cap ${cap} per mentor · ${activeMentorsCount} mentors in use` : null} />
      </StatGrid>

      <div className="grid items-start gap-5 lg:grid-cols-[22rem_minmax(0,1fr)]">
        {/* ── Faculty mentors ─────────────────────────────────────────── */}
        {isLocked ? (
          <LockedMentorsPanel
            mentors={mentors} ranges={rangesByMentor} pending={allocationChange.isPending}
            mentorFilter={mentorFilter} onFilter={setMentorFilter}
            onChange={(change) => allocationChange.mutate(change)}
          />
        ) : (
        <Card className="lg:sticky lg:top-20">
          <PanelHeader
            title="Faculty mentors"
            meta={<Badge tone="neutral">{selectedMentorIds.size ? `${selectedMentorIds.size} of ${mentors.length} selected` : `${mentors.length} eligible`}</Badge>}
          >
            <p className="mt-1 text-xs text-ink-muted">
              Leave these unticked and Auto-allocate picks the mentors needed. Tick mentors to use only them.
            </p>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle" aria-hidden />
              <Input value={mentorSearch} onChange={(e) => setMentorSearch(e.target.value)}
                     placeholder="Search mentors" aria-label="Search mentors" className="h-9 pl-8" />
            </div>
            <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-xs font-semibold">
              <button type="button" className="cursor-pointer text-accent hover:underline disabled:text-ink-subtle disabled:no-underline"
                      onClick={handleAutoSelectRequiredMentors} disabled={!requiredMentors}>
                Select required ({requiredMentors})
              </button>
              <button type="button" className="cursor-pointer text-accent hover:underline" onClick={handleSelectAllMentors}>
                Select all
              </button>
              {selectedMentorIds.size > 0 && (
                <button type="button" className="cursor-pointer text-ink-muted hover:text-ink hover:underline" onClick={handleClearMentorSelection}>
                  Clear
                </button>
              )}
            </div>
          </PanelHeader>
          {mentorsQuery.isLoading ? <LoadingState rows={5} /> : filteredMentors.length === 0 ? (
            <EmptyState compact title={mentorSearch ? "No mentor matches" : "No eligible mentors"} />
          ) : (
            <ul className="max-h-[34rem] divide-y divide-line overflow-y-auto">
              {filteredMentors.map((m) => {
                const selected = selectedMentorIds.has(m.faculty_id);
                const filtering = mentorFilter === String(m.faculty_id);
                return (
                  <li key={m.faculty_id}
                      className={cn("flex items-start gap-3 px-4 py-3 transition-colors",
                        selected ? "bg-accent-soft/50" : "hover:bg-surface-muted/50")}>
                    <span className="pt-0.5">
                      <Tick checked={selected} onChange={() => toggleSelectMentor(m.faculty_id)}
                            label={`Include ${m.name} in the next run`} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="truncate text-sm font-semibold text-ink" title={m.name}>{m.name}</p>
                        <span className={cn("shrink-0 font-mono text-xs tabular-nums", m.is_full ? "font-semibold text-warning" : "text-ink-muted")}>
                          {m.assigned_count}/{m.max_capacity}
                        </span>
                      </div>
                      <p className="truncate text-xs text-ink-subtle">
                        {[m.designation, m.department_code].filter(Boolean).join(" · ")}
                      </p>
                      <div className="mt-1.5"><LoadBar count={m.assigned_count} cap={m.max_capacity} /></div>
                      <div className="mt-1.5 flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-2xs text-ink-subtle">
                          {rangesByMentor.get(m.faculty_id) ?? "No students yet"}
                        </span>
                        {m.assigned_count > 0 && (
                          <button type="button"
                                  onClick={() => setMentorFilter(filtering ? "ALL" : String(m.faculty_id))}
                                  className={cn("shrink-0 cursor-pointer text-2xs font-semibold hover:underline",
                                    filtering ? "text-ink" : "text-accent")}>
                            {filtering ? "Showing" : "View students"}
                          </button>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        )}

        <div className="min-w-0 space-y-5">
          {/* ── The next run ──────────────────────────────────────────── */}
          <Card>
            <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center">
              <span className={cn("hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl md:flex",
                isLocked ? "bg-success-soft text-success" : "bg-accent-soft text-accent")}>
                {isLocked ? <Lock className="h-5 w-5" aria-hidden /> : <ListOrdered className="h-5 w-5" aria-hidden />}
              </span>
              <div className="min-w-0 flex-1">
                {isLocked ? (
                  <LockedSummary lockedAt={activeProgram.mentor_allocation_locked_at!}
                                 mentors={mentors.filter((m) => m.in_allocation).length}
                                 students={assignedCount} waiting={unassignedCount}
                                 onUnlock={() => setLockDialog("unlock")} />
                ) : (<>
                <h2 className="font-heading text-md font-semibold text-ink">Allocate by roll number</h2>
                <p className="mt-0.5 text-sm text-ink-muted">
                  {!cap || loadingData ? "Loading the cohort…" : totalStudents === 0 ? "No students have registered yet." : (
                    <>
                      {selectedMentorIds.size === 0 ? "Picks the mentors needed and gives each a block of consecutive roll numbers: " : "Consecutive roll numbers go to the same mentor: "}
                      <strong className="text-ink">{runSeated}</strong> of {totalStudents} students across{" "}
                      <strong className="text-ink">{runUsed}</strong> mentor{runUsed === 1 ? "" : "s"}, at most {cap} each.
                      {runLeft > 0 && (
                        <span className="text-warning"> {runLeft} will still need a mentor — select more mentors or confirm a higher cap.</span>
                      )}
                    </>
                  )}
                </p>
                <p className="mt-1 text-xs text-ink-subtle">Replaces every current mentor in this programme. Students and mentors are notified. Lock it when it is final.</p>
                </>)}
              </div>
              {isLocked ? null : (
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button variant="ghost" size="sm" className="text-danger"
                        icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
                        onClick={() => setShowResetConfirm(true)} disabled={!assignedCount || clearAllAssignments.isPending}>
                  Reset all
                </Button>
                <Button variant="accent" size="sm" loading={allocateByRollNo.isPending}
                        disabled={allocationLocked || !totalStudents || !runUsed}
                        icon={<UserCheck className="h-3.5 w-3.5" aria-hidden />}
                        onClick={handleAutoAllocate}>
                  Auto-allocate
                </Button>
                <Button variant="secondary" size="sm"
                        disabled={!totalStudents || unassignedCount > 0 || allocationChange.isPending}
                        title={unassignedCount > 0 ? "Every student needs a mentor before the allocation can be locked" : undefined}
                        icon={<Lock className="h-3.5 w-3.5" aria-hidden />}
                        onClick={() => setLockDialog("lock")}>
                  Lock
                </Button>
              </div>
              )}
            </div>
          </Card>

          {/* ── Students ──────────────────────────────────────────────── */}
          <Card>
            <div className="flex flex-col gap-3 border-b border-line px-4 py-3.5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-heading text-md font-semibold text-ink">Students</h2>
                <div role="tablist" aria-label="Filter by allocation" className="inline-flex rounded-lg bg-surface-muted p-0.5">
                  {([["ALL", "All", totalStudents], ["UNASSIGNED", "Awaiting", unassignedCount], ["ASSIGNED", "Allocated", assignedCount]] as const).map(([key, label, n]) => (
                    <button key={key} type="button" role="tab" aria-selected={assignmentTab === key}
                            onClick={() => setAssignmentTab(key)}
                            className={cn("cursor-pointer rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                              assignmentTab === key ? "bg-surface text-ink shadow-xs" : "text-ink-subtle hover:text-ink")}>
                      {label} <span className="tabular-nums text-ink-subtle">{n}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <div className="relative min-w-0 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle" aria-hidden />
                  <Input value={search} onChange={(e) => setSearch(e.target.value)} className="h-9 pl-8"
                         placeholder="Search name, roll number or organisation" aria-label="Search students" />
                </div>
                <Select aria-label="Filter by mentor" value={mentorFilter} onChange={(e) => setMentorFilter(e.target.value)} className="h-9 sm:w-56">
                  <option value="ALL">All mentors</option>
                  <option value="UNASSIGNED">No mentor</option>
                  {mentors.filter((m) => m.assigned_count > 0).map((m) => (
                    <option key={m.faculty_id} value={m.faculty_id}>{m.name} ({m.assigned_count})</option>
                  ))}
                </Select>
              </div>
              {filteredMentorName && (
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/25 bg-accent-soft/50 px-3 py-2 text-xs">
                  <Filter className="h-3.5 w-3.5 text-accent" aria-hidden />
                  <span className="text-ink">Students of <strong>{filteredMentorName}</strong></span>
                  <button type="button" onClick={() => handleClearFacultyMentees(Number(mentorFilter))}
                          className="ml-auto cursor-pointer font-semibold text-danger hover:underline">
                    Remove this mentor from all
                  </button>
                  <button type="button" onClick={() => setMentorFilter("ALL")} aria-label="Clear mentor filter"
                          className="cursor-pointer rounded p-0.5 text-ink-subtle hover:text-ink">
                    <X className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </div>
              )}
              {selectedStudentIds.size > 0 && (
                <div className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-muted px-3 py-2 text-xs">
                  <span className="font-semibold text-ink">{selectedStudentIds.size} selected</span>
                  <Button variant="ghost" size="sm" className="ml-auto h-7 text-danger"
                          icon={<Eraser className="h-3.5 w-3.5" aria-hidden />}
                          loading={clearSelectedStudents.isPending} onClick={handleClearSelectedStudents}>
                    Remove mentor
                  </Button>
                  <Button variant="ghost" size="sm" className="h-7" onClick={() => setSelectedStudentIds(new Set())}>
                    Deselect
                  </Button>
                </div>
              )}
            </div>

            {loadingData ? <LoadingState rows={6} /> : (
              <div className="max-h-[40rem] overflow-auto">
                <table className="w-full min-w-[46rem] border-collapse text-left">
                  <thead className="sticky top-0 z-10 border-b border-line bg-surface-muted">
                    <tr className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      <th scope="col" className="w-10 px-4 py-2.5">
                        <Tick checked={allVisibleSelected} indeterminate={!allVisibleSelected && someVisibleSelected}
                              onChange={toggleSelectAllStudents} label="Select every student shown" />
                      </th>
                      <th scope="col" className="px-3 py-2.5">Student</th>
                      <th scope="col" className="px-3 py-2.5">Organisation</th>
                      <th scope="col" className="w-[17rem] px-3 py-2.5">Faculty mentor</th>
                      <th scope="col" className="w-28 px-3 py-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {filteredStudents.length === 0 ? (
                      <tr><td colSpan={5} className="px-4 py-12 text-center text-sm text-ink-muted">
                        {enrollments.length === 0 ? "No students have registered yet." : "No student matches these filters."}
                      </td></tr>
                    ) : filteredStudents.map((row) => (
                      <tr key={row.id} className={cn("transition-colors", selectedStudentIds.has(row.id) ? "bg-accent-soft/40" : "hover:bg-surface-muted/50")}>
                        <td className="px-4 py-2.5">
                          <Tick checked={selectedStudentIds.has(row.id)} onChange={() => toggleSelectStudent(row.id)}
                                label={`Select ${row.student_name}`} />
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex min-w-0 items-center gap-2.5">
                            <Avatar name={row.student_name ?? undefined} size="sm" />
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium text-ink" title={row.student_name ?? undefined}>{row.student_name}</p>
                              <p className="font-mono text-2xs text-ink-subtle">{row.roll_number}</p>
                            </div>
                          </div>
                        </td>
                        <td className="max-w-[14rem] px-3 py-2.5">
                          <span className="block truncate text-xs text-ink-muted" title={row.organization_name || undefined}>
                            {row.organization_name ?? <span className="text-ink-subtle">Not recorded</span>}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <Select
                            aria-label={`Mentor for ${row.student_name}`}
                            value={String(row.mentor_faculty_id ?? "")}
                            disabled={allocationLocked || assignSingle.isPending}
                            onChange={(e) => assignSingle.mutate({ enrollmentId: row.id, mentorId: e.target.value ? Number(e.target.value) : null })}
                            className="h-8 w-full text-xs"
                          >
                            <option value="">No mentor</option>
                            {assignable.map((m) => {
                              const full = m.is_full && m.faculty_id !== row.mentor_faculty_id;
                              return (
                                <option key={m.faculty_id} value={m.faculty_id} disabled={full}>
                                  {m.name} — {m.assigned_count}/{m.max_capacity}{full ? " (full)" : ""}
                                </option>
                              );
                            })}
                          </Select>
                        </td>
                        <td className="px-3 py-2.5">
                          {row.mentor_faculty_id
                            ? <Badge tone="success">Allocated</Badge>
                            : <Badge tone="warning">Awaiting</Badge>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3 text-xs text-ink-muted">
              <span>Showing <strong className="text-ink">{filteredStudents.length}</strong> of {enrollments.length}</span>
              <span className="tabular-nums">
                <span className="font-semibold text-success">{assignedCount}</span> allocated ·{" "}
                <span className="font-semibold text-warning">{unassignedCount}</span> awaiting
              </span>
            </div>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={showResetConfirm} onClose={() => setShowResetConfirm(false)}
        onConfirm={() => clearAllAssignments.mutate()} loading={clearAllAssignments.isPending} destructive
        title="Remove every mentor allocation?"
        message={`All ${assignedCount} allocated students in ${activeProgram.code} go back to awaiting a mentor. This is recorded in the audit log.`}
        confirmLabel="Remove all"
      />
      <ConfirmDialog
        open={lockDialog !== null} onClose={() => setLockDialog(null)}
        loading={allocationChange.isPending} destructive={lockDialog === "unlock"}
        onConfirm={() => allocationChange.mutate({ method: "post", path: lockDialog === "unlock" ? "/unlock" : "/lock" })}
        title={lockDialog === "unlock" ? "Unlock the mentor allocation?" : "Lock the mentor allocation?"}
        message={lockDialog === "unlock"
          ? "Auto-allocate and Reset all become available again, and any mentor can be chosen. Unlocking is recorded in the audit log."
          : `The ${activeMentorsCount} mentors carrying students become the allocation. After this, nothing re-runs or resets it — you add, remove or replace one mentor at a time. Recorded in the audit log.`}
        confirmLabel={lockDialog === "unlock" ? "Unlock" : "Lock allocation"}
      />
    </div>
  );
}

type AllocationChange = { method: "post" | "put" | "delete"; path: string; body?: unknown };

function LockedSummary({ lockedAt, mentors, students, waiting, onUnlock }: {
  lockedAt: string; mentors: number; students: number; waiting: number; onUnlock: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 font-heading text-md font-semibold text-ink">
          Allocation locked <Badge tone="success">Final</Badge>
        </h2>
        <p className="mt-0.5 text-sm text-ink-muted">
          <strong className="text-ink">{students}</strong> students with{" "}
          <strong className="text-ink">{mentors}</strong> mentors, locked {formatDateTime(lockedAt)}.
          {waiting > 0 && <span className="text-warning"> {waiting} need a mentor — move them to one below.</span>}
        </p>
        <p className="mt-1 text-xs text-ink-subtle">
          Runs and resets are off. Add, remove or replace a mentor in the panel, or move a single student below.
        </p>
      </div>
      <Button variant="secondary" size="sm" icon={<LockOpen className="h-3.5 w-3.5" aria-hidden />}
              className="shrink-0" onClick={onUnlock}>
        Unlock
      </Button>
    </div>
  );
}

/**
 * The mentor panel once the allocation is locked: only the mentors in it, and
 * the three changes a locked allocation allows.
 */
function LockedMentorsPanel({ mentors, ranges, pending, mentorFilter, onFilter, onChange }: {
  mentors: MentorCapacity[]; ranges: Map<number, string>; pending: boolean;
  mentorFilter: string; onFilter: (value: string) => void;
  onChange: (change: AllocationChange) => void;
}) {
  const allocated = mentors.filter((m) => m.in_allocation);
  const available = mentors.filter((m) => !m.in_allocation && m.assigned_count === 0);
  const [adding, setAdding] = useState("");
  const [dialog, setDialog] = useState<{ kind: "replace" | "remove"; mentor: MentorCapacity } | null>(null);
  const [target, setTarget] = useState("");

  function open(kind: "replace" | "remove", mentor: MentorCapacity) {
    setTarget("");
    setDialog({ kind, mentor });
  }

  function confirm() {
    if (!dialog) return;
    const id = dialog.mentor.faculty_id;
    if (dialog.kind === "replace") {
      onChange({ method: "put", path: `/mentors/${id}`, body: { new_faculty_id: Number(target) } });
    } else {
      onChange({ method: "delete", path: `/mentors/${id}${target ? `?move_to=${target}` : ""}` });
    }
    setDialog(null);
  }

  return (
    <Card className="lg:sticky lg:top-20">
      <PanelHeader title="Allocated mentors" meta={<Badge tone="success">{allocated.length} in the allocation</Badge>}>
        <p className="mt-1 text-xs text-ink-muted">Only these mentors can hold students while the allocation is locked.</p>
        <div className="mt-3 flex gap-2">
          <Select aria-label="Mentor to add" value={adding} onChange={(e) => setAdding(e.target.value)}
                  className="h-9 min-w-0 flex-1 text-xs">
            <option value="">{available.length ? "Add a mentor…" : "No other eligible mentors"}</option>
            {available.map((m) => <option key={m.faculty_id} value={m.faculty_id}>{m.name}</option>)}
          </Select>
          <Button variant="secondary" size="sm" disabled={!adding || pending}
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                  onClick={() => { onChange({ method: "post", path: "/mentors", body: { faculty_id: Number(adding) } }); setAdding(""); }}>
            Add
          </Button>
        </div>
      </PanelHeader>
      {allocated.length === 0 ? <EmptyState compact title="No mentors in the allocation" /> : (
        <ul className="max-h-[34rem] divide-y divide-line overflow-y-auto">
          {allocated.map((m) => {
            const filtering = mentorFilter === String(m.faculty_id);
            return (
              <li key={m.faculty_id} className="px-4 py-3">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate text-sm font-semibold text-ink" title={m.name}>{m.name}</p>
                  <span className={cn("shrink-0 font-mono text-xs tabular-nums", m.is_full ? "font-semibold text-warning" : "text-ink-muted")}>
                    {m.assigned_count}/{m.max_capacity}
                  </span>
                </div>
                <p className="truncate text-xs text-ink-subtle">{[m.designation, m.department_code].filter(Boolean).join(" · ")}</p>
                <div className="mt-1.5"><LoadBar count={m.assigned_count} cap={m.max_capacity} /></div>
                <p className="mt-1.5 truncate font-mono text-2xs text-ink-subtle">{ranges.get(m.faculty_id) ?? "No students yet"}</p>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs font-semibold">
                  {m.assigned_count > 0 && (
                    <button type="button" onClick={() => onFilter(filtering ? "ALL" : String(m.faculty_id))}
                            className={cn("cursor-pointer hover:underline", filtering ? "text-ink" : "text-accent")}>
                      {filtering ? "Showing" : "View students"}
                    </button>
                  )}
                  <button type="button" disabled={pending} onClick={() => open("replace", m)}
                          className="inline-flex cursor-pointer items-center gap-1 text-accent hover:underline disabled:text-ink-subtle">
                    <Repeat2 className="h-3 w-3" aria-hidden />Replace
                  </button>
                  <button type="button" disabled={pending} onClick={() => open("remove", m)}
                          className="inline-flex cursor-pointer items-center gap-1 text-danger hover:underline disabled:text-ink-subtle">
                    <Trash2 className="h-3 w-3" aria-hidden />Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Modal
        open={dialog !== null} onClose={() => setDialog(null)} size="sm"
        title={dialog?.kind === "replace" ? `Replace ${dialog.mentor.name}` : `Remove ${dialog?.mentor.name ?? ""}`}
        description={dialog?.kind === "replace"
          ? `All ${dialog.mentor.assigned_count} of their students move to the new mentor. Everyone affected is notified.`
          : `Choose where their ${dialog?.mentor.assigned_count ?? 0} students go. Everyone affected is notified.`}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant={dialog?.kind === "remove" ? "danger" : "primary"} size="sm"
                    disabled={dialog?.kind === "replace" && !target} onClick={confirm}>
              {dialog?.kind === "replace" ? "Replace mentor" : "Remove mentor"}
            </Button>
          </>
        }
      >
        {dialog?.kind === "replace" ? (
          <Select aria-label="New mentor" value={target} onChange={(e) => setTarget(e.target.value)} className="w-full">
            <option value="">Choose the new mentor…</option>
            {available.map((m) => <option key={m.faculty_id} value={m.faculty_id}>{m.name}</option>)}
          </Select>
        ) : dialog ? (
          <Select aria-label="Move their students to" value={target} onChange={(e) => setTarget(e.target.value)} className="w-full">
            <option value="">Leave them waiting for a mentor</option>
            {allocated.filter((m) => m.faculty_id !== dialog.mentor.faculty_id).map((m) => {
              const over = m.assigned_count + dialog.mentor.assigned_count > m.max_capacity;
              return (
                <option key={m.faculty_id} value={m.faculty_id} disabled={over}>
                  Move to {m.name} — {m.assigned_count}/{m.max_capacity}{over ? " (not enough room)" : ""}
                </option>
              );
            })}
          </Select>
        ) : null}
      </Modal>
    </Card>
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
