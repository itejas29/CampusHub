import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpen, CheckCircle2, Lock, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { api } from "@/lib/api";
import { roman } from "@/lib/utils";
import type { ComponentType, CurriculumComponent } from "@/types";

interface Props {
  componentType: ComponentType;
  title: string;
  description: string;
  basePath: string;
}

/**
 * Renders whichever elective slots the student's curriculum defines for this
 * family. Adding a new elective family is a curriculum change, not a code change.
 */
export function ElectiveListPage({ componentType, title, description, basePath }: Props) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["elective-components", componentType],
    queryFn: () =>
      api.get<CurriculumComponent[]>(`/electives/components?component_type=${componentType}`),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description={description}
        breadcrumbs={[{ label: "Academics" }, { label: title }]}
        meta={
          <Badge tone="brand" icon={<Sparkles className="h-3 w-3" />}>
            Curriculum Managed
          </Badge>
        }
      />

      {isLoading && <SkeletonCards count={3} />}
      {error && (
        <ErrorState
          message={error instanceof Error ? error.message : undefined}
          onRetry={() => refetch()}
        />
      )}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title="No requirements of this type"
            description="Your programme's curriculum does not include this elective category."
            icon={<BookOpen className="h-5 w-5" aria-hidden />}
          />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {bySemester(data).map((group) => (
            <SemesterTile key={group.semester} group={group} basePath={basePath} />
          ))}
        </div>
      )}
    </div>
  );
}

interface SemesterGroup { semester: number; components: CurriculumComponent[] }

/** One tile per semester: Semester VI's Program Electives 2 and 3 are chosen
 *  together, so they are one thing to the student, not two cards. */
function bySemester(components: CurriculumComponent[]): SemesterGroup[] {
  const groups = new Map<number, CurriculumComponent[]>();
  for (const c of [...components].sort((x, y) => x.semester_number - y.semester_number
    || x.sequence - y.sequence || x.code.localeCompare(y.code))) {
    groups.set(c.semester_number, [...(groups.get(c.semester_number) ?? []), c]);
  }
  return [...groups].map(([semester, list]) => ({ semester, components: list }));
}

/** "Program Elective 2" + "Program Elective 3" → "Program Electives 2 & 3". */
function groupTitle(components: CurriculumComponent[]): string {
  if (components.length === 1) return components[0].title;
  const parts = components.map((c) => c.title.match(/^(.*?)\s+(\S+)$/));
  const stem = parts[0]?.[1];
  if (stem && parts.every((m) => m && m[1] === stem)) {
    return `${stem}s ${parts.map((m) => m![2]).join(" & ")}`;
  }
  return components.map((c) => c.title).join(" & ");
}

function SemesterTile({ group, basePath }: { group: SemesterGroup; basePath: string }) {
  const { components } = group;
  const first = components[0];
  const locked = components.every((c) => c.is_unlocked === false);
  const allocations = components.filter((c) => c.allocated_course);
  const labels = [...new Set(components.map((c) => c.status_label).filter(Boolean))];
  // Chosen on one screen when every slot sits in the same two-stage round.
  const together = components.length > 1 && first.round_two_stage === true
    && components.every((c) => c.round_id === first.round_id);
  const single = components.length === 1 || together;
  const offered = Math.max(0, ...components.map((c) => c.offering_count ?? 0));
  const credits = components.reduce((n, c) => n + c.credits, 0);

  const body = (
    <Card className={`group relative flex h-full flex-col transition-all duration-200 ${
      locked ? "opacity-75 bg-surface-muted/30"
        : single ? "hover:border-brand/40 hover:shadow-card-hover" : ""}`}>
      <CardBody className="flex h-full flex-col p-5">
        <div className="flex items-start justify-between gap-2">
          <span className="rounded border border-line bg-surface-muted px-2 py-0.5 font-mono text-xs font-semibold text-ink">
            {components.map((c) => c.code).join(" · ")}
          </span>
          {labels.length === 1 && <StatusBadge status={labels[0]} />}
        </div>

        <h3 className="mt-3 text-base font-bold leading-snug text-ink transition-colors group-hover:text-brand">
          {groupTitle(components)}
        </h3>
        {first.scope_label && (
          <p className="mt-1 text-xs font-medium text-ink-muted">{first.scope_label}</p>
        )}
        {components.length > 1 && (
          <p className="mt-1 text-xs text-ink-muted">
            You take {components.length} subjects this semester, one for each.
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral" className="font-mono text-2xs">Sem {roman(group.semester)}</Badge>
          <Badge tone="neutral" className="text-2xs font-semibold">{credits} Credits</Badge>
          {offered > 0 && (
            <Badge tone="brand" className="text-2xs font-semibold">{offered} Offered</Badge>
          )}
        </div>

        {allocations.length > 0 && (
          <div className="mt-4 rounded-lg border border-success/20 bg-success-soft/40 p-3 text-xs text-ink">
            <div className="flex items-center gap-1.5 font-semibold text-success">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              <span>{allocations.length > 1 ? "Allocated Courses" : "Allocated Course"}</span>
            </div>
            {allocations.map((c) => (
              <p key={c.id} className="mt-1 truncate font-medium text-ink">
                {components.length > 1 && <span className="text-ink-muted">{c.code}: </span>}
                {c.allocated_course}
              </p>
            ))}
          </div>
        )}

        <div className="mt-auto border-t border-line/60 pt-4">
          {locked ? (
            <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
              <Lock className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
              Opens in Semester {roman(group.semester)}
            </p>
          ) : single ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand transition-colors group-hover:text-brand-hover">
              {allocations.length === components.length ? "Review Allocation"
                : together ? "Choose your electives" : "Open Preference Workspace"}
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" aria-hidden />
            </span>
          ) : (
            // Ranked separately: each slot keeps its own workspace.
            <ul className="space-y-2">
              {components.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2">
                  <Link to={`${basePath}/${c.id}`}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand hover:text-brand-hover">
                    {c.title}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                  {labels.length > 1 && <StatusBadge status={c.status_label} />}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardBody>
    </Card>
  );

  return locked || !single ? <div>{body}</div> : (
    <Link to={`${basePath}/${first.id}`} className="block h-full">{body}</Link>
  );
}
