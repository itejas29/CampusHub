import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Plus, Users } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api, qs } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { CampusEvent, Club, EventRegistrationRow } from "@/types";

const TYPES = ["EVENT", "SEMINAR", "WORKSHOP", "COMPETITION", "MEETUP", "GUEST_LECTURE"];

export function EventsAdminPage() {
  const queryClient = useQueryClient();
  const [scope, setScope] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [registrationsFor, setRegistrationsFor] = useState<CampusEvent | null>(null);
  const [cancelTarget, setCancelTarget] = useState<CampusEvent | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-events", scope],
    queryFn: () => api.get<CampusEvent[]>(`/events${qs({ scope, limit: 200 })}`),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["admin-events"] });
    void queryClient.invalidateQueries({ queryKey: ["events"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  const publish = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.patch(`/events/${id}`, { status }),
    onSuccess: (_r, variables) => {
      setBanner({
        tone: "success",
        text: variables.status === "PUBLISHED"
          ? "Event published and club members notified."
          : "Event unpublished.",
      });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not update the event.",
    }),
  });

  const cancel = useMutation({
    mutationFn: (id: number) => api.delete(`/events/${id}`),
    onSuccess: () => {
      setCancelTarget(null);
      setBanner({ tone: "success", text: "Event cancelled and attendees notified." });
      invalidate();
    },
  });

  return (
    <div>
      <PageHeader
        title="Clubs & events"
        description="Create, publish and monitor events. Publishing notifies the organising club's members."
        breadcrumbs={[{ label: "Administration" }, { label: "Clubs & Events" }]}
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
            Create event
          </Button>
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <Card>
        <Tabs
          tabs={[
            { key: "all", label: "All" },
            { key: "upcoming", label: "Upcoming" },
            { key: "past", label: "Past" },
          ]}
          active={scope}
          onChange={setScope}
        />
        <CardHeader
          title={`${data?.length ?? 0} event${data?.length === 1 ? "" : "s"}`}
          icon={<CalendarDays className="h-4 w-4 text-ink-subtle" aria-hidden />}
        />

        {isLoading ? (
          <LoadingState rows={5} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.length ? (
          <EmptyState title="No events yet"
                      description="Create the first event to get started."
                      icon={<CalendarDays className="h-5 w-5" aria-hidden />} />
        ) : (
          <TableWrap>
            <THead>
              <TH>Event</TH>
              <TH width="13%">Club</TH>
              <TH width="14%">Starts</TH>
              <TH width="12%" align="right">Registered</TH>
              <TH width="11%" align="right">Interested</TH>
              <TH width="11%">Status</TH>
              <TH width="16%" align="right">Actions</TH>
            </THead>
            <TBody>
              {data.length === 0 ? (
                <TableEmpty colSpan={7}>No events in this range.</TableEmpty>
              ) : (
                data.map((event) => (
                  <TR key={event.id}>
                    <TD>
                      <p className="font-medium text-ink">{event.title}</p>
                      <p className="text-2xs text-ink-subtle">
                        {humanise(event.event_type)}
                        {event.venue && ` · ${event.venue}`}
                      </p>
                    </TD>
                    <TD className="text-ink-muted">{event.club_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-xs text-ink-muted">
                      {formatDate(event.start_at)}
                    </TD>
                    <TD align="right" className="tabular">
                      {event.registration_count}
                      {event.capacity && (
                        <span className="text-ink-subtle">/{event.capacity}</span>
                      )}
                    </TD>
                    <TD align="right" className="tabular text-ink-muted">
                      {event.interest_count}
                    </TD>
                    <TD><StatusBadge status={event.status} /></TD>
                    <TD align="right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button size="sm" variant="ghost"
                                onClick={() => setRegistrationsFor(event)}
                                icon={<Users className="h-3 w-3" aria-hidden />}>
                          List
                        </Button>
                        {event.status === "DRAFT" && (
                          <Button size="sm" variant="secondary" loading={publish.isPending}
                                  onClick={() => publish.mutate({ id: event.id, status: "PUBLISHED" })}>
                            Publish
                          </Button>
                        )}
                        {event.status === "PUBLISHED" && (
                          <Button size="sm" variant="ghost" className="text-danger"
                                  onClick={() => setCancelTarget(event)}>
                            Cancel
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
      </Card>

      {createOpen && (
        <CreateEventModal
          onClose={() => setCreateOpen(false)}
          onDone={() => {
            setCreateOpen(false);
            setBanner({ tone: "success", text: "Event created as a draft." });
            invalidate();
          }}
        />
      )}

      {registrationsFor && (
        <RegistrationsModal event={registrationsFor}
                            onClose={() => setRegistrationsFor(null)} />
      )}

      <ConfirmDialog
        open={Boolean(cancelTarget)}
        onClose={() => setCancelTarget(null)}
        onConfirm={() => cancelTarget && cancel.mutate(cancelTarget.id)}
        loading={cancel.isPending}
        destructive
        title="Cancel this event?"
        confirmLabel="Cancel event"
        cancelLabel="Keep it"
        message={
          <>
            <strong>{cancelTarget?.title}</strong> will be marked cancelled and every
            registered student will be notified. This cannot be undone from the portal.
          </>
        }
      />
    </div>
  );
}

function CreateEventModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [clubId, setClubId] = useState("");
  const [type, setType] = useState("EVENT");
  const [startAt, setStartAt] = useState("");
  const [venue, setVenue] = useState("");
  const [capacity, setCapacity] = useState("");
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  const clubs = useQuery({
    queryKey: ["clubs"],
    queryFn: () => api.get<Club[]>("/clubs"),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post("/events", {
        title,
        club_id: clubId ? Number(clubId) : null,
        event_type: type,
        start_at: new Date(startAt).toISOString(),
        venue: venue || null,
        capacity: capacity ? Number(capacity) : null,
        summary: summary || null,
        description: description || null,
        status: "DRAFT",
      }),
    onSuccess: onDone,
    onError: (err) => setError(err instanceof ApiError ? err : null),
  });

  const valid = title.trim().length >= 3 && startAt;

  return (
    <Modal
      open onClose={onClose} title="Create event" size="lg"
      description="Events are created as drafts — publish when you are ready to notify students."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={!valid} loading={create.isPending}
                  onClick={() => create.mutate()}>
            Create draft
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error.message}</Alert>}

        <FormField label="Title" required error={error?.fieldError("title")}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} data-autofocus
                 placeholder="e.g. Intro to Kubernetes" />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Organising club">
            <Select value={clubId} onChange={(e) => setClubId(e.target.value)}>
              <option value="">No club (institutional)</option>
              {(clubs.data ?? []).map((club) => (
                <option key={club.id} value={club.id}>{club.name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Type">
            <Select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((value) => (
                <option key={value} value={value}>{humanise(value)}</option>
              ))}
            </Select>
          </FormField>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Starts at" required error={error?.fieldError("start_at")}>
            <Input type="datetime-local" value={startAt}
                   onChange={(e) => setStartAt(e.target.value)} />
          </FormField>
          <FormField label="Venue">
            <Input value={venue} onChange={(e) => setVenue(e.target.value)}
                   placeholder="e.g. Seminar Hall 1" />
          </FormField>
          <FormField label="Capacity" hint="Leave blank for unlimited.">
            <Input type="number" min={1} value={capacity}
                   onChange={(e) => setCapacity(e.target.value)} />
          </FormField>
        </div>

        <FormField label="Summary" hint="One line shown on the event card.">
          <Input value={summary} onChange={(e) => setSummary(e.target.value)}
                 maxLength={300} />
        </FormField>

        <FormField label="Description">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)}
                    rows={4} />
        </FormField>
      </div>
    </Modal>
  );
}

function RegistrationsModal({
  event, onClose,
}: { event: CampusEvent; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["event-registrations", event.id],
    queryFn: () => api.get<EventRegistrationRow[]>(`/events/${event.id}/registrations`),
  });

  return (
    <Modal
      open onClose={onClose} size="lg" title="Registrations"
      description={`${event.title} · ${formatDateTime(event.start_at)}`}
      footer={<Button variant="secondary" size="sm" onClick={onClose}>Close</Button>}
    >
      {isLoading ? (
        <LoadingState rows={4} />
      ) : error ? (
        <ErrorState compact />
      ) : !data?.length ? (
        <EmptyState compact title="No registrations yet"
                    description={`${event.interest_count} student(s) marked themselves interested.`} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            <Badge tone="neutral">{data.length} registered</Badge>
            <Badge tone="neutral">{event.interest_count} interested</Badge>
            {event.capacity && <Badge tone="neutral">Capacity {event.capacity}</Badge>}
          </div>
          <TableWrap>
            <THead>
              <TH>Student</TH>
              <TH width="16%">Roll no.</TH>
              <TH width="12%">Dept</TH>
              <TH width="10%">Sem</TH>
              <TH width="16%">Status</TH>
            </THead>
            <TBody>
              {data.map((row) => (
                <TR key={row.id}>
                  <TD>
                    <p className="font-medium text-ink">{row.student_name}</p>
                    <p className="text-2xs text-ink-subtle">{row.email}</p>
                  </TD>
                  <TD className="tabular">{row.roll_number}</TD>
                  <TD>{row.department_code}</TD>
                  <TD>{row.semester}</TD>
                  <TD><StatusBadge status={row.status} /></TD>
                </TR>
              ))}
            </TBody>
          </TableWrap>
        </>
      )}
    </Modal>
  );
}
