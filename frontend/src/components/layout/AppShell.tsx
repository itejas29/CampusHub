import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { MobileSidebar, Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  // Scroll back to the top on navigation, like a real multi-page portal.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <MobileSidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenNav={() => setNavOpen(true)} />
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <div className="mx-auto w-full max-w-[84rem]">
            <Outlet />
          </div>
        </main>
        <footer className="border-t border-line px-4 py-3 text-xs text-ink-subtle sm:px-6">
          CampusHub · Pandit Deendayal Energy University · Phase 2 preview
        </footer>
      </div>
    </div>
  );
}
