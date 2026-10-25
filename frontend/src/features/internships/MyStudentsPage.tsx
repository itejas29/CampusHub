import { useQuery } from "@tanstack/react-query";
import { UserCheck, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { ProgressBar } from "@/components/ui/Stepper";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import { roman } from "@/lib/utils";
import type { EnrollmentSummary, InternshipProgram, Page } from "@/types";
import { StudentDetailDrawer } from "./StudentDetailDrawer";

interface Props {
  /** "mine" = only students I mentor; "all" = every student I coordinate. */
  scope?: "mine" | "all";
  /** Narrow to one internship type, giving CSSI and SI their own screens. */
  /** One programme type, or several shown together (the project programmes). */
  programType?: string | string[];
  title?: string;
  description?: string;
}

const PAGE_SIZE = 50;

export function MyStudentsPage({ scope = "mine", programType, title, description }: Props) {
  const [programId, setProgramId] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [search, setSearch] = useState("");
  // The list comes a page at a time; search and filters run on the server, so
  // a cohort of any size costs one page (QA-16).
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => { setPage(1); }, [query, programId, status, scope]);
  // The open record lives in the URL (?record=), so a review link from the
  // dashboard or a notification lands on that student's drawer, and Back closes it.
  const [searchParams, setSearchParams] = useSearchParams();
  const openId = Number(searchParams.get("record")) || null;
  const setOpenId = (id: number | null) =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id) next.set("record", String(id));
      else next.delete("record");
      return next;
    });

  const programs = useQuery({
    queryKey: ["internship-programs"],
    queryFn: () => api.get<InternshipProgram[]>("/internships/programs"),
  });

  // When a screen is typed (CSSI / SI) the programme filter is limited to that
  // type, so the dropdown never offers a programme the screen would hide.
  const typedPrograms = useMemo(
    () => (programs.data ?? []).filter((p) => !programType
      || (Array.isArray(programType) ? programType.includes(p.type) : p.type === programType)),
    [programs.data, programType],
  );

  const types = programType ? (Array.isArray(programType) ? programType : [programType]) : [];
  const enrollments = useQuery({
    queryKey: ["internship-enrollments", "page", scope, types.join(","), programId, status,
      query, page],
    queryFn: () =>
      api.get<Page<EnrollmentSummary>>(
        `/internships/enrollments/page${qs({
          mine: scope === "mine" ? true : undefined,
          program_id: programId || undefined,
          status: status || undefined,
          program_types: types.length ? types.join(",") : undefined,
          q: query || undefined,
          page,
          page_size: PAGE_SIZE,
        })}`,
      ),
    placeholderData: (previous) => previous,
  });

  const rows = enrollments.data?.items ?? [];
  const total = enrollments.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const last = Math.min(page * PAGE_SIZE, total);

  const isCoordinatorView = scope === "all";

  return (
    <div>
      <PageHeader
        title={title ?? (isCoordinatorView ? "Internship students" : "My students")}
        description={
          description ??
          (isCoordinatorView
            ? "Every student across the internship programmes you coordinate."
            : "Students assigned to you as faculty mentor. Open a student to review submissions and record evaluation.")
        }
        breadcrumbs={[
          { label: "Internships", to: "/internships" },
          { label: title ?? (isCoordinatorView ? "Students" : "My students") },
        ]}
        actions={
          isCoordinatorView ? (
            <Link
              to="/internships/mentor-assignment"
              className="inline-flex h-9 items-center gap-1.5 rounded bg-primary px-3 text-xs font-semibold text-white shadow-xs transition-colors hover:bg-primary-hover"
            >
              <UserCheck className="h-3.5 w-3.5" />
              Assign Mentors (Max 10 / mentor)
            </Link>
          ) : undefined
        }
      />

      <Card>
        <CardHeader
          title={`${total} student${total === 1 ? "" : "s"}`}
          icon={<Users className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder="Name, roll number or organisation"
                className="w-full sm:w-64"
              />
              <Select
                value={programId}
                onChange={(e) => setProgramId(e.target.value)}
                aria-label="Filter by programme"
                className="w-full sm:w-40"
              >
                <option value="">All programmes</option>
                {typedPrograms.map((program) => (
                  <option key={program.id} value={program.id}>{program.code}</option>
                ))}
              </Select>
              <Select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                aria-label="Filter by status"
                className="w-full sm:w-44"
              >
                <option value="">All statuses</option>
                {["REGISTERED", "MENTOR_ASSIGNED", "IN_PROGRESS", "SUBMITTED",
                  "UNDER_EVALUATION", "COMPLETED"].map((value) => (
                  <option key={value} value={value}>
                    {value.replace(/_/g, " ").toLowerCase()}
                  </option>
                ))}
              </Select>
            </div>
          }
        />

        {enrollments.isLoading ? (
          <LoadingState rows={4} />
        ) : enrollments.error ? (
          <ErrorState onRetry={() => enrollments.refetch()} compact />
        ) : (
          <TableWrap>
            <THead>
              <TH width="20%">Student</TH>
              <TH width="10%">Roll no.</TH>
              <TH width="6%">Sem</TH>
              <TH>Organisation</TH>
              <TH width="9%">Group</TH>
              <TH width="14%">Progress</TH>
              <TH width="11%">Status</TH>
              <TH width="16%">Faculty Mentor</TH>
            </THead>
            <TBody>
              {rows.length === 0 ? (
                <TableEmpty colSpan={8}>
                  {search || programId || status
                    ? "No students match these filters."
                    : isCoordinatorView
                      ? "No students are enrolled in the programmes you coordinate."
                      : "No students are assigned to you as mentor yet."}
                </TableEmpty>
              ) : (
                rows.map((row) => (
                  <TR key={row.id} onClick={() => setOpenId(row.id)}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={row.student_name} src={row.avatar_url} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{row.student_name}</p>
                          <p className="truncate text-2xs text-ink-subtle">
                            {row.department_code}
                            {row.division && ` · ${/^div/i.test(row.division) ? "" : "Div "}${row.division}`}

                          </p>
                        </div>
                      </div>
                    </TD>
                    <TD className="tabular font-mono text-xs">{row.roll_number}</TD>
                    <TD>{roman(row.semester)}</TD>
                    <TD className="text-ink-muted">
                      {row.organization_name ?? (
                        <span className="text-ink-subtle">Not set</span>
                      )}
                    </TD>
                    <TD>
                      {row.group_name ? (
                        <Badge tone="neutral">{row.group_name}</Badge>
                      ) : (
                        <span className="text-ink-subtle">—</span>
                      )}
                    </TD>
                    <TD>
                      <ProgressBar
                        value={row.progress_percent}
                        tone={row.progress_percent === 100 ? "success" : "accent"}
                        label={row.current_stage ?? undefined}
                        showValue={false}
                      />
                    </TD>
                    <TD><StatusBadge status={row.status} /></TD>
                    <TD>
                      {row.mentor_name ? (
                        <Badge tone="brand">{row.mentor_name}</Badge>
                      ) : (
                        <Badge tone="warning">Unassigned</Badge>
                      )}
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
            <span className="text-ink-muted">Showing {first}–{last} of {total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1}
                      onClick={() => setPage((n) => Math.max(1, n - 1))}>Previous</Button>
              <span className="self-center text-ink-muted">Page {page} of {pages}</span>
              <Button size="sm" variant="secondary" disabled={page >= pages}
                      onClick={() => setPage((n) => Math.min(pages, n + 1))}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      {openId !== null && (
        <StudentDetailDrawer
          enrollmentId={openId}
          onClose={() => setOpenId(null)}
          canOverrideMentor={isCoordinatorView}
        />
      )}
    </div>
  );
}
