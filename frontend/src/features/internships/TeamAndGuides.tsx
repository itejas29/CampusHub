import { useMutation, useQuery } from "@tanstack/react-query";
import { Crown, Plus, UserMinus, Users } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Form";
import { Avatar } from "@/components/ui/Misc";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EnrollmentDetail } from "@/types";

type Guide = { faculty_id: number; name: string; designation: string | null; specialization: string | null };

/**
 * A project student's team and the guides they would like, on their record.
 *
 * Only shown for a programme that allows either (`team_limits`,
 * `preference_limit`). The server decides everything — who leads, who may
 * join, when the team is fixed — and these controls simply ask.
 */
export function TeamAndGuides({ record, onChanged }: { record: EnrollmentDetail; onChanged: () => void }) {
  const { user } = useAuth();
  const [teamName, setTeamName] = useState("");
  const [roll, setRoll] = useState("");
  const [ranking, setRanking] = useState<string[]>(
    () => (record.guide_preferences ?? []).map((g) => String(g.faculty_id)));
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const team = record.team ?? null;
  const isLeader = team ? team.leader_enrollment_id === record.id : true;
  const hasGuide = Boolean(record.mentor_faculty_id);
  const limit = record.preference_limit ?? 0;

  const guides = useQuery({
    queryKey: ["programme-guides", record.program_id],
    queryFn: () => api.get<Guide[]>(`/internships/programs/${record.program_id}/guides`),
    enabled: limit > 0 && !hasGuide && user?.student?.id === record.student_id,
  });

  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: (_r, _fn) => { onChanged(); },
    onError: (err) => setMessage({ tone: "danger", text: err instanceof ApiError ? err.message : "That did not work." }),
  });
  const run = (fn: () => Promise<unknown>, done: string) => {
    setMessage(null);
    act.mutate(fn, { onSuccess: () => setMessage({ tone: "success", text: done }) });
  };

  // The student's own controls; staff manage teams from Assign Mentors.
  if (user?.student?.id !== record.student_id) return null;
  if (!record.team_limits && !limit) return null;

  return (
    <Card className="mb-5">
      <CardHeader
        title="Team & guide"
        description={hasGuide
          ? `Your guide is ${record.mentor_name}.` + (team ? " Your team is fixed now." : "")
          : "Form a team if you are working with classmates, and rank the guides you would like. The coordinator allocates guides."}
        icon={<Users className="h-4 w-4 text-ink-subtle" aria-hidden />}
      />
      <CardBody className="grid gap-6 md:grid-cols-2">
        {message && <Alert variant={message.tone} className="md:col-span-2" onDismiss={() => setMessage(null)}>{message.text}</Alert>}

        {record.team_limits && (
          <section aria-label="Team" className="min-w-0">
            <h3 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Team · up to {record.team_limits.max}
            </h3>
            {!team ? (
              hasGuide ? (
                <p className="text-sm text-ink-muted">You are working on your own.</p>
              ) : (
                <div className="flex gap-2">
                  <Input value={teamName} maxLength={120} placeholder="Team or project name"
                         aria-label="Team name" onChange={(e) => setTeamName(e.target.value)} />
                  <Button size="sm" disabled={!teamName.trim() || act.isPending}
                          onClick={() => run(() => api.post(`/internships/enrollments/${record.id}/team`, { name: teamName.trim() }),
                                             "Team formed. Add your classmates by roll number.")}>
                    Form a team
                  </Button>
                </div>
              )
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-ink">{team.name}</p>
                <ul className="divide-y divide-line rounded-lg border border-line">
                  {team.members.map((m) => {
                    const leader = m.enrollment_id === team.leader_enrollment_id;
                    const me = m.enrollment_id === record.id;
                    const canRemove = !team.is_fixed && (me ? !(leader && team.members.length > 1) : isLeader);
                    return (
                      <li key={m.enrollment_id} className="flex items-center gap-2.5 px-3 py-2">
                        <Avatar name={m.name} size="xs" />
                        <span className="min-w-0 flex-1 truncate text-sm text-ink">
                          {m.name} <span className="font-mono text-2xs text-ink-subtle">{m.roll_number}</span>
                        </span>
                        {leader && <Badge tone="accent" icon={<Crown className="h-3 w-3" aria-hidden />}>Leader</Badge>}
                        {canRemove && (
                          <Button variant="ghost" size="sm" aria-label={me ? "Leave the team" : `Remove ${m.name}`}
                                  icon={<UserMinus className="h-3.5 w-3.5" aria-hidden />}
                                  onClick={() => run(() => api.delete(`/internships/teams/${team.id}/members/${m.enrollment_id}`),
                                                     me ? "You left the team." : `${m.name} removed.`)}>
                            {me ? "Leave" : ""}
                          </Button>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {isLeader && !team.is_fixed && team.members.length < (record.team_limits.max ?? 1) && (
                  <div className="flex gap-2">
                    <Input value={roll} maxLength={20} placeholder="Classmate's roll number" aria-label="Roll number to add"
                           className="font-mono" onChange={(e) => setRoll(e.target.value.toUpperCase())} />
                    <Button size="sm" variant="secondary" disabled={roll.trim().length < 3 || act.isPending}
                            icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                            onClick={() => run(() => api.post(`/internships/teams/${team.id}/members`, { roll_number: roll.trim() }),
                                               `${roll.trim()} added to the team.`)}>
                      Add
                    </Button>
                  </div>
                )}
                <p className="text-2xs text-ink-subtle">
                  Classmates must have registered for this programme first. A team shares one guide;
                  marks stay individual.
                </p>
              </div>
            )}
          </section>
        )}

        {limit > 0 && (
          <section aria-label="Guide preferences" className="min-w-0">
            <h3 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
              Preferred guides{team ? " · for the team" : ""}
            </h3>
            {hasGuide ? (
              <p className="text-sm text-ink-muted">Guide allocated: <strong className="text-ink">{record.mentor_name}</strong>.</p>
            ) : !isLeader ? (
              <ol className="list-decimal space-y-1 pl-5 text-sm text-ink">
                {(record.guide_preferences ?? []).length
                  ? record.guide_preferences!.map((g) => <li key={g.faculty_id}>{g.name}</li>)
                  : <li className="list-none text-ink-muted">Your team leader has not ranked guides yet.</li>}
              </ol>
            ) : (
              <div className="space-y-2">
                {Array.from({ length: limit }, (_, i) => (
                  <Select key={i} aria-label={`Choice ${i + 1}`} value={ranking[i] ?? ""}
                          onChange={(e) => setRanking((list) => {
                            const next = [...list];
                            next[i] = e.target.value;
                            return next;
                          })}>
                    <option value="">{`Choice ${i + 1}${i ? " (optional)" : ""}`}</option>
                    {(guides.data ?? []).map((g) => (
                      <option key={g.faculty_id} value={g.faculty_id}
                              disabled={ranking.includes(String(g.faculty_id)) && ranking[i] !== String(g.faculty_id)}>
                        {g.name}{g.specialization ? ` — ${g.specialization.slice(0, 60)}` : ""}
                      </option>
                    ))}
                  </Select>
                ))}
                <Button size="sm" disabled={!ranking.filter(Boolean).length || act.isPending}
                        onClick={() => run(() => api.put(`/internships/enrollments/${record.id}/guide-preferences`, {
                          faculty_ids: ranking.filter(Boolean).map(Number),
                        }), team ? "Preferences saved for the whole team." : "Preferences saved.")}>
                  Save preferences
                </Button>
              </div>
            )}
          </section>
        )}
      </CardBody>
    </Card>
  );
}
