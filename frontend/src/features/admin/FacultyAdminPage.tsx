import { useQuery } from "@tanstack/react-query";
import { Edit2, Plus, Trash2, UserCog } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import type { DepartmentRow, FacultyRow } from "@/types";
import { AddFacultyModal, DeleteFacultyModal, EditFacultyModal } from "./FacultyFormModals";
import { ResetPasswordButton } from "./ResetPasswordButton";

export function FacultyAdminPage() {
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editMember, setEditMember] = useState<FacultyRow | null>(null);
  const [deleteMember, setDeleteMember] = useState<FacultyRow | null>(null);

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
    <div className="space-y-6">
      <PageHeader
        title="Faculty Management"
        description="Faculty records, mentorship allocations, designations and departmental profiles."
        breadcrumbs={[{ label: "Administration" }, { label: "Faculty" }]}
        actions={
          <Button
            size="sm"
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setAddOpen(true)}
          >
            Add New Teacher
          </Button>
        }
      />

      <Card>
        <CardHeader
          title={`${data?.length ?? 0} faculty member${data?.length === 1 ? "" : "s"}`}
          icon={<UserCog className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder="Name or specialisation"
                className="w-full sm:w-60"
              />
              <Select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                aria-label="Filter by department"
                className="w-full sm:w-40"
              >
                <option value="">All departments</option>
                {(departments.data ?? []).map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.code}
                  </option>
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
          <EmptyState
            title="No faculty records"
            icon={<UserCog className="h-5 w-5" aria-hidden />}
          />
        ) : (
          <TableWrap>
            <THead>
              <TH width="22%">Name</TH>
              <TH width="12%">Employee Code</TH>
              <TH width="8%">Dept</TH>
              <TH width="16%">Designation</TH>
              <TH>Specialisation</TH>
              <TH width="10%">Cabin</TH>
              <TH width="8%" align="right">Mentees</TH>
              <TH width="12%" align="right">Actions</TH>
            </THead>
            <TBody>
              {data.length === 0 ? (
                <TableEmpty colSpan={8}>No faculty match these filters.</TableEmpty>
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
                    <TD className="tabular font-mono text-xs">{member.employee_code}</TD>
                    <TD>{member.department_code}</TD>
                    <TD className="text-ink-muted">{member.designation}</TD>
                    <TD className="text-ink-muted">{member.specialization ?? "—"}</TD>
                    <TD className="text-ink-muted">{member.cabin ?? "—"}</TD>
                    <TD align="right">
                      {member.mentee_count > 0 ? (
                        <Badge tone="accent">{member.mentee_count}</Badge>
                      ) : (
                        <span className="text-ink-subtle">0</span>
                      )}
                    </TD>
                    <TD align="right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<Edit2 className="h-3.5 w-3.5" />}
                          onClick={() => setEditMember(member)}
                          className="h-7 px-2 text-xs"
                          aria-label={`Edit ${member.full_name}`}
                        >
                          Edit
                        </Button>
                        <ResetPasswordButton kind="faculty" id={member.id} name={member.full_name} />
                        <Button
                          variant="danger"

                          size="sm"
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setDeleteMember(member)}
                          className="h-7 px-2 text-xs"
                          aria-label={`Deactivate ${member.full_name}`}
                        />
                      </div>
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
      </Card>

      {/* Add Faculty Modal */}
      {addOpen && (
        <AddFacultyModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          onDone={() => setAddOpen(false)}
        />
      )}

      {/* Edit Faculty Modal */}
      {editMember && (
        <EditFacultyModal
          open={!!editMember}
          member={editMember}
          onClose={() => setEditMember(null)}
          onDone={() => setEditMember(null)}
        />
      )}

      {/* Delete Faculty Modal */}
      {deleteMember && (
        <DeleteFacultyModal
          open={!!deleteMember}
          member={deleteMember}
          onClose={() => setDeleteMember(null)}
          onDone={() => setDeleteMember(null)}
        />
      )}
    </div>
  );
}
