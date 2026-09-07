import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus, Mail, MapPin, MessageSquare, Phone, UserSquare2, Users2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardAction, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { Avatar, DetailList, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { MenteeTable } from "@/features/engagement/MenteeTable";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { Meeting, MenteeRow, MentorProfile } from "@/types";

export function MentorshipPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [requestOpen, setRequestOpen] = useState(false);
  const [decide, setDecide] = useState<Meeting | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [menteeSearch, setMenteeSearch] = useState("");

  const isStudent = Boolean(user?.student);

  const mentor = useQuery({
    queryKey: ["my-mentor"],
    queryFn: () => api.get<MentorProfile | null>("/mentorship/my-mentor"),
    enabled: isStudent,
  });

  const meetings = useQuery({
    queryKey: ["meetings"],
    queryFn: () => api.get<Meeting[]>("/mentorship/meetings"),
  });

  // Faculty only. The endpoint scopes to the caller's own active assignments,
  // so a faculty member who mentors nobody gets an empty list, not everyone's.
  const mentees = useQuery({
    queryKey: ["my-mentees"],
    queryFn: () => api.get<MenteeRow[]>("/mentorship/my-mentees"),
    enabled: !isStudent,
  });

  const menteeRows = useMemo(() => {
    const needle = menteeSearch.trim().toLowerCase();
    if (!needle) return mentees.data ?? [];
    return (mentees.data ?? []).filter((row) =>
      `${row.full_name} ${row.roll_number}`.toLowerCase().includes(needle),
    );
  }, [mentees.data, menteeSearch]);

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    void queryClient.invalidateQueries({ queryKey: ["calendar"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  return (
    <div>
      <PageHeader
        title="Mentor–Mentee"
        description={
          isStudent
            ? "Your assigned faculty mentor, meeting requests and mentorship announcements."
            : "The students you mentor, and the meeting requests they raise."
        }
        breadcrumbs={[{ label: "Support" }, { label: "Mentor–Mentee" }]}
        actions={
          isStudent && (
            <Button size="sm" onClick={() => setRequestOpen(true)}
                    icon={<CalendarPlus className="h-3.5 w-3.5" aria-hidden />}>
              Request a meeting
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

      <div className="grid gap-5 lg:grid-cols-3">
        {isStudent && (
          <Card className="lg:col-span-1">
            <CardHeader title="Your mentor"
                        icon={<UserSquare2 className="h-4 w-4 text-ink-subtle" aria-hidden />} />
            {mentor.isLoading ? (
              <LoadingState rows={2} />
            ) : !mentor.data ? (
              <EmptyState
                compact
                title="No mentor assigned yet"
                description="The department assigns a faculty mentor at the start of each academic year."
              />
            ) : (
              <CardBody>
                <div className="flex items-start gap-3">
                  <Avatar name={mentor.data.full_name} src={mentor.data.avatar_url} size="lg" />
                  <div className="min-w-0">
                    <p className="text-md font-semibold text-ink">{mentor.data.full_name}</p>
                    <p className="text-xs text-ink-muted">{mentor.data.designation}</p>
                    <p className="text-xs text-ink-subtle">{mentor.data.department_name}</p>
                  </div>
                </div>
                <dl className="mt-4 space-y-2 text-xs">
                  {mentor.data.cabin && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      Cabin {mentor.data.cabin}
                    </div>
                  )}
                  {mentor.data.email && (
                    <a href={`mailto:${mentor.data.email}`}
                       className="flex items-center gap-2 text-ink-muted hover:text-accent">
                      <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate">{mentor.data.email}</span>
                    </a>
                  )}
                  {mentor.data.phone && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      {mentor.data.phone}
                    </div>
                  )}
                </dl>
                {mentor.data.specialization && (
                  <div className="mt-4 border-t border-line pt-3">
                    <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      Specialisation
                    </p>
                    <p className="mt-0.5 text-sm text-ink-muted">{mentor.data.specialization}</p>
                  </div>
                )}
              </CardBody>
            )}
          </Card>
        )}

        <Card className={isStudent ? "lg:col-span-2" : "lg:col-span-3"}>
          <CardHeader
            title="Meetings"
            description={
              isStudent
                ? "Requests you have raised and their current status."
                : "Approve, reschedule or close out mentee meeting requests."
            }
            icon={<MessageSquare className="h-4 w-4 text-ink-subtle" aria-hidden />}
          />
          {meetings.isLoading ? (
            <LoadingState rows={3} />
          ) : meetings.error ? (
            <ErrorState onRetry={() => meetings.refetch()} compact />
          ) : !meetings.data?.length ? (
            <EmptyState
              compact
              title="No meetings yet"
              description={isStudent
                ? "Raise a request with a short agenda so your mentor can prepare."
                : "Requests raised by your mentees will appear here."}
            />
          ) : (
            <ul className="divide-y divide-line">
              {meetings.data.map((meeting) => (
                <li key={meeting.id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink">{meeting.title}</p>
                      <p className="mt-0.5 text-xs text-ink-muted">
                        {isStudent
                          ? meeting.faculty_name
                          : `${meeting.student_name} · ${meeting.roll_number}`}
                      </p>
                      {meeting.agenda && (
                        <p className="mt-1.5 text-sm text-ink-muted">{meeting.agenda}</p>
                      )}
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-ink-subtle">
                        <span>Requested {relativeTime(meeting.requested_at)}</span>
                        {meeting.scheduled_at && (
                          <span>Scheduled {formatDateTime(meeting.scheduled_at)}</span>
                        )}
                        {!meeting.scheduled_at && meeting.proposed_slot && (
                          <span>Proposed {formatDateTime(meeting.proposed_slot)}</span>
                        )}
                        <span>{humanise(meeting.mode)}</span>
                        {meeting.location && <span>{meeting.location}</span>}
                      </div>
                      {meeting.outcome_notes && (
                        <p className="mt-2 rounded bg-surface-muted px-2.5 py-1.5 text-xs text-ink-muted">
                          {meeting.outcome_notes}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={meeting.status} />
                      {!isStudent && meeting.status === "REQUESTED" && (
                        <Button size="sm" variant="secondary" onClick={() => setDecide(meeting)}>
                          Respond
                        </Button>
                      )}
                      {!isStudent && meeting.status === "APPROVED" && (
                        <Button size="sm" variant="ghost" onClick={() => setDecide(meeting)}>
                          Update
                        </Button>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {!isStudent && (
        <Card className="mt-5">
          <CardHeader
            title={
              mentees.data
                ? `${mentees.data.length} mentee${mentees.data.length === 1 ? "" : "s"}`
                : "My mentees"
            }
            description="Students assigned to you for academic mentorship this academic year."
            icon={<Users2 className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              <div className="flex items-center gap-3">
                {Boolean(mentees.data?.length) && (
                  <SearchInput
                    value={menteeSearch} onChange={setMenteeSearch}
                    placeholder="Name or roll number" className="w-full sm:w-56"
                  />
                )}
                <CardAction to="/mentorship/mentees" label="Open the full mentee list">
                  View all
                </CardAction>
              </div>
            }
          />
          {mentees.isLoading ? (
            <LoadingState rows={4} />
          ) : mentees.error ? (
            <ErrorState onRetry={() => mentees.refetch()} compact />
          ) : !mentees.data?.length ? (
            <EmptyState
              compact
              title="No mentees assigned"
              description="The department administrator assigns mentees each academic year."
              icon={<Users2 className="h-5 w-5" aria-hidden />}
            />
          ) : (
            <MenteeTable rows={menteeRows} search={menteeSearch} />
          )}
        </Card>
      )}

      {requestOpen && (
        <RequestMeetingModal
          onClose={() => setRequestOpen(false)}
          onDone={() => {
            setRequestOpen(false);
            setBanner({ tone: "success", text: "Meeting request sent to your mentor." });
            invalidate();
          }}
          onError={(text) => setBanner({ tone: "danger", text })}
        />
      )}

      {decide && (
        <DecideMeetingModal
          meeting={decide}
          onClose={() => setDecide(null)}
          onDone={() => {
            setDecide(null);
            setBanner({ tone: "success", text: "Meeting updated." });
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function RequestMeetingModal({
  onClose, onDone, onError,
}: { onClose: () => void; onDone: () => void; onError: (text: string) => void }) {
  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");
  const [slot, setSlot] = useState("");
  const [mode, setMode] = useState("IN_PERSON");
  const [duration, setDuration] = useState(30);

  const request = useMutation({
    mutationFn: () =>
      api.post("/mentorship/meetings", {
        title, agenda: agenda || null,
        proposed_slot: slot ? new Date(slot).toISOString() : null,
        duration_minutes: duration, mode,
      }),
    onSuccess: onDone,
    onError: (err) =>
      onError(err instanceof ApiError ? err.message : "Could not send the request."),
  });

  return (
    <Modal
      open onClose={onClose} title="Request a meeting"
      description="Your mentor will confirm or propose another slot."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={title.trim().length < 3} loading={request.isPending}
                  onClick={() => request.mutate()}>
            Send request
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Subject" required>
          <Input value={title} onChange={(e) => setTitle(e.target.value)}
                 placeholder="e.g. Semester VI elective guidance" data-autofocus />
        </FormField>
        <FormField label="Agenda" hint="A sentence or two helps your mentor prepare.">
          <Textarea value={agenda} onChange={(e) => setAgenda(e.target.value)} rows={3} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Preferred slot">
            <Input type="datetime-local" value={slot} onChange={(e) => setSlot(e.target.value)} />
          </FormField>
          <FormField label="Duration">
            <Select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
              {[15, 30, 45, 60].map((value) => (
                <option key={value} value={value}>{value} minutes</option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField label="Mode">
          <Select value={mode} onChange={(e) => setMode(e.target.value)}>
            {["IN_PERSON", "ONLINE", "PHONE"].map((value) => (
              <option key={value} value={value}>{humanise(value)}</option>
            ))}
          </Select>
        </FormField>
      </div>
    </Modal>
  );
}

function DecideMeetingModal({
  meeting, onClose, onDone,
}: { meeting: Meeting; onClose: () => void; onDone: () => void }) {
  const [status, setStatus] = useState(
    meeting.status === "REQUESTED" ? "APPROVED" : "COMPLETED",
  );
  const [scheduledAt, setScheduledAt] = useState(
    meeting.proposed_slot ? meeting.proposed_slot.slice(0, 16) : "",
  );
  const [location, setLocation] = useState(meeting.location ?? "");
  const [notes, setNotes] = useState(meeting.outcome_notes ?? "");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: () =>
      api.post(`/mentorship/meetings/${meeting.id}/decision`, {
        status,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        location: location || null,
        outcome_notes: notes || null,
      }),
    onSuccess: onDone,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not update the meeting."),
  });

  return (
    <Modal
      open onClose={onClose} title="Respond to meeting request"
      description={`${meeting.student_name} · ${meeting.title}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={decide.isPending} onClick={() => decide.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        {meeting.agenda && (
          <DetailList columns={1} items={[{ label: "Agenda", value: meeting.agenda }]} />
        )}
        <FormField label="Decision">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {["APPROVED", "RESCHEDULED", "DECLINED", "COMPLETED", "CANCELLED"].map((value) => (
              <option key={value} value={value}>{humanise(value)}</option>
            ))}
          </Select>
        </FormField>
        {(status === "APPROVED" || status === "RESCHEDULED") && (
          <>
            <FormField label="Scheduled date and time" required>
              <Input type="datetime-local" value={scheduledAt}
                     onChange={(e) => setScheduledAt(e.target.value)} />
            </FormField>
            <FormField label="Location">
              <Input value={location} onChange={(e) => setLocation(e.target.value)}
                     placeholder="e.g. Cabin 6-201 B" />
            </FormField>
          </>
        )}
        <FormField label="Notes for the student">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
        </FormField>
      </div>
    </Modal>
  );
}
