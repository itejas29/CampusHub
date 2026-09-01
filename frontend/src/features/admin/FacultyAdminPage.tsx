import { useQuery } from "@tanstack/react-query";
import { UserCog } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import type { DepartmentRow, FacultyRow } from "@/types";

export function FacultyAdminPage() {
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["faculty-admin", search, departmentId],
    queryFn: () =>
      api.get<FacultyRow[]>(
        `/faculty${qs({ q: search || undefined, department_id: departmentId || undefined })}`,
      ),
  });

  return (
    <div>
      <PageHeader
        title="Faculty"
        description="Faculty records, mentorship load and public contact details."
        breadcrumbs={[{ label: "Administration" }, { label: "Faculty" }]}
      />

      <Card>
        <CardHeader
          title={`${data?.length ?? 0} faculty member${data?.length === 1 ? "" : "s"}`}
          icon={<UserCog className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={search} onChange={setSearch}
                           placeholder="Name or specialisation" className="w-full sm:w-60" />
              <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}
                      aria-label="Filter by department" className="w-full sm:w-40">
                <option value="">All departments</option>
                {(departments.data ?? []).map((department) => (
                  <option key={department.id} value={department.id}>{department.code}</option>
                ))}
              </Select>
            </div>
          }
        />

        {isLoading ? (
          <LoadingState rows={5} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.length ? (
          <EmptyState title="No faculty records"
                      icon={<UserCog className="h-5 w-5" aria-hidden />} />
        ) : (
          <TableWrap>
            <THead>
              <TH width="24%">Name</TH>
              <TH width="12%">Code</TH>
              <TH width="10%">Dept</TH>
              <TH width="18%">Designation</TH>
              <TH>Specialisation</TH>
              <TH width="10%">Cabin</TH>
              <TH width="10%" align="right">Mentees</TH>
            </THead>
            <TBody>
              {data.length === 0 ? (
                <TableEmpty colSpan={7}>No faculty match these filters.</TableEmpty>
              ) : (
                data.map((member) => (
                  <TR key={member.id}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={member.full_name} src={member.avatar_url} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{member.full_name}</p>
                          <p className="truncate text-2xs text-ink-subtle">{member.email}</p>
                        </div>
                      </div>
                    </TD>
                    <TD className="tabular">{member.employee_code}</TD>
                    <TD>{member.department_code}</TD>
                    <TD className="text-ink-muted">{member.designation}</TD>
                    <TD className="text-ink-muted">{member.specialization ?? "—"}</TD>
                    <TD className="text-ink-muted">{member.cabin ?? "—"}</TD>
                    <TD align="right">
                      {member.mentee_count > 0
                        ? <Badge tone="accent">{member.mentee_count}</Badge>
                        : <span className="text-ink-subtle">0</span>}
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
      </Card>
    </div>
  );
}
