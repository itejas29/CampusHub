import { useQuery } from "@tanstack/react-query";
import { Users2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { PageHeader, SearchInput } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { MenteeTable } from "@/features/engagement/MenteeTable";
import { api } from "@/lib/api";
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
          <MenteeTable rows={rows} search={search} />
        )}
      </Card>
    </div>
  );
}
