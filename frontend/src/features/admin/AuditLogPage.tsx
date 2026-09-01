import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardFooter, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, TableEmpty, TableWrap } from "@/components/ui/Table";
import { api, qs } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { humanise } from "@/lib/utils";
import type { AuditLogRow, Page } from "@/types";

const ACTIONS = [
  "CREATE", "UPDATE", "DELETE", "LOGIN", "ALLOCATION_RUN", "ALLOCATION_OVERRIDE",
  "MENTOR_ASSIGN", "MENTOR_OVERRIDE", "EVALUATION_SUBMIT", "EVALUATION_UPDATE",
  "STATUS_CHANGE", "PUBLISH", "UPLOAD",
];

const HIGH_SIGNAL = new Set([
  "ALLOCATION_RUN", "ALLOCATION_OVERRIDE", "MENTOR_OVERRIDE",
  "EVALUATION_SUBMIT", "EVALUATION_UPDATE", "DELETE",
]);

export function AuditLogPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit-logs", action, entityType, page],
    queryFn: () =>
      api.get<Page<AuditLogRow>>(
        `/admin/audit-logs${qs({
          action: action || undefined, entity_type: entityType || undefined,
          page, page_size: pageSize,
        })}`,
      ),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const entityTypes = Array.from(
    new Set((data?.items ?? []).map((row) => row.entity_type)),
  ).sort();

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="Append-only record of administrative actions — allocations, mentor changes, evaluations and publishing."
        breadcrumbs={[{ label: "Administration" }, { label: "Audit Log" }]}
      />

      <Card>
        <CardHeader
          title={`${data?.total ?? 0} entr${data?.total === 1 ? "y" : "ies"}`}
          icon={<ScrollText className="h-4 w-4 text-ink-subtle" aria-hidden />}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}
                      aria-label="Filter by action" className="w-full sm:w-52">
                <option value="">All actions</option>
                {ACTIONS.map((value) => (
                  <option key={value} value={value}>{humanise(value)}</option>
                ))}
              </Select>
              <Select value={entityType}
                      onChange={(e) => { setEntityType(e.target.value); setPage(1); }}
                      aria-label="Filter by entity" className="w-full sm:w-52">
                <option value="">All entities</option>
                {entityTypes.map((value) => (
                  <option key={value} value={value}>{humanise(value)}</option>
                ))}
              </Select>
            </div>
          }
        />

        {isLoading ? (
          <LoadingState rows={6} />
        ) : error ? (
          <ErrorState onRetry={() => refetch()} compact />
        ) : !data?.items.length ? (
          <EmptyState
            title="No audit entries"
            description="Administrative actions are recorded here as they happen."
            icon={<ScrollText className="h-5 w-5" aria-hidden />}
          />
        ) : (
          <>
            <TableWrap>
              <THead>
                <TH width="17%">Action</TH>
                <TH width="16%">Entity</TH>
                <TH>Description</TH>
                <TH width="18%">Actor</TH>
                <TH width="15%" align="right">When</TH>
              </THead>
              <TBody>
                {data.items.length === 0 ? (
                  <TableEmpty colSpan={5}>No entries match these filters.</TableEmpty>
                ) : (
                  data.items.map((row) => (
                    <TR key={row.id}>
                      <TD>
                        <Badge tone={HIGH_SIGNAL.has(row.action) ? "warning" : "neutral"}>
                          {humanise(row.action)}
                        </Badge>
                      </TD>
                      <TD className="text-ink-muted">
                        {humanise(row.entity_type)}
                        {row.entity_id !== null && (
                          <span className="tabular ml-1 text-ink-subtle">#{row.entity_id}</span>
                        )}
                      </TD>
                      <TD className="text-ink-muted">
                        {row.description ?? "—"}
                        {Object.keys(row.meta ?? {}).length > 0 && (
                          <details className="mt-1">
                            <summary className="cursor-pointer text-2xs text-accent hover:underline">
                              Metadata
                            </summary>
                            <pre className="mt-1 overflow-x-auto rounded bg-surface-muted p-2 text-2xs text-ink-muted">
                              {JSON.stringify(row.meta, null, 2)}
                            </pre>
                          </details>
                        )}
                      </TD>
                      <TD className="truncate text-xs text-ink-subtle">
                        {row.actor_label?.split(" <")[0] ?? "system"}
                        {row.ip_address && (
                          <span className="block text-2xs">{row.ip_address}</span>
                        )}
                      </TD>
                      <TD align="right" className="whitespace-nowrap text-xs text-ink-subtle">
                        {formatDateTime(row.created_at)}
                      </TD>
                    </TR>
                  ))
                )}
              </TBody>
            </TableWrap>

            {totalPages > 1 && (
              <CardFooter className="flex items-center justify-between">
                <p className="text-xs text-ink-muted">Page {page} of {totalPages}</p>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" disabled={page <= 1}
                          onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button variant="secondary" size="sm" disabled={page >= totalPages}
                          onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </CardFooter>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
