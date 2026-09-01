import { useAuth } from "@/lib/auth";
import { AdminDashboard } from "./AdminDashboard";
import { FacultyDashboard } from "./FacultyDashboard";
import { StudentDashboard } from "./StudentDashboard";

/** One route, three views — chosen by role rather than by separate apps. */
export function DashboardPage() {
  const { user } = useAuth();
  if (user?.student) return <StudentDashboard />;
  if (user?.faculty) return <FacultyDashboard />;
  return <AdminDashboard />;
}
