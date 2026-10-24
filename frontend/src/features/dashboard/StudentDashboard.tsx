import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight, BookOpen, Briefcase, CheckCircle2, Clock, FolderKanban, GraduationCap,
  Layers, Mail, MapPin, Megaphone, Phone, Presentation, Route, Sparkles, UserCheck, Users,
} from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card, CardAction, CardBody, CardHeader } from "@/components/ui/Card";
import { Avatar } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deadlineLabel, formatDate } from "@/lib/format";
import { cn, pluralise, roman } from "@/lib/utils";
import type { CalendarItem, ProgressItem, StudentDashboard as Data } from "@/types";
import { FocusBanner, GreetingHeader, HeaderChip } from "./widgets/GreetingHeader";
import { ScheduleCard } from "./widgets/ScheduleCard";
import { ScoreRing } from "./widgets/ScoreRing";

type Component = NonNullable<Data["curriculum_semester"]>["components"][number];

/** Slots the student chooses or registers for, as opposed to compulsory ones. */
const CHOICE_TYPES = new Set(["OPEN_ELECTIVE", "PROGRAM_CORE_ELECTIVE", "MOOC"]);

const TYPE_LABELS: Record<string, string> = {
  CORE: "Core course",
  OPEN_ELECTIVE: "Open elective",
  PROGRAM_CORE_ELECTIVE: "Program elective",
  MOOC: "NPTEL / MOOC",
  MINOR: "Minor",
  INTERNSHIP: "Internship",
  PROJECT: "Project",
};

/** The screen where a slot is acted on; compulsory slots have none. */
function componentLink(component: Component): string | null {
  switch (component.component_type) {
    case "OPEN_ELECTIVE": return `/academics/open-electives/${component.id}`;
    case "PROGRAM_CORE_ELECTIVE": return `/academics/core-electives/${component.id}`;
    case "MOOC": return "/academics/nptel";
    default: return null;
  }
}

/** Whether a slot waits on the student. The server decides; the status match is
 *  only for an API deployed before it sent `needs_action`. */
function waitsOnStudent(component: Component): boolean {
  return component.needs_action
    ?? (component.status === "Action needed" || component.status === "REJECTED");
}

// How each programme's card is drawn. UI vocabulary only — which programmes a
// student has, and every figure on the card, come from `data.progress`.
const PROGRAMME_META: Record<string, { label: string; icon: LucideIcon; chip: string }> = {
  CSSI: { label: "CSSI", icon: Users, chip: "bg-success-soft text-success" },
  SUMMER: { label: "Summer Internship", icon: Briefcase, chip: "bg-accent-soft text-accent" },
  MINOR_PROJECT: { label: "Semester VII · Minor Project", icon: FolderKanban, chip: "bg-brand-soft text-brand" },
  SEMINAR: { label: "Semester VII · Seminar", icon: Presentation, chip: "bg-brand-soft text-brand" },
  MAJOR_PROJECT: { label: "Semester VIII · Major Project / Internship", icon: GraduationCap, chip: "bg-iris-soft text-iris" },
  MINOR: { label: "Minor Specialisation", icon: Sparkles, chip: "bg-violet-soft text-violet" },
};
const FALLBACK_PROGRAMME = { label: "Programme", icon: Route, chip: "bg-surface-muted text-ink-muted" };

export function StudentDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", "student"],
    queryFn: () => api.get<Data>("/dashboard/student"),
  });

  // Dated action items join the schedule, so a round's deadline shows on the
  // calendar even though the calendar feed does not carry rounds.
  const deadlines = useMemo<CalendarItem[]>(
    () => (data?.action_items ?? []).flatMap((item, index) => item.due_at ? [{
      id: `due-${index}`, title: item.title, start_at: item.due_at, end_at: null,
      all_day: false, kind: "deadline", category: item.context, location: null,
      link: item.link, status: null,
    }] : []),
    [data?.action_items],
  );

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "there";
  const student = user?.student;
  const stat = (key: string) => data.stats.find((item) => item.key === key);

  // Everything below is read from the student's own curriculum semester. A
  // semester with no elective slot (I–III in most programmes) must say so
  // rather than show "0 pending", which reads as a finished task.
  const semester = data.curriculum_semester;
  const components = semester?.components ?? [];
  const choiceSlots = components.filter((c) => CHOICE_TYPES.has(c.component_type));
  const settledChoices = choiceSlots.filter((c) => !waitsOnStudent(c)).length;
  const pending = stat("pending_electives");
  const pendingCount = pending?.value ?? 0;
  const semesterNumber = student?.current_semester ?? stat("semester")?.value;
  const backlogs = student?.backlog_count ?? 0;

  // Allotments outside this semester's table — an early round for next term.
  const shownInTable = new Set(components.map((c) => c.id));
  const otherAllotments = (data.allocated_electives ?? []).filter((a) => !shownInTable.has(a.component_id));

  const soonest = [...data.action_items]
    .filter((item) => item.due_at)
    .sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? ""))[0] ?? data.action_items[0];

  return (
    <div className="space-y-6">
      <GreetingHeader
        name={firstName}
        context={<>Student portal{user?.academic_year && ` · AY ${user.academic_year}`}</>}
        subtitle={student?.program_name}
        chips={student && (
          <>
            <HeaderChip icon={<GraduationCap className="h-3.5 w-3.5" aria-hidden />}>
              Semester {roman(student.current_semester)}
              {student.division && ` · ${student.division.startsWith("Div") ? student.division : `Division ${student.division}`}`}
            </HeaderChip>
            <HeaderChip mono>{student.roll_number}</HeaderChip>
            <HeaderChip tone={backlogs === 0 ? "success" : "warning"}>
              {backlogs === 0 ? "No backlogs" : pluralise(backlogs, "backlog")}
            </HeaderChip>
          </>
        )}
        actions={
          <>
            {pendingCount > 0 && pending?.link && (
              <LinkButton to={pending.link} variant="accent" icon={<Sparkles className="h-4 w-4" aria-hidden />}>
                Elective actions
              </LinkButton>
            )}
            <LinkButton to="/profile" variant="secondary">View profile</LinkButton>
          </>
        }
      />

      {soonest ? (
        <FocusBanner
          tone="iris"
          icon={<Clock className="h-5 w-5" aria-hidden />}
          title={data.action_items.length === 1
            ? "One thing needs your attention"
            : `${data.action_items.length} things need your attention`}
          description={
            <>
              {data.action_items.length > 1 ? "Most urgent: " : ""}
              <span className="font-medium text-ink">{soonest.title}</span>
              {soonest.due_at && ` · ${deadlineLabel(soonest.due_at).text}`}
            </>
          }
          action={soonest.link && (
            <LinkButton to={soonest.link} variant="accent" iconRight={<ArrowRight className="h-4 w-4" aria-hidden />}>
              Take action
            </LinkButton>
          )}
        />
      ) : (
        <FocusBanner
          tone="success"
          icon={<CheckCircle2 className="h-5 w-5" aria-hidden />}
          title={semesterNumber ? `You're all set for Semester ${roman(semesterNumber)}` : "You're all set"}
          description="No choices, uploads or returned documents are waiting on you."
        />
      )}

      {/* Performance — every figure is the student's own record. */}
      <section aria-label="Academic summary" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Cumulative CPI"
          visual={
            <ScoreRing
              value={student?.cpi ?? 0} max={10} size={72} stroke={7} tone="iris"
              label={student?.cpi != null ? `CPI ${student.cpi.toFixed(2)} out of 10` : "CPI not yet published"}
            >
              <span className="font-heading text-sm font-semibold tabular-nums text-ink">
                {student?.cpi != null ? student.cpi.toFixed(2) : "—"}
              </span>
            </ScoreRing>
          }
          value={student?.cpi != null ? <>{student.cpi.toFixed(2)}<span className="ml-1 text-xs font-normal text-ink-subtle">/ 10</span></> : "—"}
          hint={student?.cpi != null
            ? (backlogs === 0 ? "No backlogs" : pluralise(backlogs, "backlog"))
            : "Published after your first semester results"}
        />
        <MetricCard
          label="Elective choices"
          visual={
            <ScoreRing
              value={settledChoices} max={choiceSlots.length} size={72} stroke={7}
              tone={choiceSlots.length > 0 && settledChoices === choiceSlots.length ? "success" : "accent"}
              label={choiceSlots.length > 0
                ? `${settledChoices} of ${choiceSlots.length} elective slots settled`
                : "No elective slot this semester"}
            >
              <span className="font-heading text-sm font-semibold tabular-nums text-ink">
                {choiceSlots.length > 0 ? `${settledChoices}/${choiceSlots.length}` : "—"}
              </span>
            </ScoreRing>
          }
          value={choiceSlots.length > 0 ? `${settledChoices} of ${choiceSlots.length} settled` : "None"}
          hint={!semester
            ? "Curriculum not on record"
            : choiceSlots.length === 0
              ? `No elective slot in Semester ${roman(semester.semester_number)}`
              : "Allotted, submitted or registered"}
        />
        <MetricCard
          label="Semester credits"
          visual={<IconBadge icon={Layers} className="bg-accent-soft text-accent" />}
          value={semester ? pluralise(semester.total_credits, "credit") : "—"}
          hint={semester
            ? `${pluralise(components.length, "requirement")} in Semester ${roman(semester.semester_number)}`
            : "Curriculum not on record"}
        />
        <MetricCard
          label="Elective actions"
          to={pendingCount > 0 ? pending?.link : null}
          visual={
            <IconBadge
              icon={BookOpen}
              className={pendingCount > 0 ? "bg-warning-soft text-warning" : "bg-surface-muted text-ink-subtle"}
            />
          }
          value={pendingCount > 0 ? `${pendingCount} pending` : choiceSlots.length === 0 ? "None" : "Up to date"}
          hint={pendingCount > 0 ? "Waiting on your choice" : "Nothing is waiting on you"}
          tone={pendingCount > 0 ? "warning" : "neutral"}
        />
      </section>

      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-12">
        <div className="min-w-0 space-y-6 xl:col-span-8">
          <Card>
            <CardHeader
              title="Needs your attention"
              description="Open choices and internship steps waiting on you."
              icon={<Clock className="h-4 w-4 text-warning" aria-hidden />}
            />
            {data.action_items.length === 0 ? (
              <EmptyState
                compact
                title="Nothing pending"
                description="You have no open elective windows or internship steps right now."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.action_items.map((item, index) => {
                  const deadline = deadlineLabel(item.due_at);
                  return (
                    <li key={`${item.title}-${index}`}>
                      <Link
                        to={item.link ?? "#"}
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-muted/60 focus-visible:bg-surface-muted/60"
                      >
                        <span className={cn(
                          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                          item.kind === "internship" ? "bg-accent-soft text-accent" : "bg-iris-soft text-iris",
                        )}>
                          {item.kind === "internship"
                            ? <Route className="h-4 w-4" aria-hidden />
                            : <BookOpen className="h-4 w-4" aria-hidden />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-ink">{item.title}</p>
                          <p className="truncate text-xs text-ink-subtle">{item.context}</p>
                        </div>
                        {item.due_at && (
                          <Badge tone={deadline.tone} className="hidden sm:inline-flex">
                            {deadline.text}
                          </Badge>
                        )}
                        <ArrowRight className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <RequirementsCard data={data} programName={student?.program_name ?? null} />

          {data.progress.length > 0 && (
            <section aria-labelledby="programmes-heading" className="space-y-3">
              <div>
                <h2 id="programmes-heading" className="font-heading text-md font-semibold text-ink">
                  Your programmes
                </h2>
                <p className="text-sm text-ink-muted">
                  Counted from the work you have actually submitted and had approved.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {data.progress.map((item) => <ProgrammeCard key={item.label} item={item} />)}
              </div>
            </section>
          )}

          {otherAllotments.length > 0 && (
            <Card>
              <CardHeader
                title="Other elective allotments"
                description="Seats from rounds outside this semester's requirements."
                icon={<CheckCircle2 className="h-4 w-4 text-success" aria-hidden />}
              />
              <TableWrap>
                <THead>
                  <TH>Course</TH>
                  <TH>Slot</TH>
                  <TH align="right">Credits</TH>
                  <TH>Section</TH>
                  <TH>Status</TH>
                </THead>
                <TBody>
                  {otherAllotments.map((alloc) => (
                    <TR key={alloc.id}>
                      <TD>
                        <span className="font-mono text-xs font-semibold text-ink">{alloc.course_code}</span>
                        <span className="block text-sm text-ink">{alloc.course_title}</span>
                      </TD>
                      <TD className="text-ink-muted">
                        {alloc.link
                          ? <Link to={alloc.link} className="hover:text-accent hover:underline">{alloc.component_title ?? alloc.component_code}</Link>
                          : alloc.component_title ?? alloc.component_code}
                      </TD>
                      <TD align="right" className="font-mono tabular-nums">{alloc.credits}</TD>
                      <TD>{alloc.section_name ?? "—"}</TD>
                      <TD>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusBadge status={alloc.status} />
                          {alloc.preference_order_granted && (
                            <span className="text-xs text-success">Preference #{alloc.preference_order_granted}</span>
                          )}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </TableWrap>
            </Card>
          )}
        </div>

        {/* Right rail */}
        <div className="min-w-0 space-y-6 xl:col-span-4">
          <ProfileCard data={data} />
          <ScheduleCard extra={deadlines} />

          <Card>
            <CardHeader
              title="Announcements"
              icon={<Megaphone className="h-4 w-4 text-violet" aria-hidden />}
              action={<CardAction to="/announcements" label="All announcements">View all</CardAction>}
            />
            {data.announcements.length === 0 ? (
              <EmptyState compact title="No announcements" />
            ) : (
              <ul className="divide-y divide-line">
                {data.announcements.map((item) => (
                  <li key={item.id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 text-sm font-medium leading-snug text-ink">{item.title}</p>
                      {item.priority !== "NORMAL" && <StatusBadge status={item.priority} />}
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{item.excerpt}</p>
                    <p className="mt-1 text-2xs text-ink-subtle">{formatDate(item.published_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── pieces ───────────────────────────────────────────────────────────────
function IconBadge({ icon: Icon, className }: { icon: LucideIcon; className: string }) {
  return (
    <span className={cn("flex h-[4.5rem] w-[4.5rem] shrink-0 items-center justify-center rounded-2xl", className)}>
      <Icon className="h-7 w-7" aria-hidden />
    </span>
  );
}

function MetricCard({
  label, visual, value, hint, to, tone = "neutral",
}: {
  label: string; visual: ReactNode; value: ReactNode; hint: ReactNode;
  to?: string | null; tone?: "neutral" | "warning";
}) {
  const body = (
    <>
      {visual}
      <div className="min-w-0">
        <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">{label}</p>
        <p className="mt-1 font-heading text-lg font-semibold leading-tight tabular-nums text-ink">{value}</p>
        <p className={cn("mt-0.5 text-xs", tone === "warning" ? "font-medium text-warning" : "text-ink-subtle")}>
          {hint}
        </p>
      </div>
    </>
  );
  const classes = cn(
    "flex h-full items-center gap-4 rounded-xl border bg-surface p-4 shadow-sm",
    tone === "warning" ? "border-warning/30" : "border-line",
    to && "cursor-pointer transition-all duration-200 hover:-translate-y-px hover:border-line-strong hover:shadow-card-hover",
  );
  return to ? <Link to={to} className={classes}>{body}</Link> : <div className={classes}>{body}</div>;
}

function RequirementsCard({ data, programName }: { data: Data; programName: string | null }) {
  const semester = data.curriculum_semester;
  const components = semester?.components ?? [];
  return (
    <Card>
      <CardHeader
        title={semester ? `Semester ${roman(semester.semester_number)} requirements` : "This semester"}
        description={programName}
        icon={<BookOpen className="h-4 w-4 text-iris" aria-hidden />}
        action={<CardAction to="/academics/curriculum" label="View the full curriculum">Full curriculum</CardAction>}
      />
      {!semester ? (
        <EmptyState
          compact
          title="No curriculum on record for this semester"
          description="Your department has not published the structure for your batch yet."
        />
      ) : (
        <TableWrap>
          <THead>
            <TH>Code</TH>
            <TH>Requirement</TH>
            <TH align="right">Credits</TH>
            <TH>Allotment</TH>
            <TH>Status</TH>
            {/* `relative` keeps the absolutely placed label inside the table's
                scroller; otherwise it widens the page on a phone. */}
            <TH className="relative"><span className="sr-only">Action</span></TH>
          </THead>
          <TBody>
            {components.map((component) => {
              const waiting = waitsOnStudent(component);
              const link = componentLink(component);
              return (
                <TR key={component.id} className={cn(waiting && "bg-warning-soft/40")}>
                  <TD className={cn("whitespace-nowrap font-mono text-xs font-semibold", waiting ? "text-warning" : "text-ink-muted")}>
                    {component.code}
                  </TD>
                  <TD>
                    <span className="block font-medium text-ink">{component.title}</span>
                    <span className="block text-xs text-ink-subtle">
                      {TYPE_LABELS[component.component_type] ?? component.component_type}
                      {component.scope_label && ` · ${component.scope_label}`}
                    </span>
                  </TD>
                  <TD align="right" className="font-mono tabular-nums">{component.credits}</TD>
                  <TD>
                    {component.allocated_course_code ? (
                      <span className="block min-w-0">
                        <span className="font-mono text-xs font-semibold text-success">{component.allocated_course_code}</span>
                        <span className="block truncate text-xs text-ink-muted" title={component.allocated_course_title ?? undefined}>
                          {component.allocated_course_title}
                          {component.allocated_section && ` · ${component.allocated_section}`}
                        </span>
                        {component.preference_order_granted && (
                          <span className="block text-2xs text-success">Preference #{component.preference_order_granted}</span>
                        )}
                      </span>
                    ) : <span className="text-ink-subtle">—</span>}
                  </TD>
                  <TD><StatusBadge status={component.status} /></TD>
                  <TD align="right">
                    {link && (waiting ? (
                      <LinkButton to={link} size="sm" variant="accent">
                        {component.component_type === "MOOC" ? "Register" : "Choose now"}
                      </LinkButton>
                    ) : (
                      <Link to={link} className="text-xs font-semibold text-accent hover:underline">Open</Link>
                    ))}
                  </TD>
                </TR>
              );
            })}
          </TBody>
          <tfoot>
            <tr className="border-t border-line bg-surface-muted/40">
              <td colSpan={2} className="px-4 py-2.5 text-xs font-semibold text-ink-muted">
                Total · {pluralise(components.length, "requirement")}
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-sm font-semibold tabular-nums text-ink">
                {semester.total_credits}
              </td>
              <td colSpan={3} />
            </tr>
          </tfoot>
        </TableWrap>
      )}
    </Card>
  );
}

function ProgrammeCard({ item }: { item: ProgressItem }) {
  const meta = (item.kind && PROGRAMME_META[item.kind]) || FALLBACK_PROGRAMME;
  const Icon = meta.icon;
  const done = item.total > 0 && item.completed >= item.total;
  const percent = item.total > 0 ? Math.min(100, Math.round((item.completed / item.total) * 100)) : 0;
  const unit = item.unit === "credits" ? "credits" : "stages";

  return (
    <Link
      to={item.link ?? "#"}
      className="group flex h-full min-w-0 flex-col rounded-xl border border-line bg-surface p-4 shadow-sm transition-all duration-200 hover:-translate-y-px hover:border-line-strong hover:shadow-card-hover"
    >
      <div className="flex items-start gap-3">
        <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg", meta.chip)}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">{meta.label}</p>
          <h3 className="text-sm font-semibold leading-snug text-ink break-anywhere">{item.label}</h3>
        </div>
        {item.status && <StatusBadge status={item.status} className="shrink-0" />}
      </div>

      <div className="mt-4 flex items-center gap-4">
        <ScoreRing
          value={item.completed} max={item.total || 1} size={60} stroke={6}
          tone={done ? "success" : "accent"}
          label={`${item.completed} of ${item.total} ${unit} complete`}
        >
          <span className="text-xs font-semibold tabular-nums text-ink">{percent}%</span>
        </ScoreRing>
        <dl className="min-w-0 space-y-1 text-xs">
          <div className="flex gap-1.5">
            <dt className="text-ink-subtle">{unit === "credits" ? "Credits earned" : "Stages complete"}</dt>
            <dd className="font-semibold tabular-nums text-ink">{item.completed} / {item.total}</dd>
          </div>
          {item.stage && (
            <div className="flex min-w-0 gap-1.5">
              <dt className="shrink-0 text-ink-subtle">Current stage</dt>
              <dd className="truncate font-medium text-ink" title={item.stage}>{item.stage}</dd>
            </div>
          )}
        </dl>
      </div>

      <span className="mt-auto inline-flex items-center gap-1 pt-4 text-xs font-semibold text-accent">
        Open <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
      </span>
    </Link>
  );
}

function ProfileCard({ data }: { data: Data }) {
  const { user } = useAuth();
  const student = user?.student;
  const details: [string, ReactNode][] = student ? [
    ["Roll number", <span key="r" className="font-mono">{student.roll_number}</span>],
    ["Semester", roman(student.current_semester)],
    ["Division", student.division ?? "—"],
    ["Batch", student.batch ?? student.admission_year],
    ["Department", student.department_code ?? "—"],
    ["CPI", student.cpi != null ? student.cpi.toFixed(2) : "—"],
  ] : [];

  return (
    <Card>
      <CardBody className="flex items-center gap-4">
        <Avatar name={user?.full_name} src={user?.avatar_url} size="lg" className="h-14 w-14 text-base" />
        <div className="min-w-0">
          <p className="font-heading text-base font-semibold leading-snug text-ink break-anywhere">{user?.full_name}</p>
          {student?.program_name && <p className="text-xs text-ink-muted">{student.program_name}</p>}
        </div>
      </CardBody>

      {details.length > 0 && (
        <dl className="grid grid-cols-2 gap-px border-y border-line bg-line sm:grid-cols-3 xl:grid-cols-2">
          {details.map(([label, value]) => (
            <div key={label} className="min-w-0 bg-surface px-4 py-2.5">
              <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">{label}</dt>
              <dd className="mt-0.5 truncate text-sm font-medium text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="p-5">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-subtle">
          <UserCheck className="h-3.5 w-3.5 text-accent" aria-hidden /> Faculty mentor
        </p>
        {!data.mentor ? (
          <p className="mt-2 text-sm text-ink-muted">
            No mentor assigned yet. The department assigns one at the start of each academic year.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="flex items-start gap-3">
              <Avatar name={data.mentor.name} src={data.mentor.avatar_url} size="md" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">{data.mentor.name}</p>
                <p className="text-xs text-ink-muted">{data.mentor.designation}</p>
                {data.mentor.department && <p className="text-xs text-ink-subtle">{data.mentor.department}</p>}
              </div>
            </div>
            {(data.mentor.cabin || data.mentor.email || data.mentor.phone) && (
              <ul className="space-y-1.5 text-xs text-ink-muted">
                {data.mentor.cabin && (
                  <li className="flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                    Cabin {data.mentor.cabin}
                  </li>
                )}
                {data.mentor.email && (
                  <li className="flex min-w-0 items-center gap-2">
                    <Mail className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                    <a href={`mailto:${data.mentor.email}`} className="truncate hover:text-accent">{data.mentor.email}</a>
                  </li>
                )}
                {data.mentor.phone && (
                  <li className="flex items-center gap-2">
                    <Phone className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden />
                    {data.mentor.phone}
                  </li>
                )}
              </ul>
            )}
            <LinkButton to="/mentorship" variant="secondary" size="sm" className="w-full">
              Request a meeting
            </LinkButton>
          </div>
        )}
      </div>
    </Card>
  );
}
