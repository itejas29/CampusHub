import { lazy, Suspense } from "react";
import { useAuth } from "@/lib/auth";
import { LoadingState } from "@/components/ui/States";

// Lazy-load each dashboard variant so none of them ends up in the main bundle.
// Previously all four were statically imported here, which pulled ~60 kB of
// component code (plus framer-motion list animations) into the initial parse
// task and caused >1 second input delays on sidebar navigation. Each variant
// now loads on first visit only — users who never become HoD never parse that
// code at all, and the browser scheduler can yield between chunks.
const StudentDashboard = lazy(() =>
  import("./StudentDashboard").then((m) => ({ default: m.StudentDashboard })));
const FacultyDashboard = lazy(() =>
  import("./FacultyDashboard").then((m) => ({ default: m.FacultyDashboard })));
const HodDashboard = lazy(() =>
  import("./HodDashboard").then((m) => ({ default: m.HodDashboard })));
const AdminDashboard = lazy(() =>
  import("./AdminDashboard").then((m) => ({ default: m.AdminDashboard })));

/** One route, four views — chosen by role rather than by separate apps. */
export function DashboardPage() {
  const { user } = useAuth();

  let View: React.ComponentType;
  if (user?.student) View = StudentDashboard;
  else if (user?.faculty?.hod_department_id) View = HodDashboard;
  else if (user?.faculty) View = FacultyDashboard;
  else View = AdminDashboard;

  return (
    <Suspense fallback={<LoadingState rows={4} label="Loading dashboard…" />}>
      <View />
    </Suspense>
  );
}
