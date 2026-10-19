import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock, CheckCircle2, ClipboardSignature, Lock, Megaphone, PencilLine,
  Presentation, UserCheck, Users,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Misc";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn, roman } from "@/lib/utils";
import type {
  InternshipProgram, InternshipWindow, InternshipWindowKind, MentorRosterGroup,
  ProgramWindows,
} from "@/types";

/**
 * The coordinator's view of a window-run programme (CSSI): registration, then
 * mentor allocation, then posters, presentations and marks — each opened here
 * with dates and a message that goes to every student it concerns.
 *
 * The server is the authority on every rule shown here; this screen explains
 * why a step is locked, it does not decide it.
 */

const STEP_COPY: Record<InternshipWindowKind, { title: string; icon: typeof Users; blurb: string }> = {
  REGISTRATION: {
    title: "Registration",
    icon: ClipboardSignature,
    blurb:
      "Students record their organisation and their supervisor's name and phone number. " +
      "It can open in the semester before the programme runs. Locks at the deadline.",
  },
  PRESENTATION: {
    title: "Posters, presentations and marks",
    icon: Presentation,
    blurb:
      "Every student is told their faculty mentor. Posters go to the mentor by the poster " +
      "deadline; mentors record marks after the presentation. Marks lock at the deadline.",
  },
};

const STATE_TONE = { OPEN: "success", SCHEDULED: "info", CLOSED: "neutral" } as const;
const STATE_LABEL = { OPEN: "Open", SCHEDULED: "Scheduled", CLOSED: "Closed" } as const;

/** `<input type="datetime-local">` speaks local time without a zone. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

export function ProgramWindowsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const programs = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });
  const windowed = useMemo(
    () => (programs.data ?? []).filter((p) => p.window_kinds.length > 0 && p.can_manage),
    [programs.data],
  );
  const requested = Number(searchParams.get("program_id"));
  const program = windowed.find((p) => p.id === requested) ?? windowed[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Windows & deadlines"
        description="Open each step of the programme with its dates and the message students receive. Every deadline is enforced by the server."
        breadcrumbs={[{ label: "Internships", to: "/internships" }, { label: "Windows & deadlines" }]}
        actions={
          windowed.length > 1 ? (
            <Select
              aria-label="Programme"
              value={program?.id ?? ""}
              onChange={(e) => setSearchParams({ program_id: e.target.value })}
              className="w-72"
            >
              {windowed.map((p) => (
                <option key={p.id} value={p.id}>{p.name} · {p.code}</option>
              ))}
            </Select>
          ) : undefined
        }
      />

      {programs.isLoading ? (
        <LoadingState rows={3} />
      ) : programs.error ? (
        <ErrorState onRetry={() => programs.refetch()} />
      ) : !program ? (
        <Card>
          <EmptyState
            title="No window-run programme to manage"
            description="Programmes appear here when they run in coordinator-opened windows and you coordinate them."
            icon={<CalendarClock className="h-5 w-5" aria-hidden />}
          />
        </Card>
      ) : (
        <ProgramTimeline program={program} />
      )}
    </div>
  );
}

function ProgramTimeline({ program }: { program: InternshipProgram }) {
  const query = useQuery({
    queryKey: ["internship-windows", program.id],
    queryFn: () => api.get<ProgramWindows>(`/internships/programs/${program.id}/windows`),
  });
  if (query.isLoading) return <LoadingState rows={3} />;
  if (query.error || !query.data) return <ErrorState onRetry={() => query.refetch()} />;

  const data = query.data;
  const byKind = Object.fromEntries(data.windows.map((w) => [w.kind, w])) as
    Partial<Record<InternshipWindowKind, InternshipWindow>>;
  const registration = byKind.REGISTRATION;
  const presentation = byKind.PRESENTATION;
  const registrationStarted = Boolean(registration && registration.state !== "SCHEDULED");

  const presentationBlocker =
    !registration ? "Run the registration window first."
    : registration.state === "OPEN" ? "Registration is still open — close it, or wait for its deadline."
    : registration.state === "SCHEDULED" ? "Registration has not opened yet."
    : data.unassigned_count > 0 ? `${data.unassigned_count} registered students still need a faculty mentor.`
    : null;

  return (
    <ol className="relative space-y-4 before:absolute before:bottom-6 before:left-[1.35rem] before:top-6 before:w-px before:bg-line sm:before:left-[1.6rem]">
      {data.kinds.includes("REGISTRATION") && (
        <WindowStep
          index={1} kind="REGISTRATION" program={program} window={registration}
          canManage={data.can_manage}
          extra={registration && (
            <Fact label="Registered">{data.registered_count} students</Fact>
          )}
        />
      )}

      <Step
        index={data.kinds.includes("REGISTRATION") ? 2 : 1}
        icon={UserCheck}
        title="Mentor allocation"
        state={!registrationStarted ? "LOCKED" : data.unassigned_count === 0 && data.registered_count > 0 ? "DONE" : "ACTIVE"}
        blurb="Allocate faculty mentors once students have registered. Opening the next window tells every student who their mentor is."
      >
        {!registrationStarted ? (
          <LockedNote>Opens once the registration window has started.</LockedNote>
        ) : (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <Fact label="Registered">{data.registered_count}</Fact>
            <Fact label="Without a mentor">
              <span className={data.unassigned_count ? "text-warning" : "text-success"}>{data.unassigned_count}</span>
            </Fact>
            <LinkButton
              to={`/internships/mentor-assignment?program_id=${program.id}`}
              size="sm" variant="secondary" icon={<UserCheck className="h-3.5 w-3.5" aria-hidden />}
              className="ml-auto"
            >
              Allocate mentors
            </LinkButton>
          </div>
        )}
      </Step>

      {data.kinds.includes("PRESENTATION") && (
        <WindowStep
          index={data.kinds.includes("REGISTRATION") ? 3 : 2}
          kind="PRESENTATION" program={program} window={presentation}
          canManage={data.can_manage} blocker={presentationBlocker}
        />
      )}
    </ol>
  );
}

type StepState = "LOCKED" | "ACTIVE" | "DONE" | InternshipWindow["state"] | "NOT_STARTED";

function Step({
  index, icon: Icon, title, state, blurb, children, actions,
}: {
  index: number; icon: typeof Users; title: string; state: StepState; blurb: string;
  children?: ReactNode; actions?: ReactNode;
}) {
  const dot =
    state === "OPEN" || state === "ACTIVE" ? "bg-accent text-accent-fg shadow-glow-accent"
    : state === "DONE" || state === "CLOSED" ? "bg-success-solid text-white"
    : state === "SCHEDULED" ? "bg-info text-info-fg"
    : "bg-surface-muted text-ink-subtle border border-line";
  return (
    <li className="relative">
      <Card className={cn("ml-11 sm:ml-14", state === "LOCKED" && "opacity-80")}>
        <span
          aria-hidden
          className={cn("absolute left-0 top-5 flex h-11 w-11 items-center justify-center rounded-full sm:h-[3.2rem] sm:w-[3.2rem]", dot)}
        >
          {state === "DONE" || state === "CLOSED" ? <CheckCircle2 className="h-5 w-5" /> : <Icon className="h-5 w-5" />}
        </span>
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">Step {index}</p>
            <h2 className="mt-0.5 flex flex-wrap items-center gap-2 font-heading text-md font-semibold text-ink">
              {title}
              {state in STATE_LABEL && (
                <Badge tone={STATE_TONE[state as keyof typeof STATE_TONE]}>{STATE_LABEL[state as keyof typeof STATE_LABEL]}</Badge>
              )}
              {state === "NOT_STARTED" && <Badge tone="neutral">Not started</Badge>}
              {state === "LOCKED" && <Badge tone="neutral" icon={<Lock className="h-3 w-3" aria-hidden />}>Locked</Badge>}
              {state === "DONE" && <Badge tone="success">Done</Badge>}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-ink-muted">{blurb}</p>
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
        <div className="px-5 py-4">{children}</div>
      </Card>
    </li>
  );
}

function WindowStep({
  index, kind, program, window, canManage, blocker, extra,
}: {
  index: number; kind: InternshipWindowKind; program: InternshipProgram;
  window: InternshipWindow | undefined; canManage: boolean; blocker?: string | null;
  extra?: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<"open" | "edit" | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [showRoster, setShowRoster] = useState(false);
  const copy = STEP_COPY[kind];

  const close = useMutation({
    mutationFn: () => api.post<InternshipWindow>(`/internships/windows/${window!.id}/close`),
    onSuccess: () => {
      setConfirmClose(false);
      void queryClient.invalidateQueries({ queryKey: ["internship-windows", program.id] });
    },
  });

  const state: StepState = window ? window.state : blocker ? "LOCKED" : "NOT_STARTED";

  return (
    <>
      <Step
        index={index} icon={copy.icon} title={copy.title} state={state} blurb={copy.blurb}
        actions={canManage && (
          window ? (
            <>
              <Button size="sm" variant="secondary" icon={<PencilLine className="h-3.5 w-3.5" aria-hidden />}
                      onClick={() => setEditing("edit")}>
                {window.state === "CLOSED" ? "Reopen / extend" : "Edit dates"}
              </Button>
              {window.state === "OPEN" && (
                <Button size="sm" variant="ghost" className="text-danger" onClick={() => setConfirmClose(true)}>
                  Close now
                </Button>
              )}
            </>
          ) : (
            <Button size="sm" variant="accent" disabled={Boolean(blocker)}
                    icon={<Megaphone className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => setEditing("open")}>
              Open & notify
            </Button>
          )
        )}
      >
        {!window ? (
          blocker ? <LockedNote>{blocker}</LockedNote> : (
            <p className="text-sm text-ink-muted">
              Not opened yet. Opening it sends your message to every student it concerns.
            </p>
          )
        ) : (
          <div className="space-y-4">
            <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
              <Fact label="Opens">{formatDateTime(window.opens_at)}</Fact>
              {window.kind === "PRESENTATION" && (
                <>
                  <Fact label="Posters due">{formatDateTime(window.submission_due_at)}</Fact>
                  <Fact label="Presentation">
                    {formatDate(window.presentation_from)}
                    {window.presentation_to && window.presentation_to !== window.presentation_from && ` – ${formatDate(window.presentation_to)}`}
                  </Fact>
                </>
              )}
              <Fact label={window.kind === "PRESENTATION" ? "Marks lock" : "Deadline"}>
                <span className={window.state === "OPEN" ? "text-ink" : "text-ink-muted"}>
                  {formatDateTime(window.closed_early_at ?? window.closes_at)}
                </span>
              </Fact>
              {window.cohort_semester && <Fact label="For">Semester {roman(window.cohort_semester)} students</Fact>}
              {extra}
            </div>
            <details className="group rounded-lg border border-line bg-surface-sunken px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-ink">Message sent to students</summary>
              <p className="mt-2 whitespace-pre-line text-sm text-ink-muted">{window.message}</p>
            </details>
            {window.kind === "PRESENTATION" && (
              <Button size="sm" variant="secondary" icon={<Users className="h-3.5 w-3.5" aria-hidden />}
                      onClick={() => setShowRoster(true)}>
                Mentor list sent to students
              </Button>
            )}
          </div>
        )}
        {close.isError && (
          <Alert variant="danger" className="mt-3">
            {close.error instanceof ApiError ? close.error.message : "Could not close the window."}
          </Alert>
        )}
      </Step>

      {editing && (
        <WindowFormModal
          kind={kind} program={program} window={editing === "edit" ? window : undefined}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={confirmClose} onClose={() => setConfirmClose(false)} onConfirm={() => close.mutate()}
        loading={close.isPending} destructive
        title={`Close ${copy.title.toLowerCase()} now?`}
        message={kind === "PRESENTATION"
          ? "Mentors will no longer be able to enter or change marks. You can reopen it later by extending the deadline."
          : "Students will no longer be able to register or change their details. You can reopen it later by extending the deadline."}
        confirmLabel="Close now"
      />
      {showRoster && <RosterModal programId={program.id} onClose={() => setShowRoster(false)} />}
    </>
  );
}

function WindowFormModal({
  kind, program, window, onClose,
}: {
  kind: InternshipWindowKind; program: InternshipProgram; window?: InternshipWindow;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  // The semesters the server accepts (internship_windows.open_window): the one
  // the programme is announced in and the one it runs in. CSSI: II and III;
  // Summer Internship: VI only. Guessing "the semester before" offered V for
  // Summer Internship, which the server then refused.
  const cohortOptions = Array.from(new Set(
    [program.announce_from_semester ?? program.target_semester, program.target_semester]
      .filter((s): s is number => Boolean(s && s > 0)),
  )).sort((a, b) => a - b);

  const [form, setForm] = useState({
    title: window?.title ?? `${program.name} — ${STEP_COPY[kind].title.toLowerCase()}`,
    message: window?.message ?? "",
    opens_at: toLocalInput(window?.opens_at ?? new Date().toISOString()),
    closes_at: toLocalInput(window?.closes_at),
    cohort_semester: String(window?.cohort_semester ?? cohortOptions[0] ?? ""),
    submission_due_at: toLocalInput(window?.submission_due_at),
    presentation_from: window?.presentation_from ?? "",
    presentation_to: window?.presentation_to ?? "",
  });
  const set = (key: keyof typeof form) =>
    (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const save = useMutation({
    mutationFn: () => {
      const dates = {
        opens_at: fromLocalInput(form.opens_at),
        closes_at: fromLocalInput(form.closes_at),
        ...(kind === "PRESENTATION" && {
          submission_due_at: fromLocalInput(form.submission_due_at),
          presentation_from: form.presentation_from || null,
          presentation_to: form.presentation_to || null,
        }),
      };
      return window
        ? api.patch<InternshipWindow>(`/internships/windows/${window.id}`, { ...dates, message: form.message })
        : api.post<InternshipWindow>(`/internships/programs/${program.id}/windows`, {
            kind, title: form.title, message: form.message, ...dates,
            ...(kind === "REGISTRATION" && { cohort_semester: Number(form.cohort_semester) || null }),
          });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["internship-windows", program.id] });
      void queryClient.invalidateQueries({ queryKey: ["internship-programs"] });
      onClose();
    },
  });

  const ready = form.message.trim() && form.opens_at && form.closes_at
    && (kind !== "PRESENTATION" || (form.submission_due_at && form.presentation_from));

  return (
    <Modal
      open onClose={onClose} size="lg"
      title={window ? `Update ${STEP_COPY[kind].title.toLowerCase()}` : `Open ${STEP_COPY[kind].title.toLowerCase()}`}
      description={window
        ? "Students and mentors are notified of the new dates. Extending a closed window reopens it."
        : kind === "PRESENTATION"
          ? "Each student is sent your message with their faculty mentor, the poster deadline and the presentation day; each mentor is sent their list."
          : "Your message goes to every student in the chosen semester of this programme's department."}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="accent" size="sm" loading={save.isPending} disabled={!ready}
                  onClick={() => save.mutate()}>
            {window ? "Save and notify" : "Open and notify"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {save.isError && (
          <Alert variant="danger">
            {save.error instanceof ApiError ? save.error.message : "Could not save the window."}
          </Alert>
        )}
        {!window && (
          <FormField label="Title" htmlFor="w-title">
            <Input id="w-title" value={form.title} onChange={set("title")} maxLength={180} />
          </FormField>
        )}
        <FormField
          label="Message to students" htmlFor="w-message" required
          hint={kind === "REGISTRATION"
            ? "What the programme is, what students must do, and anything they need before registering."
            : "What to put on the poster, how presentations will run, and anything to bring."}
        >
          <Textarea id="w-message" rows={6} value={form.message} onChange={set("message")} maxLength={5000} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Opens" htmlFor="w-open" required>
            <Input id="w-open" type="datetime-local" value={form.opens_at} onChange={set("opens_at")} />
          </FormField>
          <FormField label={kind === "PRESENTATION" ? "Marks lock (process deadline)" : "Deadline"} htmlFor="w-close" required>
            <Input id="w-close" type="datetime-local" value={form.closes_at} onChange={set("closes_at")} />
          </FormField>
          {kind === "REGISTRATION" && !window && cohortOptions.length > 0 && (
            <FormField label="Students in" htmlFor="w-cohort"
                       hint={cohortOptions.length > 1 ? "Registration may open the semester before the programme runs." : undefined}>
              <Select id="w-cohort" value={form.cohort_semester} onChange={set("cohort_semester")}>
                {cohortOptions.map((s) => <option key={s} value={s}>Semester {roman(s)}</option>)}
              </Select>
            </FormField>
          )}
          {kind === "PRESENTATION" && (
            <>
              <FormField label="Posters due to mentor" htmlFor="w-due" required>
                <Input id="w-due" type="datetime-local" value={form.submission_due_at} onChange={set("submission_due_at")} />
              </FormField>
              <FormField label="Presentation day" htmlFor="w-from" required>
                <Input id="w-from" type="date" value={form.presentation_from} onChange={set("presentation_from")} />
              </FormField>
              <FormField label="Last presentation day" htmlFor="w-to" hint="Leave empty for a single day.">
                <Input id="w-to" type="date" value={form.presentation_to} onChange={set("presentation_to")} />
              </FormField>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}

function RosterModal({ programId, onClose }: { programId: number; onClose: () => void }) {
  const roster = useQuery({
    queryKey: ["mentor-roster", programId],
    queryFn: () => api.get<MentorRosterGroup[]>(`/internships/programs/${programId}/mentor-roster`),
  });
  return (
    <Modal open onClose={onClose} size="lg" title="Mentor list"
           description="The list students were sent, grouped by mentor in roll-number order.">
      {roster.isLoading ? <LoadingState rows={3} /> : roster.error ? (
        <ErrorState onRetry={() => roster.refetch()} compact />
      ) : (
        <MentorRosterList groups={roster.data ?? []} />
      )}
    </Modal>
  );
}

export function MentorRosterList({ groups, highlightRoll }: { groups: MentorRosterGroup[]; highlightRoll?: string }) {
  if (!groups.length) return <EmptyState compact title="No mentors allocated yet" />;
  return (
    <ul className="divide-y divide-line rounded-lg border border-line">
      {groups.map((g) => {
        const mine = highlightRoll && g.students.some((s) => s.roll_number === highlightRoll);
        return (
          <li key={g.faculty_id} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3", mine && "bg-accent-soft/60")}>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-ink" title={g.name}>
                {g.name} {mine && <Badge tone="accent" className="ml-1">Your mentor</Badge>}
              </span>
              <span className="block truncate text-xs text-ink-subtle">
                {[g.designation, g.cabin && `Cabin ${g.cabin}`, g.email].filter(Boolean).join(" · ")}
              </span>
            </span>
            <span className="font-mono text-xs text-ink-muted">{g.roll_range}</span>
            <Badge tone="neutral">{g.students.length}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-ink break-anywhere">{children}</p>
    </div>
  );
}

function LockedNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-2 text-sm text-ink-muted">
      <Lock className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden /> {children}
    </p>
  );
}

/** Small link used by other screens to send the coordinator here. */
export function WindowsLink({ programId, children }: { programId: number; children: ReactNode }) {
  return (
    <Link to={`/internships/windows?program_id=${programId}`} className="font-semibold text-accent hover:underline">
      {children}
    </Link>
  );
}
