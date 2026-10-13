import { useQuery } from "@tanstack/react-query";
import { Edit2, GraduationCap, Mail, MapPin, Phone, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { api, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DepartmentRow, FacultyRow } from "@/types";
import { AddFacultyModal, DeleteFacultyModal, EditFacultyModal } from "@/features/admin/FacultyFormModals";

export function FacultyDirectoryPage() {
  const { can, isAdmin } = useAuth();
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editMember, setEditMember] = useState<FacultyRow | null>(null);
  const [deleteMember, setDeleteMember] = useState<FacultyRow | null>(null);

  const canManageFaculty = can("faculty:manage") || isAdmin;

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
    <div className="space-y-6">
      <PageHeader
        title="Faculty Directory"
        description="Public contact details for faculty across departments — academic profiles, cabin locations, and mentorship assignments."
        breadcrumbs={[{ label: "Support" }, { label: "Faculty Directory" }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canManageFaculty && (
              <Button
                size="sm"
                icon={<Plus className="h-4 w-4" />}
                onClick={() => setAddOpen(true)}
              >
                Add New Teacher
              </Button>
            )}
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Name, designation or specialisation"
              className="w-full sm:w-64"
            />
            <Select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              aria-label="Filter by department"
              className="w-full sm:w-48"
            >
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
          <EmptyState
            title="No faculty found"
            description="Try a different search term or department."
            icon={<GraduationCap className="h-5 w-5" aria-hidden />}
          />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((member) => (
            <Card key={member.id} className="relative transition-all hover:shadow-xs">
              <CardBody className="flex h-full flex-col justify-between">
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <Avatar name={member.full_name} src={member.avatar_url} size="lg" />
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-base font-semibold text-ink">
                          {member.full_name}
                        </h3>
                        <p className="truncate text-xs font-medium text-ink-muted">{member.designation}</p>
                        <p className="truncate text-2xs text-ink-subtle">{member.department_name}</p>
                      </div>
                    </div>

                    {canManageFaculty && (
                      <div className="flex shrink-0 items-center gap-1">
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<Edit2 className="h-3.5 w-3.5" />}
                          onClick={() => setEditMember(member)}
                          className="h-7 w-7 p-0"
                          aria-label={`Edit ${member.full_name}`}
                        />
                        <Button
                          variant="danger"
                          size="sm"
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setDeleteMember(member)}
                          className="h-7 w-7 p-0"
                          aria-label={`Deactivate ${member.full_name}`}
                        />
                      </div>
                    )}
                  </div>

                  {member.specialization && (
                    <p className="mt-3 text-xs leading-relaxed text-ink-muted line-clamp-2">
                      {member.specialization}
                    </p>
                  )}

                  <dl className="mt-3.5 space-y-1.5 text-xs">
                    {member.cabin && (
                      <div className="flex items-center gap-2 text-ink-muted">
                        <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                        Cabin {member.cabin}
                      </div>
                    )}
                    {member.public_email && (
                      <a
                        href={`mailto:${member.public_email}`}
                        className="flex items-center gap-2 text-ink-muted hover:text-primary transition-colors"
                      >
                        <Mail className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                        <span className="truncate">{member.public_email}</span>
                      </a>
                    )}
                    {member.public_phone && (
                      <div className="flex items-center gap-2 text-ink-muted">
                        <Phone className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                        {member.public_phone}
                      </div>
                    )}
                  </dl>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-line/50 pt-3">
                  <Badge tone="brand" className="font-mono text-2xs">
                    {member.employee_code}
                  </Badge>
                  {member.qualification && (
                    <Badge tone="neutral" className="text-2xs">
                      {member.qualification}
                    </Badge>
                  )}
                  {member.is_mentor && (
                    <Badge tone="accent" className="text-2xs">
                      {member.mentee_count} mentees
                    </Badge>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

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
