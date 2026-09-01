import { useQuery } from "@tanstack/react-query";
import { GraduationCap, Mail, MapPin, Phone } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { api, qs } from "@/lib/api";
import type { DepartmentRow, FacultyRow } from "@/types";

export function FacultyDirectoryPage() {
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["faculty", search, departmentId],
    queryFn: () =>
      api.get<FacultyRow[]>(
        `/faculty${qs({ q: search || undefined, department_id: departmentId || undefined })}`,
      ),
  });

  return (
    <div>
      <PageHeader
        title="Faculty Directory"
        description="Public contact details for faculty across departments — the same information students see on mentor and internship records."
        breadcrumbs={[{ label: "Support" }, { label: "Faculty Directory" }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={search} onChange={setSearch}
                         placeholder="Name, designation or specialisation"
                         className="w-full sm:w-64" />
            <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}
                    aria-label="Filter by department" className="w-full sm:w-48">
              <option value="">All departments</option>
              {(departments.data ?? []).map((department) => (
                <option key={department.id} value={department.id}>
                  {department.code} — {department.short_name ?? department.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      {isLoading && <SkeletonCards count={6} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No faculty found"
                      description="Try a different search term or department."
                      icon={<GraduationCap className="h-5 w-5" aria-hidden />} />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((member) => (
            <Card key={member.id}>
              <CardBody>
                <div className="flex items-start gap-3">
                  <Avatar name={member.full_name} src={member.avatar_url} size="lg" />
                  <div className="min-w-0 flex-1">
                    <h3 className="text-md font-semibold leading-snug text-ink">
                      {member.full_name}
                    </h3>
                    <p className="text-xs text-ink-muted">{member.designation}</p>
                    <p className="text-xs text-ink-subtle">{member.department_name}</p>
                  </div>
                </div>

                {member.specialization && (
                  <p className="mt-3 text-sm text-ink-muted">{member.specialization}</p>
                )}

                <dl className="mt-3 space-y-1.5 text-xs">
                  {member.cabin && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      Cabin {member.cabin}
                    </div>
                  )}
                  {member.public_email && (
                    <a href={`mailto:${member.public_email}`}
                       className="flex items-center gap-2 text-ink-muted hover:text-accent">
                      <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate">{member.public_email}</span>
                    </a>
                  )}
                  {member.public_phone && (
                    <div className="flex items-center gap-2 text-ink-muted">
                      <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      {member.public_phone}
                    </div>
                  )}
                </dl>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone="neutral" className="font-mono">{member.employee_code}</Badge>
                  {member.qualification && <Badge tone="neutral">{member.qualification}</Badge>}
                  {member.is_mentor && (
                    <Badge tone="accent">{member.mentee_count} mentees</Badge>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
