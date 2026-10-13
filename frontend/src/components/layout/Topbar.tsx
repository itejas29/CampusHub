import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell, Check, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Sun,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";
import { Avatar, Popover } from "@/components/ui/Misc";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { visibleSections } from "@/lib/navigation";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import type { NotificationSummary } from "@/types";

function GlobalSearch() {
  const { user, can, mentorsProgram, coordinates } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const destinations = useMemo(
    () => visibleSections(user?.roles ?? [], can, mentorsProgram, coordinates,
                          user?.student?.visible_sections ?? null)
      .flatMap((s) => s.items),
    [user, can, mentorsProgram, coordinates],
  );
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return destinations.filter((item) => item.label.toLowerCase().includes(needle)).slice(0, 7);
  }, [query, destinations]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
      if (event.key === "Escape") setOpen(false);
    }
    function onClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  function go(to: string) {
    navigate(to);
    setQuery("");
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative hidden max-w-sm flex-1 sm:block">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle"
        aria-hidden
      />
      <input
        ref={inputRef}
        type="search"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) go(matches[0].to); }}
        placeholder="Search…"
        aria-label="Search the portal"
        className="topbar-search"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-line bg-surface-muted px-1.5 py-0.5 text-2xs text-ink-subtle md:block">
        ⌘K
      </kbd>
      {open && query.trim() && (
        <div className="absolute left-0 right-0 top-11 z-40 rounded-lg border border-line bg-surface p-1.5 shadow-lg animate-slide-down">
          {matches.length === 0 ? (
            <p className="px-3 py-3 text-center text-sm text-ink-muted">
              No results for "{query}"
            </p>
          ) : (
            matches.map((item) => (
              <button
                key={item.to}
                type="button"
                onClick={() => go(item.to)}
                className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-muted"
              >
                {item.icon && <item.icon className="h-4 w-4 text-ink-subtle" aria-hidden />}
                {item.label}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function NotificationBell() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationSummary>("/notifications?limit=12"),
    refetchInterval: 60_000,
  });
  const markRead = useMutation({
    mutationFn: (ids?: number[]) =>
      api.post("/notifications/read", ids ? { ids } : { all: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unread = data?.unread ?? 0;

  return (
    <Popover
      panelClassName="w-[22rem] max-w-[calc(100vw-1.5rem)] p-0"
      trigger={({ toggle, open, triggerProps }) => (
        <button
          type="button"
          onClick={toggle}
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          {...triggerProps}
          className={cn(
            "relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-md",
            "text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink",
            open && "bg-surface-muted text-ink",
          )}
        >
          <Bell className="h-4 w-4" aria-hidden />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-[1.125rem] min-w-[1.125rem] items-center justify-center rounded-full bg-danger px-1 text-2xs font-bold text-danger-fg leading-none">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      )}
    >
      {({ close }) => (
        <div>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="text-sm font-semibold text-ink">Notifications</p>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => markRead.mutate(undefined)}
                className="flex cursor-pointer items-center gap-1.5 rounded text-xs text-accent hover:underline"
              >
                <Check className="h-3 w-3" aria-hidden />
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[22rem] overflow-y-auto">
            {!data?.items.length ? (
              <EmptyState
                compact
                title="You're all caught up"
                description="Deadlines, allocations and event updates will appear here."
                icon={<Bell className="h-5 w-5" aria-hidden />}
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.items.map((item) => (
                  <li key={item.id}>
                    <Link
                      to={item.link ?? "#"}
                      onClick={() => {
                        if (!item.is_read) markRead.mutate([item.id]);
                        close();
                      }}
                      className={cn(
                        "block px-4 py-3 transition-colors hover:bg-surface-muted",
                        !item.is_read && "bg-accent-soft/20",
                      )}
                    >
                      <div className="flex items-start gap-2.5">
                        {!item.is_read && (
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                        )}
                        <div className={cn("min-w-0 flex-1", item.is_read && "pl-4")}>
                          <p className="text-sm font-medium leading-snug text-ink">
                            {item.title}
                          </p>
                          {item.message && (
                            <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">
                              {item.message}
                            </p>
                          )}
                          <p className="mt-1 text-2xs text-ink-subtle">
                            {relativeTime(item.created_at)}
                          </p>
                        </div>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Popover>
  );
}

export function Topbar({
  onOpenNav,
  collapsed = false,
  onToggleCollapse,
}: {
  onOpenNav: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const { user, signOut } = useAuth();
  const { theme, toggle } = useTheme();
  const context = user?.student
    ? `Sem ${user.student.current_semester} · ${user.student.department_code ?? ""}`
    : user?.faculty?.department_code ?? null;

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-surface/80 sm:px-6">
      <Button
        variant="ghost" size="icon" onClick={onOpenNav} aria-label="Open navigation"
        className="lg:hidden h-8 w-8 cursor-pointer"
      >
        <Menu className="h-4.5 w-4.5" aria-hidden />
      </Button>

      {onToggleCollapse && (
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar (Ctrl+B)" : "Collapse sidebar (Ctrl+B)"}
          title={collapsed ? "Expand sidebar (Ctrl+B)" : "Collapse sidebar (Ctrl+B)"}
          className="hidden lg:flex h-8 w-8 text-ink-muted hover:text-ink hover:bg-surface-muted cursor-pointer"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4.5 w-4.5" />
          ) : (
            <PanelLeftClose className="h-4.5 w-4.5" />
          )}
        </Button>
      )}

      <GlobalSearch />

      <div className="ml-auto flex items-center gap-1.5">
        {user?.academic_year && (
          <div className="mr-1 hidden items-center gap-1.5 md:flex">
            <Badge tone="neutral" className="text-2xs">{user.academic_year}</Badge>
            {context && <Badge tone="brand" className="text-2xs">{context.trim()}</Badge>}
          </div>
        )}

        {/* Theme toggle */}
        <button
          type="button"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
        >
          {theme === "dark"
            ? <Sun className="h-4 w-4" aria-hidden />
            : <Moon className="h-4 w-4" aria-hidden />}
        </button>

        <NotificationBell />

        {/* Account menu */}
        <Popover
          trigger={({ toggle: t, open, triggerProps }) => (
            <button
              type="button"
              onClick={t}
              aria-label="Account menu"
              {...triggerProps}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-md p-1 pl-1.5 transition-colors hover:bg-surface-muted",
                open && "bg-surface-muted",
              )}
            >
              <Avatar name={user?.full_name} src={user?.avatar_url} size="sm" />
            </button>
          )}
        >
          {({ close }) => (
            <div>
              <div className="border-b border-line px-3.5 py-3">
                <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
                <p className="truncate text-xs text-ink-muted mt-0.5">{user?.email}</p>
              </div>
              <div className="p-1">
                <Link
                  to="/profile"
                  onClick={close}
                  className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink transition-colors hover:bg-surface-muted"
                >
                  Profile & settings
                </Link>
                <button
                  type="button"
                  onClick={() => { close(); signOut(); }}
                  className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-danger transition-colors hover:bg-danger-soft/40"
                >
                  Sign out
                </button>
              </div>
            </div>
          )}
        </Popover>
      </div>
    </header>
  );
}
