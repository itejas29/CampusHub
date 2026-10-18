import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Download, ListChecks, Lock, Play, Plus, RotateCcw, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { FileUpload } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { ApiError, api, downloadProtectedFile } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { pluralise, roman } from "@/lib/utils";
import type { MoocCourse, MoocRosterRow, MoocRound, MoocSlot } from "@/types";

const errorText = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);

/**
 * The coordinator's NPTEL / NCC rounds — the Google Form, the approved list
 * and the department's spreadsheet, in one place. Certificates are verified in
 * the queue below this panel.
 */
export function NptelRoundsPanel() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const rounds = useQuery({
    queryKey: ["mooc-rounds"],
    queryFn: () => api.get<MoocRound[]>("/mooc/admin/rounds"),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["mooc-rounds"] });
  const canCreate = (rounds.data ?? []).some((r) => r.can_manage) || !rounds.data?.length;
  const selected = rounds.data?.find((r) => r.id === openId) ?? null;

  return (
    <Card className="mb-5">
      <CardHeader
        title="NPTEL / NCC rounds"
        description="Publish the approved course list, open choosing with a deadline, follow who has chosen, then close the semester. Students who do not clear it carry it over to the next semester; after that it is a backlog."
        icon={<ListChecks className="h-4 w-4 text-ink-subtle" aria-hidden />}
        action={canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
            New round
          </Button>
        )}
      />
      {rounds.isLoading ? <LoadingState rows={3} /> : !rounds.data?.length ? (
        <EmptyState compact title="No rounds yet"
                    description="Create one for the semester, import the department's NPTEL list, and open it." />
      ) : (
        <TableWrap>
          <THead>
            <TH>Round</TH><TH>For</TH><TH>Closes</TH><TH align="right">Chosen</TH>
            <TH align="right">Certificates</TH><TH>Status</TH><TH align="right">{" "}</TH>
          </THead>
          <TBody>
            {rounds.data.map((r) => (
              <TR key={r.id}>
                <TD>
                  <p className="font-medium text-ink">{r.title}</p>
                  <p className="text-2xs text-ink-subtle">
                    {r.component_title} · {pluralise(r.course_count, "course")} on the list
                  </p>
                </TD>
                <TD className="text-xs text-ink-muted">
                  Sem {r.eligible_semesters.map(roman).join(", ")}
                  {r.carry_over_count > 0 && ` · ${r.carry_over_count} carried over`}
                </TD>
                <TD className="text-xs text-ink-muted">{formatDateTime(r.closes_at)}</TD>
                <TD align="right" className="font-mono text-sm">
                  {r.chosen_count} / {r.status === "CLOSED" ? r.chosen_count : r.covered_count}
                  <p className="text-2xs text-ink-subtle">{r.nptel_count} NPTEL · {r.ncc_count} NCC</p>
                </TD>
                <TD align="right" className="text-xs text-ink-muted">
                  {r.verified_count} verified
                  {r.certificates_waiting > 0 && <p className="text-warning">{r.certificates_waiting} waiting</p>}
                </TD>
                <TD><StatusBadge status={r.status} /></TD>
                <TD align="right">
                  <Button size="sm" variant="secondary" onClick={() => setOpenId(r.id)}>
                    {r.can_manage ? "Manage" : "View"}
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </TableWrap>
      )}
      {creating && (
        <NewRoundModal rounds={rounds.data ?? []} onClose={() => setCreating(false)}
                       onDone={(id) => { setCreating(false); refresh(); setOpenId(id); }} />
      )}
      {selected && (
        <RoundModal round={selected} rounds={rounds.data ?? []}
                    onClose={() => setOpenId(null)} onChanged={refresh} />
      )}
    </Card>
  );
}

function NewRoundModal({ rounds, onClose, onDone }: {
  rounds: MoocRound[]; onClose: () => void; onDone: (id: number) => void;
}) {
  const slots = useQuery({
    queryKey: ["mooc-slots"],
    queryFn: () => api.get<MoocSlot[]>("/mooc/admin/slots"),
  });
  const [slotId, setSlotId] = useState("");
  const slot = slots.data?.find((s) => String(s.component_id) === slotId) ?? slots.data?.[0];
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState(
    "Choose one NPTEL course from the approved list, or NCC certification. Register for your course on the NPTEL portal yourself; submit your certificate here at the end of the semester.");
  const [semesters, setSemesters] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [platformDeadline, setPlatformDeadline] = useState("");
  const [copyFrom, setCopyFrom] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.post<MoocRound>("/mooc/admin/rounds", {
      title: title.trim() || `${slot?.title} — Semester ${roman(slot?.semester_number ?? 0)}`,
      message: message.trim() || null,
      curriculum_component_id: slot?.component_id,
      eligible_semesters: semesters.trim()
        ? semesters.split(",").map((s) => Number(s.trim())).filter(Boolean)
        : [slot?.semester_number],
      closes_at: fromLocalInput(closesAt),
      platform_deadline: platformDeadline || null,
      copy_list_from: copyFrom ? Number(copyFrom) : null,
    }),
    onSuccess: (round) => onDone(round.id),
    onError: (err) => setError(errorText(err, "Could not create the round.")),
  });

  return (
    <Modal open onClose={onClose} size="lg" title="New NPTEL / NCC round"
           description="Saved as a draft. Students see nothing until you open it."
           footer={<>
             <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
             <Button size="sm" disabled={!slot || !closesAt} loading={save.isPending}
                     onClick={() => save.mutate()}>Create draft</Button>
           </>}>
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField label="Curriculum slot" required>
          <Select value={slotId || String(slot?.component_id ?? "")}
                  onChange={(e) => setSlotId(e.target.value)}>
            {(slots.data ?? []).map((s) => (
              <option key={s.component_id} value={s.component_id}>
                {s.title} — Semester {roman(s.semester_number)} · {s.program_code} {s.curriculum_version}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Title" hint="Shown to students. Leave blank for the suggestion.">
          <Input value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder={slot ? `${slot.title} — Semester ${roman(slot.semester_number)}` : ""} />
        </FormField>
        <FormField label="Message to students">
          <Textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Students in semester(s)"
                     hint={`Default ${slot?.semester_number ?? ""}. Carried-over students are added automatically.`}>
            <Input value={semesters} placeholder={String(slot?.semester_number ?? "")}
                   onChange={(e) => setSemesters(e.target.value)} />
          </FormField>
          <FormField label="Choosing closes" required>
            <Input type="datetime-local" value={closesAt} onChange={(e) => setClosesAt(e.target.value)} />
          </FormField>
          <FormField label="NPTEL portal's last date" hint="Shown to students only.">
            <Input type="date" value={platformDeadline}
                   onChange={(e) => setPlatformDeadline(e.target.value)} />
          </FormField>
        </div>
        {rounds.length > 0 && (
          <FormField label="Start from another round's course list"
                     hint="The previous semester's list. You can still change it.">
            <Select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">No — I will import or add courses</option>
              {rounds.map((r) => <option key={r.id} value={r.id}>{r.title} ({r.course_count} courses)</option>)}
            </Select>
          </FormField>
        )}
      </div>
    </Modal>
  );
}

function RoundModal({ round, rounds, onClose, onChanged }: {
  round: MoocRound; rounds: MoocRound[]; onClose: () => void; onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("courses");
  const [message, setMessage] = useState<{ tone: "success" | "danger" | "warning"; text: string } | null>(null);
  const [confirm, setConfirm] = useState<"OPEN" | "LOCKED" | "CLOSE" | "FORCE" | "DELETE" | null>(null);
  const [closesAt, setClosesAt] = useState(toLocalInput(round.closes_at));
  const manage = round.can_manage;

  const refresh = () => {
    onChanged();
    void queryClient.invalidateQueries({ queryKey: ["mooc-round", round.id] });
    void queryClient.invalidateQueries({ queryKey: ["mooc-admin"] });
  };
  const ok = (text: string) => { setConfirm(null); setMessage({ tone: "success", text }); refresh(); };
  const bad = (err: unknown, fallback: string) => {
    setConfirm(null); setMessage({ tone: "danger", text: errorText(err, fallback) });
  };

  const move = useMutation({
    mutationFn: (target: "OPEN" | "LOCKED") =>
      api.post<MoocRound>(`/mooc/admin/rounds/${round.id}/status?target=${target}`),
    onSuccess: (r) => ok(r.status === "OPEN" ? `Open. ${pluralise(r.covered_count, "student")} notified.`
                                             : "Locked. Choices are fixed; certificates can still come in."),
    onError: (err) => bad(err, "Could not change the round."),
  });
  const deadline = useMutation({
    mutationFn: () => api.patch<MoocRound>(`/mooc/admin/rounds/${round.id}`,
      { closes_at: fromLocalInput(closesAt) }),
    onSuccess: () => ok(round.status === "OPEN" ? "Deadline moved. Students were told." : "Deadline saved."),
    onError: (err) => bad(err, "Could not change the deadline."),
  });
  const close = useMutation({
    mutationFn: (force: boolean) => api.post<{ cleared: number; carried_over: number; backlog: number }>(
      `/mooc/admin/rounds/${round.id}/close`, { force }),
    onSuccess: (r) => ok(`Semester closed: ${r.cleared} cleared, ${r.carried_over} carried over, ${r.backlog} backlog.`),
    onError: (err) => {
      if (err instanceof ApiError && err.message.includes("waiting for verification")) {
        setConfirm("FORCE"); setMessage({ tone: "warning", text: err.message });
      } else bad(err, "Could not close the semester.");
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete<{ message: string }>(`/mooc/admin/rounds/${round.id}`),
    onSuccess: (r) => { ok(r.message); onClose(); },
    onError: (err) => bad(err, "Could not delete the round."),
  });

  return (
    <Modal open onClose={onClose} size="xl" title={round.title}
           description={`${round.component_title} · Semester ${round.eligible_semesters.map(roman).join(", ")}`
             + (round.platform_deadline ? ` · NPTEL portal closes ${formatDate(round.platform_deadline)}` : "")}
           footer={<Button variant="secondary" size="sm" onClick={onClose}>Close</Button>}>
      <div className="space-y-4">
        {message && (
          <Alert variant={message.tone} onDismiss={() => setMessage(null)}>{message.text}</Alert>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={round.status} />
          <span className="text-sm text-ink-muted">
            {round.chosen_count} chosen ({round.nptel_count} NPTEL, {round.ncc_count} NCC) ·{" "}
            {round.verified_count} verified · {round.failed_count} did not pass
          </span>
          {manage && (
            <div className="ml-auto flex flex-wrap gap-2">
              {(round.status === "DRAFT" || round.status === "LOCKED") && (
                <Button size="sm" onClick={() => setConfirm("OPEN")}
                        icon={round.status === "DRAFT" ? <Play className="h-3.5 w-3.5" aria-hidden />
                          : <RotateCcw className="h-3.5 w-3.5" aria-hidden />}>
                  {round.status === "DRAFT" ? "Open" : "Reopen"}
                </Button>
              )}
              {round.status === "OPEN" && (
                <Button size="sm" variant="secondary" onClick={() => setConfirm("LOCKED")}
                        icon={<Lock className="h-3.5 w-3.5" aria-hidden />}>Lock</Button>
              )}
              {round.status === "LOCKED" && (
                <Button size="sm" variant="secondary" onClick={() => setConfirm("CLOSE")}>
                  Close semester
                </Button>
              )}
              {round.status !== "CLOSED" && round.chosen_count === 0 && (
                <Button size="sm" variant="ghost" onClick={() => setConfirm("DELETE")}
                        icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}>Delete</Button>
              )}
            </div>
          )}
        </div>
        {manage && round.status !== "CLOSED" && (
          <div className="flex flex-wrap items-end gap-2">
            <FormField label="Choosing closes">
              <Input type="datetime-local" value={closesAt} className="w-56"
                     onChange={(e) => setClosesAt(e.target.value)} />
            </FormField>
            <Button size="sm" variant="secondary" loading={deadline.isPending}
                    disabled={!closesAt || closesAt === toLocalInput(round.closes_at)}
                    onClick={() => deadline.mutate()}
                    icon={<CalendarClock className="h-3.5 w-3.5" aria-hidden />}>
              Save deadline
            </Button>
          </div>
        )}
        <Tabs tabs={[{ key: "courses", label: `Approved list (${round.course_count})` },
                     { key: "students", label: `Students (${round.covered_count || round.chosen_count})` }]}
              active={tab} onChange={setTab} />
        {tab === "courses" ? <CoursesTab round={round} rounds={rounds} onChanged={refresh} />
                           : <StudentsTab round={round} />}
      </div>
      {confirm === "OPEN" && (
        <ConfirmDialog open onClose={() => setConfirm(null)} onConfirm={() => move.mutate("OPEN")}
                       loading={move.isPending} title="Open choosing?" confirmLabel="Open"
                       message={`${pluralise(round.covered_count, "student")} will be notified to choose an NPTEL course or NCC before ${formatDateTime(round.closes_at)}.`} />
      )}
      {confirm === "LOCKED" && (
        <ConfirmDialog open onClose={() => setConfirm(null)} onConfirm={() => move.mutate("LOCKED")}
                       loading={move.isPending} title="Lock choosing?" confirmLabel="Lock"
                       message="Students can no longer change their choice. They can still submit certificates, or say they did not pass." />
      )}
      {confirm === "CLOSE" && (
        <ConfirmDialog open onClose={() => setConfirm(null)} onConfirm={() => close.mutate(false)}
                       loading={close.isPending} title="Close the semester?" confirmLabel="Close semester"
                       message="Each student's outcome is recorded: verified certificates are cleared; everyone else carries over to next semester, or — if they were already carrying it over — becomes a backlog. This cannot be undone." />
      )}
      {confirm === "FORCE" && (
        <ConfirmDialog open destructive onClose={() => setConfirm(null)} onConfirm={() => close.mutate(true)}
                       loading={close.isPending} title="Close anyway?" confirmLabel="Close anyway"
                       message="Students whose certificates are still waiting will be carried over (or become a backlog). Verify them first if you can." />
      )}
      {confirm === "DELETE" && (
        <ConfirmDialog open destructive onClose={() => setConfirm(null)} onConfirm={() => remove.mutate()}
                       loading={remove.isPending} title="Delete this round?" confirmLabel="Delete"
                       message="Nobody has chosen yet. The round and its list are removed; the courses stay in the catalogue." />
      )}
    </Modal>
  );
}

function CoursesTab({ round, rounds, onChanged }: {
  round: MoocRound; rounds: MoocRound[]; onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const manage = round.can_manage && round.status !== "CLOSED";
  const courses = useQuery({
    queryKey: ["mooc-round", round.id, "courses"],
    queryFn: () => api.get<MoocCourse[]>(`/mooc/admin/rounds/${round.id}/courses`),
  });
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<{ code: string; title: string; weeks: string; url: string } | null>(null);
  const [copyFrom, setCopyFrom] = useState("");
  const [note, setNote] = useState<{ tone: "success" | "danger" | "warning"; text: string; list?: string[] } | null>(null);
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["mooc-round", round.id] });
    onChanged();
  };
  const bad = (err: unknown, fallback: string) => setNote({ tone: "danger", text: errorText(err, fallback) });

  const importFile = useMutation({
    mutationFn: () => {
      const data = new FormData();
      data.append("file", file as File);
      return api.upload<{ added: string[]; updated: string[]; already_listed: string[];
        skipped: { course: string; reason: string }[] }>(
        `/mooc/admin/rounds/${round.id}/courses/import`, data);
    },
    onSuccess: (r) => {
      setFile(null);
      setNote({ tone: r.skipped.length ? "warning" : "success",
        text: `${r.added.length + r.updated.length} course(s) listed`
          + (r.already_listed.length ? `, ${r.already_listed.length} already on the list` : "")
          + (r.skipped.length ? `; ${r.skipped.length} skipped:` : "."),
        list: r.skipped.map((s) => s.reason) });
      done();
    },
    onError: (err) => bad(err, "Could not read that file."),
  });
  const add = useMutation({
    mutationFn: () => api.post(`/mooc/admin/rounds/${round.id}/courses`, {
      code: form!.code.trim(), title: form!.title.trim(), weeks: Number(form!.weeks) || 0,
      url: form!.url.trim() || null,
    }),
    onSuccess: () => { setForm(null); setNote({ tone: "success", text: "Course added." }); done(); },
    onError: (err) => bad(err, "Could not add the course."),
  });
  const removeCourse = useMutation({
    mutationFn: (id: number) => api.delete(`/mooc/admin/rounds/${round.id}/courses/${id}`),
    onSuccess: () => { setNote({ tone: "success", text: "Removed from the list." }); done(); },
    onError: (err) => bad(err, "Could not remove it."),
  });
  const copy = useMutation({
    mutationFn: () => api.post<{ message: string }>(
      `/mooc/admin/rounds/${round.id}/courses/copy/${copyFrom}`),
    onSuccess: (r) => { setNote({ tone: "success", text: r.message }); done(); },
    onError: (err) => bad(err, "Could not copy the list."),
  });

  return (
    <div className="space-y-4">
      {note && (
        <Alert variant={note.tone} onDismiss={() => setNote(null)}>
          {note.text}
          {note.list && note.list.length > 0 && (
            <ul className="mt-1 list-disc pl-5">{note.list.map((t, i) => <li key={i}>{t}</li>)}</ul>
          )}
        </Alert>
      )}
      {manage && (
        <Card>
          <CardBody className="space-y-3">
            <p className="text-sm text-ink-muted">
              Import the department's sheet (.xlsx or .csv with Course ID, Course Name, Duration…).
              Only 12-week courses are listed; each counts as 3 credits.
            </p>
            <FileUpload onSelect={setFile} accept=".xlsx,.csv" selectedName={file?.name ?? null}
                        label="Choose the course list" hint="Excel (.xlsx) or .csv" />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" disabled={!file} loading={importFile.isPending}
                      onClick={() => importFile.mutate()}>Import</Button>
              <Button size="sm" variant="secondary"
                      onClick={() => setForm({ code: "", title: "", weeks: "12", url: "" })}
                      icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>Add a course</Button>
              {rounds.filter((r) => r.id !== round.id && r.course_count > 0).length > 0 && (
                <>
                  <Select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)} className="w-64">
                    <option value="">Copy the list from…</option>
                    {rounds.filter((r) => r.id !== round.id && r.course_count > 0).map((r) =>
                      <option key={r.id} value={r.id}>{r.title}</option>)}
                  </Select>
                  <Button size="sm" variant="secondary" disabled={!copyFrom} loading={copy.isPending}
                          onClick={() => copy.mutate()}>Copy</Button>
                </>
              )}
            </div>
            {form && (
              <div className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-4">
                <FormField label="NPTEL course ID" required>
                  <Input value={form.code} placeholder="noc26-cs171"
                         onChange={(e) => setForm({ ...form, code: e.target.value })} />
                </FormField>
                <FormField label="Course name" required className="sm:col-span-2">
                  <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                </FormField>
                <FormField label="Weeks" required>
                  <Input type="number" value={form.weeks}
                         onChange={(e) => setForm({ ...form, weeks: e.target.value })} />
                </FormField>
                <FormField label="NPTEL link" className="sm:col-span-3">
                  <Input value={form.url} placeholder="https://nptel.ac.in/courses/…"
                         onChange={(e) => setForm({ ...form, url: e.target.value })} />
                </FormField>
                <div className="flex items-end gap-2">
                  <Button size="sm" loading={add.isPending}
                          disabled={!form.code.trim() || !form.title.trim()}
                          onClick={() => add.mutate()}>Add</Button>
                  <Button size="sm" variant="secondary" onClick={() => setForm(null)}>Cancel</Button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      )}
      {courses.isLoading ? <LoadingState rows={3} /> : !courses.data?.length ? (
        <EmptyState compact title="No courses on the list yet" />
      ) : (
        <TableWrap>
          <THead>
            <TH>Course</TH><TH>Faculty (SME)</TH><TH>Coordinating institute</TH>
            <TH align="right">Weeks · credits</TH><TH align="right">Chose it</TH>
            {manage && <TH align="right">{" "}</TH>}
          </THead>
          <TBody>
            {courses.data.map((c) => (
              <TR key={c.course_id}>
                <TD>
                  <p className="font-medium text-ink">{c.title}</p>
                  <p className="text-2xs text-ink-subtle">{c.code}{c.discipline ? ` · ${c.discipline}` : ""}</p>
                </TD>
                <TD className="text-xs text-ink-muted">{c.instructors ?? "—"}</TD>
                <TD className="text-xs text-ink-muted">{c.coordinating_institute ?? c.institute ?? "—"}</TD>
                <TD align="right" className="text-xs">{c.weeks} · {c.credits}</TD>
                <TD align="right" className="font-mono">{c.chosen_count ?? 0}</TD>
                {manage && (
                  <TD align="right">
                    <Button size="sm" variant="ghost" disabled={(c.chosen_count ?? 0) > 0}
                            onClick={() => removeCourse.mutate(c.course_id)}
                            icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}>Remove</Button>
                  </TD>
                )}
              </TR>
            ))}
          </TBody>
        </TableWrap>
      )}
    </div>
  );
}

function StudentsTab({ round }: { round: MoocRound }) {
  const [filter, setFilter] = useState("all");
  const [note, setNote] = useState<string | null>(null);
  const roster = useQuery({
    queryKey: ["mooc-round", round.id, "students"],
    queryFn: () => api.get<MoocRosterRow[]>(`/mooc/admin/rounds/${round.id}/students`),
  });
  const remind = useMutation({
    mutationFn: () => api.post<{ notified: number }>(`/mooc/admin/rounds/${round.id}/remind`),
    onSuccess: (r) => setNote(`Reminder sent to ${pluralise(r.notified, "student")} who have not chosen.`),
    onError: (err) => setNote(errorText(err, "Could not send the reminder.")),
  });
  const rows = (roster.data ?? []).filter((r) =>
    filter === "all" ? true : filter === "none" ? !r.option
      : filter === "carry" ? r.carry_over : r.option === filter);
  const waiting = (roster.data ?? []).filter((r) => !r.option).length;

  return (
    <div className="space-y-3">
      {note && <Alert variant="info" onDismiss={() => setNote(null)}>{note}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="w-56">
          <option value="all">Everyone ({roster.data?.length ?? 0})</option>
          <option value="none">Not chosen yet ({waiting})</option>
          <option value="NPTEL">Chose NPTEL</option>
          <option value="NCC">Chose NCC</option>
          <option value="carry">Carried over</option>
        </Select>
        {round.can_manage && round.status === "OPEN" && waiting > 0 && (
          <Button size="sm" variant="secondary" loading={remind.isPending}
                  onClick={() => remind.mutate()} icon={<Send className="h-3.5 w-3.5" aria-hidden />}>
            Remind the {waiting} who have not chosen
          </Button>
        )}
        <Button size="sm" variant="secondary" className="ml-auto"
                onClick={() => void downloadProtectedFile(`/mooc/admin/rounds/${round.id}/export`)}
                icon={<Download className="h-3.5 w-3.5" aria-hidden />}>
          Export CSV
        </Button>
      </div>
      {roster.isLoading ? <LoadingState rows={4} /> : (
        <TableWrap>
          <THead>
            <TH>Student</TH><TH>Sem</TH><TH>Choice</TH><TH>Status</TH><TH>Certificate</TH>
          </THead>
          <TBody>
            {rows.map((r) => (
              <TR key={r.student_id}>
                <TD>
                  <p className="font-medium text-ink">{r.student_name}</p>
                  <p className="text-2xs text-ink-subtle">
                    {r.roll_number}{r.carry_over && <Badge tone="warning" className="ml-1.5">Carried over</Badge>}
                  </p>
                </TD>
                <TD className="text-xs">{r.semester ? roman(r.semester) : "—"}</TD>
                <TD className="text-xs">
                  {r.option ? <><span className="font-medium text-ink">{r.course_title}</span>
                    {r.option === "NPTEL" && <p className="text-2xs text-ink-subtle">{r.course_code}</p>}</>
                    : <span className="text-ink-subtle">Not chosen</span>}
                </TD>
                <TD>{r.status ? <StatusBadge status={r.status === "FAILED" ? "Not passed" : r.status} /> : "—"}</TD>
                <TD className="text-xs">
                  {r.certificate_url ? (
                    <a href={r.certificate_url} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                      View · {r.verification_status?.toLowerCase()}
                    </a>
                  ) : "—"}
                </TD>
              </TR>
            ))}
          </TBody>
        </TableWrap>
      )}
    </div>
  );
}
