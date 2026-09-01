import { GraduationCap, LogOut, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { Avatar } from "@/components/ui/Misc";
import { useAuth } from "@/lib/auth";
import { PROFILE_ITEM, visibleSections } from "@/lib/navigation";
import { cn, humanise } from "@/lib/utils";

function itemClass({ isActive }: { isActive: boolean }) {
  return cn(
    "group flex items-center gap-2.5 rounded px-2.5 py-1.5 text-sm transition-colors duration-150",
    isActive
      ? "bg-brand-soft font-medium text-brand"
      : "text-ink-muted hover:bg-surface-muted hover:text-ink",
  );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, can, mentorsProgram, coordinates, signOut } = useAuth();
  const sections = visibleSections(user?.roles ?? [], can, mentorsProgram, coordinates);

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
        <span className="flex h-8 w-8 items-center justify-center rounded bg-brand text-brand-fg">
          <GraduationCap className="h-4.5 w-4.5" aria-hidden />
        </span>
        <span className="min-w-0">
          <span className="block font-heading text-md font-semibold leading-tight text-ink">
            CampusHub
          </span>
          <span className="block truncate text-2xs uppercase tracking-wide text-ink-subtle">
            PDEU Student Portal
          </span>
        </span>
      </div>

      <nav className="min-h-0 flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Main">
        {sections.map((section, index) => (
          <div key={section.title ?? `section-${index}`}>
            {section.title && (
              <p className="mb-1.5 px-2.5 text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.end} className={itemClass} onClick={onNavigate}>
                    {item.icon && <item.icon className="h-4 w-4 shrink-0" aria-hidden />}
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-line p-3">
        <NavLink
          to={PROFILE_ITEM.to}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded p-2 transition-colors duration-150",
              isActive ? "bg-brand-soft" : "hover:bg-surface-muted",
            )
          }
          onClick={onNavigate}
        >
          <Avatar name={user?.full_name} src={user?.avatar_url} size="sm" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">
              {user?.full_name}
            </span>
            <span className="block truncate text-2xs text-ink-subtle">
              {user?.roles.map((role) => humanise(role)).join(" · ")}
            </span>
          </span>
        </NavLink>
        <button
          type="button"
          onClick={signOut}
          className="mt-1 flex w-full cursor-pointer items-center gap-2.5 rounded px-2.5 py-1.5 text-sm text-ink-muted transition-colors hover:bg-surface-muted hover:text-danger"
        >
          <LogOut className="h-4 w-4 shrink-0" aria-hidden />
          Sign out
        </button>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-line lg:block">
      <div className="fixed inset-y-0 left-0 w-60">
        <SidebarContent />
      </div>
    </aside>
  );
}

export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="absolute inset-0 bg-ink/40 animate-fade-in" onClick={onClose} aria-hidden />
      <div className="absolute inset-y-0 left-0 w-64 border-r border-line shadow-lg animate-slide-up">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="absolute -right-11 top-3 flex h-9 w-9 cursor-pointer items-center justify-center rounded bg-surface text-ink shadow-md"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
        <SidebarContent onNavigate={onClose} />
      </div>
    </div>
  );
}
