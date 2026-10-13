import { GraduationCap, LogOut, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { drawerLeft, fade } from "@/lib/motion";
import { Avatar } from "@/components/ui/Misc";
import { useAuth } from "@/lib/auth";
import { PROFILE_ITEM, visibleSections } from "@/lib/navigation";
import { cn, humanise } from "@/lib/utils";

function itemClass({ isActive }: { isActive: boolean }) {
  return cn(
    "group flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-sm font-medium",
    "transition-all duration-150 select-none",
    isActive
      ? "bg-[rgb(var(--c-sidebar-item-active-bg))] text-[rgb(var(--c-sidebar-item-active-text))] font-semibold"
      : "text-[rgb(var(--c-sidebar-item-text))] hover:bg-[rgb(var(--c-sidebar-item-hover-bg))] hover:text-ink",
  );
}

function iconClass(isActive: boolean) {
  return cn(
    "h-4 w-4 shrink-0 transition-colors duration-150",
    isActive
      ? "text-[rgb(var(--c-sidebar-item-active-text))]"
      : "text-[rgb(var(--c-sidebar-item-icon))] group-hover:text-ink-muted",
  );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, can, mentorsProgram, coordinates, signOut } = useAuth();
  const sections = visibleSections(user?.roles ?? [], can, mentorsProgram, coordinates,
                                   user?.student?.visible_sections ?? null);

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "rgb(var(--c-sidebar-bg))", borderRight: "1px solid rgb(var(--c-sidebar-border))" }}
    >
      {/* Logo */}
      <div
        className="flex h-14 shrink-0 items-center gap-3 px-4"
        style={{ borderBottom: "1px solid rgb(var(--c-sidebar-border))" }}
      >
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md"
          style={{
            background: "rgb(var(--c-sidebar-logo-bg))",
          }}
        >
          <GraduationCap
            className="h-4.5 w-4.5"
            style={{ color: "rgb(var(--c-sidebar-logo-fg))" }}
            aria-hidden
          />
        </span>
        <span className="min-w-0">
          <span className="block font-heading text-md font-semibold leading-tight text-ink">
            CampusHub
          </span>
          <span
            className="block truncate text-2xs uppercase tracking-wider font-semibold"
            style={{ color: "rgb(var(--c-sidebar-section-text))" }}
          >
            PDEU Portal
          </span>
        </span>
      </div>

      {/* Nav */}
      <nav className="min-h-0 flex-1 overflow-y-auto px-2.5 py-3" aria-label="Main">
        {sections.map((section, index) => (
          <div key={section.title ?? `section-${index}`} className={index > 0 ? "mt-5" : ""}>
            {section.title && (
              <p
                className="mb-1 px-2.5 text-2xs font-semibold uppercase tracking-wider"
                style={{ color: "rgb(var(--c-sidebar-section-text))" }}
              >
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => itemClass({ isActive })}
                    onClick={onNavigate}
                  >
                    {({ isActive }) => (
                      <>
                        {item.icon && (
                          <item.icon className={iconClass(isActive)} aria-hidden />
                        )}
                        <span className="truncate">{item.label}</span>
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
        className="shrink-0 p-2.5"
        style={{ borderTop: "1px solid rgb(var(--c-sidebar-border))" }}
      >
        <NavLink
          to={PROFILE_ITEM.to}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 transition-all duration-150",
              isActive
                ? "bg-[rgb(var(--c-sidebar-item-active-bg))]"
                : "hover:bg-[rgb(var(--c-sidebar-item-hover-bg))]",
            )
          }
          onClick={onNavigate}
        >
          <Avatar name={user?.full_name} src={user?.avatar_url} size="sm" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink">
              {user?.full_name}
            </span>
            <span
              className="block truncate text-2xs"
              style={{ color: "rgb(var(--c-sidebar-section-text))" }}
            >
              {user?.roles.map((role) => humanise(role)).join(" · ")}
            </span>
          </span>
        </NavLink>
        <button
          type="button"
          onClick={signOut}
          className="mt-0.5 flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-all duration-150 hover:bg-danger-soft/50 hover:text-danger"
          style={{ color: "rgb(var(--c-sidebar-item-text))" }}
        >
          <LogOut className="h-4 w-4 shrink-0" aria-hidden />
          <span className="text-sm">Sign out</span>
        </button>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 lg:block" aria-label="Sidebar">
      <div className="fixed inset-y-0 left-0 w-60">
        <SidebarContent />
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
