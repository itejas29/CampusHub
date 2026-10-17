import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, ShieldCheck, Trash2, UserCog } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Checkbox, FormField, Input, Select, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { humanise } from "@/lib/utils";
import { RoleBoard } from "./RoleBoard";
import type {
  DepartmentRow, FacultyRow, RoleAssignment, RoleDefinition, RoleMatrix,
} from "@/types";

interface DomainOption { value: string; label: string }

/** Tone per domain so the same coordination reads the same everywhere. */
const DOMAIN_TONE: Record<string, "brand" | "accent" | "info" | "success" | "warning"> = {
  CSSI: "warning",
  SUMMER_INTERNSHIP: "accent",
  MINOR: "success",
  MOOC: "info",
  OPEN_ELECTIVE: "brand",
  CORE_ELECTIVE: "brand",
  MENTORSHIP: "info",
};

export function RoleAssignmentsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  // A Head of Department works inside one department; the registrar sees all.
  const headed = user?.faculty?.hod_department_code ?? null;
  const [tab, setTab] = useState("board");
  const [search, setSearch] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const [revoke, setRevoke] = useState<RoleAssignment | null>(null);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const matrix = useQuery({
    queryKey: ["role-matrix"],
    queryFn: () => api.get<RoleMatrix>("/admin/roles/matrix"),
  });
  const assignments = useQuery({
    queryKey: ["role-assignments"],
    queryFn: () => api.get<RoleAssignment[]>("/admin/roles"),
  });
  const [edit, setEdit] = useState<RoleAssignment | null>(null);

  const roles = useQuery({
    queryKey: ["role-definitions"],
    queryFn: () => api.get<RoleDefinition[]>("/admin/roles/definitions"),
  });
  const domains = useQuery({
    queryKey: ["role-domains"],
    queryFn: () => api.get<DomainOption[]>("/admin/roles/domains"),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["role-matrix"] });
    void queryClient.invalidateQueries({ queryKey: ["role-assignments"] });
  }

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/roles/${id}`),
    onSuccess: () => {
      setRevoke(null);
      setBanner({ tone: "success", text: "Coordination revoked." });
      invalidate();
    },
    onError: (err) => {
      setRevoke(null);
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not revoke.",
      });
    },
  });

  const labelFor = (domain: string) =>
    domains.data?.find((d) => d.value === domain)?.label ?? humanise(domain);

  const summary = (matrix.data?.faculty_summary ?? []).filter((row) => {
    const needle = search.trim().toLowerCase();
    if (!needle) return true;
    return `${row.name} ${row.employee_code} ${row.department_code ?? ""}`
      .toLowerCase().includes(needle);
  });

  return (
    <div>
      <PageHeader
        title={headed ? `${headed} coordinators and mentors` : "Role assignments"}
        description={
          headed
            ? `As Head of ${headed} you appoint and remove this department's coordinators and mentors. Each role covers one module — coordinating Open Electives grants nothing over Core Electives — and Coordinator is a different grant from Mentor.`
            : "Every role is scoped to a module and a department — Summer Internship for ICT is a different grant from Summer Internship for CSE, and Coordinator is a different grant from Mentor. One person may hold several; each applies only inside its own scope. Each department's Head appoints its own."
        }
        breadcrumbs={[{ label: "Administration" }, { label: "Coordinators & Mentors" }]}
        actions={
          <Button size="sm" onClick={() => setAssignOpen(true)}
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}>
            Create assignment
          </Button>
        }
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <Tabs
        tabs={[
          { key: "board", label: "Roles" },
          { key: "assignments", label: "Assignments",
            count: assignments.data?.length },
          { key: "faculty", label: "By faculty", count: summary.length },
          { key: "coverage", label: "By module", count: matrix.data?.coverage.length },
          { key: "gaps", label: "Uncovered", count: matrix.data?.gaps.length },
        ]}
        active={tab}
        onChange={setTab}
        className="mb-5"
      />

      {/* ── roles as cards: holders as chips, + Add, × to remove ──────── */}
      {tab === "board" && (domains.data && roles.data
        ? <RoleBoard domains={domains.data} roles={roles.data} />
        : <LoadingState rows={6} />)}

      {/* ── every assignment: faculty · role · module · dept · status ─── */}
      {tab === "assignments" && (
        <Card>
          <CardHeader
            title="Role assignments"
            description="Coordinator and Mentor are independent grants. One person may hold several; each applies only inside its own scope."
            icon={<ShieldCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
          />
          {assignments.isLoading ? (
            <LoadingState rows={5} />
          ) : (
            <TableWrap>
              <THead>
                <TH width="24%">Faculty</TH>
                <TH width="13%">Role</TH>
                <TH width="19%">Module</TH>
                <TH width="14%">Department</TH>
                <TH width="12%">Status</TH>
                <TH width="18%" align="right">Actions</TH>
              </THead>
              <TBody>
                {(assignments.data ?? []).length === 0 ? (
                  <TableEmpty colSpan={6}>No assignments yet.</TableEmpty>
                ) : (
                  (assignments.data ?? []).map((a) => (
                    <TR key={a.id}>
                      <TD>
                        <p className="font-medium text-ink">{a.faculty_name}</p>
                        <p className="text-2xs text-ink-subtle">
                          <span className="font-mono">{a.employee_code}</span>
                          {a.designation && ` · ${a.designation}`}
                        </p>
                      </TD>
                      <TD>
                        <Badge tone={a.role === "COORDINATOR" ? "brand" : "info"}>
                          {a.role_label ?? humanise(a.role)}
                        </Badge>
                      </TD>
                      <TD>
                        <Badge tone={DOMAIN_TONE[a.domain] ?? "neutral"}>
                          {a.domain_label ?? labelFor(a.domain)}
                        </Badge>
                      </TD>
                      <TD className="text-ink-muted">
                        {a.is_institution_wide
                          ? <Badge tone="brand">All departments</Badge>
                          : a.department_code}
                      </TD>
                      <TD>
                        <StatusBadge status={a.is_current ? "ACTIVE" : "CLOSED"} />
                        {(a.starts_on || a.ends_on) && (
                          <p className="mt-1 text-2xs text-ink-subtle">
                            {a.starts_on ? formatDate(a.starts_on) : "—"}
                            {" → "}
                            {a.ends_on ? formatDate(a.ends_on) : "open"}
                          </p>
                        )}
                      </TD>
                      <TD align="right">
                        <div className="flex flex-wrap justify-end gap-1">
                          <Button variant="ghost" size="sm" onClick={() => setEdit(a)}>
                            Edit
                          </Button>
                          <Button variant="ghost" size="sm" className="text-danger"
                                  onClick={() => setRevoke(a)}>
                            Revoke
                          </Button>
                        </div>
                      </TD>
                    </TR>
                  ))
                )}
              </TBody>
            </TableWrap>
          )}
        </Card>
      )}

      {matrix.isLoading && tab !== "assignments" && tab !== "board" && <LoadingState rows={5} />}
      {matrix.error && tab !== "assignments" && tab !== "board" && (
        <ErrorState onRetry={() => matrix.refetch()} />
      )}

      {/* ── who holds what ─────────────────────────────────────────────── */}
      {matrix.data && tab === "faculty" && (
        <Card>
          <CardHeader
            title="Every faculty member and the roles they hold"
            icon={<UserCog className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              <SearchInput value={search} onChange={setSearch}
                           placeholder="Name, code or department"
                           className="w-full sm:w-64" />
            }
          />
          <TableWrap>
            <THead>
              <TH width="24%">Faculty</TH>
              <TH width="10%">Dept</TH>
              <TH width="22%">System roles</TH>
              <TH>Roles held</TH>
            </THead>
            <TBody>
              {summary.length === 0 ? (
                <TableEmpty colSpan={4}>No faculty match “{search}”.</TableEmpty>
              ) : (
                summary.map((row) => (
                  <TR key={row.faculty_id}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={row.name} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{row.name}</p>
                          <p className="truncate text-2xs text-ink-subtle">
                            <span className="font-mono">{row.employee_code}</span>
                            {" · "}{row.designation}
                          </p>
                        </div>
                      </div>
                    </TD>
                    <TD>{row.department_code ?? "—"}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        {row.roles.map((role) => (
                          <Badge key={role} tone="neutral">{humanise(role)}</Badge>
                        ))}
                      </div>
                    </TD>
                    <TD>
                      {row.coordinations.length === 0 ? (
                        <span className="text-ink-subtle">No roles assigned</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {row.coordinations.map((c) => (
                            <span
                              key={c.id}
                              className="inline-flex overflow-hidden rounded border border-line"
                            >
                              {/* The role is named on every chip: coordinating a
                                  module and mentoring its students are different
                                  grants and must never read the same. */}
                              <span
                                className={
                                  "px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide "
                                  + (c.role === "COORDINATOR"
                                      ? "bg-brand-soft text-brand"
                                      : "bg-info-soft text-info")
                                }
                              >
                                {c.role_label}
                              </span>
                              <span className="px-1.5 py-0.5 text-xs font-medium text-ink-muted">
                                {c.domain_label} · {c.department_code}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        </Card>
      )}

      {/* ── module × department coverage ───────────────────────────────── */}
      {matrix.data && tab === "coverage" && (
        <Card>
          <CardHeader
            title="Coverage per module and department"
            description="Two faculty can hold the same module for different departments. A module with mentors but no coordinator still counts as uncovered."
            icon={<ShieldCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
          />
          {matrix.data.coverage.length === 0 ? (
            <EmptyState compact title="No coordinators assigned yet" />
          ) : (
            <TableWrap>
              <THead>
                <TH width="24%">Module</TH>
                <TH width="16%">Department</TH>
                <TH>Coordinator</TH>
                <TH width="16%">Assigned</TH>
                <TH width="10%" align="right">Revoke</TH>
              </THead>
              <TBody>
                {matrix.data.coverage.flatMap((cell) =>
                  cell.coordinators.map((c) => (
                    <TR key={c.id}>
                      <TD>
                        <Badge tone={DOMAIN_TONE[cell.domain] ?? "neutral"}>
                          {labelFor(cell.domain)}
                        </Badge>
                      </TD>
                      <TD className="text-ink-muted">
                        {c.is_institution_wide
                          ? <Badge tone="brand">All departments</Badge>
                          : cell.department_code}
                      </TD>
                      <TD>
                        <p className="font-medium text-ink">{c.faculty_name}</p>
                        <p className="text-2xs text-ink-subtle">
                          <span className="font-mono">{c.employee_code}</span>
                          {" · "}{c.designation}
                        </p>
                      </TD>
                      <TD className="text-xs text-ink-subtle">
                        {formatDate(c.assigned_at)}
                        {c.assigned_by_name && (
                          <span className="block">by {c.assigned_by_name}</span>
                        )}
                      </TD>
                      <TD align="right">
                        <Button
                          variant="ghost" size="sm" className="text-danger"
                          onClick={() => setRevoke(c)}
                          icon={<Trash2 className="h-3 w-3" aria-hidden />}
                        >
                          Revoke
                        </Button>
                      </TD>
                    </TR>
                  )),
                )}
              </TBody>
            </TableWrap>
          )}
        </Card>
      )}

      {/* ── gaps ───────────────────────────────────────────────────────── */}
      {matrix.data && tab === "gaps" && (
        <Card>
          <CardHeader
            title="Modules with no coordinator"
            description="Nobody can approve or configure these until someone is assigned."
            icon={<AlertTriangle className="h-4 w-4 text-warning" aria-hidden />}
          />
          {matrix.data.gaps.length === 0 ? (
            <EmptyState compact title="Every module is covered"
                        description="All departments have a coordinator for every module." />
          ) : (
            <CardBody className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {matrix.data.gaps.map((gap) => (
                <div
                  key={`${gap.domain}-${gap.department_id}`}
                  className="flex items-center justify-between gap-2 rounded border border-line px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-ink">{gap.domain_label}</p>
                    <p className="truncate text-2xs text-ink-subtle">
                      {gap.department_name}
                    </p>
                  </div>
                  <Badge tone="warning">{gap.department_code}</Badge>
                </div>
              ))}
            </CardBody>
          )}
        </Card>
      )}

      {assignOpen && (
        <AssignModal
          roles={roles.data ?? []}
          domains={domains.data ?? []}
          onClose={() => setAssignOpen(false)}
          onDone={(text) => {
            setAssignOpen(false);
            setBanner({ tone: "success", text });
            invalidate();
          }}
        />
      )}

      {edit && (
        <EditModal
          assignment={edit}
          onClose={() => setEdit(null)}
          onDone={(text) => {
            setEdit(null);
            setBanner({ tone: "success", text });
            void queryClient.invalidateQueries({ queryKey: ["role-assignments"] });
            void queryClient.invalidateQueries({ queryKey: ["role-matrix"] });
          }}
        />
      )}

      <ConfirmDialog
        open={Boolean(revoke)}
        onClose={() => setRevoke(null)}
        onConfirm={() => revoke && revokeMutation.mutate(revoke.id)}
        loading={revokeMutation.isPending}
        destructive
        title="Revoke this assignment?"
        confirmLabel="Revoke"
        message={
          <>
            <strong>{revoke?.faculty_name}</strong> will lose the{" "}
            {(revoke?.role_label ?? "").toLowerCase()} role for{" "}
            {revoke?.domain_label ?? labelFor(revoke?.domain ?? "")} in{" "}
            {revoke?.department_code ?? "all departments"}. Their other roles are
            untouched. The change is audit-logged.
          </>
        }
      />

      {/* Assignments the matrix does not show (inactive / other years). */}
      {assignments.data && assignments.data.length > 0 && tab === "coverage" && (
        <p className="mt-3 text-xs text-ink-subtle">
          {assignments.data.length} active assignment
          {assignments.data.length === 1 ? "" : "s"} in total.
        </p>
      )}
    </div>
  );
}

function AssignModal({
  domains, roles, onClose, onDone,
}: {
  domains: DomainOption[]; roles: RoleDefinition[];
  onClose: () => void; onDone: (text: string) => void;
}) {
  const { user } = useAuth();
  // For a Head of Department the scope is not a choice: it is their department,
  // and the server refuses anything else.
  const hodDepartmentId = user?.faculty?.hod_department_id ?? null;
  const hodDepartmentCode = user?.faculty?.hod_department_code ?? null;
  const [facultyId, setFacultyId] = useState("");
  const [role, setRole] = useState("COORDINATOR");
  const [domain, setDomain] = useState(domains[0]?.value ?? "SUMMER_INTERNSHIP");
  const [departmentId, setDepartmentId] = useState(
    hodDepartmentId ? String(hodDepartmentId) : "",
  );
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const chosenRole = roles.find((r) => r.value === role);

  const faculty = useQuery({
    queryKey: ["faculty"],
    queryFn: () => api.get<FacultyRow[]>("/faculty"),
  });
  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  // The HoD appoints from their own department and is never an appointee.
  const candidates = (faculty.data ?? []).filter((f) =>
    hodDepartmentId
      ? f.department_id === hodDepartmentId && f.id !== user?.faculty?.id
      : true,
  );
  const chosen = candidates.find((f) => String(f.id) === facultyId);

  const assign = useMutation({
    mutationFn: () =>
      api.post("/admin/roles", {
        faculty_id: Number(facultyId),
        role,
        domain,
        department_id: departmentId ? Number(departmentId) : null,
        starts_on: startsOn || null,
        ends_on: endsOn || null,
        notes: notes || null,
      }),
    onSuccess: () =>
      onDone(`${chosenRole?.label ?? "Role"} assigned.`),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not assign."),
  });

  return (
    <Modal
      open onClose={onClose} title="Create assignment"
      description="A role, over one module, for one department."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={!facultyId} loading={assign.isPending}
                  onClick={() => assign.mutate()}>
            Assign
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <FormField label="Faculty member" required>
          <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}
                  data-autofocus>
            <option value="">Select a faculty member…</option>
            {candidates.map((f) => (
              <option key={f.id} value={f.id}>
                {f.full_name} — {f.department_code} ({f.designation})
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Role" required hint={chosenRole?.description}>
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </Select>
        </FormField>

        <FormField label="Module / domain" required
                   hint="CSSI and Summer Internship are separate grants — holding one
                         gives no access to the other.">
          <Select value={domain} onChange={(e) => setDomain(e.target.value)}>
            {domains.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </Select>
        </FormField>

        {hodDepartmentId ? (
          <FormField label="Department scope"
                     hint="You appoint for your own department only.">
            <Input value={hodDepartmentCode ?? ""} readOnly disabled />
          </FormField>
        ) : (
          <FormField
            label="Department scope"
            hint="Leave blank to make this institution-wide across every department."
          >
            <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value="">All departments (institution-wide)</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.code} — {d.name}</option>
              ))}
            </Select>
          </FormField>
        )}

        {chosen && departmentId && String(chosen.department_id) !== departmentId && (
          <Alert variant="info">
            {chosen.full_name} belongs to {chosen.department_code} but will
            hold this role for a different department. That is allowed — just
            confirm it is intended.
          </Alert>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Start date" hint="Optional — blank means immediately.">
            <Input type="date" value={startsOn}
                   onChange={(e) => setStartsOn(e.target.value)} />
          </FormField>
          <FormField label="End date" hint="Optional — blank means until revoked.">
            <Input type="date" value={endsOn}
                   onChange={(e) => setEndsOn(e.target.value)} />
          </FormField>
        </div>

        <FormField label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
                    placeholder="e.g. Effective from this academic year." />
        </FormField>
      </div>
    </Modal>
  );
}


function EditModal({
  assignment, onClose, onDone,
}: {
  assignment: RoleAssignment;
  onClose: () => void;
  onDone: (text: string) => void;
}) {
  const [departmentId, setDepartmentId] = useState(
    assignment.department_id ? String(assignment.department_id) : "",
  );
  const [startsOn, setStartsOn] = useState(assignment.starts_on ?? "");
  const [endsOn, setEndsOn] = useState(assignment.ends_on ?? "");
  const [isActive, setIsActive] = useState(assignment.is_active);
  const [notes, setNotes] = useState(assignment.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  const save = useMutation({
    mutationFn: () =>
      api.patch(`/admin/roles/${assignment.id}`, {
        department_id: departmentId ? Number(departmentId) : null,
        starts_on: startsOn || null,
        ends_on: endsOn || null,
        is_active: isActive,
        notes: notes || null,
      }),
    onSuccess: () => onDone("Assignment updated."),
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  return (
    <Modal
      open onClose={onClose} title="Edit assignment"
      description={`${assignment.faculty_name} · ${assignment.role_label} · ${assignment.domain_label}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <Alert variant="info">
          The role and module cannot be changed here. Rewriting them in place
          would misrepresent the audit trail — revoke this assignment and create
          the new one instead.
        </Alert>

        <FormField label="Department scope"
                   hint="Blank makes it institution-wide across every department.">
          <Select value={departmentId} data-autofocus
                  onChange={(e) => setDepartmentId(e.target.value)}>
            <option value="">All departments (institution-wide)</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.code} — {d.name}</option>
            ))}
          </Select>
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Start date">
            <Input type="date" value={startsOn}
                   onChange={(e) => setStartsOn(e.target.value)} />
          </FormField>
          <FormField label="End date">
            <Input type="date" value={endsOn}
                   onChange={(e) => setEndsOn(e.target.value)} />
          </FormField>
        </div>

        <Checkbox
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          label="Active"
          description="Clearing this suspends the role without deleting the record."
        />

        <FormField label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </FormField>
      </div>
    </Modal>
  );
}
