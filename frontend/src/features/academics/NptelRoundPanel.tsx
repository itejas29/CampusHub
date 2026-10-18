import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Modal";
import { FileUpload } from "@/components/ui/Misc";
import { ApiError, api } from "@/lib/api";
import { deadlineLabel, formatDate, formatDateTime } from "@/lib/format";
import { cn, roman } from "@/lib/utils";
import type { MoocOption, StudentMoocRound, StudentMoocStanding } from "@/types";

const errorText = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

/** Where the student stands on the slot overall: cleared, carried, backlog. */
export function NptelStandingBanner({ data }: { data: StudentMoocStanding }) {
  if (data.standing === "CLEARED") {
    return (
      <Alert variant="success" title={`${data.component_title ?? "NPTEL / NCC"}: completed`}
             className="mb-5">
        Your certificate has been verified. This requirement is cleared.
      </Alert>
    );
  }
  if (data.standing === "CARRIED_OVER") {
    return (
      <Alert variant="warning" title="Carried over to this semester" className="mb-5">
        {data.component_title ?? "This requirement"} was not cleared in Semester{" "}
        {roman(data.component_semester ?? 0)}. Choose an NPTEL course or NCC again in this
        semester's round — you can switch between them. Not cleared this semester, it
        becomes a backlog.
      </Alert>
    );
  }
  if (data.standing === "BACKLOG") {
    return (
      <Alert variant="danger" title="Backlog" className="mb-5">
        {data.component_title ?? "This requirement"} was not cleared in either semester and
        is now a backlog. Contact the department.
      </Alert>
    );
  }
  return null;
}

/**
 * The semester's NPTEL / NCC round, as the student meets it: choose one
 * approved course or NCC, then submit the certificate — or say you did not
 * pass. The server decides what is open; this only reflects it.
 */
export function NptelRoundPanel({ round }: { round: StudentMoocRound }) {
  const queryClient = useQueryClient();
  const [option, setOption] = useState<MoocOption>(round.choice?.option ?? "NPTEL");
  const [courseId, setCourseId] = useState<number | null>(round.choice?.course?.course_id ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [confirmFail, setConfirmFail] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  useEffect(() => {
    setOption(round.choice?.option ?? "NPTEL");
    setCourseId(round.choice?.course?.course_id ?? null);
  }, [round.choice]);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["mooc"] });
  const fail = (err: unknown, fallback: string) =>
    setMessage({ tone: "danger", text: errorText(err, fallback) });

  const save = useMutation({
    mutationFn: () => api.post<StudentMoocRound>(`/mooc/rounds/${round.id}/choice`, {
      option, course_id: option === "NCC" ? null : courseId,
    }),
    onSuccess: () => {
      setMessage({ tone: "success", text: option === "NCC"
        ? "NCC recorded. Submit your NCC certificate here when you complete it."
        : "Course recorded. Register for it on the NPTEL portal yourself, and submit the certificate here when you pass." });
      refresh();
    },
    onError: (err) => fail(err, "Could not save your choice."),
  });
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file as File);
      return api.upload(`/mooc/${round.choice!.registration_id}/certificate`, form);
    },
    onSuccess: () => {
      setFile(null);
      setMessage({ tone: "success", text: "Certificate submitted. The coordinator will verify it." });
      refresh();
    },
    onError: (err) => fail(err, "Upload failed."),
  });
  const failed = useMutation({
    mutationFn: () => api.post(`/mooc/${round.choice!.registration_id}/failed`),
    onSuccess: () => {
      setConfirmFail(false);
      setMessage({ tone: "success", text: "Recorded. This requirement carries over to next semester when the semester closes." });
      refresh();
    },
    onError: (err) => { setConfirmFail(false); fail(err, "Could not record that."); },
  });

  const choice = round.choice;
  const deadline = deadlineLabel(round.closes_at);
  const unchanged = choice && choice.option === option
    && (option === "NCC" || choice.course?.course_id === courseId);
  const ready = option === "NCC" || courseId !== null;
  const ncc = choice?.option === "NCC";

  return (
    <Card className="mb-5">
      <CardHeader
        title={round.title}
        description={round.message ?? undefined}
        action={
          <div className="flex flex-wrap items-center gap-1.5">
            {round.carry_over && <Badge tone="warning">Carried over</Badge>}
            {round.closes_at && round.status === "OPEN" && (
              <Badge tone={deadline.tone}>{deadline.text}</Badge>
            )}
          </div>
        }
      />
      <CardBody className="space-y-4">
        {message && (
          <Alert variant={message.tone === "success" ? "success" : "danger"}
                 onDismiss={() => setMessage(null)}>{message.text}</Alert>
        )}
        {round.platform_deadline && (
          <p className="text-sm text-ink-muted">
            Register for your course on the NPTEL portal yourself, by{" "}
            <strong>{formatDate(round.platform_deadline)}</strong>. Only registered candidates
            can sit the NPTEL exam.
          </p>
        )}

        {choice && (
          <div className="rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-subtle">Your choice</p>
                <p className="mt-0.5 font-semibold text-ink">
                  {ncc ? "NCC certification" : `${choice.course?.title} (${choice.course?.code})`}
                </p>
                {!ncc && choice.course?.url && (
                  <a href={choice.course.url} target="_blank" rel="noreferrer"
                     className="mt-1 inline-flex items-center gap-1 text-xs text-brand hover:underline">
                    NPTEL course page <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                )}
              </div>
              {/* "Registered" would read as NPTEL portal registration, which the
                  portal does not track: here it means the choice is recorded. */}
              <StatusBadge status={choice.status === "FAILED" ? "Not passed"
                : choice.status === "REGISTERED" ? "Chosen" : choice.status} />
            </div>
            {choice.verification_status === "REJECTED" && choice.remarks && (
              <Alert variant="warning" className="mt-3">
                Certificate not accepted: {choice.remarks}. Submit it again.
              </Alert>
            )}
            {choice.verification_status === "VERIFIED" && (
              <Alert variant="success" className="mt-3">Your certificate has been verified.</Alert>
            )}
            {round.can_submit_result && choice.status !== "FAILED" && (
              <div className="mt-4 space-y-3 border-t border-line pt-4">
                <p className="text-sm text-ink-muted">
                  {ncc ? "When you complete NCC, submit your NCC certificate."
                       : "NPTEL certifies only those who pass. When your result is out, submit the certificate — or tell us you did not pass."}
                </p>
                <FileUpload onSelect={setFile} accept=".pdf,.jpg,.jpeg,.png"
                            selectedName={file?.name ?? null}
                            label={choice.certificate_url ? "Replace the certificate" : "Choose the certificate"} />
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" disabled={!file} loading={upload.isPending}
                          onClick={() => upload.mutate()}>
                    Submit certificate
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setConfirmFail(true)}>
                    I did not pass
                  </Button>
                </div>
              </div>
            )}
            {choice.status === "FAILED" && (
              <p className="mt-3 text-sm text-ink-muted">
                You reported that you did not pass. This carries over to next semester's round
                when the semester closes.
              </p>
            )}
          </div>
        )}

        {round.can_choose ? (
          <div className="space-y-3">
            <p className="font-medium text-ink">
              {choice ? "Change your choice (until the deadline)" : "Choose one"}
            </p>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="NPTEL or NCC">
              {(["NPTEL", "NCC"] as MoocOption[]).map((value) => (
                <button key={value} type="button" role="radio" aria-checked={option === value}
                        onClick={() => setOption(value)}
                        className={cn("rounded-lg border px-4 py-2 text-sm font-semibold",
                          option === value ? "border-brand bg-brand-soft text-brand"
                            : "border-line text-ink-muted hover:border-brand/40")}>
                  {value === "NPTEL" ? "An NPTEL course" : "NCC certification"}
                </button>
              ))}
            </div>
            {option === "NPTEL" ? (
              <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Approved courses">
                {round.courses.map((course) => (
                  <label key={course.course_id}
                         className={cn("flex cursor-pointer gap-3 rounded-lg border p-3",
                           courseId === course.course_id ? "border-brand bg-brand-soft/40"
                             : "border-line hover:border-brand/40")}>
                    <input type="radio" name="nptel-course" className="mt-1"
                           checked={courseId === course.course_id}
                           onChange={() => setCourseId(course.course_id)} />
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{course.title}</span>
                      <span className="block text-xs text-ink-muted">
                        {course.code} · {course.weeks} weeks · {course.credits} credits
                      </span>
                      {(course.instructors || course.institute) && (
                        <span className="block text-xs text-ink-subtle">
                          {[course.instructors, course.coordinating_institute ?? course.institute]
                            .filter(Boolean).join(" · ")}
                        </span>
                      )}
                      {course.url && (
                        <a href={course.url} target="_blank" rel="noreferrer"
                           onClick={(e) => e.stopPropagation()}
                           className="mt-1 inline-flex items-center gap-1 text-xs text-brand hover:underline">
                          Details <ExternalLink className="h-3 w-3" aria-hidden />
                        </a>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-muted">
                NCC needs no course, credits or weeks. You submit your NCC certificate when you
                complete it.
              </p>
            )}
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-ink-subtle">
                {round.closes_at && `Choosing closes ${formatDateTime(round.closes_at)}.`}
              </p>
              <Button disabled={!ready || Boolean(unchanged)} loading={save.isPending}
                      onClick={() => save.mutate()}>
                {choice ? "Save my new choice" : "Save my choice"}
              </Button>
            </div>
          </div>
        ) : (
          !choice && round.reason && <Alert variant="info">{round.reason}</Alert>
        )}
      </CardBody>
      {confirmFail && (
        <ConfirmDialog
          open onClose={() => setConfirmFail(false)} onConfirm={() => failed.mutate()}
          loading={failed.isPending} title="You did not pass?"
          confirmLabel="Yes, I did not pass"
          message="NPTEL gives no certificate to students who do not pass. This requirement will carry over to next semester, when you choose again — an NPTEL course or NCC."
        />
      )}
    </Card>
  );
}
