import { Award, CheckCircle2, Printer, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/format";
import type { EnrollmentDetail } from "@/types";

interface Props {
  enrollment: EnrollmentDetail;
  open: boolean;
  onClose: () => void;
}

export function InternshipCertificateModal({ enrollment, open, onClose }: Props) {
  if (!open) return null;

  const issueDate = formatDate(enrollment.end_date ?? new Date().toISOString());
  const refCode = `PDEU/SOT/INT-${new Date().getFullYear()}/${String(enrollment.id).padStart(4, "0")}`;

  function handlePrint() {
    window.print();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Official Internship Completion Certificate"
      size="xl"
    >
      <div className="space-y-4">
        {/* Print Action Bar */}
        <div className="flex items-center justify-between bg-surface-muted/60 p-3 rounded-lg border border-line print:hidden">
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
            <span>Digital verification code: <strong className="font-mono text-ink">{refCode}</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={handlePrint}
              icon={<Printer className="h-4 w-4 text-ink-muted" aria-hidden />}
            >
              Print / Save PDF
            </Button>
          </div>
        </div>

        {/* Certificate Canvas */}
        <div className="certificate-sheet relative overflow-hidden rounded-xl border-4 border-double border-amber-600/40 bg-[#fdfcf9] dark:bg-stone-900/90 text-stone-900 dark:text-stone-100 p-8 sm:p-12 shadow-2xl">
          {/* Ornamental corner accents */}
          <div className="absolute top-3 left-3 w-8 h-8 border-t-2 border-l-2 border-amber-600/60 pointer-events-none" />
          <div className="absolute top-3 right-3 w-8 h-8 border-t-2 border-r-2 border-amber-600/60 pointer-events-none" />
          <div className="absolute bottom-3 left-3 w-8 h-8 border-b-2 border-l-2 border-amber-600/60 pointer-events-none" />
          <div className="absolute bottom-3 right-3 w-8 h-8 border-b-2 border-r-2 border-amber-600/60 pointer-events-none" />

          {/* Background Watermark */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none">
            <span className="font-heading text-9xl font-black uppercase tracking-widest text-amber-900">PDEU</span>
          </div>

          {/* Institutional Header */}
          <div className="relative text-center space-y-2 pb-6 border-b border-amber-600/20">
            <div className="inline-flex items-center justify-center h-14 w-14 rounded-full bg-amber-500/10 text-amber-600 mb-1 border border-amber-500/20">
              <Award className="h-8 w-8" aria-hidden />
            </div>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold tracking-tight text-amber-900 dark:text-amber-200 uppercase">
              Pandit Deendayal Energy University
            </h1>
            <p className="text-xs uppercase tracking-widest text-stone-600 dark:text-stone-400 font-semibold">
              School of Technology • Department of {enrollment.department_code ?? "Information & Communication Technology"}
            </p>
            <div className="pt-2">
              <span className="inline-block px-4 py-1 rounded-full bg-amber-600/10 text-amber-800 dark:text-amber-300 font-serif text-xs font-bold uppercase tracking-widest border border-amber-600/20">
                Certificate of Completion
              </span>
            </div>
          </div>

          {/* Certificate Body */}
          <div className="relative my-8 text-center space-y-5">
            <p className="text-sm font-serif italic text-stone-600 dark:text-stone-400">
              This is to certify that
            </p>

            <h2 className="font-serif text-3xl sm:text-4xl font-extrabold text-stone-900 dark:text-white tracking-wide underline decoration-amber-500/30 underline-offset-8">
              {enrollment.student_name ?? "Student Name"}
            </h2>

            <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-stone-700 dark:text-stone-300 font-mono">
              <span className="px-2.5 py-1 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700">
                Roll No: <strong>{enrollment.roll_number ?? "—"}</strong>
              </span>
              {enrollment.division && (
                <span className="px-2.5 py-1 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700">
                  Division: <strong>{enrollment.division}</strong>
                </span>
              )}
              {enrollment.semester && (
                <span className="px-2.5 py-1 rounded bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700">
                  Semester: <strong>{enrollment.semester}</strong>
                </span>
              )}
            </div>

            <p className="max-w-2xl mx-auto text-sm sm:text-base leading-relaxed text-stone-700 dark:text-stone-300 font-serif">
              has satisfactorily completed the prescribed requirements for the{" "}
              <strong className="text-stone-900 dark:text-white font-semibold">
                {enrollment.program_code ?? "Internship Program"}
              </strong>
              {enrollment.organization_name ? (
                <>
                  {" "}at{" "}
                  <strong className="text-stone-900 dark:text-white font-semibold">
                    {enrollment.organization_name}
                  </strong>
                  {enrollment.location ? ` (${enrollment.location})` : ""}
                </>
              ) : null}
              {enrollment.start_date && enrollment.end_date && (
                <>
                  {" "}from{" "}
                  <span className="font-sans font-medium">{formatDate(enrollment.start_date)}</span>
                  {" "}to{" "}
                  <span className="font-sans font-medium">{formatDate(enrollment.end_date)}</span>
                </>
              )}
              .
            </p>

            {enrollment.project?.title && (
              <div className="max-w-xl mx-auto rounded-lg bg-stone-50 dark:bg-stone-800/60 p-3 border border-stone-200/80 dark:border-stone-700 text-xs">
                <span className="text-stone-500 uppercase tracking-wider font-semibold block text-2xs mb-0.5">Project Title</span>
                <p className="font-medium text-stone-800 dark:text-stone-200 italic">"{enrollment.project.title}"</p>
              </div>
            )}

            {/* Performance Outcomes */}
            {(enrollment.final_marks !== null || enrollment.final_grade) && (
              <div className="flex items-center justify-center gap-4 pt-2">
                {enrollment.final_grade && (
                  <div className="text-center px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                    <span className="text-2xs text-emerald-800 dark:text-emerald-300 font-semibold uppercase block">Final Grade</span>
                    <span className="text-xl font-heading font-black text-emerald-700 dark:text-emerald-400">{enrollment.final_grade}</span>
                  </div>
                )}
                {enrollment.final_marks !== null && (
                  <div className="text-center px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                    <span className="text-2xs text-emerald-800 dark:text-emerald-300 font-semibold uppercase block">Aggregate Score</span>
                    <span className="text-xl font-heading font-black text-emerald-700 dark:text-emerald-400">{enrollment.final_marks} / 100</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Signatures & Verification Footer */}
          <div className="relative pt-8 border-t border-amber-600/20 grid grid-cols-3 gap-4 text-center items-end">
            {/* Faculty Mentor */}
            <div className="space-y-1">
              <div className="h-10 flex items-end justify-center pb-1">
                <span className="font-serif italic text-sm text-stone-600 dark:text-stone-400">
                  {enrollment.mentor?.name ?? "Faculty Mentor"}
                </span>
              </div>
              <div className="border-t border-stone-400 dark:border-stone-600 pt-1">
                <p className="text-xs font-bold text-stone-800 dark:text-stone-200">
                  {enrollment.mentor?.name ?? "Faculty Mentor"}
                </p>
                <p className="text-2xs text-stone-500">Internal Faculty Guide</p>
              </div>
            </div>

            {/* Security Badge / QR Seal */}
            <div className="flex flex-col items-center justify-center space-y-1">
              <div className="h-12 w-12 rounded-full border-2 border-dashed border-amber-600/40 flex items-center justify-center text-amber-700 bg-amber-50 dark:bg-amber-950/40">
                <CheckCircle2 className="h-6 w-6 text-amber-600" />
              </div>
              <p className="text-3xs uppercase tracking-wider text-stone-400 font-mono">
                Verified Authentic
              </p>
              <p className="text-3xs font-mono text-stone-500">
                Issue Date: {issueDate}
              </p>
            </div>

            {/* Department Head */}
            <div className="space-y-1">
              <div className="h-10 flex items-end justify-center pb-1">
                <span className="font-serif italic text-sm text-stone-600 dark:text-stone-400">
                  Dr. Rakesh Bhatt
                </span>
              </div>
              <div className="border-t border-stone-400 dark:border-stone-600 pt-1">
                <p className="text-xs font-bold text-stone-800 dark:text-stone-200">
                  Dr. Rakesh Bhatt
                </p>
                <p className="text-2xs text-stone-500">Head of Department</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
