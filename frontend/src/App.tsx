import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy } from "react";
import { MotionConfig } from "framer-motion";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { NotFoundPage, RequireAccess, RequireAuth } from "@/components/layout/RouteGuards";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";

import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";

// Every screen except sign-in and the dashboard loads on first visit, so the
// initial bundle carries only what the first screen needs.
const AdminDashboard = lazy(() => import("@/features/dashboard/AdminDashboard").then((m) => ({ default: m.AdminDashboard })));
const CourseCataloguePage = lazy(() => import("@/features/academics/CourseCataloguePage").then((m) => ({ default: m.CourseCataloguePage })));
const CurriculumExplorerPage = lazy(() => import("@/features/academics/CurriculumExplorerPage").then((m) => ({ default: m.CurriculumExplorerPage })));
const CurriculumPage = lazy(() => import("@/features/academics/CurriculumPage").then((m) => ({ default: m.CurriculumPage })));
const ElectiveListPage = lazy(() => import("@/features/academics/ElectiveListPage").then((m) => ({ default: m.ElectiveListPage })));
const ElectiveWorkspacePage = lazy(() => import("@/features/academics/ElectiveWorkspacePage").then((m) => ({ default: m.ElectiveWorkspacePage })));
const MinorsPage = lazy(() => import("@/features/academics/MinorsPage").then((m) => ({ default: m.MinorsPage })));
const NptelPage = lazy(() => import("@/features/academics/NptelPage").then((m) => ({ default: m.NptelPage })));
const InternshipRecordPage = lazy(() => import("@/features/internships/InternshipRecordPage").then((m) => ({ default: m.InternshipRecordPage })));
const InternshipsPage = lazy(() => import("@/features/internships/InternshipsPage").then((m) => ({ default: m.InternshipsPage })));
const ProgramWindowsPage = lazy(() => import("@/features/internships/ProgramWindowsPage").then((m) => ({ default: m.ProgramWindowsPage })));
const MentorAssignmentPage = lazy(() => import("@/features/internships/MentorAssignmentPage").then((m) => ({ default: m.MentorAssignmentPage })));
const MyStudentsPage = lazy(() => import("@/features/internships/MyStudentsPage").then((m) => ({ default: m.MyStudentsPage })));
const ProgramsAdminPage = lazy(() => import("@/features/internships/ProgramsAdminPage").then((m) => ({ default: m.ProgramsAdminPage })));
const CalendarPage = lazy(() => import("@/features/community/CalendarPage").then((m) => ({ default: m.CalendarPage })));
const ClubDetailPage = lazy(() => import("@/features/community/ClubsPage").then((m) => ({ default: m.ClubDetailPage })));
const ClubsPage = lazy(() => import("@/features/community/ClubsPage").then((m) => ({ default: m.ClubsPage })));
const EventDetailRedirect = lazy(() => import("@/features/community/EventsPage").then((m) => ({ default: m.EventDetailRedirect })));
const EventsPage = lazy(() => import("@/features/community/EventsPage").then((m) => ({ default: m.EventsPage })));
const AnnouncementsPage = lazy(() => import("@/features/engagement/AnnouncementsPage").then((m) => ({ default: m.AnnouncementsPage })));
const FacultyDirectoryPage = lazy(() => import("@/features/engagement/FacultyDirectoryPage").then((m) => ({ default: m.FacultyDirectoryPage })));
const MenteesPage = lazy(() => import("@/features/engagement/MenteesPage").then((m) => ({ default: m.MenteesPage })));
const MentorshipPage = lazy(() => import("@/features/engagement/MentorshipPage").then((m) => ({ default: m.MentorshipPage })));
const AuditLogPage = lazy(() => import("@/features/admin/AuditLogPage").then((m) => ({ default: m.AuditLogPage })));
const CurriculumAdminPage = lazy(() => import("@/features/admin/CurriculumAdminPage").then((m) => ({ default: m.CurriculumAdminPage })));
const StudentProfilePage = lazy(() => import("@/features/people/StudentProfilePage").then((m) => ({ default: m.StudentProfilePage })));
const DepartmentsPage = lazy(() => import("@/features/admin/DepartmentsPage").then((m) => ({ default: m.DepartmentsPage })));
const ElectiveAdminPage = lazy(() => import("@/features/admin/ElectiveAdminPage").then((m) => ({ default: m.ElectiveAdminPage })));
const EventsAdminPage = lazy(() => import("@/features/admin/EventsAdminPage").then((m) => ({ default: m.EventsAdminPage })));
const FacultyAdminPage = lazy(() => import("@/features/admin/FacultyAdminPage").then((m) => ({ default: m.FacultyAdminPage })));
const MinorAdminPage = lazy(() => import("@/features/admin/MinorAdminPage").then((m) => ({ default: m.MinorAdminPage })));
const NptelAdminPage = lazy(() => import("@/features/admin/NptelAdminPage").then((m) => ({ default: m.NptelAdminPage })));
const RegistrationRoundsPage = lazy(() => import("@/features/admin/RegistrationRoundsPage").then((m) => ({ default: m.RegistrationRoundsPage })));
const RoleAssignmentsPage = lazy(() => import("@/features/admin/RoleAssignmentsPage").then((m) => ({ default: m.RoleAssignmentsPage })));
const StudentsAdminPage = lazy(() => import("@/features/admin/StudentsAdminPage").then((m) => ({ default: m.StudentsAdminPage })));
const ProfilePage = lazy(() => import("@/features/profile/ProfilePage").then((m) => ({ default: m.ProfilePage })));

function EnrollmentLink() {
  const { enrollmentId } = useParams();
  return <Navigate to={`/internships/review?record=${enrollmentId ?? ""}`} replace />;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Never retry an auth/permission failure — it will not succeed.
        const status = (error as { status?: number })?.status;
        if (status === 401 || status === 403 || status === 404) return false;
        return failureCount < 2;
      },
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {/* `reducedMotion="user"` drops transform/layout animation for anyone with
            the OS setting on, while keeping opacity so the UI still reads as
            responsive. The CSS block in index.css cannot cover Framer Motion,
            which animates via inline style rather than CSS transitions. */}
        <MotionConfig reducedMotion="user">
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route index element={<DashboardPage />} />

                {/* ── Academics ─────────────────────────────────────── */}
                <Route path="academics/curriculum" element={<CurriculumPage />} />
                {/* Notifications stored before Open and Core were split still
                    carry the old combined path. Send them somewhere real. */}
                <Route
                  path="academics/electives"
                  element={<Navigate to="/academics/open-electives" replace />}
                />
                <Route
                  path="academics/electives/:componentId"
                  element={<Navigate to="/academics/open-electives" replace />}
                />
                <Route
                  path="academics/open-electives"
                  element={
                    <ElectiveListPage
                      componentType="OPEN_ELECTIVE"
                      title="Open Electives"
                      description="Broadening electives taken outside your own department. The source restriction for each slot comes from your curriculum."
                      basePath="/academics/open-electives"
                    />
                  }
                />
                <Route
                  path="academics/open-electives/:componentId"
                  element={
                    <ElectiveWorkspacePage
                      backLabel="Open Electives" backTo="/academics/open-electives"
                    />
                  }
                />
                <Route
                  path="academics/core-electives"
                  element={
                    <ElectiveListPage
                      componentType="PROGRAM_CORE_ELECTIVE"
                      title="Program Core Electives"
                      description="Specialisation electives within your programme's own tracks — Software and Networks, Artificial Intelligence, Communication and Signal Processing, and Embedded and VLSI."
                      basePath="/academics/core-electives"
                    />
                  }
                />
                <Route
                  path="academics/core-electives/:componentId"
                  element={
                    <ElectiveWorkspacePage
                      backLabel="Core Electives" backTo="/academics/core-electives"
                    />
                  }
                />
                <Route path="academics/nptel" element={<NptelPage />} />
                <Route path="academics/minors" element={<MinorsPage />} />
                <Route
                  path="academics/courses"
                  element={
                    <RequireAccess permission="academics:read">
                      <CourseCataloguePage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="academics/curriculums"
                  element={
                    <RequireAccess permission="academics:read">
                      <CurriculumExplorerPage />
                    </RequireAccess>
                  }
                />

                {/* ── Internships ───────────────────────────────────── */}
                <Route path="internships" element={<InternshipsPage />} />
                <Route path="internships/record/:enrollmentId" element={<InternshipRecordPage />} />
                <Route
                  path="internships/cssi-students"
                  element={
                    <RequireAccess permission="students:read">
                      <MyStudentsPage
                        scope="mine"
                        programType="CSSI"
                        title="CSSI students"
                        description="Students you supervise for the Community and Social Service Internship. Open a student to review submissions and record evaluation."
                      />
                    </RequireAccess>
                  }
                />
                <Route
                  path="internships/si-students"
                  element={
                    <RequireAccess permission="students:read">
                      <MyStudentsPage
                        scope="mine"
                        programType="SUMMER"
                        title="Summer Internship students"
                        description="Students you mentor for the Summer Internship. Weekly reports and the final evaluation are reviewed here."
                      />
                    </RequireAccess>
                  }
                />
                <Route
                  path="internships/project-students"
                  element={
                    <RequireAccess permission="students:read">
                      <MyStudentsPage
                        scope="mine"
                        programType={["MINOR_PROJECT", "SEMINAR", "MAJOR_PROJECT"]}
                        title="Project students"
                        description="Students you guide for the Semester VII Minor Project or Seminar and the Semester VIII Major Project. Open a student to review submissions and record evaluation."
                      />
                    </RequireAccess>
                  }
                />
                {/* Old combined route kept so existing links still resolve. */}
                <Route
                  path="internships/my-students"
                  element={<Navigate to="/internships/cssi-students" replace />}
                />
                <Route
                  path="internships/students"
                  element={
                    <RequireAccess permission="internships:manage">
                      <MyStudentsPage scope="all" />
                    </RequireAccess>
                  }
                />
                <Route
                  path="internships/windows"
                  element={
                    <RequireAccess permission="internships:manage">
                      <ProgramWindowsPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="internships/mentor-assignment"
                  element={
                    <RequireAccess permission="internships:manage">
                      <MentorAssignmentPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="internships/programs"
                  element={
                    <RequireAccess permission="internships:manage">
                      <ProgramsAdminPage />
                    </RequireAccess>
                  }
                />
                {/* Notification deep links land here. */}
                {/* Review links (dashboard queue, notifications) name one record.
                    They used to redirect to the CSSI list and drop the student —
                    even for a Summer intern. Now they open that record's drawer
                    on the mentor's combined list. */}
                <Route path="internships/students/:enrollmentId" element={<EnrollmentLink />} />
                <Route
                  path="internships/review"
                  element={
                    <MyStudentsPage
                      scope="mine"
                      title="My internship students"
                      description="Every CSSI and Summer Internship student you mentor."
                    />
                  }
                />
                <Route path="internships/:programId"
                       element={<Navigate to="/internships" replace />} />

                {/* ── Campus ────────────────────────────────────────── */}
                <Route path="clubs" element={<ClubsPage />} />
                <Route path="clubs/:slug" element={<ClubDetailPage />} />
                <Route path="events" element={<EventsPage />} />
                <Route path="events/:eventId" element={<EventDetailRedirect />} />
                <Route path="calendar" element={<CalendarPage />} />

                {/* ── Support ───────────────────────────────────────── */}
                <Route path="mentorship" element={<MentorshipPage />} />
                <Route
                  path="mentorship/mentees"
                  element={
                    <RequireAccess roles={["FACULTY", "DEPARTMENT_ADMIN", "SUPER_ADMIN"]}>
                      <MenteesPage />
                    </RequireAccess>
                  }
                />
                <Route path="faculty" element={<FacultyDirectoryPage />} />
                <Route path="announcements" element={<AnnouncementsPage />} />
                <Route path="profile" element={<ProfilePage />} />

                {/* ── Administration ────────────────────────────────── */}
                <Route
                  path="admin"
                  element={
                    <RequireAccess permission="reports:view">
                      <AdminDashboard />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/students"
                  element={
                    <RequireAccess permission="students:read">
                      <StudentsAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/faculty"
                  element={
                    <RequireAccess permission="faculty:manage">
                      <FacultyAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/departments"
                  element={
                    <RequireAccess permission="academics:manage">
                      <DepartmentsPage />
                    </RequireAccess>
                  }
                />
                {/* The central faculty view. Access is decided by the backend
                    per student, so the route itself only needs a signed-in user. */}
                <Route path="people/students/:studentId"
                       element={<StudentProfilePage />} />
                <Route
                  path="admin/curriculum"
                  element={
                    <RequireAccess permission="academics:manage">
                      <CurriculumAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/elective-rounds"
                  element={
                    <RequireAccess
                      permission="electives:manage"
                      coordinates={["OPEN_ELECTIVE", "CORE_ELECTIVE"]}
                      orRoles={["HOD"]}
                    >
                      <RegistrationRoundsPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/electives"
                  element={
                    <RequireAccess
                      permission="electives:manage"
                      coordinates={["OPEN_ELECTIVE", "CORE_ELECTIVE"]}
                    >
                      <ElectiveAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/nptel"
                  element={
                    <RequireAccess permission="mooc:verify" coordinates={["MOOC"]}>
                      <NptelAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/minors"
                  element={
                    <RequireAccess permission="minors:manage" coordinates={["MINOR"]}>
                      <MinorAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/events"
                  element={
                    <RequireAccess permission="events:manage">
                      <EventsAdminPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/roles"
                  element={
                    <RequireAccess permission="roles:assign">
                      <RoleAssignmentsPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/audit"
                  element={
                    <RequireAccess permission="audit:view">
                      <AuditLogPage />
                    </RequireAccess>
                  }
                />
                <Route
                  path="admin/internships"
                  element={<Navigate to="/internships/programs" replace />}
                />
                <Route path="admin/clubs" element={<Navigate to="/clubs" replace />} />
                <Route path="admin/notifications"
                       element={<Navigate to="/announcements" replace />} />

                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
        </MotionConfig>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
