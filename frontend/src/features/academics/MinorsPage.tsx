import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2, GraduationCap, Sparkles, Users, X,
} from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn, roman } from "@/lib/utils";
import { MinorRules } from "./MinorRules";
import type { MinorProgram, MinorWorkspace } from "@/types";

export function MinorsPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [motivation, setMotivation] = useState("");
  const [detail, setDetail] = useState<MinorProgram | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["minors", "workspace"],
    queryFn: () => api.get<MinorWorkspace>("/minors/workspace"),
  });

  const apply = useMutation({
    mutationFn: () =>
      api.post("/minors/apply", { preferences: selected, motivation: motivation || null }),
    onSuccess: () => {
      setSelected([]);
      setMotivation("");
      setBanner({ tone: "success", text: "Application submitted." });
      void queryClient.invalidateQueries({ queryKey: ["minors"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) =>
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not submit your application.",
      }),
  });

  const withdraw = useMutation({
    mutationFn: () => api.delete("/minors/applications"),
    onSuccess: () => {
      setConfirmWithdraw(false);
      setBanner({ tone: "success", text: "Application withdrawn." });
      void queryClient.invalidateQueries({ queryKey: ["minors"] });
    },
    onError: (err) => {
      setConfirmWithdraw(false);
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not withdraw.",
      });
    },
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined}
                       onRetry={() => refetch()} />;
  }

  const enrolled = data.enrollment;
  const pending = data.applications.filter((a) => a.status === "SUBMITTED");
  const canApply = data.is_eligible && !enrolled && pending.length === 0;

  function toggle(id: number) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : current.length >= 3 ? current : [...current, id],
    );
  }

  return (
    <div>
      <PageHeader
        title="Minor Specialisation"
        description="A structured minor taken in a department other than your own. Eligibility thresholds, seat counts and application windows are configured per minor by the offering department."
        breadcrumbs={[{ label: "Academics" }, { label: "Minor Specialisation" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      {/* Rules first: a student has to be able to read what they are signing up
          to before they are asked to choose, not after, and not from inside a
          dialog they have to know to open. */}
      <MinorRules programs={data.programs} />

      {!data.is_eligible && data.eligibility_notes.length > 0 && (
        <Alert variant="warning" title="Not eligible yet" className="mb-5">
          <ul className="list-inside list-disc space-y-0.5">
            {data.eligibility_notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </Alert>
      )}

      {/* Enrolled state */}
      {enrolled && (
        <Card className="mb-5 border-success/40">
          <CardHeader
            title="Your minor"
            description={enrolled.minor_department ?? undefined}
            icon={<CheckCircle2 className="h-4 w-4 text-success" aria-hidden />}
            action={<StatusBadge status={enrolled.status} />}
          />
          <CardBody>
            <h3 className="font-heading text-lg font-semibold text-ink">
              {enrolled.minor_name}
            </h3>
            <ProgressBar
              className="mt-4 max-w-md"
              label="Credits completed"
              value={enrolled.credits_completed}
              max={enrolled.total_credits ?? 1}
              tone="success"
            />
            {enrolled.courses.length > 0 && (
              <div className="mt-5">
                <h4 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Course sequence
                </h4>
                <ol className="mt-2 space-y-1.5">
                  {enrolled.courses.map((course) => (
                    <li
                      key={course.id}
                      className="flex items-center gap-2.5 rounded border border-line px-3 py-2"
                    >
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-muted text-2xs font-semibold text-ink-muted">
                        {course.sequence}
                      </span>
                      <span className="tabular text-ink-muted">{course.course_code}</span>
                      <span className="min-w-0 flex-1 text-sm text-ink">{course.course_title}</span>
                      <span className="shrink-0 text-xs text-ink-muted">
                        {course.credits} cr
                      </span>
                      {course.is_completed && <Badge tone="success">Done</Badge>}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {/* Pending applications */}
      {pending.length > 0 && (
        <Card className="mb-5">
          <CardHeader
            title="Your application"
            description="Submitted and awaiting a departmental decision."
            action={
              <Button variant="ghost" size="sm" className="text-danger"
                      onClick={() => setConfirmWithdraw(true)}>
                Withdraw
              </Button>
            }
          />
          <CardBody className="space-y-2">
            {data.applications.map((application) => (
              <div
                key={application.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded border border-line px-3 py-2.5"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-2xs font-semibold text-brand-fg">
                  {application.preference_order}
                </span>
                <span className="min-w-0 flex-1 text-sm font-medium text-ink">
                  {application.minor_name}
                </span>
                <span className="text-xs text-ink-muted">{application.minor_department}</span>
                <StatusBadge status={application.status} />
              </div>
            ))}
            <p className="pt-1 text-xs text-ink-subtle">
              Submitted {formatDate(data.applications[0]?.submitted_at)} · CPI recorded at
              submission: {data.applications[0]?.cpi_at_application ?? "—"}
            </p>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <Card>
            <CardHeader
              title="Available minors"
              description={
                canApply
                  ? "Choose up to three minors in your order of preference."
                  : "Browse the minors offered across departments."
              }
              icon={<Sparkles className="h-4 w-4 text-ink-subtle" aria-hidden />}
            />
            {data.programs.length === 0 ? (
              <EmptyState compact title="No minors published yet" />
            ) : (
              <CardBody className="space-y-3">
                {data.programs.map((program) => {
                  const index = selected.indexOf(program.id);
                  const isSelected = index >= 0;
                  const eligible = program.is_eligible !== false;
                  return (
                    <div
                      key={program.id}
                      className={cn(
                        "rounded-md border p-4 transition-colors",
                        isSelected ? "border-accent bg-accent-soft/30" : "border-line",
                        !eligible && "bg-surface-muted/30",
                      )}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                              {program.code}
                            </span>
                            {isSelected && <Badge tone="accent">Preference {index + 1}</Badge>}
                            {program.my_application_status && (
                              <StatusBadge status={program.my_application_status} />
                            )}
                          </div>
                          <h3 className="mt-1.5 text-sm font-semibold text-ink">
                            {program.name}
                          </h3>
                          <p className="text-xs text-ink-muted">{program.department_name}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                            <span className="flex items-center gap-1">
                              <GraduationCap className="h-3 w-3" aria-hidden />
                              {program.total_credits} credits
                            </span>
                            <span className="flex items-center gap-1">
                              <Users className="h-3 w-3" aria-hidden />
                              {program.seats_available}/{program.capacity} seats
                            </span>
                            <span>From semester {roman(program.eligible_from_semester)}</span>
                            {program.min_cpi && <span>Min CPI {program.min_cpi}</span>}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Button variant="ghost" size="sm" onClick={() => setDetail(program)}>
                            Details
                          </Button>
                          {canApply && (
                            <Button
                              variant={isSelected ? "secondary" : "primary"}
                              size="sm"
                              disabled={!eligible || (!isSelected && selected.length >= 3)}
                              onClick={() => toggle(program.id)}
                            >
                              {isSelected ? "Remove" : "Add"}
                            </Button>
                          )}
                        </div>
                      </div>

                      {!eligible && program.eligibility_notes.length > 0 && (
                        <ul className="mt-2.5 space-y-0.5 border-t border-line pt-2.5">
                          {program.eligibility_notes.map((note) => (
                            <li key={note} className="flex items-start gap-1.5 text-xs text-warning">
                              <X className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                              {note}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </CardBody>
            )}
          </Card>
        </div>

        <div>
          {canApply && (
            <Card className="lg:sticky lg:top-20">
              <CardHeader
                title="Submit application"
                description={`${selected.length} of 3 selected`}
              />
              <CardBody className="space-y-4">
                {selected.length === 0 ? (
                  <p className="py-4 text-center text-sm text-ink-muted">
                    Add minors from the list to build your preference order.
                  </p>
                ) : (
                  <ol className="space-y-1.5">
                    {selected.map((id, index) => {
                      const program = data.programs.find((p) => p.id === id);
                      return (
                        <li key={id} className="flex items-center gap-2 rounded border border-line px-2.5 py-2">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand text-2xs font-semibold text-brand-fg">
                            {index + 1}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm text-ink">
                            {program?.name}
                          </span>
                          <button
                            type="button"
                            onClick={() => toggle(id)}
                            aria-label={`Remove ${program?.name}`}
                            className="shrink-0 cursor-pointer rounded p-0.5 text-ink-subtle hover:text-danger"
                          >
                            <X className="h-3.5 w-3.5" aria-hidden />
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                )}

                <FormField
                  label="Why this minor?"
                  hint="Optional. Helps the reviewing department understand your interest."
                >
                  <Textarea
                    value={motivation}
                    onChange={(e) => setMotivation(e.target.value)}
                    rows={4}
                    maxLength={2000}
                    placeholder="A few sentences about how this minor fits your goals…"
                  />
                </FormField>

                <Button
                  className="w-full"
                  disabled={selected.length === 0}
                  loading={apply.isPending}
                  onClick={() => apply.mutate()}
                >
                  Submit application
                </Button>
              </CardBody>
            </Card>
          )}

          <Alert variant="info" className={canApply ? "mt-4" : undefined}>
            Allocation is decided by the offering department after the window
            closes. Seat counts, CPI thresholds and backlog limits shown here
            are the configured values for each minor.
          </Alert>
        </div>
      </div>

      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.name ?? ""}
        description={detail?.department_name ?? undefined}
        size="lg"
      >
        {detail && (
          <div className="space-y-5">
            <DetailList
              items={[
                { label: "Code", value: <span className="tabular">{detail.code}</span> },
                { label: "Offering department", value: detail.department_name },
                { label: "Total credits", value: detail.total_credits },
                { label: "Seats", value: `${detail.seats_available} of ${detail.capacity} available` },
                { label: "Opens from", value: `Semester ${roman(detail.eligible_from_semester)}` },
                { label: "Minimum CPI", value: detail.min_cpi ?? "Not specified" },
                { label: "Maximum backlogs", value: detail.max_backlogs ?? "Not specified" },
                { label: "Coordinator", value: detail.coordinator_name ?? "—" },
                { label: "Applications close", value: formatDate(detail.application_closes_at) },
              ]}
            />
            {detail.description && (
              <p className="text-sm leading-relaxed text-ink-muted">{detail.description}</p>
            )}
            {detail.courses.length > 0 && (
              <div>
                <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Course structure
                </h3>
                <ol className="mt-2 space-y-1.5">
                  {detail.courses.map((course) => (
                    <li key={course.id} className="flex items-center gap-2.5 rounded border border-line px-3 py-2">
                      <span className="tabular text-ink-muted">{course.course_code}</span>
                      <span className="min-w-0 flex-1 text-sm text-ink">{course.course_title}</span>
                      <span className="shrink-0 text-xs text-ink-muted">{course.credits} cr</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={confirmWithdraw}
        onClose={() => setConfirmWithdraw(false)}
        onConfirm={() => withdraw.mutate()}
        loading={withdraw.isPending}
        destructive
        title="Withdraw application?"
        confirmLabel="Withdraw"
        message="Your submitted minor preferences will be withdrawn. You can apply again while the window is open."
      />
    </div>
  );
}
