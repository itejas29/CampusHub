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
          {data.map((component) => {
            const locked = component.is_unlocked === false;
            const hasAllocation = Boolean(component.allocated_course);

            const cardContent = (
              <Card
                className={`group relative flex h-full flex-col transition-all duration-200 ${
                  locked
                    ? "opacity-75 bg-surface-muted/30"
                    : "hover:border-brand/40 hover:shadow-card-hover"
                }`}
              >
                <CardBody className="flex h-full flex-col p-5">
                  <div className="flex items-start justify-between gap-2">
                    <span className="rounded border border-line bg-surface-muted px-2 py-0.5 font-mono text-xs font-semibold text-ink">
                      {component.code}
                    </span>
                    <StatusBadge status={component.status_label} />
                  </div>

                  <h3 className="mt-3 text-base font-bold leading-snug text-ink transition-colors group-hover:text-brand">
                    {component.title}
                  </h3>
                  {component.scope_label && (
                    <p className="mt-1 text-xs font-medium text-ink-muted">{component.scope_label}</p>
                  )}

                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    <Badge tone="neutral" className="font-mono text-2xs">
                      Sem {roman(component.semester_number)}
                    </Badge>
                    <Badge tone="neutral" className="text-2xs font-semibold">
                      {component.credits} Credits
                    </Badge>
                    {(component.offering_count ?? 0) > 0 && (
                      <Badge tone="brand" className="text-2xs font-semibold">
                        {component.offering_count} Offered
                      </Badge>
                    )}
                  </div>

                  {hasAllocation && (
                    <div className="mt-4 rounded-lg border border-success/20 bg-success-soft/40 p-3 text-xs text-ink">
                      <div className="flex items-center gap-1.5 font-semibold text-success">
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                        <span>Allocated Course</span>
                      </div>
                      <p className="mt-1 font-medium text-ink truncate">{component.allocated_course}</p>
                    </div>
                  )}

                  <div className="mt-auto border-t border-line/60 pt-4">
                    {locked ? (
                      <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
                        <Lock className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                        Opens in Semester {roman(component.semester_number)}
                      </p>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand transition-colors group-hover:text-brand-hover">
                        {hasAllocation ? "Review Allocation" : "Open Preference Workspace"}
                        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" aria-hidden />
                      </span>
                    )}
                  </div>
                </CardBody>
              </Card>
            );

            return locked ? (
              <div key={component.id}>{cardContent}</div>
            ) : (
              <Link key={component.id} to={`${basePath}/${component.id}`} className="block h-full">
                {cardContent}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
