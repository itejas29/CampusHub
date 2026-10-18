import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Checkbox, Input, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";
import { humanise } from "@/lib/utils";
import type { InternshipProgram } from "@/types";

/**
 * The coordinator's editors for a programme's stages and rubric.
 *
 * The server holds every rule — a stage with submitted work cannot be removed,
 * a rubric is fixed once marks exist, a stage's code never changes — and
 * answers with the reason when an edit is refused. These screens only gather
 * the edit and show that reason.
 */

const DOCUMENT_TYPES = [
  "SYNOPSIS", "REPORT", "PRESENTATION", "POSTER", "CERTIFICATE", "OFFER_LETTER",
  "PHOTO", "JOINING_LETTER", "COMPLETION_LETTER", "OTHER",
];
const OWNERS = [
  { value: "STUDENT", label: "Student submits" },
  { value: "COORDINATOR", label: "Coordinator does" },
  { value: "FACULTY", label: "Faculty marks" },
];

type StageRow = {
  key: string; id?: number; name: string; description: string; owner_role: string;
  requires_document: boolean; document_type: string; is_mandatory: boolean;
};
type CriterionRow = { key: string; id?: number; name: string; description: string; max_marks: string };

function move<T>(list: T[], index: number, by: number): T[] {
  const next = [...list];
  const [item] = next.splice(index, 1);
  next.splice(Math.max(0, Math.min(next.length, index + by)), 0, item);
  return next;
}

function useSave(program: InternshipProgram, path: string, onDone: () => void) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (body: unknown) => api.put<InternshipProgram>(`/internships/programs/${program.id}/${path}`, body),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["internship-programs"] });
      onDone();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "The change could not be saved."),
  });
  return { mutation, error, setError };
}

function RowControls({ index, count, onMove, onRemove, label }: {
  index: number; count: number; onMove: (by: number) => void; onRemove: () => void; label: string;
}) {
  return (
    <div className="flex shrink-0 gap-0.5">
      <Button variant="ghost" size="icon" disabled={index === 0} onClick={() => onMove(-1)}
              aria-label={`Move ${label} up`} icon={<ArrowUp className="h-4 w-4" aria-hidden />} />
      <Button variant="ghost" size="icon" disabled={index === count - 1} onClick={() => onMove(1)}
              aria-label={`Move ${label} down`} icon={<ArrowDown className="h-4 w-4" aria-hidden />} />
      <Button variant="ghost" size="icon" className="text-danger" disabled={count === 1} onClick={onRemove}
              aria-label={`Remove ${label}`} icon={<Trash2 className="h-4 w-4" aria-hidden />} />
    </div>
  );
}

export function StagesEditor({ program, open, onClose }: {
  program: InternshipProgram; open: boolean; onClose: () => void;
}) {
  const initial = (): StageRow[] => [...program.stages]
    .sort((a, b) => a.sequence - b.sequence)
    .map((s) => ({
      key: `s${s.id}`, id: s.id, name: s.name, description: s.description ?? "",
      owner_role: s.owner_role, requires_document: s.requires_document,
      document_type: s.document_type ?? "", is_mandatory: s.is_mandatory,
    }));
  const [rows, setRows] = useState<StageRow[]>(initial);
  const { mutation, error, setError } = useSave(program, "stages", onClose);
  const update = (index: number, patch: Partial<StageRow>) =>
    setRows((list) => list.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  function close() { setRows(initial()); setError(null); onClose(); }

  return (
    <Modal open={open} onClose={close} size="lg" title={`Stages — ${program.name}`}
           description="The steps every student works through, in order. Students already under way get a new stage straight away."
           footer={
             <>
               <Button variant="secondary" size="sm" onClick={close}>Cancel</Button>
               <Button size="sm" loading={mutation.isPending}
                       disabled={rows.some((r) => !r.name.trim() || (r.requires_document && !r.document_type))}
                       onClick={() => mutation.mutate({
                         stages: rows.map((r) => ({
                           id: r.id, name: r.name.trim(), description: r.description.trim() || null,
                           owner_role: r.owner_role, requires_document: r.requires_document,
                           document_type: r.requires_document ? r.document_type : null,
                           is_mandatory: r.is_mandatory,
                         })),
                       })}>
                 Save stages
               </Button>
             </>
           }>
      <div className="space-y-3">
        {error && <Alert variant="danger">{error}</Alert>}
        <ol className="space-y-2">
          {rows.map((row, index) => (
            <li key={row.key} className="rounded-lg border border-line p-3">
              <div className="flex items-start gap-2">
                <span className="mt-2 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-muted text-2xs font-semibold text-ink-subtle">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                  <Input value={row.name} maxLength={150} aria-label={`Stage ${index + 1} name`}
                         placeholder="Stage name" onChange={(e) => update(index, { name: e.target.value })} />
                  <div className="flex flex-wrap items-center gap-2">
                    <Select aria-label={`Stage ${index + 1}: who acts`} value={row.owner_role} className="h-8 w-44 text-xs"
                            onChange={(e) => update(index, { owner_role: e.target.value })}>
                      {OWNERS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </Select>
                    <Checkbox label="Needs a document" checked={row.requires_document}
                              onChange={(e) => update(index, { requires_document: e.target.checked })} />
                    {row.requires_document && (
                      <Select aria-label={`Stage ${index + 1}: document`} value={row.document_type} className="h-8 w-44 text-xs"
                              onChange={(e) => update(index, { document_type: e.target.value })}>
                        <option value="">Which document?</option>
                        {DOCUMENT_TYPES.map((t) => <option key={t} value={t}>{humanise(t)}</option>)}
                      </Select>
                    )}
                    <Checkbox label="Required" checked={row.is_mandatory}
                              onChange={(e) => update(index, { is_mandatory: e.target.checked })} />
                  </div>
                </div>
                <RowControls index={index} count={rows.length} label={row.name || "stage"}
                             onMove={(by) => setRows((list) => move(list, index, by))}
                             onRemove={() => setRows((list) => list.filter((_, i) => i !== index))} />
              </div>
            </li>
          ))}
        </ol>
        <Button variant="secondary" size="sm" icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                onClick={() => setRows((list) => [...list, {
                  key: `n${Date.now()}`, name: "", description: "", owner_role: "STUDENT",
                  requires_document: false, document_type: "", is_mandatory: true,
                }])}>
          Add a stage
        </Button>
      </div>
    </Modal>
  );
}

export function RubricEditor({ program, open, onClose }: {
  program: InternshipProgram; open: boolean; onClose: () => void;
}) {
  const initial = (): CriterionRow[] => [...program.criteria]
    .sort((a, b) => a.sequence - b.sequence)
    .map((c) => ({ key: `c${c.id}`, id: c.id, name: c.name, description: c.description ?? "",
                   max_marks: String(c.max_marks) }));
  const [rows, setRows] = useState<CriterionRow[]>(initial);
  const { mutation, error, setError } = useSave(program, "criteria", onClose);
  const update = (index: number, patch: Partial<CriterionRow>) =>
    setRows((list) => list.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const total = rows.reduce((sum, r) => sum + (Number(r.max_marks) || 0), 0);

  function close() { setRows(initial()); setError(null); onClose(); }

  return (
    <Modal open={open} onClose={close} size="lg" title={`Rubric — ${program.name}`}
           description="What each student is marked on. The rubric can change until the first marks are recorded; after that it stays fixed."
           footer={
             <>
               <span className="mr-auto text-sm text-ink-muted">Total <strong className="tabular text-ink">{total}</strong> marks</span>
               <Button variant="secondary" size="sm" onClick={close}>Cancel</Button>
               <Button size="sm" loading={mutation.isPending}
                       disabled={rows.some((r) => !r.name.trim() || !(Number(r.max_marks) > 0))}
                       onClick={() => mutation.mutate({
                         criteria: rows.map((r) => ({ id: r.id, name: r.name.trim(),
                                                      description: r.description.trim() || null,
                                                      max_marks: Number(r.max_marks) })),
                       })}>
                 Save rubric
               </Button>
             </>
           }>
      <div className="space-y-3">
        {error && <Alert variant="danger">{error}</Alert>}
        <ul className="space-y-2">
          {rows.map((row, index) => (
            <li key={row.key} className="flex items-center gap-2 rounded-lg border border-line p-2.5">
              {/* The shared control is w-full, so each input is sized by its wrapper. */}
              <div className="min-w-0 flex-1">
                <Input value={row.name} maxLength={180} aria-label={`Criterion ${index + 1}`}
                       placeholder="Criterion" onChange={(e) => update(index, { name: e.target.value })} />
              </div>
              <div className="w-20 shrink-0">
                <Input value={row.max_marks} inputMode="decimal" aria-label={`Criterion ${index + 1} maximum marks`}
                       className="text-right tabular"
                       onChange={(e) => update(index, { max_marks: e.target.value.replace(/[^0-9.]/g, "") })} />
              </div>
              <RowControls index={index} count={rows.length} label={row.name || "criterion"}
                           onMove={(by) => setRows((list) => move(list, index, by))}
                           onRemove={() => setRows((list) => list.filter((_, i) => i !== index))} />
            </li>
          ))}
        </ul>
        <Button variant="secondary" size="sm" icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                onClick={() => setRows((list) => [...list, { key: `n${Date.now()}`, name: "", description: "", max_marks: "10" }])}>
          Add a criterion
        </Button>
      </div>
    </Modal>
  );
}

/** Confirm, one at a time, what the department had to confirm. */
export function ConfirmPending({ program }: { program: InternshipProgram }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const confirm = useMutation({
    mutationFn: (item: string) => api.post<InternshipProgram>(`/internships/programs/${program.id}/confirm`, { item }),
    onSuccess: () => { setError(null); void queryClient.invalidateQueries({ queryKey: ["internship-programs"] }); },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not confirm."),
  });
  const pending = program.needs_confirmation ?? [];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {pending.map((item) => (
        <Button key={item} variant="secondary" size="sm" loading={confirm.isPending && confirm.variables === item}
                onClick={() => confirm.mutate(item)}>
          Confirm {item}
        </Button>
      ))}
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
