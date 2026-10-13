import { useAuth } from "@/lib/auth";
import { AdminDashboard } from "./AdminDashboard";
import { FacultyDashboard } from "./FacultyDashboard";
import { HodDashboard } from "./HodDashboard";
import { StudentDashboard } from "./StudentDashboard";

/** One route, four views — chosen by role rather than by separate apps. */
export function DashboardPage() {
  const { user } = useAuth();
  if (user?.student) return <StudentDashboard />;
  // A Head of Department has no mentees or review queue, so the faculty
  // dashboard — which is built around both — is the wrong screen for them.
  if (user?.faculty?.hod_department_id) return <HodDashboard />;
  if (user?.faculty) return <FacultyDashboard />;
  return <AdminDashboard />;
}
