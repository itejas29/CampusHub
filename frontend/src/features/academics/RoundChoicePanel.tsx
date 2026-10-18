import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Form";
import { ApiError, api } from "@/lib/api";
import { deadlineLabel, formatDateTime } from "@/lib/format";
import type { StudentRound } from "@/types";

/**
 * Ticking subjects in a two-stage round. In the interest stage a tick is a
 * vote; in the final stage it is a subject the student will take. Either way
 * the student ticks exactly the number the coordinator set — the server checks
 * that too, and decides whether the round is open.
 */
export function RoundChoicePanel({ round, onSaved }: {
  round: StudentRound; onSaved: (round: StudentRound) => void;
}) {
  const [picked, setPicked] = useState<number[]>(round.my_course_ids);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setPicked(round.my_course_ids); }, [round]);

  const isFinal = round.stage === "FINAL";
  const deadline = deadlineLabel(round.closes_at);
  const exact = picked.length === round.pick_count;
  const unchanged = picked.length === round.my_course_ids.length
    && picked.every((id) => round.my_course_ids.includes(id));

  const save = useMutation({
    mutationFn: () => api.put<StudentRound>(`/electives/rounds/${round.id}/choices`,
      { course_ids: picked }),
    onSuccess: (saved) => { setError(null); onSaved(saved); },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  function toggle(id: number) {
    setPicked((now) => (now.includes(id) ? now.filter((x) => x !== id)
      : now.length >= round.pick_count ? now : [...now, id]));
  }

  return (
    <Card>
      <CardHeader
        title={isFinal ? "Final round — choose your electives" : "Interest round"}
        description={isFinal
          ? `Tick exactly ${round.pick_count} of the shortlisted subjects. These are the subjects you will take, if they run.`
          : `Tick exactly ${round.pick_count} subjects you are interested in. The department shortlists the most wanted ones for the final round.`}
        action={round.closes_at ? (
          <Badge tone={deadline.tone}>{deadline.text}</Badge>
        ) : undefined}
      />
      <CardBody className="space-y-4">
        {!round.can_submit && round.reason && <Alert variant="info">{round.reason}</Alert>}
        {round.submitted_at && (
          <Alert variant="success">
            Submitted {formatDateTime(round.submitted_at)}.
            {round.can_submit && " You can change it until the deadline."}
          </Alert>
        )}
        {error && <Alert variant="danger">{error}</Alert>}
        <div className="grid gap-2 sm:grid-cols-2">
          {round.subjects.map((subject) => {
            const on = picked.includes(subject.course_id);
            const wasInterest = isFinal && round.my_interest_course_ids.includes(subject.course_id);
            return (
              <div key={subject.course_id}
                   className="rounded-lg border border-line px-3 py-2.5">
                <Checkbox
                  checked={on}
                  disabled={!round.can_submit || (!on && picked.length >= round.pick_count)}
                  onChange={() => toggle(subject.course_id)}
                  label={<span className="font-medium">{subject.title}</span>}
                  description={`${subject.code}${subject.credits != null ? ` · ${subject.credits} credits` : ""}`
                    + (wasInterest ? " · you showed interest" : "")}
                />
              </div>
            );
          })}
        </div>
        {round.can_submit && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-muted">
              {picked.length} of {round.pick_count} ticked
            </p>
            <Button disabled={!exact || unchanged} loading={save.isPending}
                    onClick={() => save.mutate()}>
              {round.my_course_ids.length ? "Update my choice" : "Submit"}
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
