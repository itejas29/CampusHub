import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays, Clock, ExternalLink, Heart, MapPin, Star, Users, Video,
} from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader, SearchInput } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { ApiError, api, qs } from "@/lib/api";
import { deadlineLabel, formatDateTime, relativeTime } from "@/lib/format";
import { cn, humanise } from "@/lib/utils";
import type { CampusEvent } from "@/types";

const TYPES = ["EVENT", "SEMINAR", "WORKSHOP", "COMPETITION", "MEETUP", "GUEST_LECTURE"];

export function EventsPage() {
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<"upcoming" | "past">("upcoming");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState<CampusEvent | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["events", scope, type, search],
    queryFn: () =>
      api.get<CampusEvent[]>(`/events${qs({ scope, event_type: type || undefined, q: search || undefined })}`),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["events"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["calendar"] });
  }

  const register = useMutation({
    mutationFn: (id: number) => api.post<CampusEvent>(`/events/${id}/register`),
    onSuccess: (updated) => {
      setDetail((current) => (current?.id === updated.id ? updated : current));
      setBanner({
        tone: "success",
        text: updated.my_registration_status === "WAITLISTED"
          ? "The event is full — you have been added to the waitlist."
          : "Registration confirmed.",
      });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Registration failed.",
    }),
  });

  const cancel = useMutation({
    mutationFn: (id: number) => api.delete<CampusEvent>(`/events/${id}/register`),
    onSuccess: (updated) => {
      setDetail((current) => (current?.id === updated.id ? updated : current));
      setBanner({ tone: "success", text: "Registration cancelled." });
      invalidate();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not cancel." ,
    }),
  });

  const interest = useMutation({
    mutationFn: ({ id, interested }: { id: number; interested: boolean }) =>
      api.post<CampusEvent>(`/events/${id}/interest`, { interested }),
    onSuccess: (updated) => {
      setDetail((current) => (current?.id === updated.id ? updated : current));
      invalidate();
    },
  });

  return (
    <div>
      <PageHeader
        title="Events"
        description="Workshops, seminars, competitions and club activities across campus."
        breadcrumbs={[{ label: "Campus" }, { label: "Events" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Tabs
          tabs={[{ key: "upcoming", label: "Upcoming" }, { key: "past", label: "Past" }]}
          active={scope}
          onChange={(key) => setScope(key as "upcoming" | "past")}
          className="border-b-0"
        />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SearchInput value={search} onChange={setSearch} placeholder="Search events"
                       className="w-full sm:w-56" />
          <Select value={type} onChange={(e) => setType(e.target.value)}
                  aria-label="Filter by type" className="w-full sm:w-44">
            <option value="">All types</option>
            {TYPES.map((value) => (
              <option key={value} value={value}>{humanise(value)}</option>
            ))}
          </Select>
        </div>
      </div>

      {isLoading && <SkeletonCards count={6} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title={scope === "upcoming" ? "No upcoming events" : "No past events"}
            description={
              search || type
                ? "Try clearing the filters."
                : "New events published by clubs will appear here."
            }
            icon={<CalendarDays className="h-5 w-5" aria-hidden />}
          />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((event) => {
            const deadline = deadlineLabel(event.registration_deadline);
            const registered =
              event.my_registration_status &&
              event.my_registration_status !== "CANCELLED";
            return (
              <Card key={event.id} className="flex h-full flex-col">
                <CardBody className="flex flex-1 flex-col">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <Badge tone="accent">{humanise(event.event_type)}</Badge>
                    {event.status !== "PUBLISHED" && <StatusBadge status={event.status} />}
                    {registered && <Badge tone="success">
                      {event.my_registration_status === "WAITLISTED" ? "Waitlisted" : "Going"}
                    </Badge>}
                  </div>

                  <h3 className="mt-2.5 text-md font-semibold leading-snug text-ink">
                    {event.title}
                  </h3>
                  {event.club_name && (
                    <p className="mt-0.5 text-xs text-ink-muted">{event.club_name}</p>
                  )}
                  {event.summary && (
                    <p className="mt-2 line-clamp-2 text-sm text-ink-muted">{event.summary}</p>
                  )}

                  <dl className="mt-3 space-y-1.5 text-xs text-ink-muted">
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      {formatDateTime(event.start_at)}
                    </div>
                    <div className="flex items-center gap-1.5">
                      {event.mode === "ONLINE"
                        ? <Video className="h-3.5 w-3.5 shrink-0" aria-hidden />
                        : <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />}
                      {event.venue ?? humanise(event.mode)}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Users className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      {event.registration_count} registered
                      {event.capacity ? ` of ${event.capacity}` : ""}
                      {event.interest_count > 0 && ` · ${event.interest_count} interested`}
                    </div>
                  </dl>

                  {scope === "upcoming" && event.registration_deadline && (
                    <p className={cn(
                      "mt-2.5 text-xs",
                      deadline.tone === "danger" ? "text-danger"
                        : deadline.tone === "warning" ? "text-warning" : "text-ink-subtle",
                    )}>
                      {deadline.text}
                    </p>
                  )}

                  <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
                    <Button variant="secondary" size="sm" onClick={() => setDetail(event)}>
                      Details
                    </Button>
                    {scope === "upcoming" && (
                      <>
                        {registered ? (
                          <Button
                            variant="ghost" size="sm" className="text-danger"
                            loading={cancel.isPending}
                            onClick={() => cancel.mutate(event.id)}
                          >
                            Cancel
                          </Button>
                        ) : event.registration_open ? (
                          <Button size="sm" loading={register.isPending}
                                  onClick={() => register.mutate(event.id)}>
                            Register
                          </Button>
                        ) : (
                          <span className="text-xs text-ink-subtle">
                            {event.is_full ? "Full" : "Registration closed"}
                          </span>
                        )}
                        <button
                          type="button"
                          aria-label={event.am_i_interested ? "Remove interest" : "Mark interested"}
                          aria-pressed={event.am_i_interested}
                          onClick={() =>
                            interest.mutate({ id: event.id, interested: !event.am_i_interested })
                          }
                          className={cn(
                            "ml-auto flex h-8 w-8 cursor-pointer items-center justify-center rounded transition-colors",
                            event.am_i_interested
                              ? "bg-danger-soft text-danger"
                              : "text-ink-subtle hover:bg-surface-muted hover:text-ink",
                          )}
                        >
                          <Heart
                            className={cn("h-4 w-4", event.am_i_interested && "fill-current")}
                            aria-hidden
                          />
                        </button>
                      </>
                    )}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.title ?? ""}
        description={detail?.club_name ?? undefined}
        size="lg"
        footer={
          detail && scope === "upcoming" ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setDetail(null)}>Close</Button>
              {detail.my_registration_status && detail.my_registration_status !== "CANCELLED" ? (
                <Button variant="danger" size="sm" loading={cancel.isPending}
                        onClick={() => cancel.mutate(detail.id)}>
                  Cancel registration
                </Button>
              ) : detail.registration_open ? (
                <Button size="sm" loading={register.isPending}
                        onClick={() => register.mutate(detail.id)}>
                  Register
                </Button>
              ) : null}
            </>
          ) : undefined
        }
      >
        {detail && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="accent">{humanise(detail.event_type)}</Badge>
              <StatusBadge status={detail.status} />
              {detail.tags.map((tag) => <Badge key={tag} tone="neutral">{tag}</Badge>)}
            </div>

            <DetailList
              items={[
                { label: "Starts", value: formatDateTime(detail.start_at) },
                { label: "Ends", value: formatDateTime(detail.end_at) },
                { label: "Venue", value: detail.venue ?? humanise(detail.mode) },
                { label: "Speaker", value: detail.speaker },
                {
                  label: "Registration closes",
                  value: formatDateTime(detail.registration_deadline),
                },
                {
                  label: "Seats",
                  value: detail.capacity
                    ? `${detail.registration_count} of ${detail.capacity} taken`
                    : `${detail.registration_count} registered`,
                },
                { label: "Interested", value: `${detail.interest_count} students` },
                { label: "Organised by", value: detail.club_name },
              ]}
            />

            {detail.description && (
              <div>
                <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  About this event
                </h3>
                <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-ink-muted">
                  {detail.description}
                </p>
              </div>
            )}

            {detail.external_url && (
              <a href={detail.external_url} target="_blank" rel="noreferrer"
                 className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
                External page <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            )}

            <div className="flex items-center gap-2 rounded border border-line bg-surface-muted/40 p-3">
              <Star className="h-4 w-4 shrink-0 text-warning" aria-hidden />
              <p className="text-xs text-ink-muted">
                {detail.am_i_interested
                  ? "You marked yourself interested — you will be notified about updates."
                  : "Mark yourself interested to help organisers gauge demand."}
              </p>
              <Button
                variant="ghost" size="sm" className="ml-auto"
                onClick={() =>
                  interest.mutate({ id: detail.id, interested: !detail.am_i_interested })
                }
              >
                {detail.am_i_interested ? "Not interested" : "Interested"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

/** Deep-linked single event (used by notification links). */
export function EventDetailRedirect() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.get<CampusEvent>(`/events/${eventId}`),
    enabled: Boolean(eventId),
  });

  if (isLoading) return <SkeletonCards count={1} />;
  if (error || !data) return <ErrorState title="Event not found" />;

  return (
    <div>
      <PageHeader
        title={data.title}
        description={data.summary ?? undefined}
        breadcrumbs={[{ label: "Campus" }, { label: "Events", to: "/events" }, { label: data.title }]}
        meta={
          <>
            <Badge tone="accent">{humanise(data.event_type)}</Badge>
            <StatusBadge status={data.status} />
            <Badge tone="neutral">{relativeTime(data.start_at)}</Badge>
          </>
        }
      />
      <Card>
        <CardHeader title="Details" />
        <CardBody className="space-y-5">
          <DetailList
            items={[
              { label: "Starts", value: formatDateTime(data.start_at) },
              { label: "Venue", value: data.venue ?? humanise(data.mode) },
              { label: "Organised by", value: data.club_name },
              { label: "Registered", value: `${data.registration_count}` },
            ]}
          />
          {data.description && (
            <p className="whitespace-pre-line text-sm leading-relaxed text-ink-muted">
              {data.description}
            </p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
