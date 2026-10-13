import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Eye, Lock, Pencil, Play, Plus, RotateCcw } from "lucide-react";
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
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { pluralise, roman } from "@/lib/utils";
import type { ComponentType, RegistrationWindow, RoundSlot } from "@/types";

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

type Action = "OPEN" | "LOCKED" | "REOPEN";

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

  const move = useMutation({
    mutationFn: ({ round, action }: { round: RegistrationWindow; action: Action }) =>
      api.post<RegistrationWindow>(
        `/electives/admin/windows/${round.id}/status?target=${action === "REOPEN" ? "OPEN" : action}`,
      ),
    onSuccess: (round, { action }) => {
      setConfirm(null);
      const told = pluralise(round.eligible_student_count, "student");
      setBanner({
        tone: "success",
        text: action === "LOCKED"
          ? `${round.title} is locked. Preferences are frozen.`
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
          description="Draft → Open → Locked. Allocation and publishing follow once preferences are in."
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
                          <Button size="sm" variant="secondary"
                                  onClick={() => setDeadlineFor(round)}
                                  icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>
                            Reopen
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

      {confirm && (
        <ConfirmDialog
          open
          onClose={() => setConfirm(null)}
          onConfirm={() => move.mutate(confirm)}
          loading={move.isPending}
          title={confirm.action === "LOCKED" ? "Lock this round?" : "Open this round?"}
          confirmLabel={confirm.action === "LOCKED" ? "Lock round" : "Open round"}
          message={
            confirm.action === "LOCKED" ? (
              <>
                Choice filling stops now for{" "}
                {pluralise(confirm.round.eligible_student_count, "student")}.{" "}
                {confirm.round.submitted_student_count} have submitted. You can reopen
                the round later if needed.
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
  const [slotId, setSlotId] = useState(
    String(editingSlotId ?? slots[0]?.component_id ?? ""),
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
            {slots.map((s) => (
              <option key={s.component_id} value={s.component_id}>
                {s.title} — Semester {roman(s.semester_number)} · {s.program_code} {s.curriculum_version}
                {" "}({pluralise(s.offerings.length, "course")})
              </option>
            ))}
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
