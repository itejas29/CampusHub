import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, GraduationCap, Layers, UserCog, Users } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { FormField, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DepartmentRow, FacultyRow } from "@/types";

export function DepartmentsPage() {
  const { can } = useAuth();
  // Appointing a Head of Department is the registrar's office alone.
  const canAppoint = can("departments:manage");
  const [appoint, setAppoint] = useState<DepartmentRow | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

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
        description="Schools, departments and the programmes they run. Open Elective scope rules resolve against this structure. Each department's Head appoints its coordinators."
        breadcrumbs={[{ label: "Administration" }, { label: "Departments" }]}
      />

      {banner && (
        <Alert variant="success" className="mb-4" onDismiss={() => setBanner(null)}>
          {banner}
        </Alert>
      )}

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
                      <div className="mt-3 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                            Head of Department
                          </p>
                          <p className="truncate text-sm text-ink">
                            {department.hod_name
                              ?? <span className="text-ink-subtle">Not appointed</span>}
                          </p>
                        </div>
                        {canAppoint && (
                          <Button variant="secondary" size="sm"
                                  onClick={() => setAppoint(department)}
                                  icon={<UserCog className="h-3.5 w-3.5" aria-hidden />}>
                            {department.hod_name ? "Change" : "Appoint"}
                          </Button>
                        )}
                      </div>
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

      {appoint && (
        <AppointHodModal
          department={appoint}
          onClose={() => setAppoint(null)}
          onDone={(text) => {
            setAppoint(null);
            setBanner(text);
          }}
        />
      )}
    </div>
  );
}

function AppointHodModal({
  department, onClose, onDone,
}: {
  department: DepartmentRow; onClose: () => void; onDone: (text: string) => void;
}) {
  const queryClient = useQueryClient();
  const [facultyId, setFacultyId] = useState(
    department.hod_faculty_id ? String(department.hod_faculty_id) : "",
  );
  const [error, setError] = useState<string | null>(null);

  const faculty = useQuery({
    queryKey: ["faculty"],
    queryFn: () => api.get<FacultyRow[]>("/faculty"),
  });
  // A department is headed by one of its own faculty.
  const candidates = (faculty.data ?? []).filter(
    (f) => f.department_id === department.id && f.is_active,
  );

  const save = useMutation({
    mutationFn: () =>
      api.put<DepartmentRow>(`/departments/${department.id}/hod`, {
        faculty_id: facultyId ? Number(facultyId) : null,
      }),
    onSuccess: (row) => {
      void queryClient.invalidateQueries({ queryKey: ["departments"] });
      onDone(row.hod_name
        ? `${row.hod_name} is now Head of ${department.code}.`
        : `Head of ${department.code} cleared.`);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not appoint."),
  });

  return (
    <Modal
      open onClose={onClose} title={`Head of ${department.code}`}
      description="The Head appoints this department's coordinators and mentors, and holds none of those roles or any mentees themselves."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <FormField
          label="Faculty member"
          hint="Anyone who still has mentees or a coordinator or mentor role must hand those over first."
        >
          <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}
                  data-autofocus>
            <option value="">No Head of Department</option>
            {candidates.map((f) => (
              <option key={f.id} value={f.id}>{f.full_name} ({f.designation})</option>
            ))}
          </Select>
        </FormField>
      </div>
    </Modal>
  );
}
