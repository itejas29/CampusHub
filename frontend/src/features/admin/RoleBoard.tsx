import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, ShieldCheck, Users, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Form";
import { Avatar } from "@/components/ui/Misc";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { DepartmentRow, FacultyRow, RoleAssignment, RoleDefinition } from "@/types";

/**
 * Roles as a board: one card per role, its holders as chips, "+ Add" to
 * appoint and × to remove — the way a Discord server's roles read.
 *
 * The list of roles is fixed (module × Coordinator/Mentor), never invented
 * here: each is tied to a scope the server enforces. Everything is decided by
 * the server — only the department's own HoD (or the registrar) appoints, the
 * HoD is never an appointee, and each change is audited and notified.
 */

interface DomainOption { value: string; label: string }

/** A colour per module, from the design tokens, so dark mode follows. */
const DOMAIN_COLOUR: Record<string, { dot: string; chip: string }> = {
  CSSI: { dot: "bg-warning-solid", chip: "border-warning/30 bg-warning-soft/60" },
  SUMMER_INTERNSHIP: { dot: "bg-accent", chip: "border-accent/30 bg-accent-soft/60" },
  MINOR: { dot: "bg-success-solid", chip: "border-success/30 bg-success-soft/60" },
  MOOC: { dot: "bg-info", chip: "border-info/30 bg-info-soft/60" },
  OPEN_ELECTIVE: { dot: "bg-violet", chip: "border-violet/30 bg-violet-soft/60" },
  CORE_ELECTIVE: { dot: "bg-iris", chip: "border-iris/30 bg-iris-soft/60" },
  MENTORSHIP: { dot: "bg-brand", chip: "border-brand/30 bg-brand-soft/60" },
};
const NEUTRAL = { dot: "bg-ink-subtle", chip: "border-line bg-surface-muted" };

/** Chips shown before a long role folds behind "+N more". */
const CHIP_LIMIT = 8;

type RoleKey = { role: "COORDINATOR" | "MENTOR"; domain: string };
const keyOf = (k: RoleKey) => `${k.role}:${k.domain}`;

export function RoleBoard({ domains, roles }: { domains: DomainOption[]; roles: RoleDefinition[] }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const hodDepartmentId = user?.faculty?.hod_department_id ?? null;
  const [pickedDepartment, setPickedDepartment] = useState<string>("");
  const [adding, setAdding] = useState<RoleKey | null>(null);
  const [removing, setRemoving] = useState<RoleAssignment | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });
  const faculty = useQuery({ queryKey: ["faculty"], queryFn: () => api.get<FacultyRow[]>("/faculty") });
  const assignments = useQuery({
    queryKey: ["role-assignments"],
    queryFn: () => api.get<RoleAssignment[]>("/admin/roles"),
  });

  // A Head of Department works in their own department only; the registrar
  // chooses (ICT first, the department being built out).
  const departmentId = hodDepartmentId
    ?? (pickedDepartment ? Number(pickedDepartment)
      : departments.data?.find((d) => d.code === "ICT")?.id ?? departments.data?.[0]?.id ?? null);
  const department = departments.data?.find((d) => d.id === departmentId) ?? null;

  const holders = useMemo(() => {
    const map = new Map<string, RoleAssignment[]>();
    for (const a of assignments.data ?? []) {
      if (!a.is_active) continue;
      if (a.department_id !== departmentId && !a.is_institution_wide) continue;
      const k = keyOf({ role: a.role as RoleKey["role"], domain: a.domain });
      map.set(k, [...(map.get(k) ?? []), a]);
    }
    return map;
  }, [assignments.data, departmentId]);

  // Every module has a coordinator role. Mentor is shown for Mentor–Mentee,
  // and for any module where someone already holds it.
  const board: RoleKey[] = [
    ...domains.map((d) => ({ role: "COORDINATOR" as const, domain: d.value })),
    ...domains.filter((d) => d.value === "MENTORSHIP" || holders.has(keyOf({ role: "MENTOR", domain: d.value })))
      .map((d) => ({ role: "MENTOR" as const, domain: d.value })),
  ];
  const label = (k: RoleKey) =>
    `${domains.find((d) => d.value === k.domain)?.label ?? k.domain} ${k.role === "COORDINATOR" ? "Coordinator" : "Mentor"}`;

  function done(text: string) {
    setBanner({ tone: "success", text });
    void queryClient.invalidateQueries({ queryKey: ["role-assignments"] });
    void queryClient.invalidateQueries({ queryKey: ["role-matrix"] });
  }
  function failed(err: unknown, fallback: string) {
    setBanner({ tone: "danger", text: err instanceof ApiError ? err.message : fallback });
  }

  const appoint = useMutation({
    mutationFn: ({ key, facultyId }: { key: RoleKey; facultyId: number }) =>
      api.post<RoleAssignment>("/admin/roles", {
        faculty_id: facultyId, role: key.role, domain: key.domain, department_id: departmentId,
      }),
    onSuccess: (a, vars) => done(`${a.faculty_name} is now ${label(vars.key)}. They have been notified.`),
    onError: (err) => failed(err, "Could not give that role."),
  });
  const revoke = useMutation({
    mutationFn: (a: RoleAssignment) => api.delete(`/admin/roles/${a.id}`),
    onSuccess: (_r, a) => {
      setRemoving(null);
      done(`${a.faculty_name} no longer holds ${label({ role: a.role as RoleKey["role"], domain: a.domain })}.`);
    },
    onError: (err) => { setRemoving(null); failed(err, "Could not remove that role."); },
  });

  if (departments.isLoading || assignments.isLoading) return <LoadingState rows={6} />;
  if (assignments.error) return <ErrorState onRetry={() => assignments.refetch()} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">
          {hodDepartmentId
            ? <>Give and remove roles for <strong className="text-ink">{department?.name ?? "your department"}</strong>. Each role covers one module only.</>
            : "Each role covers one module in one department. The department's Head normally appoints; as registrar you can act anywhere."}
        </p>
        {!hodDepartmentId && (
          <Select aria-label="Department" value={String(departmentId ?? "")}
                  onChange={(e) => setPickedDepartment(e.target.value)} className="h-9 w-56 text-sm">
            {(departments.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
          </Select>
        )}
      </div>

      {banner && (
        <Alert variant={banner.tone} onDismiss={() => setBanner(null)}>{banner.text}</Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {board.map((k) => {
          const colour = DOMAIN_COLOUR[k.domain] ?? NEUTRAL;
          const members = holders.get(keyOf(k)) ?? [];
          const description = roles.find((r) => r.value === k.role)?.description;
          const open = expanded.has(keyOf(k));
          const visible = open ? members : members.slice(0, CHIP_LIMIT);
          return (
            <Card key={keyOf(k)} className="flex flex-col">
              <div className="flex items-start gap-3 border-b border-line px-4 py-3.5">
                <span aria-hidden className={cn("mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full", colour.dot)} />
                <div className="min-w-0 flex-1">
                  <h3 className="truncate font-heading text-sm font-semibold text-ink">{label(k)}</h3>
                  <p className="mt-0.5 text-2xs text-ink-subtle" title={description}>
                    {k.role === "COORDINATOR" ? "Runs the module" : "Guides assigned students"} · {department?.code ?? "—"}
                  </p>
                </div>
                <Badge tone={members.length ? "neutral" : k.role === "COORDINATOR" ? "warning" : "neutral"}>
                  {members.length ? members.length : k.role === "COORDINATOR" ? "Nobody" : "0"}
                </Badge>
              </div>
              <div className="flex flex-1 flex-wrap content-start gap-1.5 p-3">
                {visible.map((a) => (
                  <span key={a.id}
                        className={cn("inline-flex max-w-full items-center gap-1.5 rounded-full border py-0.5 pl-0.5 pr-1 text-xs text-ink", colour.chip)}>
                    <Avatar name={a.faculty_name ?? "?"} size="xs" />
                    <span className="truncate" title={`${a.faculty_name} · ${a.designation ?? ""}`}>{a.faculty_name}</span>
                    {a.is_institution_wide && <span className="text-2xs text-ink-subtle">· all depts</span>}
                    <button type="button" onClick={() => setRemoving(a)}
                            aria-label={`Remove ${a.faculty_name} from ${label(k)}`}
                            className="grid h-4 w-4 shrink-0 cursor-pointer place-items-center rounded-full text-ink-subtle hover:bg-danger-soft hover:text-danger">
                      <X className="h-3 w-3" aria-hidden />
                    </button>
                  </span>
                ))}
                {members.length > CHIP_LIMIT && (
                  <button type="button"
                          onClick={() => setExpanded((prev) => {
                            const next = new Set(prev);
                            if (open) next.delete(keyOf(k)); else next.add(keyOf(k));
                            return next;
                          })}
                          className="cursor-pointer rounded-full px-2 py-1 text-xs font-medium text-accent hover:underline">
                    {open ? "Show less" : `+${members.length - CHIP_LIMIT} more`}
                  </button>
                )}
                <button type="button" onClick={() => setAdding(k)} disabled={!departmentId}
                        className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-dashed border-line-strong px-2.5 py-1 text-xs font-medium text-ink-muted hover:border-accent hover:text-accent disabled:cursor-not-allowed">
                  <Plus className="h-3 w-3" aria-hidden />Add
                </button>
              </div>
            </Card>
          );
        })}
      </div>

      <AddMemberModal
        open={adding !== null} title={adding ? `Give ${label(adding)}` : ""}
        faculty={(faculty.data ?? []).filter((f) =>
          f.department_id === departmentId
          // Not the HoD (they appoint), and not an office account (`is_mentor`
          // is false for both): the server refuses them anyway.
          && f.is_mentor && f.id !== department?.hod_faculty_id
          && !(adding && (holders.get(keyOf(adding)) ?? []).some((a) => a.faculty_id === f.id)))}
        loading={faculty.isLoading}
        pendingId={appoint.isPending ? appoint.variables?.facultyId ?? null : null}
        onClose={() => setAdding(null)}
        onPick={(f) => { if (adding) appoint.mutate({ key: adding, facultyId: f.id }, { onSettled: () => setAdding(null) }); }}
      />

      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} destructive
        loading={revoke.isPending} onConfirm={() => removing && revoke.mutate(removing)}
        title="Remove this role?"
        message={removing
          ? `${removing.faculty_name} stops being ${label({ role: removing.role as RoleKey["role"], domain: removing.domain })} straight away. This is recorded in the audit log.`
          : ""}
        confirmLabel="Remove role"
      />
    </div>
  );
}

function AddMemberModal({ open, title, faculty, loading, pendingId, onClose, onPick }: {
  open: boolean; title: string; faculty: FacultyRow[]; loading: boolean;
  pendingId: number | null; onClose: () => void; onPick: (f: FacultyRow) => void;
}) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const shown = faculty.filter((f) =>
    !needle || `${f.full_name} ${f.designation} ${f.employee_code}`.toLowerCase().includes(needle));
  return (
    <Modal open={open} onClose={() => { setSearch(""); onClose(); }} title={title} size="sm"
           description="Choose a faculty member. They are notified as soon as you pick them.">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle" aria-hidden />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search faculty"
               aria-label="Search faculty" className="h-9 pl-8" data-autofocus />
      </div>
      {loading ? <LoadingState rows={4} /> : shown.length === 0 ? (
        <EmptyState compact icon={<Users className="h-5 w-5" aria-hidden />}
                    title={needle ? "Nobody matches" : "Everyone eligible already holds this role"} />
      ) : (
        <ul className="-mx-1 mt-3 max-h-80 overflow-y-auto">
          {shown.map((f) => (
            <li key={f.id}>
              <button type="button" disabled={pendingId !== null} onClick={() => onPick(f)}
                      className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-muted disabled:opacity-60">
                <Avatar name={f.full_name} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">{f.full_name}</span>
                  <span className="block truncate text-2xs text-ink-subtle">
                    {f.designation}{f.is_demo && " · Demo account"}
                  </span>
                </span>
                {pendingId === f.id
                  ? <span className="text-2xs text-ink-subtle">Adding…</span>
                  : <ShieldCheck className="h-4 w-4 text-ink-subtle" aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
