import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Lock } from "lucide-react";
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
    <div>
      <PageHeader
        title={title}
        description={description}
        breadcrumbs={[{ label: "Academics" }, { label: title }]}
      />

      {isLoading && <SkeletonCards count={3} />}
      {error && (
        <ErrorState message={error instanceof Error ? error.message : undefined}
                    onRetry={() => refetch()} />
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
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((component) => {
            const locked = component.is_unlocked === false;
            const card = (
              <Card
                className={`h-full transition-colors ${
                  locked ? "opacity-75" : "hover:border-line-strong"
                }`}
              >
                <CardBody className="flex h-full flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <span className="tabular rounded bg-surface-muted px-1.5 py-0.5 text-ink-muted">
                      {component.code}
                    </span>
                    <StatusBadge status={component.status_label} />
                  </div>

                  <h3 className="mt-2.5 text-md font-semibold leading-snug text-ink">
                    {component.title}
                  </h3>
                  {component.scope_label && (
                    <p className="mt-1 text-sm text-ink-muted">{component.scope_label}</p>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <Badge tone="neutral">Semester {roman(component.semester_number)}</Badge>
                    <Badge tone="neutral">{component.credits} credits</Badge>
                    {(component.offering_count ?? 0) > 0 && (
                      <Badge tone="accent">{component.offering_count} courses</Badge>
                    )}
                  </div>

                  {component.allocated_course && (
                    <p className="mt-3 rounded bg-success-soft/50 px-2.5 py-2 text-xs text-ink">
                      <span className="font-medium">Allocated:</span> {component.allocated_course}
                    </p>
                  )}

                  <div className="mt-auto pt-4">
                    {locked ? (
                      <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
                        <Lock className="h-3.5 w-3.5" aria-hidden />
                        Opens in semester {roman(component.semester_number)}
                      </p>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-sm font-medium text-accent">
                        Open workspace
                        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                      </span>
                    )}
                  </div>
                </CardBody>
              </Card>
            );

            return locked ? (
              <div key={component.id}>{card}</div>
            ) : (
              <Link key={component.id} to={`${basePath}/${component.id}`} className="block">
                {card}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
