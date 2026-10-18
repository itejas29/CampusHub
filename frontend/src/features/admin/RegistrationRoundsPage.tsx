import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3, BookOpen, CalendarClock, CheckCheck, Download, Undo2, Eye, ListChecks, Lock, Pencil, Play,
  Plus, RotateCcw, Trash2, Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Checkbox, FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { ApiError, api, downloadProtectedFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { pluralise, roman } from "@/lib/utils";
import type {
  AllocationRunResult, AllocationStrategy, ComponentType, FinaliseResult, InterestTally,
  RegistrationWindow, RoundSelectionMode, RoundSlot, Subject,
} from "@/types";

const FAMILY_LABEL: Record<string, string> = {
  OPEN_ELECTIVE: "Open Elective",
  PROGRAM_CORE_ELECTIVE: "Core Elective",
};

/** `datetime-local` wants local wall-clock time without a zone. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/** Who a round is for, in the coordinator's words. */
function audience(round: RegistrationWindow): string {
  if (round.eligible_semesters.length === 0) return "—";
  const semesters = round.eligible_semesters.map((n) => `Sem ${roman(n)}`).join(", ");
  const ahead = round.slot_semester != null
    && round.eligible_semesters.every((n) => n < round.slot_semester!);
  return ahead ? `${semesters} · choosing ahead` : semesters;
}

type Action = "OPEN" | "LOCKED" | "ALLOCATED" | "PUBLISHED" | "REOPEN" | "DELETE" | "UNDO";

/** Until allocation has run nobody holds a seat from a round, so it can go. */
const DELETABLE = new Set(["DRAFT", "OPEN", "LOCKED"]);

/**
 * Where a coordinator runs choice filling: which students, for which elective,
 * from when until when. The Head of Department sees the same table with nothing
 * to press — the server decides that (`can_manage`), not this screen.
 */
export function RegistrationRoundsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isHod = Boolean(user?.faculty?.hod_department_id);
  const [family, setFamily] = useState("ALL");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<RegistrationWindow | null>(null);
  const [deadlineFor, setDeadlineFor] = useState<RegistrationWindow | null>(null);
  const [allocateFor, setAllocateFor] = useState<RegistrationWindow | null>(null);
  const [shortlistFor, setShortlistFor] = useState<RegistrationWindow | null>(null);
  const [votesFor, setVotesFor] = useState<RegistrationWindow | null>(null);
  const [finaliseFor, setFinaliseFor] = useState<RegistrationWindow | null>(null);
  const [subjectsOpen, setSubjectsOpen] = useState(false);
  const [confirm, setConfirm] = useState<{ round: RegistrationWindow; action: Action } | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const rounds = useQuery({
    queryKey: ["registration-rounds"],
    queryFn: () => api.get<RegistrationWindow[]>("/electives/admin/windows"),
  });
  // The slots a round can be built from. A Head of Department runs no rounds,
  // so they are not asked for (and would be refused).
  const slots = useQuery({
    queryKey: ["round-slots"],
    queryFn: () => api.get<RoundSlot[]>("/electives/admin/slots"),
    enabled: !isHod,
  });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["registration-rounds"] });
    void queryClient.invalidateQueries({ queryKey: ["round-slots"] });
  }

  const remove = useMutation({
    mutationFn: (round: RegistrationWindow) =>
      api.delete<{ message: string }>(`/electives/admin/windows/${round.id}`),
    onSuccess: (result) => {
      setConfirm(null);
      setBanner({ tone: "success", text: result.message });
      refresh();
    },
    onError: (err) => {
      setConfirm(null);
      setBanner({ tone: "danger", text: errorText(err, "Could not delete the round.") });
    },
  });

  // Takes back an unpublished run; the round returns to Locked to run again.
  const undo = useMutation({
    mutationFn: (round: RegistrationWindow) =>
      api.post<RegistrationWindow>(`/electives/admin/windows/${round.id}/undo-allocation`),
    onSuccess: (round) => {
      setConfirm(null);
      setBanner({ tone: "success", text: `Allocation undone for ${round.title}. The round is locked again — run it when ready.` });
      refresh();
    },
    onError: (err) => {
      setConfirm(null);
      setBanner({ tone: "danger", text: errorText(err, "Could not undo the allocation.") });
    },
  });

  const move = useMutation({
    mutationFn: async ({ round, action }: { round: RegistrationWindow; action: Action }) => {
      return api.post<RegistrationWindow>(
        `/electives/admin/windows/${round.id}/status?target=${action === "REOPEN" ? "OPEN" : action}`,
      );
    },
    onSuccess: (round, { action }) => {
      setConfirm(null);
      const told = pluralise(round.eligible_student_count, "student");
      setBanner({
        tone: "success",
        text: action === "LOCKED"
          ? `${round.title} is locked. Preferences are frozen.`
          : action === "ALLOCATED"
          ? `Allocation complete for ${round.title}. Review the results, then publish to notify students.`
          : action === "PUBLISHED"
          ? `Results published for ${round.title}. ${told} notified.`
          : `${round.title} is open. ${told} notified.`,
      });
      refresh();
    },
    onError: (err) => {
      setConfirm(null);
      setBanner({ tone: "danger", text: errorText(err, "Could not update the round.") });
    },
  });

  const families = useMemo(
    () => [...new Set((rounds.data ?? []).map((r) => r.component_type))],
    [rounds.data],
  );
  const visible = (rounds.data ?? []).filter(
    (r) => family === "ALL" || r.component_type === family,
  );
  const canCreate = !isHod && (slots.data?.length ?? 0) > 0;

  return (
    <div>
      <PageHeader
        title="Registration rounds"
        description={
          isHod
            ? "Every elective registration round in your department. Rounds are opened, extended and locked by the coordinator you appointed; you can see them here but not change them."
            : "A round decides which students may fill their elective choices, and from when until when. Open one mid-way through the semester before the elective so the timetable can be built over the vacation. The deadline is enforced by the server."
        }
        breadcrumbs={[{ label: "Administration" }, { label: "Registration Rounds" }]}
        actions={
          canCreate && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={() => setSubjectsOpen(true)}
                      icon={<BookOpen className="h-3.5 w-3.5" aria-hidden />}>
                Subjects
              </Button>
              <Button size="sm" onClick={() => setFormOpen(true)}
                      icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
                New round
              </Button>
            </div>
          )
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {families.length > 1 && (
        <Tabs
          tabs={[
            { key: "ALL", label: "All", count: rounds.data?.length },
            ...families.map((key) => ({
              key, label: `${FAMILY_LABEL[key] ?? key}s`,
              count: rounds.data?.filter((r) => r.component_type === key).length,
            })),
          ]}
          active={family}
          onChange={setFamily}
          className="mb-5"
        />
      )}

      <Card>
        <CardHeader
          title={pluralise(visible.length, "round")}
          description="Draft → Open → Locked → Allocated → Published. Run allocation once preferences are in, then publish to release results to students."
          icon={<CalendarClock className="h-4 w-4 text-ink-subtle" aria-hidden />}
        />
        {rounds.isLoading ? (
          <LoadingState rows={4} />
        ) : rounds.error ? (
          <ErrorState onRetry={() => rounds.refetch()} compact />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No rounds yet"
            description={
              isHod
                ? "Rounds appear here once a coordinator creates one."
                : "Create a round to let students start filling their choices."
            }
            icon={<CalendarClock className="h-5 w-5" aria-hidden />}
          />
        ) : (
          <TableWrap>
            <THead>
              <TH width="27%">Round</TH>
              <TH width="15%">For students in</TH>
              <TH width="15%">Opens</TH>
              <TH width="15%">Closes</TH>
              <TH width="10%" align="right">Submitted</TH>
              <TH width="8%">Status</TH>
              <TH align="right">Actions</TH>
            </THead>
            <TBody>
              {visible.map((round) => (
                <TR key={round.id}>
                  <TD>
                    <p className="font-medium text-ink">{round.title}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-2xs text-ink-subtle">
                      <Badge tone="brand">{FAMILY_LABEL[round.component_type] ?? round.component_type}</Badge>
                      {round.selection_mode === "TWO_STAGE" && (
                        <Badge tone="accent">
                          {round.stage === "FINAL" ? "Final round" : "Interest round"}
                        </Badge>
                      )}
                      {round.slot_semester != null && (
                        <span>Semester {roman(round.slot_semester)} slot</span>
                      )}
                      <span>· {pluralise(round.offering_count, "course")}</span>
                    </p>
                  </TD>
                  <TD className="text-xs text-ink-muted">{audience(round)}</TD>
                  <TD className="text-xs text-ink-muted">{formatDateTime(round.opens_at)}</TD>
                  <TD className="text-xs">
                    <span className={round.is_past_deadline && round.status === "OPEN"
                      ? "text-danger" : "text-ink-muted"}>
                      {formatDateTime(round.closes_at)}
                    </span>
                    {round.is_past_deadline && round.status === "OPEN" && (
                      <span className="block text-2xs text-danger">Deadline passed</span>
                    )}
                  </TD>
                  <TD align="right" className="tabular">
                    {round.submitted_student_count}
                    <span className="text-ink-subtle"> / {round.eligible_student_count}</span>
                  </TD>
                  <TD><StatusBadge status={round.status} /></TD>
                  <TD align="right">
                    {!round.can_manage ? (
                      <span className="inline-flex items-center gap-1 text-2xs text-ink-subtle">
                        <Eye className="h-3 w-3" aria-hidden /> View only
                      </span>
                    ) : (
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {round.status === "DRAFT" && (
                          <>
                            <Button size="sm" variant="secondary"
                                    onClick={() => setEditing(round)}
                                    icon={<Pencil className="h-3.5 w-3.5" aria-hidden />}>
                              Edit
                            </Button>
                            <Button size="sm"
                                    onClick={() => setConfirm({ round, action: "OPEN" })}
                                    icon={<Play className="h-3.5 w-3.5" aria-hidden />}>
                              Open
                            </Button>
                          </>
                        )}
                        {round.status === "OPEN" && (
                          <>
                            <Button size="sm" variant="secondary"
                                    onClick={() => setDeadlineFor(round)}
                                    icon={<CalendarClock className="h-3.5 w-3.5" aria-hidden />}>
                              Change deadline
                            </Button>
                            <Button size="sm" variant="secondary"
                                    onClick={() => setConfirm({ round, action: "LOCKED" })}
                                    icon={<Lock className="h-3.5 w-3.5" aria-hidden />}>
                              Lock
                            </Button>
                          </>
                        )}
                        {round.selection_mode === "TWO_STAGE" && round.stage === "INTEREST"
                          && round.status === "OPEN" && (
                          <Button size="sm" variant="secondary"
                                  onClick={() => setVotesFor(round)}
                                  icon={<BarChart3 className="h-3.5 w-3.5" aria-hidden />}>
                            Votes
                          </Button>
                        )}
                        {round.status === "LOCKED" && round.selection_mode === "TWO_STAGE" && (
                          <>
                            <Button size="sm" variant="secondary"
                                    onClick={() => setDeadlineFor(round)}
                                    icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>
                              Reopen
                            </Button>
                            {round.stage === "INTEREST" ? (
                              <Button size="sm" onClick={() => setShortlistFor(round)}
                                      icon={<ListChecks className="h-3.5 w-3.5" aria-hidden />}>
                                Shortlist
                              </Button>
                            ) : (
                              <Button size="sm" onClick={() => setFinaliseFor(round)}
                                      icon={<Zap className="h-3.5 w-3.5" aria-hidden />}>
                                Finalise
                              </Button>
                            )}
                          </>
                        )}
                        {round.status === "LOCKED" && round.selection_mode !== "TWO_STAGE" && (
                          <>
                            <Button size="sm" variant="secondary"
                                    onClick={() => setDeadlineFor(round)}
                                    icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>
                              Reopen
                            </Button>
                            <Button size="sm"
                                    onClick={() => setAllocateFor(round)}
                                    icon={<Zap className="h-3.5 w-3.5" aria-hidden />}>
                              Run allocation
                            </Button>
                          </>
                        )}
                        {(round.status === "ALLOCATED" || round.status === "PUBLISHED") && round.slots.length > 0 && (
                          <Button size="sm" variant="secondary"
                                  onClick={() => {
                                    const slot = round.slots[0];
                                    if (slot) {
                                      void downloadProtectedFile(`/electives/admin/allocations/export?component_id=${slot.id}`);
                                    }
                                  }}
                                  icon={<Download className="h-3.5 w-3.5" aria-hidden />}>
                            Export CSV
                          </Button>
                        )}
                        {round.status === "ALLOCATED" && (
                          <Button size="sm" variant="ghost"
                                  onClick={() => setConfirm({ round, action: "UNDO" })}
                                  icon={<Undo2 className="h-3.5 w-3.5" aria-hidden />}>
                            Undo allocation
                          </Button>
                        )}
                        {round.status === "ALLOCATED" && (
                          <Button size="sm"
                                  onClick={() => setConfirm({ round, action: "PUBLISHED" })}
                                  icon={<CheckCheck className="h-3.5 w-3.5" aria-hidden />}>
                            Publish results
                          </Button>
                        )}
                        {DELETABLE.has(round.status) && (
                          <Button size="sm" variant="ghost"
                                  onClick={() => setConfirm({ round, action: "DELETE" })}
                                  aria-label={`Delete ${round.title}`}
                                  icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}>
                            Delete
                          </Button>
                        )}
                      </div>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </TableWrap>
        )}
      </Card>

      {(formOpen || editing) && (
        <RoundFormModal
          slots={slots.data ?? []}
          round={editing}
          onClose={() => { setFormOpen(false); setEditing(null); }}
          onDone={(text) => {
            setFormOpen(false);
            setEditing(null);
            setBanner({ tone: "success", text });
            refresh();
          }}
        />
      )}

      {deadlineFor && (
        <DeadlineModal
          round={deadlineFor}
          onClose={() => setDeadlineFor(null)}
          onDone={(text) => {
            setDeadlineFor(null);
            setBanner({ tone: "success", text });
            refresh();
          }}
        />
      )}

      {(shortlistFor || votesFor) && (
        <ShortlistModal
          round={(shortlistFor ?? votesFor)!}
          readOnly={!shortlistFor}
          onClose={() => { setShortlistFor(null); setVotesFor(null); }}
          onDone={(text) => {
            setShortlistFor(null);
            setBanner({ tone: "success", text });
            refresh();
          }}
        />
      )}

      {finaliseFor && (
        <FinaliseModal
          round={finaliseFor}
          onClose={() => setFinaliseFor(null)}
          onDone={(text) => {
            setFinaliseFor(null);
            setBanner({ tone: "success", text });
            refresh();
          }}
        />
      )}

      {subjectsOpen && (
        <SubjectsModal slots={slots.data ?? []} onClose={() => { setSubjectsOpen(false); refresh(); }} />
      )}

      {allocateFor && (
        <AllocateModal
          round={allocateFor}
          onClose={() => setAllocateFor(null)}
          onDone={(text) => {
            setAllocateFor(null);
            setBanner({ tone: "success", text });
            refresh();
          }}
        />
      )}

      {confirm && (
        <ConfirmDialog
          open
          onClose={() => setConfirm(null)}
          onConfirm={() => (confirm.action === "DELETE" ? remove.mutate(confirm.round)
            : confirm.action === "UNDO" ? undo.mutate(confirm.round) : move.mutate(confirm))}
          loading={move.isPending || remove.isPending || undo.isPending}
          destructive={confirm.action === "DELETE" || confirm.action === "UNDO"}
          title={
            confirm.action === "UNDO" ? "Undo this allocation?"
            : confirm.action === "DELETE" ? "Delete this round?"
            : confirm.action === "LOCKED" ? "Lock this round?"
            : confirm.action === "ALLOCATED" ? "Run allocation?"
            : confirm.action === "PUBLISHED" ? "Publish results?"
            : "Open this round?"
          }
          confirmLabel={
            confirm.action === "UNDO" ? "Undo allocation"
            : confirm.action === "DELETE" ? "Delete round"
            : confirm.action === "LOCKED" ? "Lock round"
            : confirm.action === "ALLOCATED" ? "Run allocation"
            : confirm.action === "PUBLISHED" ? "Publish results"
            : "Open round"
          }
          message={
            confirm.action === "UNDO" ? (
              <>
                Every seat this run gave in <strong>{confirm.round.title}</strong> is removed and
                the class sections it formed are cleared. The round goes back to{" "}
                <strong>Locked</strong> with everyone's choices intact, so you can run it again.
                Students were never told, so nobody is notified. Recorded in the audit log.
              </>
            ) : confirm.action === "DELETE" ? (
              <>
                <strong>{confirm.round.title}</strong> will be removed and its{" "}
                {pluralise(confirm.round.offering_count, "course")} freed for a new round.
                {confirm.round.status === "DRAFT" ? (
                  " Students have not seen it yet."
                ) : (
                  <>
                    {" "}The {confirm.round.submitted_student_count} choice list(s) filled
                    in it are deleted, and{" "}
                    {pluralise(confirm.round.eligible_student_count, "student")} are told
                    it was withdrawn.
                  </>
                )}{" "}
                <strong>This cannot be undone.</strong>
              </>
            ) : confirm.action === "LOCKED" ? (
              <>
                Choice filling stops now for{" "}
                {pluralise(confirm.round.eligible_student_count, "student")}.{" "}
                {confirm.round.submitted_student_count} have submitted. You can reopen
                the round later if needed.
              </>
            ) : confirm.action === "ALLOCATED" ? (
              <>
                Allocation will run against the{" "}
                {confirm.round.submitted_student_count} submitted preference lists.
                Students are <strong>not notified</strong> until you publish the results.
                You can review and adjust the allocation before publishing.
              </>
            ) : confirm.action === "PUBLISHED" ? (
              <>
                Results will be sent to all{" "}
                {pluralise(confirm.round.eligible_student_count, "student")}.
                Students with a seat will see their course; those without a seat
                will be told to contact the coordinator. <strong>This cannot be undone.</strong>
              </>
            ) : (
              <>
                {pluralise(confirm.round.eligible_student_count, "student")} ({audience(confirm.round)})
                will be notified and can fill their choices until{" "}
                <strong>{formatDateTime(confirm.round.closes_at)}</strong>.
              </>
            )
          }
        />
      )}
    </div>
  );
}

/** Create a round, or edit one that is still a draft. */
function RoundFormModal({
  slots, round, onClose, onDone,
}: {
  slots: RoundSlot[]; round: RegistrationWindow | null;
  onClose: () => void; onDone: (text: string) => void;
}) {
  const editingSlotId = round?.slots[0]?.id;
  // A course can be in one round at a time, so a slot is only worth offering
  // while it still has a course that is in none. Start on the first that does.
  // Counted as subjects: the same course offered again next year is one subject.
  const freeCourses = (s: RoundSlot) => new Set(
    s.offerings.filter((o) => o.registration_window_id === null).map((o) => o.course_code)).size;
  const [slotId, setSlotId] = useState(
    String(editingSlotId
      ?? (slots.find((s) => freeCourses(s) > 0) ?? slots[0])?.component_id ?? ""),
  );
  const slot = slots.find((s) => String(s.component_id) === slotId);

  const [title, setTitle] = useState(round?.title ?? "");
  const [semester, setSemester] = useState<number | null>(
    round?.eligible_semesters[0] ?? null,
  );
  const [opensAt, setOpensAt] = useState(
    toLocalInput(round?.opens_at ?? new Date().toISOString()),
  );
  const [closesAt, setClosesAt] = useState(toLocalInput(round?.closes_at ?? null));
  const [minPrefs, setMinPrefs] = useState(String(round?.min_preferences ?? 3));
  const [maxPrefs, setMaxPrefs] = useState(String(round?.max_preferences ?? 5));
  const [divisions, setDivisions] = useState<string[]>(round?.eligible_divisions ?? []);
  const [notes, setNotes] = useState(round?.notes ?? "");
  const [picked, setPicked] = useState<number[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // How students choose, and the coordinator's own numbers for this round.
  const [mode, setMode] = useState<RoundSelectionMode>(round?.selection_mode ?? "RANKED");
  const [interestCount, setInterestCount] = useState(String(round?.interest_pick_count ?? ""));
  const [minRun, setMinRun] = useState(String(round?.min_students_to_run ?? ""));
  const [sectionCap, setSectionCap] = useState(String(round?.section_capacity ?? ""));
  const twoStage = mode === "TWO_STAGE";
  // Set once the slots are known: the curriculum's count, unless edited.
  const [countTouched, setCountTouched] = useState(Boolean(round?.interest_pick_count));

  // The other slots of the same semester and family — Program Elective 4 and 5
  // are chosen together in one two-stage round.
  const siblings = slot ? slots.filter((s) => s.component_id !== slot.component_id
    && s.curriculum_id === slot.curriculum_id && s.semester_number === slot.semester_number
    && s.component_type === slot.component_type) : [];
  const [alsoSlots, setAlsoSlots] = useState<number[] | null>(
    round ? round.slots.slice(1).map((s) => s.id) : null,
  );
  const extraSlots = twoStage
    ? (alsoSlots ?? siblings.map((s) => s.component_id))
        .filter((id) => siblings.some((s) => s.component_id === id))
    : [];
  const included = slot
    ? [slot, ...siblings.filter((s) => extraSlots.includes(s.component_id))] : [];
  const curriculumCount = Math.max(1, included.length);
  // Until the coordinator types a number, follow the curriculum's.
  useEffect(() => {
    if (twoStage && !countTouched) setInterestCount(String(curriculumCount));
  }, [twoStage, countTouched, curriculumCount]);

  // A course can be in one round at a time, so only free ones — and the ones
  // already in this round — are offered.
  const all = included.flatMap((s) => s.offerings.map((o) => ({ ...o, slot_code: s.code })));
  const available = all.filter(
    (o) => o.registration_window_id === null || o.registration_window_id === round?.id,
  );
  const taken = all.length - available.length;
  // The coordinator chooses subjects, not offerings. One subject is offered
  // once in every slot (PE2 and PE3 share a basket) and again every year, but
  // it is still one subject: one row. Ticking it attaches, in each slot of the
  // round, the offering meant for this round — the one already in it, else the
  // newest year's that no earlier cohort holds seats in.
  const rank = (o: (typeof available)[number]) => [
    o.registration_window_id === round?.id && round ? 1 : 0,
    o.seats_taken === 0 ? 1 : 0,
    o.academic_year ?? "",
  ] as const;
  const better = (x: (typeof available)[number], y: (typeof available)[number]) => {
    const [a1, b1, c1] = rank(x);
    const [a2, b2, c2] = rank(y);
    return a1 !== a2 ? a1 > a2 : b1 !== b2 ? b1 > b2 : c1 > c2;
  };
  const subjects_ = Object.values(available.reduce<Record<string, {
    key: string; code: string; title: string; department: string | null;
    perSlot: Record<string, (typeof available)[number]>;
  }>>((groups, o) => {
    const group = groups[o.course_code] ??= { key: o.course_code, code: o.course_code,
      title: o.course_title, department: o.department_code, perSlot: {} };
    const current = group.perSlot[o.slot_code];
    if (!current || better(o, current)) group.perSlot[o.slot_code] = o;
    return groups;
  }, {})).map((g) => {
    const chosen = Object.values(g.perSlot);
    return { ...g, ids: chosen.map((o) => o.id),
      seated: chosen.reduce((n, o) => n + o.seats_taken, 0) };
  });
  const subjects = subjects_;
  const chosenCourses = picked ?? (
    round ? available.filter((o) => o.registration_window_id === round.id).map((o) => o.id)
          : subjects.filter((g) => g.seated === 0).flatMap((g) => g.ids)
  );

  // Choosing ahead — the semester before the slot — is the normal case.
  const chosenSemester = semester ?? (slot ? slot.semester_number - 1 : null);
  const defaultTitle = slot && chosenSemester != null
    ? `${included.length > 1 ? included.map((s) => s.title).join(" & ") : slot.title}`
      + ` — choice filling for Semester ${roman(slot.semester_number)}`
    : "";

  function pickSlot(value: string) {
    setSlotId(value);
    setSemester(null);
    setPicked(null);
    setDivisions([]);
    setAlsoSlots(null);
  }

  const asNumber = (value: string) => (value.trim() === "" ? null : Number(value) || null);

  const save = useMutation({
    mutationFn: async () => {
      if (!slot || chosenSemester == null) throw new Error("Choose an elective slot.");
      const body = {
        title: title.trim() || defaultTitle,
        opens_at: fromLocalInput(opensAt),
        closes_at: fromLocalInput(closesAt),
        eligible_semesters: [chosenSemester],
        eligible_program_ids: [slot.program_id],
        eligible_divisions: divisions,
        min_preferences: twoStage ? null : Number(minPrefs) || null,
        max_preferences: twoStage ? null : Number(maxPrefs) || null,
        notes: notes.trim() || null,
        selection_mode: mode,
        interest_pick_count: twoStage ? asNumber(interestCount) : null,
        min_students_to_run: asNumber(minRun),
        section_capacity: slot?.component_type === "OPEN_ELECTIVE" ? asNumber(sectionCap) : null,
      };
      const saved = round
        ? await api.patch<RegistrationWindow>(`/electives/admin/windows/${round.id}`, body)
        : await api.post<RegistrationWindow>("/electives/admin/windows", {
            ...body,
            // Unique per round; the coordinator never has to think about it.
            code: `${slot.code}-S${chosenSemester}-${Date.now().toString(36).toUpperCase()}`,
            component_type: slot.component_type as ComponentType,
            department_id: slot.department_id,
          });
      return api.post<RegistrationWindow>(
        `/electives/admin/windows/${saved.id}/offerings`, { offering_ids: chosenCourses },
      );
    },
    onSuccess: (saved) =>
      onDone(round
        ? `${saved.title} updated.`
        : `${saved.title} saved as a draft. Open it when you are ready for students to start.`),
    onError: (err) => setError(errorText(err, err instanceof Error ? err.message : "Could not save the round.")),
  });

  const ready = Boolean(slot) && Boolean(closesAt) && chosenCourses.length > 0
    && (!twoStage || Boolean(asNumber(interestCount)));

  return (
    <Modal
      open onClose={onClose} size="lg"
      title={round ? "Edit round" : "New registration round"}
      description="Saved as a draft. Nothing reaches students until you open it."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={!ready} loading={save.isPending}
                  onClick={() => save.mutate()}>
            {round ? "Save changes" : "Save draft"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <FormField label="Elective slot" required
                   hint="The slot in the curriculum that these students will fill.">
          <Select value={slotId} onChange={(e) => pickSlot(e.target.value)}
                  disabled={Boolean(round)} data-autofocus>
            {slots.length === 0 && <option value="">No slots available</option>}
            {slots.map((s) => {
              const free = freeCourses(s);
              const usable = free > 0 || s.component_id === editingSlotId;
              return (
                <option key={s.component_id} value={s.component_id} disabled={!usable}>
                  {s.title} — Semester {roman(s.semester_number)} · {s.curriculum_version} scheme
                  {" "}({s.offerings.length === 0 ? "no courses on offer yet"
                    : free === 0 ? "all courses already in a round"
                    : `${pluralise(free, "subject")} available`})
                </option>
              );
            })}
          </Select>
        </FormField>

        {slot && (
          <FormField label="Open it to students currently in" required
                     hint="Choosing ahead lets the timetable be built before the semester starts.">
            <Select value={String(chosenSemester)}
                    onChange={(e) => setSemester(Number(e.target.value))}>
              {slot.semester_number > 1 && (
                <option value={slot.semester_number - 1}>
                  Semester {roman(slot.semester_number - 1)} — choosing ahead for Semester {roman(slot.semester_number)}
                </option>
              )}
              <option value={slot.semester_number}>
                Semester {roman(slot.semester_number)} — already in the semester
              </option>
            </Select>
          </FormField>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Choice filling starts" hint="Blank means as soon as you open it.">
            <Input type="datetime-local" value={opensAt}
                   onChange={(e) => setOpensAt(e.target.value)} />
          </FormField>
          <FormField label="Deadline" required hint="Enforced by the server.">
            <Input type="datetime-local" value={closesAt}
                   onChange={(e) => setClosesAt(e.target.value)} />
          </FormField>
        </div>

        <FormField label="How students choose" required
                   hint={twoStage
                     ? "Students first tick subjects they are interested in. You then shortlist from the votes and open a final round, in which each student ticks the subjects they will take."
                     : "Students rank the courses; an allocation rule seats them."}>
          <Select value={mode} disabled={Boolean(round) && round?.status !== "DRAFT"}
                  onChange={(e) => setMode(e.target.value as RoundSelectionMode)}>
            <option value="RANKED">Final choice only — students rank the courses</option>
            <option value="TWO_STAGE">Interest round first — then shortlist and a final round</option>
          </Select>
        </FormField>

        {twoStage && siblings.length > 0 && (
          <FormField label={`Electives this round fills (${included.length})`}
                     hint={`Semester ${roman(slot?.semester_number ?? 0)} has ${pluralise(siblings.length + 1, "elective")} in the curriculum. `
                       + `Each student takes one subject for each one ticked here — ${pluralise(included.length, "subject")} each. `
                       + "Untick one to run it as a separate round."}>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              <Checkbox label={slot?.title ?? ""} checked disabled />
              {siblings.map((s) => (
                <Checkbox key={s.component_id} label={s.title}
                          checked={extraSlots.includes(s.component_id)}
                          onChange={(e) => {
                            setPicked(null);
                            setAlsoSlots(e.target.checked
                              ? [...extraSlots, s.component_id]
                              : extraSlots.filter((id) => id !== s.component_id));
                          }} />
              ))}
            </div>
          </FormField>
        )}

        {twoStage ? (
          <FormField label="Subjects each student ticks in the interest round" required
                     hint={Number(interestCount) === curriculumCount
                       ? `Matches the curriculum: Semester ${roman(slot?.semester_number ?? 0)} has ${pluralise(curriculumCount, "elective")} in this round.`
                       : "Exactly this many. You set the final round's number when you shortlist."}>
            <div className="flex flex-wrap items-center gap-2">
              <Input type="number" min={1} max={20} value={interestCount} className="w-28"
                     onChange={(e) => { setCountTouched(true); setInterestCount(e.target.value); }} />
              {Number(interestCount) !== curriculumCount && (
                <Alert variant="info" className="flex-1">
                  The curriculum has {pluralise(curriculumCount, "elective")} in this round
                  ({included.map((s) => s.code).join(", ")}), so each student chooses{" "}
                  {curriculumCount}.{" "}
                  <Button size="sm" variant="secondary"
                          onClick={() => setInterestCount(String(curriculumCount))}>
                    Use {curriculumCount}
                  </Button>
                </Alert>
              )}
            </div>
          </FormField>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Minimum preferences">
              <Input type="number" min={1} max={20} value={minPrefs}
                     onChange={(e) => setMinPrefs(e.target.value)} />
            </FormField>
            <FormField label="Maximum preferences">
              <Input type="number" min={1} max={20} value={maxPrefs}
                     onChange={(e) => setMaxPrefs(e.target.value)} />
            </FormField>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Minimum students for a subject to run"
                     hint="Your rule for this round. Leave blank to keep each course's own.">
            <Input type="number" min={1} value={minRun} placeholder="e.g. 48"
                   onChange={(e) => setMinRun(e.target.value)} />
          </FormField>
          {slot?.component_type === "OPEN_ELECTIVE" && (
            <FormField label="Students per section"
                       hint="Demand above this opens another section. Blank keeps the course's own.">
              <Input type="number" min={1} value={sectionCap} placeholder="e.g. 75"
                     onChange={(e) => setSectionCap(e.target.value)} />
            </FormField>
          )}
        </div>

        {slot && slot.divisions.length > 0 && (
          <FormField label="Divisions" hint="Leave all unticked to include every division.">
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {slot.divisions.map((name) => (
                <Checkbox
                  key={name} label={`Division ${name}`}
                  checked={divisions.includes(name)}
                  onChange={(e) => setDivisions(e.target.checked
                    ? [...divisions, name] : divisions.filter((d) => d !== name))}
                />
              ))}
            </div>
          </FormField>
        )}

        {slot && (
          <FormField
            label={`Subjects students choose from (${subjects.filter((g) =>
              g.ids.every((id) => chosenCourses.includes(id))).length} of ${subjects.length})`}
            required
            hint={taken > 0
              ? `${pluralise(taken, "course")} of this slot ${taken === 1 ? "is" : "are"} already in another round and cannot be added here.`
              : undefined}
          >
            {available.length === 0 ? (
              <Alert variant="warning">
                Every course on offer for this slot is already in another round.
              </Alert>
            ) : (
              <div className="max-h-48 space-y-2 overflow-y-auto rounded border border-line p-3">
                {subjects.map((subject) => (
                  <Checkbox
                    key={subject.key}
                    label={`${subject.code} · ${subject.title}`}
                    description={[subject.department,
                      subject.seated ? `${subject.seated} already seated` : null,
                    ].filter(Boolean).join(" · ") || undefined}
                    checked={subject.ids.every((id) => chosenCourses.includes(id))}
                    onChange={(e) => setPicked(e.target.checked
                      ? [...new Set([...chosenCourses, ...subject.ids])]
                      : chosenCourses.filter((id) => !subject.ids.includes(id)))}
                  />
                ))}
              </div>
            )}
          </FormField>
        )}

        <FormField label="Title" hint="Shown to students. Leave blank to use the suggestion.">
          <Input value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder={defaultTitle} />
        </FormField>

        <FormField label="Notes" hint="For you and the Head of Department; students do not see this.">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </FormField>
      </div>
    </Modal>
  );
}

/** Move the deadline of a live round, or reopen a locked one with a new one. */
function DeadlineModal({
  round, onClose, onDone,
}: {
  round: RegistrationWindow; onClose: () => void; onDone: (text: string) => void;
}) {
  const reopening = round.status === "LOCKED";
  const [closesAt, setClosesAt] = useState(toLocalInput(round.closes_at));
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const updated = await api.patch<RegistrationWindow>(
        `/electives/admin/windows/${round.id}`, { closes_at: fromLocalInput(closesAt) },
      );
      // A locked round keeps its old deadline until it is told otherwise, so
      // the new one is saved first and the round reopened against it.
      return reopening
        ? api.post<RegistrationWindow>(`/electives/admin/windows/${round.id}/status?target=OPEN`)
        : updated;
    },
    onSuccess: (updated) =>
      onDone(`${updated.title} now closes ${formatDateTime(updated.closes_at)}. `
        + `${pluralise(updated.eligible_student_count, "student")} notified.`),
    onError: (err) => setError(errorText(err, "Could not change the deadline.")),
  });

  return (
    <Modal
      open onClose={onClose}
      title={reopening ? "Reopen this round" : "Change the deadline"}
      description={round.title}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={!closesAt} loading={save.isPending}
                  onClick={() => save.mutate()}>
            {reopening ? "Reopen round" : "Save deadline"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField
          label="New deadline" required
          hint={`${pluralise(round.eligible_student_count, "student")} will be notified. `
            + `${round.submitted_student_count} have submitted so far.`}
        >
          <Input type="datetime-local" value={closesAt} data-autofocus
                 onChange={(e) => setClosesAt(e.target.value)} />
        </FormField>
      </div>
    </Modal>
  );
}

/** What a run did, added up over the round's slots. */
function addUp(results: AllocationRunResult[]) {
  return results.reduce(
    (sum, r) => ({
      allocated: sum.allocated + r.allocated,
      waitlisted: sum.waitlisted + r.waitlisted,
      unallocated: sum.unallocated + r.unallocated,
      random: sum.random + r.preview.filter(
        (row) => !row.preference_order_granted && row.status === "ALLOCATED").length,
      notes: [...sum.notes, ...r.notes],
    }),
    { allocated: 0, waitlisted: 0, unallocated: 0, random: 0, notes: [] as string[] },
  );
}

/**
 * Allocate a locked round: choose the rule and the seat limit, preview, run.
 * Only this round's courses and students are touched, and nobody is told until
 * the results are published.
 */
function AllocateModal({
  round, onClose, onDone,
}: {
  round: RegistrationWindow; onClose: () => void; onDone: (text: string) => void;
}) {
  const strategies = useQuery({
    queryKey: ["allocation-strategies"],
    queryFn: () => api.get<AllocationStrategy[]>("/electives/strategies"),
  });
  const usable = (strategies.data ?? []).filter((s) => s.is_available && s.key !== "manual");
  const [strategy, setStrategy] = useState("first_come_first_served");
  // An even split, so every covered student can be seated. A suggestion: the
  // coordinator knows the real room sizes.
  const coursesPerSlot = Math.max(1, Math.round(round.offering_count / Math.max(1, round.slots.length)));
  const [seats, setSeats] = useState(
    String(Math.max(1, Math.ceil(round.eligible_student_count / coursesPerSlot))),
  );
  const [preview, setPreview] = useState<ReturnType<typeof addUp> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chosen = usable.find((s) => s.key === strategy);

  async function runAll(dryRun: boolean) {
    const results: AllocationRunResult[] = [];
    for (const slot of round.slots) {
      results.push(await api.post<AllocationRunResult>("/electives/admin/allocate", {
        curriculum_component_id: slot.id,
        registration_window_id: round.id,
        strategy,
        seats_per_course: Number(seats) || null,
        dry_run: dryRun,
      }));
    }
    return addUp(results);
  }

  const check = useMutation({
    mutationFn: () => runAll(true),
    onSuccess: (sum) => { setError(null); setPreview(sum); },
    onError: (err) => setError(errorText(err, "Could not preview the allocation.")),
  });
  const run = useMutation({
    mutationFn: async () => {
      const sum = await runAll(false);
      await api.post<RegistrationWindow>(
        `/electives/admin/windows/${round.id}/status?target=ALLOCATED`);
      return sum;
    },
    onSuccess: (sum) => onDone(
      `Allocation complete for ${round.title}: ${pluralise(sum.allocated, "seat")} assigned`
      + (sum.random ? `, ${sum.random} placed at random` : "")
      + (sum.unallocated ? `, ${sum.unallocated} not seated` : "")
      + ". Review it, then publish to notify students."),
    onError: (err) => setError(errorText(err, "Could not run the allocation.")),
  });

  return (
    <Modal
      open onClose={onClose} size="lg"
      title="Run allocation"
      description={`${round.title} · ${pluralise(round.eligible_student_count, "student")}, `
        + `${round.submitted_student_count} submitted`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" size="sm" loading={check.isPending}
                  disabled={!chosen || run.isPending} onClick={() => check.mutate()}>
            Preview
          </Button>
          <Button size="sm" loading={run.isPending}
                  disabled={!chosen || check.isPending} onClick={() => run.mutate()}>
            Run allocation
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField label="Allocation rule" hint={chosen?.description}>
          <Select value={strategy}
                  onChange={(e) => { setStrategy(e.target.value); setPreview(null); }}>
            {usable.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </Select>
        </FormField>
        <FormField
          label="Seats per course"
          hint={`Prefilled so all ${round.eligible_student_count} students fit across `
            + `${pluralise(coursesPerSlot, "course")}. Leave empty for no limit.`}
        >
          <Input type="number" min={1} value={seats}
                 onChange={(e) => { setSeats(e.target.value); setPreview(null); }} />
        </FormField>
        <p className="text-sm text-ink-muted">
          Only this round&apos;s courses and students are allocated. Students are{" "}
          <strong>not notified</strong> until you publish the results.
        </p>
        {preview && (
          <Alert variant={preview.unallocated ? "warning" : "info"}>
            <p>
              Preview: {pluralise(preview.allocated, "seat")} from choices and at random
              {preview.random ? ` (${preview.random} at random)` : ""}
              {preview.waitlisted ? `, ${preview.waitlisted} waitlisted` : ""}
              {preview.unallocated ? `, ${preview.unallocated} without a seat` : ""}.
            </p>
            {preview.notes.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {preview.notes.map((note, i) => <li key={i}>{note}</li>)}
              </ul>
            )}
          </Alert>
        )}
      </div>
    </Modal>
  );
}

/**
 * The interest round's votes, and — once it is locked — the shortlist.
 * The coordinator keeps whichever subjects they choose; nothing is fixed at a
 * "top N". Read-only while the interest round is still open.
 */
function ShortlistModal({
  round, readOnly, onClose, onDone,
}: {
  round: RegistrationWindow; readOnly: boolean;
  onClose: () => void; onDone: (text: string) => void;
}) {
  const tally = useQuery({
    queryKey: ["interest-tally", round.id],
    queryFn: () => api.get<InterestTally>(`/electives/admin/windows/${round.id}/interest`),
  });
  const rows = (tally.data?.subjects ?? []).filter((r) => r.in_round);
  const [keep, setKeep] = useState<number[]>([]);
  const [topN, setTopN] = useState("");
  const slotCount = tally.data?.slot_count ?? round.slots.length;
  const [picks, setPicks] = useState(String(round.final_pick_count ?? Math.max(1, round.slots.length)));
  const [opensAt, setOpensAt] = useState(toLocalInput(new Date().toISOString()));
  const [closesAt, setClosesAt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.post<RegistrationWindow>(
      `/electives/admin/windows/${round.id}/shortlist`, {
        course_ids: keep, final_pick_count: Number(picks),
        opens_at: fromLocalInput(opensAt), closes_at: fromLocalInput(closesAt),
      }),
    onSuccess: (saved) => onDone(
      `Final round open for ${saved.title}: ${pluralise(keep.length, "subject")} shortlisted, `
      + `${pluralise(saved.eligible_student_count, "student")} notified.`),
    onError: (err) => setError(errorText(err, "Could not open the final round.")),
  });

  function pickTop() {
    const n = Number(topN);
    if (n > 0) setKeep(rows.slice(0, n).map((r) => r.course_id));
  }

  return (
    <Modal
      open onClose={onClose} size="lg"
      title={readOnly ? "Interest votes so far" : "Shortlist for the final round"}
      description={tally.data
        ? `${round.title} · ${tally.data.voters} of ${tally.data.eligible_student_count} students voted, `
          + `${tally.data.interest_pick_count ?? "?"} ticks each. Only you and the Head of Department see this.`
        : round.title}
      footer={readOnly ? (
        <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
      ) : (
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={save.isPending}
                  disabled={keep.length === 0 || !closesAt || !Number(picks)}
                  onClick={() => save.mutate()}>
            Open final round
          </Button>
        </>
      )}
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        {tally.isLoading ? <LoadingState rows={4} /> : (
          <TableWrap>
              <THead>
                  {!readOnly && <TH className="w-10">Keep</TH>}
                  <TH>Subject</TH>
                  <TH align="right">Votes</TH>
                </THead>
              <TBody>
                {rows.map((row) => (
                  <TR key={row.course_id}>
                    {!readOnly && (
                      <TD>
                        <Checkbox label="" aria-label={`Keep ${row.title}`}
                                  checked={keep.includes(row.course_id)}
                                  onChange={(e) => setKeep(e.target.checked
                                    ? [...keep, row.course_id]
                                    : keep.filter((id) => id !== row.course_id))} />
                      </TD>
                    )}
                    <TD>
                      <p className="font-medium text-ink">{row.title}</p>
                      <p className="text-2xs text-ink-subtle">{row.code}</p>
                    </TD>
                    <TD align="right" className="font-mono">{row.votes}</TD>
                  </TR>
                ))}
              </TBody>
          </TableWrap>
        )}
        {!readOnly && (
          <>
            <div className="flex flex-wrap items-end gap-2">
              <FormField label="Quick pick" hint="Ticks the most voted subjects; adjust after.">
                <Input type="number" min={1} value={topN} placeholder="e.g. 4"
                       onChange={(e) => setTopN(e.target.value)} className="w-28" />
              </FormField>
              <Button size="sm" variant="secondary" onClick={pickTop} disabled={!Number(topN)}>
                Tick top {topN || "N"}
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField label="Subjects each student takes" required
                         hint={`At most ${slotCount}: one per elective slot in this round.`}>
                <Input type="number" min={1} max={slotCount} value={picks}
                       onChange={(e) => setPicks(e.target.value)} />
              </FormField>
              <FormField label="Final round starts">
                <Input type="datetime-local" value={opensAt}
                       onChange={(e) => setOpensAt(e.target.value)} />
              </FormField>
              <FormField label="Final round deadline" required>
                <Input type="datetime-local" value={closesAt}
                       onChange={(e) => setClosesAt(e.target.value)} />
              </FormField>
            </div>
            <p className="text-sm text-ink-muted">
              Subjects you do not keep leave the round. Every student of the round is told
              the final round is open — including those who did not vote.
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

/**
 * Decide which subjects run and seat everyone. A subject runs with at least
 * the coordinator's minimum, unless they decide otherwise; students whose
 * subject was withdrawn, and students who did not submit, are placed in
 * subjects that run. Nobody is told until the results are published.
 */
function FinaliseModal({
  round, onClose, onDone,
}: {
  round: RegistrationWindow; onClose: () => void; onDone: (text: string) => void;
}) {
  const [minimum, setMinimum] = useState(String(round.min_students_to_run ?? ""));
  const [runIds, setRunIds] = useState<number[] | null>(null);
  const [plan, setPlan] = useState<FinaliseResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const request = (dryRun: boolean) => api.post<FinaliseResult>(
    `/electives/admin/windows/${round.id}/finalise`, {
      dry_run: dryRun, min_students_to_run: Number(minimum) || null,
      run_course_ids: runIds,
    });
  const preview = useMutation({
    mutationFn: () => request(true),
    onSuccess: (result) => { setError(null); setPlan(result); },
    onError: (err) => setError(errorText(err, "Could not preview.")),
  });
  const run = useMutation({
    mutationFn: () => request(false),
    onSuccess: (result) => onDone(
      `${round.title} finalised: ${pluralise(result.students_placed, "student")} seated `
      + `(${result.replaced_withdrawn} moved from a withdrawn subject, `
      + `${result.placed_no_submission} placed by the department). Review, then publish.`),
    onError: (err) => setError(errorText(err, "Could not finalise.")),
  });

  useEffect(() => { preview.mutate(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const running = runIds ?? plan?.subjects.filter((s) => s.runs).map((s) => s.course_id) ?? [];

  return (
    <Modal
      open onClose={onClose} size="lg"
      title="Finalise electives"
      description={`${round.title} · each student takes ${round.final_pick_count ?? "?"}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" size="sm" loading={preview.isPending}
                  onClick={() => preview.mutate()}>
            Update preview
          </Button>
          <Button size="sm" loading={run.isPending} disabled={!plan || preview.isPending}
                  onClick={() => run.mutate()}>
            Finalise
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField label="Minimum students for a subject to run" required
                   hint="Your rule for this year. Change it and update the preview.">
          <Input type="number" min={1} value={minimum} placeholder="e.g. 48" className="w-32"
                 onChange={(e) => { setMinimum(e.target.value); setRunIds(null); }} />
        </FormField>
        {plan && (
          <>
            <TableWrap>
                <THead>
                    <TH className="w-10">Runs</TH>
                    <TH>Subject</TH>
                    <TH align="right">Chose it</TH>
                    <TH align="right">Seated</TH>
                  </THead>
                <TBody>
                  {plan.subjects.map((row) => (
                    <TR key={row.course_id}>
                      <TD>
                        <Checkbox label="" aria-label={`${row.title} runs`}
                                  checked={running.includes(row.course_id)}
                                  onChange={(e) => setRunIds(e.target.checked
                                    ? [...running, row.course_id]
                                    : running.filter((id) => id !== row.course_id))} />
                      </TD>
                      <TD>
                        <p className="font-medium text-ink">{row.title}</p>
                        <p className="text-2xs text-ink-subtle">{row.code}</p>
                      </TD>
                      <TD align="right" className="font-mono">{row.demand}</TD>
                      <TD align="right" className="font-mono">{row.seated}</TD>
                    </TR>
                  ))}
                </TBody>
            </TableWrap>
            {runIds && (
              <p className="text-sm text-warning">
                You changed which subjects run. Update the preview to see the seats.
              </p>
            )}
            <Alert variant={plan.unplaced ? "warning" : "info"}>
              <p>
                {pluralise(plan.students_placed, "student")} seated: {plan.by_choice} as they
                chose, {plan.replaced_withdrawn} moved from a withdrawn subject,{" "}
                {plan.placed_no_submission} who did not submit placed by the department
                {plan.unplaced ? `; ${plan.unplaced} could not be seated` : ""}.
              </p>
              {plan.notes.length > 0 && (
                <ul className="mt-1 list-disc pl-5">
                  {plan.notes.map((note, i) => <li key={i}>{note}</li>)}
                </ul>
              )}
            </Alert>
            <p className="text-sm text-ink-muted">
              Students are <strong>not notified</strong> until you publish. You can change any
              seat from Elective Allocation before publishing.
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

/** Add, edit and remove the subjects offered in a slot. */
function SubjectsModal({ slots, onClose }: { slots: RoundSlot[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [slotId, setSlotId] = useState(String(slots[0]?.component_id ?? ""));
  const slot = slots.find((s) => String(s.component_id) === slotId);
  const [editing, setEditing] = useState<{ offeringId: number | null; code: string;
    title: string; credits: string } | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [removing, setRemoving] = useState<{ id: number; label: string } | null>(null);

  const done = (text: string) => {
    setMessage({ tone: "success", text });
    setEditing(null);
    void queryClient.invalidateQueries({ queryKey: ["round-slots"] });
  };
  const fail = (err: unknown) => setMessage({ tone: "danger", text: errorText(err, "Could not save.") });

  const save = useMutation({
    mutationFn: async () => {
      if (!editing || !slot) throw new Error("Nothing to save.");
      const body = { code: editing.code.trim(), title: editing.title.trim(),
        credits: editing.credits.trim() === "" ? undefined : Number(editing.credits) };
      return editing.offeringId
        ? api.patch<Subject>(`/electives/admin/subjects/${editing.offeringId}`, body)
        : api.post<Subject>(`/electives/admin/slots/${slot.component_id}/subjects`, body);
    },
    onSuccess: (subject) => done(editing?.offeringId
      ? `${subject.code} saved. The change shows everywhere this course is offered.`
      : `${subject.code} added to ${slot?.title}.`),
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete<{ message: string }>(`/electives/admin/subjects/${id}`),
    onSuccess: (result) => { setRemoving(null); done(result.message); },
    onError: (err) => { setRemoving(null); fail(err); },
  });

  return (
    <Modal open onClose={onClose} size="lg" title="Subjects"
           description="Add, rename or remove the subjects offered in a slot."
           footer={<Button variant="secondary" size="sm" onClick={onClose}>Done</Button>}>
      <div className="space-y-4">
        {message && (
          <Alert variant={message.tone === "success" ? "success" : "danger"}
                 onDismiss={() => setMessage(null)}>{message.text}</Alert>
        )}
        <FormField label="Elective slot">
          <Select value={slotId} onChange={(e) => { setSlotId(e.target.value); setEditing(null); }}>
            {slots.map((s) => (
              <option key={s.component_id} value={s.component_id}>
                {s.title} · Semester {roman(s.semester_number)} · {s.curriculum_version}
              </option>
            ))}
          </Select>
        </FormField>

        {slot && (
          <TableWrap>
              <THead><TH>Subject</TH><TH>In a round</TH><TH align="right">Actions</TH></THead>
              <TBody>
                {slot.offerings.map((o) => (
                  <TR key={o.id}>
                    <TD>
                      <p className="font-medium text-ink">{o.course_title}</p>
                      <p className="text-2xs text-ink-subtle">
                        {[o.course_code, o.academic_year,
                          o.seats_taken ? `${o.seats_taken} seated` : null].filter(Boolean).join(" · ")}
                      </p>
                    </TD>
                    <TD className="text-xs text-ink-muted">{o.registration_window_id ? "Yes" : "—"}</TD>
                    <TD align="right">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="ghost"
                                icon={<Pencil className="h-3.5 w-3.5" aria-hidden />}
                                onClick={() => setEditing({ offeringId: o.id, code: o.course_code,
                                  title: o.course_title, credits: "" })}>
                          Edit
                        </Button>
                        <Button size="sm" variant="ghost"
                                icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                                onClick={() => setRemoving({ id: o.id,
                                  label: `${o.course_code} · ${o.course_title}` })}>
                          Remove
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
          </TableWrap>
        )}

        {editing ? (
          <div className="space-y-3 rounded-lg border border-line p-4">
            <p className="font-medium text-ink">
              {editing.offeringId ? "Edit subject" : `Add a subject to ${slot?.title}`}
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField label="Code" required>
                <Input value={editing.code}
                       onChange={(e) => setEditing({ ...editing, code: e.target.value })} />
              </FormField>
              <FormField label="Name" required className="sm:col-span-2">
                <Input value={editing.title}
                       onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
              </FormField>
              <FormField label="Credits" hint={editing.offeringId ? "Blank keeps the current credits." : undefined}>
                <Input type="number" min={0} step="0.5" value={editing.credits}
                       onChange={(e) => setEditing({ ...editing, credits: e.target.value })} />
              </FormField>
            </div>
            {editing.offeringId && (
              <p className="text-xs text-ink-muted">
                The course is edited everywhere it is offered, in every slot and year.
              </p>
            )}
            <div className="flex gap-2">
              <Button size="sm" loading={save.isPending}
                      disabled={!editing.code.trim() || !editing.title.trim()}
                      onClick={() => save.mutate()}>
                {editing.offeringId ? "Save" : "Add subject"}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
            </div>
          </div>
        ) : (
          slot && (
            <Button size="sm" icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => setEditing({ offeringId: null, code: "", title: "", credits: "3" })}>
              Add subject
            </Button>
          )
        )}
      </div>
      {removing && (
        <ConfirmDialog
          open destructive
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing.id)}
          loading={remove.isPending}
          title="Remove this subject?"
          confirmLabel="Remove"
          message={<><strong>{removing.label}</strong> is taken out of {slot?.title}. The course stays in the catalogue.</>}
        />
      )}
    </Modal>
  );
}
