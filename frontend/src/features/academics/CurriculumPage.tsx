import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleDot, Lock } from "lucide-react";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import type { Curriculum } from "@/types";
import { cn } from "@/lib/utils";

const TYPE_TONE = {
  CORE: "brand", OPEN_ELECTIVE: "accent", PROGRAM_CORE_ELECTIVE: "info",
  MOOC: "warning", MINOR: "success", INTERNSHIP: "warning", PROJECT: "neutral",
} as const;

export function CurriculumPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["curriculum", "me"],
    queryFn: () => api.get<Curriculum>("/curriculum/me"),
  });

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        title="Curriculum unavailable"
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="Curriculum"
        description="Your programme structure, semester by semester. Elective slots and their source restrictions come from the published curriculum — not from a fixed list in the app."
        breadcrumbs={[{ label: "Academics" }, { label: "Curriculum" }]}
        meta={
          <>
            <Badge tone="brand">{data.program_name}</Badge>
            <Badge tone="neutral">Version {data.version}</Badge>
            {data.total_credits && <Badge tone="neutral">{data.total_credits} total credits</Badge>}
          </>
        }
      />

      <div className="space-y-4">
        {data.semesters.map((semester) => (
          <Card
            key={semester.semester_number}
            className={cn(semester.is_current && "border-accent/50 ring-1 ring-accent/20")}
          >
            <CardHeader
              title={
                <span className="flex items-center gap-2">
                  {semester.label}
                  {semester.is_current && <Badge tone="accent">Current</Badge>}
                  {semester.is_completed && (
                    <Badge tone="success" icon={<CheckCircle2 className="h-3 w-3" aria-hidden />}>
                      Completed
                    </Badge>
                  )}
                </span>
              }
              description={`${semester.components.length} requirement${
                semester.components.length === 1 ? "" : "s"
              } · ${semester.total_credits} credits`}
              icon={
                semester.is_completed
                  ? <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
                  : semester.is_current
                    ? <CircleDot className="h-4 w-4 text-accent" aria-hidden />
                    : <Lock className="h-4 w-4 text-ink-subtle" aria-hidden />
              }
            />
            <CardBody className="grid gap-2.5 sm:grid-cols-2">
              {semester.components.map((component) => (
                <div
                  key={component.id}
                  className={cn(
                    "rounded-md border p-3.5",
                    component.is_unlocked === false
                      ? "border-line bg-surface-muted/40"
                      : "border-line",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                      {component.code}
                    </span>
                    <StatusBadge status={component.status_label} />
                  </div>
                  <p className="mt-2 text-sm font-medium leading-snug text-ink">
                    {component.title}
                  </p>
                  {component.scope_label && (
                    <p className="mt-0.5 text-xs text-ink-muted">{component.scope_label}</p>
                  )}
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <Badge tone={TYPE_TONE[component.component_type] ?? "neutral"}>
                      {component.component_type.replace(/_/g, " ").toLowerCase()}
                    </Badge>
                    <Badge tone="neutral">{component.credits} cr</Badge>
                    {component.is_elective && (component.offering_count ?? 0) > 0 && (
                      <Badge tone="neutral">{component.offering_count} options</Badge>
                    )}
                  </div>
                  {component.allocated_course && (
                    <p className="mt-2 rounded bg-success-soft/50 px-2 py-1.5 text-xs text-ink">
                      <span className="font-medium">Allocated:</span>{" "}
                      {component.allocated_course}
                    </p>
                  )}
                </div>
              ))}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
