import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Building2, CheckCircle2, ChevronDown, ChevronUp, Clock, Send,
  Trash2, Users, X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader } from "@/components/ui/Misc";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { deadlineLabel, formatDateTime } from "@/lib/format";
import { cn, roman } from "@/lib/utils";
import type { CourseOffering, ElectiveWorkspace } from "@/types";
import { RoundChoicePanel } from "./RoundChoicePanel";

export function ElectiveWorkspacePage({ backLabel, backTo }: {
  backLabel: string; backTo: string;
}) {
  const { componentId } = useParams<{ componentId: string }>();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [detail, setDetail] = useState<CourseOffering | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const queryKey = ["elective-workspace", componentId];
  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: () => api.get<ElectiveWorkspace>(`/electives/components/${componentId}/workspace`),
    enabled: Boolean(componentId),
  });

  // Seed the picker from whatever the student already submitted.
  useEffect(() => {
    if (data) {
      setSelected(
        [...data.my_preferences]
          .sort((a, b) => a.preference_order - b.preference_order)
          .map((p) => p.course_offering_id),
      );
    }
  }, [data]);

  const submit = useMutation({
    mutationFn: () =>
      api.post("/electives/preferences", {
        curriculum_component_id: Number(componentId),
        preferences: selected.map((id, index) => ({
          course_offering_id: id, preference_order: index + 1,
        })),
      }),
    onSuccess: () => {
      setBanner({ tone: "success", text: "Your preferences have been recorded." });
      void queryClient.invalidateQueries({ queryKey });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) => {
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not save your preferences.",
      });
    },
  });

  const withdraw = useMutation({
    mutationFn: () => api.delete(`/electives/preferences/${componentId}`),
    onSuccess: () => {
      setConfirmWithdraw(false);
      setSelected([]);
      setBanner({ tone: "success", text: "Preferences withdrawn." });
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (err) => {
      setConfirmWithdraw(false);
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not withdraw preferences.",
      });
    },
  });

  const offeringById = useMemo(
    () => new Map((data?.offerings ?? []).map((o) => [o.id, o])),
    [data],
  );

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  const { component, my_allocation: allocation } = data;

  // A two-stage round is chosen by ticking subjects across the whole round,
  // not by ranking this slot's courses, so it gets its own screen — before
  // and after allocation. (Per-slot enrolment counts would mislead here: a
  // subject's strength is counted across all the round's slots.)
  if (data.round) {
    return (
      <div>
        <PageHeader
          title={data.round.title}
          description={data.round.slot_titles.length > 1
            ? `${data.round.slot_titles.join(" and ")} are chosen together in this round: `
              + `you take ${data.round.slot_titles.length} subjects, one for each.`
            : `${component.title} is chosen in this round.`}
          breadcrumbs={[
            { label: "Academics" },
            { label: backLabel, to: backTo },
            { label: data.round.slot_codes.length ? data.round.slot_codes.join(" · ") : component.code },
          ]}
          meta={
            <>
              <Badge tone="brand">
                {data.round.stage === "FINAL" ? "Final round" : "Interest round"}
              </Badge>
              <Badge tone="neutral">Semester {roman(component.semester_number)}</Badge>
            </>
          }
        />
        {allocation ? (
          <Alert variant="success" title={`${component.title}: your elective`}>
            You have been allocated{" "}
            <strong>{allocation.course_code} · {allocation.course_title}</strong>
            {allocation.section_name ? ` (${allocation.section_name})` : ""}.
            {allocation.remarks && (
              <p className="mt-1 text-sm">{allocation.remarks}.</p>
            )}
          </Alert>
        ) : (
          <RoundChoicePanel
            round={data.round}
            onSaved={(saved) => {
              queryClient.setQueryData<ElectiveWorkspace>(queryKey,
                (old) => (old ? { ...old, round: saved } : old));
              void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
            }}
          />
        )}
      </div>
    );
  }

  const locked = Boolean(allocation) || !data.eligible || !data.window_open;
  const deadline = deadlineLabel(data.closes_at);
  const canSubmit =
    !locked && selected.length >= data.min_preferences && selected.length <= data.max_preferences;

  function toggle(id: number) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : current.length >= data!.max_preferences
          ? current
          : [...current, id],
    );
  }

  function move(index: number, direction: -1 | 1) {
    setSelected((current) => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  return (
    <div>
      <PageHeader
        title={component.title}
        description={component.description ?? undefined}
        breadcrumbs={[
          { label: "Academics" },
          { label: backLabel, to: backTo },
          { label: component.code },
        ]}
        meta={
          <>
            <Badge tone="brand" className="font-mono">{component.code}</Badge>
            <Badge tone="neutral">Semester {roman(component.semester_number)}</Badge>
            <Badge tone="neutral">{component.credits} credits</Badge>
            {component.scope_label && <Badge tone="accent">{component.scope_label}</Badge>}
          </>
        }
      />

      {banner && (
        <Alert
          variant={banner.tone === "success" ? "success" : "danger"}
          className="mb-4"
          onDismiss={() => setBanner(null)}
        >
          {banner.text}
        </Alert>
      )}

      {allocation && (
        <Alert variant="success" title="Seat allocated" className="mb-4">
          You have been allocated <strong>{allocation.course_code} · {allocation.course_title}</strong>
          {allocation.preference_order_granted &&
            ` (your preference #${allocation.preference_order_granted})`}
          . Preferences are now locked for this component.
        </Alert>
      )}

      {!data.eligible && data.eligibility_notes.length > 0 && (
        <Alert variant="warning" title="Not available yet" className="mb-4">
          <ul className="list-inside list-disc space-y-0.5">
            {data.eligibility_notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </Alert>
      )}

      {/* The backend derives this state and enforces it. The banner reports
          that decision — it never computes its own from a countdown, because a
          stale tab or a skewed clock would then show the wrong thing. */}
      {data.eligible && !data.window_open && !allocation && (
        <Alert
          variant={data.registration_state === "LOCKED" ? "warning" : "info"}
          title={data.registration_label ?? "Registration is not open"}
          className="mb-4"
        >
          {data.registration_reason ??
            "The preference window for this component is not currently open."}
          {data.window_title && (
            <p className="mt-1 text-xs text-ink-subtle">Round: {data.window_title}</p>
          )}
        </Alert>
      )}

      {data.eligible && data.window_open && data.registration_state === "SUBMITTED" && (
        <Alert variant="success" title="Preferences submitted" className="mb-4">
          You can still change them until the deadline.
          {data.closes_at && ` Closes ${new Date(data.closes_at).toLocaleString()}.`}
        </Alert>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Course catalogue */}
        <div className="min-w-0 lg:col-span-2">
          <Card>
            <CardHeader
              title="Available courses"
              description={
                locked
                  ? "Browse the courses offered for this requirement."
                  : `Select between ${data.min_preferences} and ${data.max_preferences} courses, then order them by preference.`
              }
              action={
                data.closes_at && !allocation ? (
                  <Badge tone={deadline.tone === "neutral" ? "neutral" : deadline.tone}
                         icon={<Clock className="h-3 w-3" aria-hidden />}>
                    {deadline.text}
                  </Badge>
                ) : undefined
              }
            />
            {data.offerings.length === 0 ? (
              <CardBody>
                <p className="py-6 text-center text-sm text-ink-muted">
                  No courses have been published for this requirement yet.
                </p>
              </CardBody>
            ) : (
              <CardBody className="space-y-2.5">
                {data.offerings.map((offering) => {
                  const index = selected.indexOf(offering.id);
                  const isSelected = index >= 0;
                  // Open Electives open another section rather than filling
                  // up, so only a single-section capped course can be full.
                  const full =
                    offering.section_capacity !== null &&
                    !offering.allow_multiple_sections &&
                    offering.seats_filled >= offering.section_capacity;
                  return (
                    <div
                      key={offering.id}
                      className={cn(
                        "rounded-md border p-3.5 transition-colors",
                        isSelected ? "border-accent bg-accent-soft/30" : "border-line",
                      )}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                              {offering.course.code}
                            </span>
                            {isSelected && (
                              <Badge tone="accent">Preference {index + 1}</Badge>
                            )}
                            {full && <Badge tone="danger">Full</Badge>}
                          </div>
                          <p className="mt-1.5 text-sm font-medium text-ink">
                            {offering.course.title}
                          </p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                            <span className="flex items-center gap-1">
                              <Building2 className="h-3 w-3" aria-hidden />
                              {offering.course.offering_school ??
                                offering.course.department_name ?? "—"}
                            </span>
                            <span>{offering.course.credits} credits</span>
                            {offering.course.specialization_area && (
                              <span>{offering.course.specialization_area}</span>
                            )}
                            <span className="flex items-center gap-1">
                              <Users className="h-3 w-3" aria-hidden />
                              {offering.seats_filled} enrolled
                            </span>
                            {offering.seats_filled < offering.min_students_to_run && (
                              <span className="text-warning">
                                needs {offering.min_students_to_run} to run
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Button variant="ghost" size="sm" onClick={() => setDetail(offering)}>
                            Details
                          </Button>
                          {!locked && (
                            <Button
                              variant={isSelected ? "secondary" : "primary"}
                              size="sm"
                              onClick={() => toggle(offering.id)}
                              disabled={
                                !isSelected &&
                                (selected.length >= data.max_preferences || full)
                              }
                            >
                              {isSelected ? "Remove" : "Add"}
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </CardBody>
            )}
          </Card>
        </div>

        {/* Preference list */}
        <div>
          <Card className="lg:sticky lg:top-20">
            <CardHeader
              title="Your preference order"
              description={
                locked ? "Locked" : `${selected.length} of ${data.max_preferences} selected`
              }
            />
            <CardBody>
              {selected.length === 0 ? (
                <p className="py-6 text-center text-sm text-ink-muted">
                  {locked
                    ? "No preferences were submitted."
                    : "Add courses from the list to build your ranked preference order."}
                </p>
              ) : (
                <ol className="space-y-2">
                  {selected.map((id, index) => {
                    const offering = offeringById.get(id);
                    return (
                      <li
                        key={id}
                        className="flex items-center gap-2 rounded border border-line px-2.5 py-2"
                      >
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-2xs font-semibold text-brand-fg">
                          {index + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-ink">
                            {offering?.course.code}
                          </p>
                          <p className="truncate text-2xs text-ink-subtle">
                            {offering?.course.title}
                          </p>
                        </div>
                        {!locked && (
                          <div className="flex shrink-0 flex-col">
                            <button
                              type="button"
                              onClick={() => move(index, -1)}
                              disabled={index === 0}
                              aria-label={`Move ${offering?.course.code} up`}
                              className="cursor-pointer px-1 text-ink-subtle transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                            </button>
                            <button
                              type="button"
                              onClick={() => move(index, 1)}
                              disabled={index === selected.length - 1}
                              aria-label={`Move ${offering?.course.code} down`}
                              className="cursor-pointer px-1 text-ink-subtle transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                            </button>
                          </div>
                        )}
                        {!locked && (
                          <button
                            type="button"
                            onClick={() => toggle(id)}
                            aria-label={`Remove ${offering?.course.code}`}
                            className="shrink-0 cursor-pointer rounded p-1 text-ink-subtle transition-colors hover:text-danger"
                          >
                            <X className="h-3.5 w-3.5" aria-hidden />
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}

              {!locked && (
                <>
                  {selected.length > 0 && selected.length < data.min_preferences && (
                    <p className="mt-3 flex items-start gap-1.5 text-xs text-warning">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                      Select at least {data.min_preferences} courses before submitting.
                    </p>
                  )}
                  <Button
                    className="mt-4 w-full"
                    disabled={!canSubmit}
                    loading={submit.isPending}
                    onClick={() => submit.mutate()}
                    icon={<Send className="h-3.5 w-3.5" aria-hidden />}
                  >
                    {data.my_preferences.length ? "Update preferences" : "Submit preferences"}
                  </Button>
                  {data.my_preferences.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-1.5 w-full text-danger"
                      onClick={() => setConfirmWithdraw(true)}
                      icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                    >
                      Withdraw preferences
                    </Button>
                  )}
                </>
              )}

              {data.my_preferences.length > 0 && (
                <p className="mt-3 flex items-start gap-1.5 text-2xs text-ink-subtle">
                  <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-success" aria-hidden />
                  Last submitted {formatDateTime(data.my_preferences[0].submitted_at)}
                </p>
              )}
            </CardBody>
          </Card>

          <Alert variant="info" className="mt-4">
            Seats are allocated by the department after the window closes. The
            allocation rule is configured centrally — submitting early does not
            by itself improve your chance.
          </Alert>
        </div>
      </div>

      {/* Course detail modal */}
      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.course.title ?? ""}
        description={detail?.course.code}
        size="lg"
      >
        {detail && (
          <div className="space-y-5">
            <DetailList
              items={[
                { label: "Course code", value: <span className="tabular">{detail.course.code}</span> },
                { label: "Credits", value: `${detail.course.credits}` },
                {
                  label: "Offered by",
                  value: detail.course.offering_school ?? detail.course.department_name ?? "—",
                },
                {
                  label: "Contact hours",
                  value: `L ${detail.course.lecture_hours} · T ${detail.course.tutorial_hours} · P ${detail.course.practical_hours}`,
                },
                { label: "Specialisation", value: detail.course.specialization_area ?? "—" },
                {
                  label: "Enrolled",
                  value: detail.section_capacity === null
                    ? `${detail.seats_filled} (no upper limit)`
                    : detail.allow_multiple_sections
                      ? `${detail.seats_filled} · ${detail.section_capacity} per section`
                      : `${detail.seats_filled} of ${detail.section_capacity}`,
                },
                {
                  label: "Minimum to run",
                  value: `${detail.min_students_to_run} students`,
                },
                { label: "Schedule", value: detail.schedule_note ?? "To be announced" },
                { label: "Venue", value: detail.venue ?? "To be announced" },
                { label: "Coordinator", value: detail.coordinator_name ?? "—" },
                {
                  label: "Registration closes",
                  value: formatDateTime(detail.registration_closes_at),
                },
              ]}
            />
            {detail.course.description && (
              <div>
                <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Description
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-ink-muted">
                  {detail.course.description}
                </p>
              </div>
            )}
            {detail.course.prerequisites && (
              <div>
                <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Prerequisites
                </h3>
                <p className="mt-1 text-sm text-ink-muted">{detail.course.prerequisites}</p>
              </div>
            )}
            {detail.course.syllabus_url && (
              <a
                href={detail.course.syllabus_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex text-sm font-medium text-accent hover:underline"
              >
                Open syllabus document
              </a>
            )}
            <div className="rounded border border-line bg-surface-muted/40 p-3">
              <StatusBadge status={detail.status} />
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={confirmWithdraw}
        onClose={() => setConfirmWithdraw(false)}
        onConfirm={() => withdraw.mutate()}
        loading={withdraw.isPending}
        destructive
        title="Withdraw preferences?"
        confirmLabel="Withdraw"
        message="Your submitted preference list for this component will be removed. You can submit a new list while the window is open."
      />
    </div>
  );
}
