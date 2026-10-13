import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { MobileSidebar, Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { slideUp } from "@/lib/motion";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem("campushub_sidebar_collapsed") === "true";
    } catch {
      return false;
    }
  });
  const location = useLocation();

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("campushub_sidebar_collapsed", String(next));
      } catch {}
      return next;
    });
  };

  // Keyboard shortcut Ctrl+B or Cmd+B to toggle sidebar collapse
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Scroll back to the top on navigation, like a real multi-page portal.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={toggleSidebar} />
      <MobileSidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col transition-all duration-200">
        <Topbar
          onOpenNav={() => setNavOpen(true)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={toggleSidebar}
        />
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 sm:py-7">
          <div className="mx-auto w-full max-w-[84rem]">
            {/*
              Enter-only, deliberately. Wrapping <Outlet/> in an AnimatePresence
              with an exit animation looks right but is not: the exiting copy
              re-reads router context while it animates, so it renders the
              INCOMING route's content on the way out — the new page fades out
              and then straight back in.

              Keying on pathname alone remounts on navigation, so a search-param
              change (a filter, a tab) updates in place rather than replaying the
              transition on every keystroke.
            */}
            <motion.div
              key={location.pathname}
              variants={slideUp}
              initial="hidden"
              animate="shown"
            >
              <Outlet />
            </motion.div>
          </div>
        </main>
        <footer className="border-t border-line px-4 py-3 sm:px-6">
          <p className="text-xs text-ink-subtle">
            CampusHub · Pandit Deendayal Energy University
            <span className="mx-1.5 opacity-40">·</span>
            <span className="opacity-60">Phase 2</span>
          </p>
        </footer>
      </div>
    </div>
  );
}
