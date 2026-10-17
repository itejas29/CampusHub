import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock, CheckCheck, Download, Eye, Lock, Pencil, Play, Plus, RotateCcw, Trash2, Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
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
  AllocationRunResult, AllocationStrategy, ComponentType, RegistrationWindow, RoundSlot,
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

type Action = "OPEN" | "LOCKED" | "ALLOCATED" | "PUBLISHED" | "REOPEN" | "DELETE";

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
            <Button size="sm" onClick={() => setFormOpen(true)}
                    icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
              New round
            </Button>
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
                        {round.status === "LOCKED" && (
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
          onConfirm={() => (confirm.action === "DELETE"
            ? remove.mutate(confirm.round) : move.mutate(confirm))}
          loading={move.isPending || remove.isPending}
          destructive={confirm.action === "DELETE"}
          title={
            confirm.action === "DELETE" ? "Delete this round?"
            : confirm.action === "LOCKED" ? "Lock this round?"
            : confirm.action === "ALLOCATED" ? "Run allocation?"
            : confirm.action === "PUBLISHED" ? "Publish results?"
            : "Open this round?"
          }
          confirmLabel={
            confirm.action === "DELETE" ? "Delete round"
            : confirm.action === "LOCKED" ? "Lock round"
            : confirm.action === "ALLOCATED" ? "Run allocation"
            : confirm.action === "PUBLISHED" ? "Publish results"
            : "Open round"
          }
          message={
            confirm.action === "DELETE" ? (
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
  const freeCourses = (s: RoundSlot) =>
    s.offerings.filter((o) => o.registration_window_id === null).length;
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

  // A course can be in one round at a time, so only free ones — and the ones
  // already in this round — are offered.
  const available = (slot?.offerings ?? []).filter(
    (o) => o.registration_window_id === null || o.registration_window_id === round?.id,
  );
  const taken = (slot?.offerings.length ?? 0) - available.length;
  const chosenCourses = picked ?? (
    round ? available.filter((o) => o.registration_window_id === round.id).map((o) => o.id)
          : available.map((o) => o.id)
  );
  // Choosing ahead — the semester before the slot — is the normal case.
  const chosenSemester = semester ?? (slot ? slot.semester_number - 1 : null);
  const defaultTitle = slot && chosenSemester != null
    ? `${slot.title} — choice filling for Semester ${roman(slot.semester_number)}`
    : "";

  function pickSlot(value: string) {
    setSlotId(value);
    setSemester(null);
    setPicked(null);
    setDivisions([]);
  }

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
        min_preferences: Number(minPrefs) || null,
        max_preferences: Number(maxPrefs) || null,
        notes: notes.trim() || null,
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

  const ready = Boolean(slot) && Boolean(closesAt) && chosenCourses.length > 0;

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
                    : `${pluralise(free, "course")} available`})
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
            label={`Courses students choose from (${chosenCourses.length} of ${available.length})`}
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
                {available.map((offering) => (
                  <Checkbox
                    key={offering.id}
                    label={`${offering.course_code} · ${offering.course_title}`}
                    description={offering.department_code ?? undefined}
                    checked={chosenCourses.includes(offering.id)}
                    onChange={(e) => setPicked(e.target.checked
                      ? [...chosenCourses, offering.id]
                      : chosenCourses.filter((id) => id !== offering.id))}
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
