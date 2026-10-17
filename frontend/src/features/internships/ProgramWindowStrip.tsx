import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Clock, Users } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deadlineLabel, formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InternshipWindow, MentorRosterGroup, ProgramWindows } from "@/types";
import { MentorRosterList } from "./ProgramWindowsPage";

const LABEL = { REGISTRATION: "Registration", PRESENTATION: "Posters, presentation & marks" } as const;

/**
 * What a student needs to know about a window-run programme: which step is
 * open, until when, and what the coordinator said. The deadlines shown here
 * are informational — the server enforces them.
 */
export function ProgramWindowStrip({ programId }: { programId: number }) {
  const { user } = useAuth();
  const [rosterOpen, setRosterOpen] = useState(false);
  const query = useQuery({
    queryKey: ["internship-windows", programId],
    queryFn: () => api.get<ProgramWindows>(`/internships/programs/${programId}/windows`),
  });
  if (query.isLoading) return <div className="skeleton mt-4 h-16 rounded-lg" />;
  if (!query.data) return null;

  const { kinds, windows } = query.data;
  const byKind = Object.fromEntries(windows.map((w) => [w.kind, w])) as Record<string, InternshipWindow>;
  const presentation = byKind.PRESENTATION;

  return (
    <div className="mt-4 space-y-2">
      {kinds.map((kind) => {
        const w = byKind[kind];
        return (
          <div
            key={kind}
            className={cn(
              "rounded-lg border px-3.5 py-3",
              w?.state === "OPEN" ? "border-accent/30 bg-accent-soft/50" : "border-line bg-surface-sunken",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                <CalendarClock className="h-4 w-4 text-ink-subtle" aria-hidden />
                {LABEL[kind]}
              </p>
              <Badge tone={!w ? "neutral" : w.state === "OPEN" ? "success" : w.state === "SCHEDULED" ? "info" : "neutral"}>
                {!w ? "Not announced yet" : w.state === "OPEN" ? "Open" : w.state === "SCHEDULED" ? "Opens soon" : "Closed"}
              </Badge>
            </div>
            {w && <WindowDates window={w} />}
            {w && w.state !== "CLOSED" && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-accent">Message from the coordinator</summary>
                <p className="mt-1.5 whitespace-pre-line text-xs text-ink-muted">{w.message}</p>
              </details>
            )}
          </div>
        );
      })}
      {presentation && (
        <Button size="sm" variant="secondary" icon={<Users className="h-3.5 w-3.5" aria-hidden />}
                onClick={() => setRosterOpen(true)}>
          Mentor list
        </Button>
      )}
      {rosterOpen && (
        <RosterModal programId={programId} roll={user?.student?.roll_number}
                     onClose={() => setRosterOpen(false)} />
      )}
    </div>
  );
}

function WindowDates({ window: w }: { window: InternshipWindow }) {
  const deadline = deadlineLabel(w.closed_early_at ?? w.closes_at);
  return (
    <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
      {w.state === "SCHEDULED" && (
        <div><dt className="inline text-ink-subtle">Opens </dt><dd className="inline text-ink">{formatDateTime(w.opens_at)}</dd></div>
      )}
      {w.kind === "PRESENTATION" && (
        <>
          <div><dt className="inline text-ink-subtle">Poster to mentor by </dt><dd className="inline text-ink">{formatDateTime(w.submission_due_at)}</dd></div>
          <div>
            <dt className="inline text-ink-subtle">Presentation </dt>
            <dd className="inline text-ink">
              {formatDate(w.presentation_from)}
              {w.presentation_to && w.presentation_to !== w.presentation_from && ` – ${formatDate(w.presentation_to)}`}
            </dd>
          </div>
        </>
      )}
      <div className="flex items-center gap-1">
        <Clock className="h-3 w-3 text-ink-subtle" aria-hidden />
        <dt className="text-ink-subtle">{w.kind === "PRESENTATION" ? "Closes" : "Deadline"}</dt>
        <dd className={cn("font-medium", w.state === "OPEN" ? "text-ink" : "text-ink-muted")}>
          {formatDateTime(w.closed_early_at ?? w.closes_at)}
          {w.state === "OPEN" && deadline.tone !== "neutral" && (
            <span className={cn("ml-1", deadline.tone === "danger" ? "text-danger" : "text-warning")}>({deadline.text})</span>
          )}
        </dd>
      </div>
    </dl>
  );
}

function RosterModal({ programId, roll, onClose }: { programId: number; roll?: string; onClose: () => void }) {
  const roster = useQuery({
    queryKey: ["mentor-roster", programId],
    queryFn: () => api.get<MentorRosterGroup[]>(`/internships/programs/${programId}/mentor-roster`),
  });
  return (
    <Modal open onClose={onClose} size="lg" title="Mentor list"
           description="Faculty mentors and the roll numbers each one mentors.">
      {roster.isLoading ? <LoadingState rows={3} /> : roster.error ? (
        <ErrorState onRetry={() => roster.refetch()} compact />
      ) : (
        <MentorRosterList groups={roster.data ?? []} highlightRoll={roll} />
      )}
    </Modal>
  );
}
