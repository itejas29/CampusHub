import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Misc";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { roman } from "@/lib/utils";
import type { MenteeRow } from "@/types";

/**
 * The mentee roster, shared by the Mentor–Mentee overview and the dedicated
 * mentees screen so both render one list instead of two copies that drift.
 * Presentational only — the caller owns fetching and filtering.
 */
export function MenteeTable({
  rows, search,
}: { rows: MenteeRow[]; search?: string }) {
  return (
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
          <TableEmpty colSpan={8}>
            {search ? `No mentees match “${search}”.` : "No mentees to show."}
          </TableEmpty>
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
  );
}
