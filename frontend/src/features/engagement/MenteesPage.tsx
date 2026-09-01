import { useQuery } from "@tanstack/react-query";
import { Users2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { Avatar, PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api } from "@/lib/api";
import { roman } from "@/lib/utils";
import type { MenteeRow } from "@/types";

export function MenteesPage() {
  const [search, setSearch] = useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["my-mentees"],
    queryFn: () => api.get<MenteeRow[]>("/mentorship/my-mentees"),
  });

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return data ?? [];
    return (data ?? []).filter((row) =>
      `${row.full_name} ${row.roll_number}`.toLowerCase().includes(needle),
    );
  }, [data, search]);

  return (
    <div>
      <PageHeader
        title="My mentees"
        description="Students assigned to you for academic mentorship this academic year."
        breadcrumbs={[
          { label: "Support" },
          { label: "Mentor–Mentee", to: "/mentorship" },
          { label: "Mentees" },
        ]}
      />

      <Card>
        <CardHeader
          title={`${rows.length} mentee${rows.length === 1 ? "" : "s"}`}
          icon={<Users2 className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <SearchInput value={search} onChange={setSearch}
                         placeholder="Name or roll number" className="w-full sm:w-64" />
          }
        />
        {isLoading ? (
          <LoadingState rows={4} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.length ? (
          <EmptyState
            title="No mentees assigned"
            description="The department administrator assigns mentees each academic year."
            icon={<Users2 className="h-5 w-5" aria-hidden />}
          />
        ) : (
          <TableWrap>
            <THead>
              <TH width="26%">Student</TH>
              <TH width="12%">Roll no.</TH>
              <TH width="8%">Sem</TH>
              <TH width="8%">Div</TH>
              <TH width="10%" align="right">CPI</TH>
              <TH width="10%" align="right">Backlogs</TH>
              <TH>Contact</TH>
              <TH width="12%" align="right">Open requests</TH>
            </THead>
            <TBody>
              {rows.length === 0 ? (
                <TableEmpty colSpan={8}>No mentees match “{search}”.</TableEmpty>
              ) : (
                rows.map((row) => (
                  <TR key={row.student_id}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={row.full_name} src={row.avatar_url} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{row.full_name}</p>
                          <p className="truncate text-2xs text-ink-subtle">{row.program_name}</p>
                        </div>
                      </div>
                    </TD>
                    <TD className="tabular">{row.roll_number}</TD>
                    <TD>{roman(row.semester)}</TD>
                    <TD>{row.division ?? "—"}</TD>
                    <TD align="right" className="tabular font-medium">
                      {row.cpi?.toFixed(2) ?? "—"}
                    </TD>
                    <TD align="right">
                      {row.backlog_count > 0 ? (
                        <Badge tone="warning">{row.backlog_count}</Badge>
                      ) : (
                        <span className="text-ink-subtle">0</span>
                      )}
                    </TD>
                    <TD className="truncate text-xs text-ink-muted">
                      <a href={`mailto:${row.email}`} className="hover:text-accent">{row.email}</a>
                      {row.phone && <span className="block text-ink-subtle">{row.phone}</span>}
                    </TD>
                    <TD align="right">
                      {row.open_meetings > 0 ? (
                        <Badge tone="info">{row.open_meetings}</Badge>
                      ) : (
                        <span className="text-ink-subtle">—</span>
                      )}
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </TableWrap>
        )}
      </Card>
    </div>
  );
}
