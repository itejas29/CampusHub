import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardFooter, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ResetPasswordButton } from "./ResetPasswordButton";
import { roman } from "@/lib/utils";
import type { DepartmentRow, Page, StudentRow } from "@/types";

export function StudentsAdminPage() {
  const { can } = useAuth();
  const canManage = can("students:manage");
  const [search, setSearch] = useState("");

  const [departmentId, setDepartmentId] = useState("");
  const [semester, setSemester] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["students", search, departmentId, semester, page],
    queryFn: () =>
      api.get<Page<StudentRow>>(
        `/students${qs({
          q: search || undefined, department_id: departmentId || undefined,
          semester: semester || undefined, page, page_size: pageSize,
        })}`,
      ),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div>
      <PageHeader
        title="Students"
        description="Student records across departments and semesters."
        breadcrumbs={[{ label: "Administration" }, { label: "Students" }]}
      />

      <Card>
        <CardHeader
          title={`${data?.total ?? 0} student${data?.total === 1 ? "" : "s"}`}
          icon={<Users className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={search}
                onChange={(value) => { setSearch(value); setPage(1); }}
                placeholder="Name, roll number or email"
                className="w-full sm:w-64"
              />
              <Select
                value={departmentId}
                onChange={(e) => { setDepartmentId(e.target.value); setPage(1); }}
                aria-label="Filter by department" className="w-full sm:w-40"
              >
                <option value="">All departments</option>
                {(departments.data ?? []).map((department) => (
                  <option key={department.id} value={department.id}>{department.code}</option>
                ))}
              </Select>
              <Select
                value={semester}
                onChange={(e) => { setSemester(e.target.value); setPage(1); }}
                aria-label="Filter by semester" className="w-full sm:w-36"
              >
                <option value="">All semesters</option>
                {[1, 2, 3, 4, 5, 6, 7, 8].map((value) => (
                  <option key={value} value={value}>Semester {roman(value)}</option>
                ))}
              </Select>
            </div>
          }
        />

        {isLoading ? (
          <LoadingState rows={6} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : (
          <>
            <TableWrap>
              <THead>
                <TH width="24%">Student</TH>
                <TH width="12%">Roll no.</TH>
                <TH width="10%">Dept</TH>
                <TH width="8%">Sem</TH>
                <TH width="8%">Div</TH>
                <TH width="10%" align="right">CPI</TH>
                <TH width="10%" align="right">Backlogs</TH>
                <TH width="12%">Status</TH>
                {canManage && <TH width="10%" align="right">Account</TH>}
              </THead>
              <TBody>
                {!data?.items.length ? (
                  <TableEmpty colSpan={canManage ? 9 : 8}>No students match these filters.</TableEmpty>
                ) : (
                  data.items.map((student) => (
                    <TR key={student.id}>
                      <TD>
                        <div className="flex items-center gap-2.5">
                          <Avatar name={student.full_name} src={student.avatar_url} size="sm" />
                          <div className="min-w-0">
                            {/* The profile decides its own access per student,
                                so linking every row is safe: a caller without
                                access is told so rather than shown a blank. */}
                            <Link to={`/people/students/${student.id}`}
                                  className="truncate font-medium text-ink hover:text-brand hover:underline">
                              {student.full_name}
                            </Link>
                            <p className="truncate text-2xs text-ink-subtle">{student.email}</p>
                          </div>
                        </div>
                      </TD>
                      <TD className="tabular">{student.roll_number}</TD>
                      <TD>{student.department_code}</TD>
                      <TD>{roman(student.current_semester)}</TD>
                      <TD>{student.division ?? "—"}</TD>
                      <TD align="right" className="tabular font-medium">
                        {student.cpi?.toFixed(2) ?? "—"}
                      </TD>
                      <TD align="right">
                        {student.backlog_count > 0
                          ? <Badge tone="warning">{student.backlog_count}</Badge>
                          : <span className="text-ink-subtle">0</span>}
                      </TD>
                      <TD><StatusBadge status={student.status} /></TD>
                      {canManage && (
                        <TD align="right">
                          <ResetPasswordButton kind="students" id={student.id} name={student.full_name} />
                        </TD>
                      )}
                    </TR>

                  ))
                )}
              </TBody>
            </TableWrap>

            {totalPages > 1 && (
              <CardFooter className="flex items-center justify-between">
                <p className="text-xs text-ink-muted">
                  Page {page} of {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" disabled={page <= 1}
                          onClick={() => setPage((p) => p - 1)}>
                    Previous
                  </Button>
                  <Button variant="secondary" size="sm" disabled={page >= totalPages}
                          onClick={() => setPage((p) => p + 1)}>
                    Next
                  </Button>
                </div>
              </CardFooter>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
