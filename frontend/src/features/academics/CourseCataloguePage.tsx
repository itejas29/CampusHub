import { useQuery } from "@tanstack/react-query";
import { Library } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardFooter, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { DetailList, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import type { Course, DepartmentRow, Page } from "@/types";

export function CourseCataloguePage() {
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [area, setArea] = useState("");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<Course | null>(null);
  const pageSize = 25;

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });
  const areas = useQuery({
    queryKey: ["specializations"],
    queryFn: () => api.get<string[]>("/courses/specializations"),
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["courses", search, departmentId, area, page],
    queryFn: () =>
      api.get<Page<Course>>(
        `/courses${qs({
          q: search || undefined, department_id: departmentId || undefined,
          specialization_area: area || undefined, page, page_size: pageSize,
        })}`,
      ),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div>
      <PageHeader
        title="Course catalogue"
        description="Every course in the system — programme cores, electives, MOOCs and minor courses."
        breadcrumbs={[{ label: "Academics" }, { label: "Course Catalogue" }]}
      />

      <Card>
        <CardHeader
          title={`${data?.total ?? 0} course${data?.total === 1 ? "" : "s"}`}
          icon={<Library className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={search}
                           onChange={(value) => { setSearch(value); setPage(1); }}
                           placeholder="Code or title" className="w-full sm:w-56" />
              <Select value={departmentId}
                      onChange={(e) => { setDepartmentId(e.target.value); setPage(1); }}
                      aria-label="Filter by department" className="w-full sm:w-40">
                <option value="">All departments</option>
                {(departments.data ?? []).map((department) => (
                  <option key={department.id} value={department.id}>{department.code}</option>
                ))}
              </Select>
              <Select value={area} onChange={(e) => { setArea(e.target.value); setPage(1); }}
                      aria-label="Filter by specialisation" className="w-full sm:w-56">
                <option value="">All specialisations</option>
                {(areas.data ?? []).map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </Select>
            </div>
          }
        />

        {isLoading ? (
          <LoadingState rows={6} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.items.length ? (
          <EmptyState title="No courses found" description="Try clearing the filters."
                      icon={<Library className="h-5 w-5" aria-hidden />} />
        ) : (
          <>
            <TableWrap>
              <THead>
                <TH width="12%">Code</TH>
                <TH>Title</TH>
                <TH width="14%">Owner</TH>
                <TH width="20%">Specialisation</TH>
                <TH width="9%" align="right">Credits</TH>
                <TH width="9%" align="right">L-T-P</TH>
              </THead>
              <TBody>
                {data.items.length === 0 ? (
                  <TableEmpty colSpan={6}>No courses match these filters.</TableEmpty>
                ) : (
                  data.items.map((course) => (
                    <TR key={course.id} onClick={() => setDetail(course)}>
                      <TD className="tabular">{course.code}</TD>
                      <TD className="font-medium text-ink">
                        {course.title}
                        {course.platform && (
                          <Badge tone="warning" className="ml-2">{course.platform}</Badge>
                        )}
                      </TD>
                      <TD className="text-ink-muted">
                        {course.department_code ?? course.offering_school ?? "—"}
                      </TD>
                      <TD className="text-ink-muted">{course.specialization_area ?? "—"}</TD>
                      <TD align="right" className="tabular">{course.credits}</TD>
                      <TD align="right" className="tabular text-ink-subtle">
                        {course.lecture_hours}-{course.tutorial_hours}-{course.practical_hours}
                      </TD>
                    </TR>
                  ))
                )}
              </TBody>
            </TableWrap>

            {totalPages > 1 && (
              <CardFooter className="flex items-center justify-between">
                <p className="text-xs text-ink-muted">Page {page} of {totalPages}</p>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" disabled={page <= 1}
                          onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button variant="secondary" size="sm" disabled={page >= totalPages}
                          onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </CardFooter>
            )}
          </>
        )}
      </Card>

      <Modal open={Boolean(detail)} onClose={() => setDetail(null)}
             title={detail?.title ?? ""} description={detail?.code} size="lg">
        {detail && (
          <div className="space-y-5">
            <DetailList
              items={[
                { label: "Code", value: <span className="tabular">{detail.code}</span> },
                { label: "Credits", value: detail.credits },
                { label: "Department", value: detail.department_name ?? "—" },
                { label: "Offering school", value: detail.offering_school ?? "—" },
                {
                  label: "Contact hours",
                  value: `L ${detail.lecture_hours} · T ${detail.tutorial_hours} · P ${detail.practical_hours}`,
                },
                { label: "Specialisation", value: detail.specialization_area ?? "—" },
                { label: "Platform", value: detail.platform ?? "—" },
                { label: "Duration", value: detail.duration_weeks ? `${detail.duration_weeks} weeks` : "—" },
              ]}
            />
            {detail.description && (
              <p className="text-sm leading-relaxed text-ink-muted">{detail.description}</p>
            )}
            {detail.prerequisites && (
              <div>
                <h3 className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                  Prerequisites
                </h3>
                <p className="mt-1 text-sm text-ink-muted">{detail.prerequisites}</p>
              </div>
            )}
            {detail.provider_url && (
              <a href={detail.provider_url} target="_blank" rel="noreferrer"
                 className="inline-flex text-sm font-medium text-accent hover:underline">
                Open provider page
              </a>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
