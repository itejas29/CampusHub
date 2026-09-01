import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api } from "@/lib/api";
import type { Curriculum } from "@/types";

const TYPE_TONE = {
  CORE: "brand", OPEN_ELECTIVE: "accent", PROGRAM_CORE_ELECTIVE: "info",
  MOOC: "warning", MINOR: "success", INTERNSHIP: "warning", PROJECT: "neutral",
} as const;

const STATUS_TONE = {
  PUBLISHED: "success", DRAFT: "warning", ARCHIVED: "neutral",
} as const;

const CONFIDENCE_LABEL: Record<string, string> = {
  CONFIRMED_OFFICIAL_SOURCE: "Confirmed from official source",
  PARTIAL_SOURCE: "Official source is incomplete",
  DERIVED_FROM_INTAKE: "Derived, not cited",
  REQUIRES_FACULTY_CONFIRMATION: "Requires faculty confirmation",
};

/**
 * Read-only view proving the curriculum is data. Every programme and every
 * version renders through this one page with no per-department code — including
 * two versions of the same programme whose structures genuinely differ.
 */
export function CurriculumExplorerPage() {
  const [selectedId, setSelectedId] = useState<string>("");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["curriculums"],
    queryFn: () => api.get<Curriculum[]>("/curriculum"),
  });

  const curriculum = data?.find((c) => String(c.id) === selectedId) ?? data?.[0];

  // Grouped by school, because that is how the university is organised and how
  // Open Elective eligibility is written.
  const grouped = useMemo(() => {
    const bySchool = new Map<string, Curriculum[]>();
    for (const item of data ?? []) {
      const key = item.school ?? "Other";
      if (!bySchool.has(key)) bySchool.set(key, []);
      bySchool.get(key)!.push(item);
    }
    return [...bySchool.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);

  const source = curriculum?.source;

  return (
    <div>
      <PageHeader
        title="Curriculum explorer"
        description="Every programme's structure exactly as stored. Versions are scoped to admission batches, so a cohort part-way through its degree keeps the curriculum it started on."
        breadcrumbs={[{ label: "Academics" }, { label: "Curriculum Explorer" }]}
        actions={
          data && data.length > 0 && (
            <Select
              value={selectedId || String(curriculum?.id ?? "")}
              onChange={(e) => setSelectedId(e.target.value)}
              aria-label="Select curriculum"
              className="w-full sm:w-96"
            >
              {grouped.map(([school, items]) => (
                <optgroup key={school} label={school}>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.program_name ?? item.name} — {item.version}
                      {item.status !== "PUBLISHED" ? ` (${item.status.toLowerCase()})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          )
        }
      />

      {isLoading && <LoadingState rows={5} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No curriculums published"
                      icon={<Network className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      {curriculum && (
        <div className="space-y-4">
          <Card>
            <CardBody className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="brand">{curriculum.program_name}</Badge>
                {curriculum.school && <Badge tone="neutral">{curriculum.school}</Badge>}
                <Badge tone="neutral">Version {curriculum.version}</Badge>
                <Badge tone="info">{curriculum.batch_label}</Badge>
                {curriculum.total_credits && (
                  <Badge tone="neutral">{curriculum.total_credits} total credits</Badge>
                )}
                <Badge tone={STATUS_TONE[curriculum.status] ?? "neutral"}>
                  {curriculum.status.toLowerCase()}
                </Badge>
              </div>

              {source && (
                <div className="rounded-md border border-line bg-surface-muted p-3 text-xs text-ink-muted">
                  <p className="font-medium text-ink">Source</p>
                  {source.title && <p className="mt-1">{source.title}</p>}
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                    {source.publisher && <span>{source.publisher}</span>}
                    {source.retrieved_at && <span>· retrieved {source.retrieved_at}</span>}
                    {source.confidence && (
                      <Badge tone={source.confidence === "CONFIRMED_OFFICIAL_SOURCE"
                        ? "success" : "warning"}>
                        {CONFIDENCE_LABEL[source.confidence] ?? source.confidence}
                      </Badge>
                    )}
                  </p>
                  {source.url && (
                    <a href={source.url} target="_blank" rel="noreferrer"
                       className="mt-1.5 inline-flex items-center gap-1 text-brand hover:underline">
                      Open the official document
                      <ExternalLink className="h-3 w-3" aria-hidden />
                    </a>
                  )}
                  {source.verified_by && (
                    <p className="mt-1.5">Verified by {source.verified_by}</p>
                  )}
                  {source.review_notes && (
                    <p className="mt-1.5 text-warning">{source.review_notes}</p>
                  )}
                </div>
              )}

              {curriculum.flagged_component_count > 0 && (
                <p className="flex items-start gap-1.5 text-xs text-warning">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  {curriculum.flagged_component_count} component(s) need faculty
                  confirmation before this version can be published. The
                  uncertainty is recorded rather than resolved by guesswork.
                </p>
              )}
            </CardBody>
          </Card>

          {curriculum.semesters.map((semester) => (
            <Card key={semester.semester_number}>
              <CardHeader
                title={semester.label}
                description={`${semester.components.length} requirement(s) · ${semester.total_credits} credits`}
              />
              <CardBody className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {semester.components.map((component) => (
                  <div key={component.id}
                       className={`rounded-md border p-3.5 ${
                         component.source_confidence === "REQUIRES_FACULTY_CONFIRMATION"
                           ? "border-warning/50 bg-warning/5" : "border-line"}`}>
                    <div className="flex items-start justify-between gap-2">
                      <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                        {component.course_code ?? component.code}
                      </span>
                      <Badge tone={TYPE_TONE[component.component_type] ?? "neutral"}>
                        {component.component_type.replace(/_/g, " ").toLowerCase()}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm font-medium leading-snug text-ink">
                      {component.title}
                    </p>
                    {component.scope_label && (
                      <p className="mt-0.5 text-xs text-ink-muted">{component.scope_label}</p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-2xs text-ink-subtle">
                      <span>{component.credits} credits</span>
                      {component.course_category && (
                        <><span>·</span><span>{component.course_category}</span></>
                      )}
                      {component.delivery_mode && (
                        <>
                          <span>·</span>
                          <span>{component.delivery_mode.replace(/_/g, "+").toLowerCase()}</span>
                        </>
                      )}
                      {component.is_elective && (
                        <>
                          <span>·</span>
                          <span>scope: {component.source_scope.replace(/_/g, " ").toLowerCase()}</span>
                        </>
                      )}
                      {component.offering_count ? (
                        <><span>·</span><span>{component.offering_count} offerings</span></>
                      ) : null}
                    </div>
                    {Array.isArray((component.eligibility as { eligible_schools?: string[] })
                      ?.eligible_schools) && (
                      <p className="mt-1.5 text-2xs text-ink-subtle">
                        Open to:{" "}
                        {((component.eligibility as { eligible_schools: string[] })
                          .eligible_schools).join(", ")}
                      </p>
                    )}
                    {component.source_note && (
                      <p className="mt-2 flex items-start gap-1 text-2xs text-warning">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                        {component.source_note}
                      </p>
                    )}
                  </div>
                ))}
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
