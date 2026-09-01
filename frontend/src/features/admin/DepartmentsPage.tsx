import { useQuery } from "@tanstack/react-query";
import { Building2, GraduationCap, Layers, Users } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { api } from "@/lib/api";
import type { DepartmentRow } from "@/types";

export function DepartmentsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  const bySchool = (data ?? []).reduce<Record<string, DepartmentRow[]>>((acc, row) => {
    (acc[row.school] ??= []).push(row);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Departments"
        description="Schools, departments and the programmes they run. Open Elective scope rules resolve against this structure."
        breadcrumbs={[{ label: "Administration" }, { label: "Departments" }]}
      />

      {isLoading && <SkeletonCards count={6} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No departments configured"
                      icon={<Building2 className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="space-y-6">
          {Object.entries(bySchool).map(([school, departments]) => (
            <section key={school}>
              <h2 className="mb-3 text-md font-semibold text-ink">{school}</h2>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {departments.map((department) => (
                  <Card key={department.id}>
                    <CardBody>
                      <div className="flex items-start justify-between gap-2">
                        <Badge tone="brand" className="font-mono">{department.code}</Badge>
                        {!department.is_active && <Badge tone="neutral">Inactive</Badge>}
                      </div>
                      <h3 className="mt-2.5 text-md font-semibold leading-snug text-ink">
                        {department.name}
                      </h3>
                      {department.description && (
                        <p className="mt-1 line-clamp-2 text-sm text-ink-muted">
                          {department.description}
                        </p>
                      )}
                      <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3">
                        {[
                          { icon: Users, label: "Students", value: department.student_count },
                          { icon: GraduationCap, label: "Faculty", value: department.faculty_count },
                          { icon: Layers, label: "Programmes", value: department.program_count },
                        ].map((stat) => (
                          <div key={stat.label}>
                            <dt className="flex items-center gap-1 text-2xs text-ink-subtle">
                              <stat.icon className="h-3 w-3" aria-hidden />
                              {stat.label}
                            </dt>
                            <dd className="mt-0.5 font-heading text-lg font-semibold tabular-nums text-ink">
                              {stat.value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </CardBody>
                  </Card>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
