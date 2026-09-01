import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Pin, Plus } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Checkbox, FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, relativeTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { Announcement } from "@/types";

const CATEGORIES = [
  "GENERAL", "ACADEMIC", "EXAMINATION", "INTERNSHIP", "EVENT", "MENTORSHIP", "URGENT",
];

export function AnnouncementsPage() {
  const { can, user } = useAuth();
  const queryClient = useQueryClient();
  const [composeOpen, setComposeOpen] = useState(false);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const canPublish = can("announcements:publish");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["announcements"],
    queryFn: () => api.get<Announcement[]>("/announcements"),
  });

  return (
    <div>
      <PageHeader
        title="Announcements"
        description="Notices from the department, coordinators, clubs and your faculty mentor."
        breadcrumbs={[{ label: "Support" }, { label: "Announcements" }]}
        actions={
          canPublish && (
            <Button size="sm" onClick={() => setComposeOpen(true)}
                    icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
              New announcement
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

      {isLoading && <LoadingState rows={4} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title="No announcements"
            description="Notices addressed to you will appear here."
            icon={<Megaphone className="h-5 w-5" aria-hidden />}
          />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((announcement) => (
            <Card key={announcement.id}
                  className={announcement.is_pinned ? "border-accent/40" : undefined}>
              <CardBody>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {announcement.is_pinned && (
                        <Badge tone="accent" icon={<Pin className="h-3 w-3" aria-hidden />}>
                          Pinned
                        </Badge>
                      )}
                      <Badge tone="neutral">{humanise(announcement.category)}</Badge>
                      {announcement.priority !== "NORMAL" && (
                        <StatusBadge status={announcement.priority} />
                      )}
                      {announcement.audience_label && (
                        <Badge tone="brand">{announcement.audience_label}</Badge>
                      )}
                    </div>
                    <h2 className="mt-2 text-md font-semibold leading-snug text-ink">
                      {announcement.title}
                    </h2>
                  </div>
                  <span className="shrink-0 text-xs text-ink-subtle">
                    {relativeTime(announcement.published_at)}
                  </span>
                </div>

                <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-muted">
                  {announcement.body}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-ink-subtle">
                  {announcement.published_by_name && (
                    <span>Posted by {announcement.published_by_name}</span>
                  )}
                  <span>{formatDate(announcement.published_at)}</span>
                  {announcement.expires_at && (
                    <span>Expires {formatDate(announcement.expires_at)}</span>
                  )}
                  {announcement.link_url && (
                    <a href={announcement.link_url} target="_blank" rel="noreferrer"
                       className="text-accent hover:underline">
                      Related link
                    </a>
                  )}
                  {announcement.attachment_url && (
                    <a href={announcement.attachment_url} target="_blank" rel="noreferrer"
                       className="text-accent hover:underline">
                      Attachment
                    </a>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {composeOpen && (
        <ComposeModal
          canTargetMentees={Boolean(user?.faculty)}
          onClose={() => setComposeOpen(false)}
          onDone={() => {
            setComposeOpen(false);
            setBanner({ tone: "success", text: "Announcement published." });
            void queryClient.invalidateQueries({ queryKey: ["announcements"] });
            void queryClient.invalidateQueries({ queryKey: ["notifications"] });
          }}
        />
      )}
    </div>
  );
}

function ComposeModal({
  onClose, onDone, canTargetMentees,
}: { onClose: () => void; onDone: () => void; canTargetMentees: boolean }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("GENERAL");
  const [priority, setPriority] = useState("NORMAL");
  const [audience, setAudience] = useState(canTargetMentees ? "MENTEES" : "ALL");
  const [pinned, setPinned] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const publish = useMutation({
    mutationFn: () =>
      api.post("/announcements", {
        title, body, category, priority, audience_type: audience,
        is_pinned: pinned, is_published: true,
      }),
    onSuccess: onDone,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not publish."),
  });

  const audiences = ["ALL", ...(canTargetMentees ? ["MENTEES"] : [])];

  return (
    <Modal
      open onClose={onClose} title="New announcement" size="lg"
      description="Recipients are resolved on the server from the audience you choose."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            disabled={title.trim().length < 3 || body.trim().length < 3}
            loading={publish.isPending}
            onClick={() => publish.mutate()}
          >
            Publish
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField label="Title" required>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} data-autofocus
                 placeholder="e.g. Mentor meeting slots for this fortnight" />
        </FormField>
        <FormField label="Message" required>
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Category">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>{humanise(value)}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Priority">
            <Select value={priority} onChange={(e) => setPriority(e.target.value)}>
              {["LOW", "NORMAL", "HIGH", "CRITICAL"].map((value) => (
                <option key={value} value={value}>{humanise(value)}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="Audience">
            <Select value={audience} onChange={(e) => setAudience(e.target.value)}>
              {audiences.map((value) => (
                <option key={value} value={value}>
                  {value === "MENTEES" ? "My mentees" : "Everyone"}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <Checkbox label="Pin to the top of the list" checked={pinned}
                  onChange={(e) => setPinned(e.target.checked)} />
      </div>
    </Modal>
  );
}
