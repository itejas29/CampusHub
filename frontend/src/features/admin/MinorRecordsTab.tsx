import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormField, Input, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { ApiError, api } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { roman } from "@/lib/utils";
import type { MinorProgram } from "@/types";

/**
 * The minor coordinator's records once students hold seats: each course's
 * results, and each semester's fee and who has paid it. The server checks
 * that the coordinator runs the minor and keeps every change in the audit log.
 */

type GradeRow = {
  enrollment_id: number; student_name: string; roll_number: string; department: string | null;
  semester: number; marks: number | null; grade: string | null; status: string | null;
};
type FeeStatusRow = {
  enrollment_id: number; student_name: string; roll_number: string;
  semesters: { semester: number; amount: number; paid: boolean; reference: string | null }[];
};

const semesterOf = (program: MinorProgram, offset: number) => program.eligible_from_semester + Math.max(offset, 1) - 1;
const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function ProgramPicker({ programs, value, onChange }: {
  programs: MinorProgram[]; value: number | null; onChange: (id: number) => void;
}) {
  return (
    <Select aria-label="Minor" value={value ?? ""} className="w-full sm:w-80"
            onChange={(e) => onChange(Number(e.target.value))}>
      {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </Select>
  );
}

export function MinorGradebookTab({ programs }: { programs: MinorProgram[] }) {
  const mine = programs.filter((p) => p.can_manage);
  const [programId, setProgramId] = useState<number | null>(mine[0]?.id ?? null);
  const program = mine.find((p) => p.id === programId) ?? null;
  const [courseId, setCourseId] = useState<number | null>(null);
  useEffect(() => { setCourseId(program?.courses[0]?.id ?? null); }, [program?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [rows, setRows] = useState<GradeRow[]>([]);
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const book = useQuery({
    queryKey: ["minor-gradebook", programId, courseId],
    queryFn: () => api.get<GradeRow[]>(`/minors/${programId}/gradebook?minor_course_id=${courseId}`),
    enabled: Boolean(programId && courseId),
  });
  useEffect(() => { if (book.data) setRows(book.data); }, [book.data]);

  const save = useMutation({
    mutationFn: () => api.put<GradeRow[]>(`/minors/${programId}/courses/${courseId}/results`, {
      results: rows.map((r) => ({ enrollment_id: r.enrollment_id, marks: r.marks, grade: r.grade || null,
                                  status: r.status || "IN_PROGRESS" })),
    }),
    onSuccess: (data) => { setRows(data); setBanner({ tone: "success", text: "Results saved. Students see them on their minor page." }); },
    onError: (err) => setBanner({ tone: "danger", text: errorText(err, "Could not save the results.") }),
  });
  const update = (i: number, patch: Partial<GradeRow>) => setRows((list) => list.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  if (!mine.length) {
    return <Card><EmptyState title="No minor to grade" description="You do not coordinate a minor programme." /></Card>;
  }
  const course = program?.courses.find((c) => c.id === courseId);
  return (
    <Card>
      <CardHeader title="Course results"
                  description="Marks out of 100 and the grade, as your department records them. A passed course counts towards the student's credits."
                  action={<ProgramPicker programs={mine} value={programId} onChange={setProgramId} />} />
      <CardBody className="space-y-4">
        {banner && <Alert variant={banner.tone} onDismiss={() => setBanner(null)}>{banner.text}</Alert>}
        <Select aria-label="Course" value={courseId ?? ""} onChange={(e) => setCourseId(Number(e.target.value))}>
          {(program?.courses ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              Semester {roman(semesterOf(program!, c.semester_offset))} · {c.course_code} — {c.course_title} ({c.credits} cr)
            </option>
          ))}
        </Select>
        {book.isLoading ? <LoadingState rows={3} /> : rows.length === 0 ? (
          <EmptyState compact title="Nobody holds a seat in this minor yet" />
        ) : (
          <TableWrap className="rounded border border-line">
            <THead>
              <TH>Student</TH>
              <TH width="14%">Marks</TH>
              <TH width="12%">Grade</TH>
              <TH width="20%">Result</TH>
            </THead>
            <TBody>
              {rows.map((row, i) => (
                <TR key={row.enrollment_id}>
                  <TD>
                    <p className="font-medium text-ink">{row.student_name}</p>
                    <p className="font-mono text-2xs text-ink-subtle">{row.roll_number} · {row.department} · Sem {roman(row.semester)}</p>
                  </TD>
                  <TD>
                    <Input aria-label={`Marks for ${row.student_name}`} inputMode="decimal" className="h-8 text-right tabular"
                           value={row.marks ?? ""} onChange={(e) => update(i, { marks: e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9.]/g, "")) })} />
                  </TD>
                  <TD>
                    <Input aria-label={`Grade for ${row.student_name}`} maxLength={4} className="h-8 font-mono uppercase"
                           value={row.grade ?? ""} onChange={(e) => update(i, { grade: e.target.value.toUpperCase() })} />
                  </TD>
                  <TD>
                    <Select aria-label={`Result for ${row.student_name}`} className="h-8 text-xs"
                            value={row.status ?? "IN_PROGRESS"} onChange={(e) => update(i, { status: e.target.value })}>
                      <option value="IN_PROGRESS">In progress</option>
                      <option value="PASSED">Passed</option>
                      <option value="FAILED">Failed</option>
                    </Select>
                  </TD>
                </TR>
              ))}
            </TBody>
          </TableWrap>
        )}
        {rows.length > 0 && (
          <div className="flex justify-end">
            <Button size="sm" loading={save.isPending} icon={<Save className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => save.mutate()}>
              Save results for {course?.course_code ?? "this course"}
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function MinorFeesTab({ programs }: { programs: MinorProgram[] }) {
  const queryClient = useQueryClient();
  const mine = programs.filter((p) => p.can_manage);
  const [programId, setProgramId] = useState<number | null>(mine[0]?.id ?? null);
  const program = mine.find((p) => p.id === programId) ?? null;
  const semesters = useMemo(() => [...new Set((program?.courses ?? []).map((c) => semesterOf(program!, c.semester_offset)))].sort((a, b) => a - b), [program]);
  const [schedule, setSchedule] = useState<{ semester: number; amount: string; due_on: string; note: string }[]>([]);
  useEffect(() => {
    setSchedule((program?.fees ?? []).map((f) => ({ semester: f.semester, amount: String(f.amount), due_on: f.due_on ?? "", note: f.note ?? "" })));
  }, [program?.id, program?.fees]);
  const [paying, setPaying] = useState<{ row: FeeStatusRow; semester: number; amount: number } | null>(null);
  const [payment, setPayment] = useState({ reference: "", paid_on: "" });
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const status = useQuery({
    queryKey: ["minor-fee-status", programId],
    queryFn: () => api.get<FeeStatusRow[]>(`/minors/${programId}/fee-status`),
    enabled: Boolean(programId),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["minor-programs"] });
    void queryClient.invalidateQueries({ queryKey: ["minor-fee-status"] });
  };
  const saveSchedule = useMutation({
    mutationFn: () => api.put(`/minors/${programId}/fees`, {
      fees: schedule.map((f) => ({ semester: f.semester, amount: Number(f.amount), due_on: f.due_on || null, note: f.note || null })),
    }),
    onSuccess: () => { setBanner({ tone: "success", text: "Fee schedule saved. Students see it on their minor page." }); refresh(); },
    onError: (err) => setBanner({ tone: "danger", text: errorText(err, "Could not save the fees.") }),
  });
  const pay = useMutation({
    mutationFn: () => api.put(`/minors/enrollments/${paying!.row.enrollment_id}/fees/${paying!.semester}`, {
      amount: paying!.amount, reference: payment.reference || null, paid_on: payment.paid_on || null,
    }),
    onSuccess: () => { setPaying(null); setBanner({ tone: "success", text: "Payment recorded." }); refresh(); },
    onError: (err) => setBanner({ tone: "danger", text: errorText(err, "Could not record the payment.") }),
  });
  const unpay = useMutation({
    mutationFn: ({ enrollmentId, semester }: { enrollmentId: number; semester: number }) =>
      api.delete(`/minors/enrollments/${enrollmentId}/fees/${semester}`),
    onSuccess: () => { setBanner({ tone: "success", text: "Payment removed." }); refresh(); },
    onError: (err) => setBanner({ tone: "danger", text: errorText(err, "Could not remove the payment.") }),
  });

  if (!mine.length) {
    return <Card><EmptyState title="No minor fees to manage" description="You do not coordinate a minor programme." /></Card>;
  }
  const unused = semesters.filter((s) => !schedule.some((f) => f.semester === s));
  return (
    <div className="space-y-5">
      {banner && <Alert variant={banner.tone} onDismiss={() => setBanner(null)}>{banner.text}</Alert>}
      <Card>
        <CardHeader title="Fee per semester"
                    description="The minor fee your department charges each semester. Nothing is shown to students until you set it."
                    action={<ProgramPicker programs={mine} value={programId} onChange={setProgramId} />} />
        <CardBody className="space-y-3">
          {schedule.length === 0 && <p className="text-sm text-ink-muted">No fee announced yet.</p>}
          {schedule.map((f, i) => (
            <div key={f.semester} className="flex flex-wrap items-end gap-2 rounded-lg border border-line p-3">
              <p className="w-28 pb-2 text-sm font-semibold text-ink">Semester {roman(f.semester)}</p>
              <div className="w-36"><FormField label="Amount (₹)" htmlFor={`fee-${f.semester}`}>
                <Input id={`fee-${f.semester}`} inputMode="decimal" value={f.amount}
                       onChange={(e) => setSchedule((l) => l.map((x, j) => (j === i ? { ...x, amount: e.target.value.replace(/[^0-9.]/g, "") } : x)))} />
              </FormField></div>
              <div className="w-44"><FormField label="Due on" htmlFor={`due-${f.semester}`}>
                <Input id={`due-${f.semester}`} type="date" value={f.due_on}
                       onChange={(e) => setSchedule((l) => l.map((x, j) => (j === i ? { ...x, due_on: e.target.value } : x)))} />
              </FormField></div>
              <div className="min-w-0 flex-1"><FormField label="Note" htmlFor={`note-${f.semester}`}>
                <Input id={`note-${f.semester}`} maxLength={300} value={f.note}
                       onChange={(e) => setSchedule((l) => l.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)))} />
              </FormField></div>
              <Button variant="ghost" size="icon" className="text-danger" aria-label={`Remove semester ${f.semester} fee`}
                      icon={<Trash2 className="h-4 w-4" aria-hidden />}
                      onClick={() => setSchedule((l) => l.filter((_, j) => j !== i))} />
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            {unused.length > 0 && (
              <Select aria-label="Add a semester" value="" className="w-56"
                      onChange={(e) => e.target.value && setSchedule((l) => [...l, { semester: Number(e.target.value), amount: "", due_on: "", note: "" }]
                        .sort((a, b) => a.semester - b.semester))}>
                <option value="">Add a semester's fee…</option>
                {unused.map((s) => <option key={s} value={s}>Semester {roman(s)}</option>)}
              </Select>
            )}
            <Button size="sm" className="ml-auto" loading={saveSchedule.isPending}
                    disabled={schedule.some((f) => f.amount === "")}
                    icon={<Save className="h-3.5 w-3.5" aria-hidden />} onClick={() => saveSchedule.mutate()}>
              Save fee schedule
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Payments" description="Record a student's fee as paid with the receipt number." />
        {status.isLoading ? <CardBody><LoadingState rows={3} /></CardBody> : !(status.data ?? []).length ? (
          <EmptyState compact title="Nobody holds a seat in this minor yet" />
        ) : !(program?.fees ?? []).length ? (
          <EmptyState compact title="Set the fee schedule first" />
        ) : (
          <TableWrap>
            <THead>
              <TH>Student</TH>
              {(program?.fees ?? []).map((f) => <TH key={f.semester}>Sem {roman(f.semester)} · {formatCurrency(f.amount)}</TH>)}
            </THead>
            <TBody>
              {(status.data ?? []).map((row) => (
                <TR key={row.enrollment_id}>
                  <TD>
                    <p className="font-medium text-ink">{row.student_name}</p>
                    <p className="font-mono text-2xs text-ink-subtle">{row.roll_number}</p>
                  </TD>
                  {row.semesters.map((s) => (
                    <TD key={s.semester}>
                      {s.paid ? (
                        <span className="flex items-center gap-1.5">
                          <Badge tone="success">Paid{s.reference ? ` · ${s.reference}` : ""}</Badge>
                          <Button variant="ghost" size="icon" aria-label={`Remove ${row.student_name}'s semester ${s.semester} payment`}
                                  icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                                  onClick={() => unpay.mutate({ enrollmentId: row.enrollment_id, semester: s.semester })} />
                        </span>
                      ) : (
                        <Button variant="secondary" size="sm" icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                                onClick={() => { setPayment({ reference: "", paid_on: "" }); setPaying({ row, semester: s.semester, amount: s.amount }); }}>
                          Mark paid
                        </Button>
                      )}
                    </TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </TableWrap>
        )}
      </Card>

      <Modal open={paying !== null} onClose={() => setPaying(null)} size="sm"
             title={paying ? `${paying.row.student_name} — Semester ${roman(paying.semester)} fee` : ""}
             description={paying ? `${formatCurrency(paying.amount)} recorded as paid.` : undefined}
             footer={<>
               <Button variant="secondary" size="sm" onClick={() => setPaying(null)}>Cancel</Button>
               <Button size="sm" loading={pay.isPending} onClick={() => pay.mutate()}>Record payment</Button>
             </>}>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Receipt / reference" htmlFor="pay-ref">
            <Input id="pay-ref" maxLength={80} value={payment.reference} data-autofocus
                   onChange={(e) => setPayment((p) => ({ ...p, reference: e.target.value }))} />
          </FormField>
          <FormField label="Paid on" htmlFor="pay-on">
            <Input id="pay-on" type="date" value={payment.paid_on}
                   onChange={(e) => setPayment((p) => ({ ...p, paid_on: e.target.value }))} />
          </FormField>
        </div>
      </Modal>
    </div>
  );
}
