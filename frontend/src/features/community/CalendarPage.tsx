import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays, ChevronLeft, ChevronRight, Clock, MapPin,
} from "lucide-react";
import {
  addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isSameDay,
  isSameMonth, isToday, parseISO, startOfMonth, startOfWeek, subMonths,
} from "date-fns";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Misc";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { api, qs } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CalendarItem } from "@/types";

const KIND_TONE = {
  event: "accent", deadline: "warning", meeting: "info", academic: "brand",
} as const;

export function CalendarPage() {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [selected, setSelected] = useState<Date>(new Date());

  const range = useMemo(() => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    return { start, end };
  }, [month]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["calendar", range.start.toISOString(), range.end.toISOString()],
    queryFn: () =>
      api.get<CalendarItem[]>(
        `/calendar${qs({ start: range.start.toISOString(), end: range.end.toISOString() })}`,
      ),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarItem[]>();
    for (const item of data ?? []) {
      const key = format(parseISO(item.start_at), "yyyy-MM-dd");
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return map;
  }, [data]);

  const days = useMemo(
    () => eachDayOfInterval({ start: range.start, end: range.end }),
    [range],
  );

  const selectedItems = byDay.get(format(selected, "yyyy-MM-dd")) ?? [];
  const upcoming = (data ?? [])
    .filter((item) => parseISO(item.start_at) >= new Date())
    .slice(0, 8);

  return (
    <div>
      <PageHeader
        title="Calendar"
        description="Events, registration deadlines and mentor meetings in one view."
        breadcrumbs={[{ label: "Campus" }, { label: "Calendar" }]}
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title={format(month, "MMMM yyyy")}
            icon={<CalendarDays className="h-4 w-4 text-ink-subtle" aria-hidden />}
            action={
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" aria-label="Previous month"
                        onClick={() => setMonth((m) => subMonths(m, 1))}>
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                </Button>
                <Button variant="secondary" size="sm"
                        onClick={() => { setMonth(startOfMonth(new Date())); setSelected(new Date()); }}>
                  Today
                </Button>
                <Button variant="ghost" size="icon" aria-label="Next month"
                        onClick={() => setMonth((m) => addMonths(m, 1))}>
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            }
          />
          <CardBody>
            {isLoading ? (
              <LoadingState rows={3} />
            ) : error ? (
              <ErrorState onRetry={() => refetch()} compact />
            ) : (
              <>
                <div className="grid grid-cols-7 gap-px text-center">
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label) => (
                    <div key={label}
                         className="pb-2 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                      {label}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-px overflow-hidden rounded border border-line bg-line">
                  {days.map((day) => {
                    const key = format(day, "yyyy-MM-dd");
                    const items = byDay.get(key) ?? [];
                    const outside = !isSameMonth(day, month);
                    const isSelected = isSameDay(day, selected);
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setSelected(day)}
                        aria-label={`${format(day, "d MMMM yyyy")}, ${items.length} items`}
                        aria-pressed={isSelected}
                        className={cn(
                          "flex min-h-[4.25rem] cursor-pointer flex-col items-start gap-1 bg-surface p-1.5 text-left transition-colors hover:bg-surface-muted",
                          outside && "bg-surface-muted/40 text-ink-subtle",
                          isSelected && "ring-2 ring-inset ring-accent",
                        )}
                      >
                        <span className={cn(
                          "flex h-5 w-5 items-center justify-center rounded-full text-xs tabular-nums",
                          isToday(day) ? "bg-brand font-semibold text-brand-fg"
                            : outside ? "text-ink-subtle" : "text-ink",
                        )}>
                          {format(day, "d")}
                        </span>
                        <span className="flex w-full flex-col gap-0.5">
                          {items.slice(0, 2).map((item) => (
                            <span
                              key={item.id}
                              className={cn(
                                "truncate rounded px-1 py-0.5 text-2xs",
                                item.kind === "deadline" ? "bg-warning-soft text-warning"
                                  : item.kind === "meeting" ? "bg-info-soft text-info"
                                  : "bg-accent-soft text-accent",
                              )}
                            >
                              {item.title}
                            </span>
                          ))}
                          {items.length > 2 && (
                            <span className="px-1 text-2xs text-ink-subtle">
                              +{items.length - 2} more
                            </span>
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader title={format(selected, "d MMMM yyyy")}
                        description={`${selectedItems.length} item${selectedItems.length === 1 ? "" : "s"}`} />
            {selectedItems.length === 0 ? (
              <EmptyState compact title="Nothing scheduled" />
            ) : (
              <ul className="divide-y divide-line">
                {selectedItems.map((item) => (
                  <li key={item.id} className="px-5 py-3">
                    <ItemRow item={item} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="Coming up" />
            {upcoming.length === 0 ? (
              <EmptyState compact title="Nothing upcoming" />
            ) : (
              <ul className="divide-y divide-line">
                {upcoming.map((item) => (
                  <li key={item.id} className="px-5 py-3">
                    <ItemRow item={item} showDate />
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

function ItemRow({ item, showDate }: { item: CalendarItem; showDate?: boolean }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm font-medium leading-snug text-ink">{item.title}</p>
        <Badge tone={KIND_TONE[item.kind as keyof typeof KIND_TONE] ?? "neutral"}>
          {item.kind}
        </Badge>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-subtle">
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3" aria-hidden />
          {showDate
            ? format(parseISO(item.start_at), "d MMM, HH:mm")
            : formatTime(item.start_at)}
        </span>
        {item.location && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" aria-hidden />{item.location}
          </span>
        )}
        {item.status && <span>{item.status}</span>}
      </div>
    </>
  );
  return item.link ? (
    <Link to={item.link} className="block rounded transition-colors hover:opacity-80">
      {body}
    </Link>
  ) : (
    <div>{body}</div>
  );
}
