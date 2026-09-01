import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ExternalLink, Instagram, Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { ApiError, api, qs } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { Club, ClubDetail } from "@/types";

const CATEGORIES = [
  "TECHNICAL", "CULTURAL", "SPORTS", "SOCIAL", "ENTREPRENEURSHIP", "LITERARY", "OTHER",
];

export function ClubsPage() {
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["clubs", category, search],
    queryFn: () =>
      api.get<Club[]>(`/clubs${qs({ category: category || undefined, q: search || undefined })}`),
  });

  return (
    <div>
      <PageHeader
        title="Clubs"
        description="Student-run technical, cultural and social communities on campus."
        breadcrumbs={[{ label: "Campus" }, { label: "Clubs" }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={search} onChange={setSearch} placeholder="Search clubs"
                         className="w-full sm:w-52" />
            <Select value={category} onChange={(e) => setCategory(e.target.value)}
                    aria-label="Filter by category" className="w-full sm:w-44">
              <option value="">All categories</option>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>{humanise(value)}</option>
              ))}
            </Select>
          </div>
        }
      />

      {isLoading && <SkeletonCards count={6} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No clubs found"
                      description="Try clearing the filters."
                      icon={<Users className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((club) => (
            <Link key={club.id} to={`/clubs/${club.slug}`} className="block">
              <Card className="h-full transition-colors hover:border-line-strong">
                <CardBody className="flex h-full flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <Badge tone="accent">{humanise(club.category)}</Badge>
                    {club.is_member && <Badge tone="success">Member</Badge>}
                  </div>
                  <h3 className="mt-2.5 text-md font-semibold text-ink">{club.name}</h3>
                  {club.tagline && (
                    <p className="mt-0.5 text-sm italic text-ink-muted">{club.tagline}</p>
                  )}
                  {club.description && (
                    <p className="mt-2 line-clamp-2 text-sm text-ink-muted">
                      {club.description}
                    </p>
                  )}
                  <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 pt-4 text-xs text-ink-muted">
                    <span className="flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" aria-hidden />
                      {club.member_count} members
                    </span>
                    {club.upcoming_event_count > 0 && (
                      <span className="flex items-center gap-1">
                        <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                        {club.upcoming_event_count} upcoming
                      </span>
                    )}
                  </div>
                </CardBody>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function ClubDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const queryClient = useQueryClient();
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["club", slug],
    queryFn: () => api.get<ClubDetail>(`/clubs/${slug}`),
    enabled: Boolean(slug),
  });

  const join = useMutation({
    mutationFn: () => api.post(`/clubs/${data!.id}/join`),
    onSuccess: () => {
      setBanner({ tone: "success", text: `You have joined ${data?.name}.` });
      void queryClient.invalidateQueries({ queryKey: ["club", slug] });
      void queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not join.",
    }),
  });

  const leave = useMutation({
    mutationFn: () => api.delete(`/clubs/${data!.id}/leave`),
    onSuccess: () => {
      setBanner({ tone: "success", text: "Membership removed." });
      void queryClient.invalidateQueries({ queryKey: ["club", slug] });
      void queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
  });

  if (isLoading) return <SkeletonCards count={2} />;
  if (error || !data) {
    return <ErrorState title="Club not found" onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader
        title={data.name}
        description={data.tagline ?? undefined}
        breadcrumbs={[
          { label: "Campus" }, { label: "Clubs", to: "/clubs" }, { label: data.name },
        ]}
        meta={
          <>
            <Badge tone="accent">{humanise(data.category)}</Badge>
            <Badge tone="neutral">{data.member_count} members</Badge>
            {data.founded_year && <Badge tone="neutral">Since {data.founded_year}</Badge>}
          </>
        }
        actions={
          data.is_member !== null && (
            data.is_member ? (
              <Button variant="secondary" size="sm" loading={leave.isPending}
                      onClick={() => leave.mutate()}>
                Leave club
              </Button>
            ) : (
              <Button size="sm" loading={join.isPending} onClick={() => join.mutate()}>
                Join club
              </Button>
            )
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
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader title="About" />
            <CardBody>
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-muted">
                {data.description ?? "No description has been added yet."}
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                {data.instagram_url && (
                  <a href={data.instagram_url} target="_blank" rel="noreferrer"
                     className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
                    <Instagram className="h-3.5 w-3.5" aria-hidden /> Instagram
                  </a>
                )}
                {data.website_url && (
                  <a href={data.website_url} target="_blank" rel="noreferrer"
                     className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden /> Website
                  </a>
                )}
                {data.email && (
                  <a href={`mailto:${data.email}`}
                     className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
                    {data.email}
                  </a>
                )}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Events"
                        action={<Link to="/events" className="text-xs text-accent hover:underline">All events</Link>} />
            {data.events.length === 0 ? (
              <EmptyState compact title="No events published yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.events.map((event) => (
                  <li key={event.id} className="px-5 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">{event.title}</p>
                        <p className="mt-0.5 text-xs text-ink-subtle">
                          {formatDateTime(event.start_at)}
                          {event.venue && ` · ${event.venue}`}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge tone="neutral">{event.registration_count} registered</Badge>
                        <Badge tone="accent">{humanise(event.event_type)}</Badge>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          {data.faculty_advisor_name && (
            <Card>
              <CardHeader title="Faculty advisor" />
              <CardBody className="flex items-center gap-3">
                <Avatar name={data.faculty_advisor_name} size="md" />
                <p className="text-sm font-medium text-ink">{data.faculty_advisor_name}</p>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Members" description={`${data.members.length} active`} />
            {data.members.length === 0 ? (
              <EmptyState compact title="No members yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.members.map((member) => (
                  <li key={member.id} className="flex items-center gap-2.5 px-5 py-2.5">
                    <Avatar name={member.student_name} src={member.avatar_url} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-ink">{member.student_name}</p>
                      <p className="truncate text-2xs text-ink-subtle">
                        {member.roll_number}
                      </p>
                    </div>
                    {member.role !== "MEMBER" && (
                      <Badge tone="brand">{member.position_title ?? humanise(member.role)}</Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
