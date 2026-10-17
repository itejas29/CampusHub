import { GraduationCap, LogOut, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { drawerLeft, fade, spring } from "@/lib/motion";
import { Avatar } from "@/components/ui/Misc";
import { useAuth } from "@/lib/auth";
import { PROFILE_ITEM, visibleSections } from "@/lib/navigation";
import { cn, humanise } from "@/lib/utils";

function iconClass(isActive: boolean) {
  return cn(
    "h-4 w-4 shrink-0 transition-colors duration-150",
    isActive ? "text-sidebar-active-fg" : "text-sidebar-icon group-hover:text-sidebar-ink",
  );
}

export function SidebarContent({
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: {
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const { user, can, mentorsProgram, coordinates, signOut } = useAuth();
  const sections = visibleSections(user?.roles ?? [], can, mentorsProgram, coordinates,
                                   user?.student?.visible_sections ?? null);
  // One shared layoutId per sidebar instance, so the desktop rail and the
  // mobile drawer never try to animate one indicator between them.
  const indicatorId = useId();

  return (
    <div
      className={cn(
        "relative flex h-full flex-col overflow-hidden bg-sidebar text-sidebar-text transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      {/* A faint electric glow at the top — the shell's one decorative flourish. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 left-1/2 h-48 w-48 -translate-x-1/2 rounded-full bg-electric/25 blur-3xl"
      />

      {/* Logo & collapse header */}
      <div
        className={cn(
          "relative flex h-14 shrink-0 items-center border-b border-sidebar-ink/[0.08]",
          collapsed ? "justify-center px-2" : "gap-3 px-4",
        )}
      >
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "CampusHub home"}
          title={collapsed ? "Expand sidebar (Ctrl+B)" : "CampusHub PDEU Portal"}
          className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg bg-accent-gradient text-white shadow-glow-accent transition-transform hover:scale-105"
        >
          <GraduationCap className="h-4.5 w-4.5" aria-hidden />
        </button>

        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block font-heading text-md font-semibold leading-tight text-sidebar-ink">
                CampusHub
              </span>
              <span className="block truncate text-2xs font-semibold uppercase tracking-wider text-sidebar-section">
                PDEU Portal
              </span>
            </span>

            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-sidebar-icon transition-colors hover:bg-sidebar-ink/[0.08] hover:text-sidebar-ink"
                title="Collapse sidebar (Ctrl+B)"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            )}
          </>
        )}
      </div>

      {/* Nav */}
      <nav
        className={cn(
          "sidebar-scroll relative min-h-0 flex-1 overflow-y-auto py-3",
          collapsed ? "px-2" : "px-2.5",
        )}
        aria-label="Main"
      >
        {sections.map((section, index) => (
          <div
            key={section.title ?? `section-${index}`}
            className={index > 0 ? (collapsed ? "mt-3 border-t border-sidebar-ink/[0.08] pt-3" : "mt-5") : ""}
          >
            {!collapsed && section.title && (
              <p className="mb-1.5 px-2.5 text-2xs font-semibold uppercase tracking-wider text-sidebar-section">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    title={collapsed ? item.label : undefined}
                    aria-label={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        "group relative flex select-none items-center rounded-md text-sm font-medium transition-colors duration-150",
                        collapsed ? "mx-auto h-9 w-9 justify-center p-0" : "gap-2.5 px-2.5 py-[7px]",
                        isActive
                          ? "font-semibold text-sidebar-active-fg"
                          : "text-sidebar-text hover:bg-sidebar-ink/[0.07] hover:text-sidebar-ink",
                      )
                    }
                    onClick={onNavigate}
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          // The active pill glides between items rather than
                          // blinking, so the eye follows where it went.
                          <motion.span
                            layoutId={`sidebar-active-${indicatorId}`}
                            className="absolute inset-0 rounded-md bg-sidebar-active shadow-sm"
                            transition={spring}
                            aria-hidden
                          />
                        )}
                        {isActive && !collapsed && (
                          <span
                            aria-hidden
                            className="absolute -left-2.5 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-sidebar-indicator"
                          />
                        )}
                        {item.icon && (
                          <item.icon className={cn(iconClass(isActive), "relative")} aria-hidden />
                        )}
                        {!collapsed && <span className="relative truncate">{item.label}</span>}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* User profile footer */}
      <div
        className={cn(
          "relative shrink-0 border-t border-sidebar-ink/[0.08] p-2.5",
          collapsed && "flex flex-col items-center gap-1.5 p-2",
        )}
      >
        {collapsed ? (
          <>
            <NavLink
              to={PROFILE_ITEM.to}
              title={`${user?.full_name ?? "Profile"} (${user?.roles.map((r) => humanise(r)).join(", ")})`}
              aria-label="Your profile"
              className={({ isActive }) =>
                cn(
                  "flex h-9 w-9 items-center justify-center rounded-md transition-colors duration-150",
                  isActive ? "bg-sidebar-ink/[0.12]" : "hover:bg-sidebar-ink/[0.07]",
                )
              }
              onClick={onNavigate}
            >
              <Avatar name={user?.full_name} src={user?.avatar_url} size="xs" />
            </NavLink>
            <button
              type="button"
              onClick={signOut}
              title="Sign out"
              aria-label="Sign out"
              className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-sidebar-icon transition-colors duration-150 hover:bg-danger/20 hover:text-white"
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden />
            </button>
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                title="Expand sidebar (Ctrl+B)"
                aria-label="Expand sidebar"
                className="mt-1 flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-sidebar-icon transition-colors hover:bg-sidebar-ink/[0.08] hover:text-sidebar-ink"
              >
                <PanelLeftOpen className="h-4 w-4 shrink-0" />
              </button>
            )}
          </>
        ) : (
          <>
            <NavLink
              to={PROFILE_ITEM.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors duration-150",
                  isActive ? "bg-sidebar-ink/[0.12]" : "hover:bg-sidebar-ink/[0.07]",
                )
              }
              onClick={onNavigate}
            >
              <Avatar name={user?.full_name} src={user?.avatar_url} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-sidebar-ink" title={user?.full_name}>
                  {user?.full_name}
                </span>
                <span className="block truncate text-2xs text-sidebar-section">
                  {user?.roles.map((role) => humanise(role)).join(" · ")}
                </span>
              </span>
            </NavLink>
            <button
              type="button"
              onClick={signOut}
              className="mt-0.5 flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm text-sidebar-text transition-colors duration-150 hover:bg-danger/20 hover:text-white"
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden />
              <span>Sign out</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function Sidebar({
  collapsed = false,
  onToggleCollapse,
}: {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  return (
    <aside
      className={cn(
        "hidden shrink-0 lg:block transition-all duration-200 ease-in-out",
        collapsed ? "w-16" : "w-60",
      )}
      aria-label="Sidebar"
    >
      <div
        className={cn(
          "fixed inset-y-0 left-0 transition-all duration-200 ease-in-out z-20",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <SidebarContent collapsed={collapsed} onToggleCollapse={onToggleCollapse} />
      </div>
    </aside>
  );
}

export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <motion.div
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
            variants={fade}
            initial="hidden"
            animate="shown"
            exit="exit"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            variants={drawerLeft}
            initial="hidden"
            animate="shown"
            exit="exit"
            className="absolute inset-y-0 left-0 w-64 shadow-xl"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="Close navigation"
              className="absolute -right-11 top-3 flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg bg-surface text-ink shadow-lg hover:bg-surface-muted transition-colors"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
            <SidebarContent onNavigate={onClose} />
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
