import { useQuery } from "@tanstack/react-query";
import {
  addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isAfter,
  isSameDay, isSameMonth, isToday, parseISO, startOfDay, startOfMonth, startOfWeek, subMonths,
} from "date-fns";
import { CalendarDays, ChevronLeft, ChevronRight, Clock, MapPin } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardAction, CardHeader } from "@/components/ui/Card";
import { api, qs } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CalendarItem } from "@/types";

const KIND_DOT: Record<string, string> = {
  event: "bg-accent", deadline: "bg-warning-solid", meeting: "bg-iris", academic: "bg-brand",
};
const KIND_LABEL: Record<string, string> = {
  event: "Event", deadline: "Deadline", meeting: "Meeting", academic: "Academic",
};
const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const dayKey = (date: Date) => format(date, "yyyy-MM-dd");

/**
 * A month at a glance and what comes next, from the same `/calendar` feed as
 * the Calendar page. `extra` adds dated items the feed does not carry — the
 * dashboard's own deadlines (registration rounds, NPTEL choices) — once each.
 */
export function ScheduleCard({ extra = [] }: { extra?: CalendarItem[] }) {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [selected, setSelected] = useState<Date | null>(null);

  const range = useMemo(() => {
    const gridStart = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const gridEnd = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    // Far enough ahead that "Coming up" is not cut short by the month's end.
    const horizon = addDays(startOfDay(new Date()), 60);
    return { gridStart, gridEnd, end: isAfter(horizon, gridEnd) ? horizon : gridEnd };
  }, [month]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["calendar", "dashboard", range.gridStart.toISOString(), range.end.toISOString()],
    queryFn: () => api.get<CalendarItem[]>(
      `/calendar${qs({ start: range.gridStart.toISOString(), end: range.end.toISOString() })}`,
    ),
  });

  const items = useMemo(() => {
    const feed = data ?? [];
    const seen = new Set(feed.map((i) => `${i.link}|${i.start_at.slice(0, 10)}`));
    return [...feed, ...extra.filter((i) => !seen.has(`${i.link}|${i.start_at.slice(0, 10)}`))]
      .sort((a, b) => a.start_at.localeCompare(b.start_at));
  }, [data, extra]);

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarItem[]>();
    for (const item of items) {
      const key = dayKey(parseISO(item.start_at));
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return map;
  }, [items]);

  const days = useMemo(
    () => eachDayOfInterval({ start: range.gridStart, end: range.gridEnd }),
    [range],
  );

  const now = new Date();
  const listed = selected
    ? byDay.get(dayKey(selected)) ?? []
    : items.filter((i) => parseISO(i.end_at ?? i.start_at) >= now).slice(0, 5);

  return (
    <Card>
      <CardHeader
        title="Schedule"
        icon={<CalendarDays className="h-4 w-4 text-iris" aria-hidden />}
        action={<CardAction to="/calendar" label="Open the full calendar">Full calendar</CardAction>}
      />

      <div className="px-4 pt-4 sm:px-5">
        <div className="mb-2 flex items-center justify-between">
          <p className="font-heading text-sm font-semibold text-ink">{format(month, "MMMM yyyy")}</p>
          <div className="flex items-center gap-1">
            <button
              type="button" onClick={() => { setMonth((m) => subMonths(m, 1)); setSelected(null); }}
              aria-label="Previous month"
              className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button" onClick={() => { setMonth((m) => addMonths(m, 1)); setSelected(null); }}
              aria-label="Next month"
              className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <ChevronRight className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-7 text-center" role="group" aria-label={format(month, "MMMM yyyy")}>
          {WEEKDAYS.map((d) => (
            <span key={d} aria-hidden className="pb-1 text-2xs font-semibold text-ink-subtle">{d}</span>
          ))}
          {days.map((day) => {
            const dayItems = byDay.get(dayKey(day)) ?? [];
            const kinds = [...new Set(dayItems.map((i) => i.kind))].slice(0, 3);
            const isSelected = selected !== null && isSameDay(day, selected);
            const inMonth = isSameMonth(day, month);
            return (
              <button
                key={dayKey(day)} type="button"
                aria-pressed={isSelected}
                aria-label={`${format(day, "d MMMM")}${dayItems.length ? `, ${dayItems.length} scheduled` : ""}`}
                onClick={() => setSelected(isSelected ? null : day)}
                className={cn(
                  "relative mx-auto flex h-9 w-9 cursor-pointer flex-col items-center justify-center rounded-lg text-xs tabular-nums transition-colors",
                  // Out-of-month days are told apart by the grey token, not by
                  // fading it: an alpha made them 2.3:1, unreadable.
                  isSelected
                    ? "bg-accent font-semibold text-accent-fg"
                    : isToday(day)
                      ? "font-semibold text-accent ring-1 ring-inset ring-accent/40"
                      : inMonth ? "text-ink hover:bg-surface-muted" : "text-ink-subtle hover:bg-surface-muted",
                )}
              >
                {format(day, "d")}
                {kinds.length > 0 && (
                  <span aria-hidden className="absolute bottom-1 flex gap-0.5">
                    {kinds.map((k) => (
                      <span key={k} className={cn("h-1 w-1 rounded-full", isSelected ? "bg-white" : KIND_DOT[k] ?? "bg-ink-subtle")} />
                    ))}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3 border-t border-line px-4 py-4 sm:px-5">
        <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
          {selected ? format(selected, "EEEE, d MMMM") : "Coming up"}
        </p>
        {isLoading ? (
          <div className="mt-3 space-y-2" aria-busy="true" aria-label="Loading schedule">
            {[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded-md bg-surface-muted" />)}
          </div>
        ) : error ? (
          <p className="mt-3 text-sm text-ink-muted">
            The schedule could not be loaded.{" "}
            <button type="button" onClick={() => refetch()} className="cursor-pointer font-semibold text-accent hover:underline">
              Try again
            </button>
          </p>
        ) : listed.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            {selected ? "Nothing scheduled on this day." : "Nothing scheduled in the next few weeks."}
          </p>
        ) : (
          <ol className="relative mt-3 space-y-3 border-l border-line pl-4">
            {listed.map((item) => {
              const start = parseISO(item.start_at);
              const body = (
                <>
                  <span
                    aria-hidden
                    className={cn("absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full ring-2 ring-surface", KIND_DOT[item.kind] ?? "bg-ink-subtle")}
                  />
                  <span className="block text-sm font-medium leading-snug text-ink break-anywhere">{item.title}</span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-subtle">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden />
                      {selected ? formatTime(start) : `${format(start, "d MMM")} · ${formatTime(start)}`}
                    </span>
                    <span>{KIND_LABEL[item.kind] ?? item.kind}</span>
                    {item.location && (
                      <span className="inline-flex min-w-0 items-center gap-1">
                        <MapPin className="h-3 w-3 shrink-0" aria-hidden />
                        <span className="truncate">{item.location}</span>
                      </span>
                    )}
                  </span>
                </>
              );
              return (
                <li key={item.id} className="relative">
                  {item.link ? (
                    <Link to={item.link} className="block rounded-md transition-colors hover:text-accent focus-visible:text-accent">
                      {body}
                    </Link>
                  ) : body}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </Card>
  );
}
