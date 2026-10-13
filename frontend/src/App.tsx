import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { NotFoundPage, RequireAccess, RequireAuth } from "@/components/layout/RouteGuards";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";

import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AdminDashboard } from "@/features/dashboard/AdminDashboard";

import { CourseCataloguePage } from "@/features/academics/CourseCataloguePage";
import { CurriculumExplorerPage } from "@/features/academics/CurriculumExplorerPage";
import { CurriculumPage } from "@/features/academics/CurriculumPage";
import { ElectiveListPage } from "@/features/academics/ElectiveListPage";
import { ElectiveWorkspacePage } from "@/features/academics/ElectiveWorkspacePage";
import { MinorsPage } from "@/features/academics/MinorsPage";
import { NptelPage } from "@/features/academics/NptelPage";

import { InternshipRecordPage } from "@/features/internships/InternshipRecordPage";
import { InternshipsPage } from "@/features/internships/InternshipsPage";
import { MentorAssignmentPage } from "@/features/internships/MentorAssignmentPage";
import { MyStudentsPage } from "@/features/internships/MyStudentsPage";
import { ProgramsAdminPage } from "@/features/internships/ProgramsAdminPage";

import { CalendarPage } from "@/features/community/CalendarPage";
import { ClubDetailPage, ClubsPage } from "@/features/community/ClubsPage";
import { EventDetailRedirect, EventsPage } from "@/features/community/EventsPage";

import { AnnouncementsPage } from "@/features/engagement/AnnouncementsPage";
import { FacultyDirectoryPage } from "@/features/engagement/FacultyDirectoryPage";
import { MenteesPage } from "@/features/engagement/MenteesPage";
import { MentorshipPage } from "@/features/engagement/MentorshipPage";

import { AuditLogPage } from "@/features/admin/AuditLogPage";
import { CurriculumAdminPage } from "@/features/admin/CurriculumAdminPage";
import { StudentProfilePage } from "@/features/people/StudentProfilePage";
import { DepartmentsPage } from "@/features/admin/DepartmentsPage";
import { ElectiveAdminPage } from "@/features/admin/ElectiveAdminPage";
import { EventsAdminPage } from "@/features/admin/EventsAdminPage";
import { FacultyAdminPage } from "@/features/admin/FacultyAdminPage";
import { MinorAdminPage } from "@/features/admin/MinorAdminPage";
import { NptelAdminPage } from "@/features/admin/NptelAdminPage";
import { RoleAssignmentsPage } from "@/features/admin/RoleAssignmentsPage";
import { StudentsAdminPage } from "@/features/admin/StudentsAdminPage";

import { ProfilePage } from "@/features/profile/ProfilePage";

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
        <BrowserRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
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
                <Route path="internships/students/:enrollmentId"
                       element={<Navigate to="/internships/my-students" replace />} />
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
                    <RequireAccess permission="faculty:manage">
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
