import {
  BadgeCheck, BarChart3, BookOpen, Building2, CalendarDays, ClipboardList,
  FileStack, GraduationCap, Users, Layers, LayoutDashboard, Library, Megaphone,
  Network, Route, School, ScrollText, Settings, Sparkles, UserCheck, UserCog, UserSquare2,
  type LucideIcon,
} from "lucide-react";
import type { CoordinationDomain, Role } from "@/types";

export interface NavItem {
  label: string;
  to: string;
  icon?: LucideIcon;
  /** Visible when the user holds ANY of these roles (empty = everyone). */
  roles?: Role[];
  /** Hidden from anyone holding one of these roles, whatever else they hold. */
  excludeRoles?: Role[];
  /**
   * Visible with this backend permission. When `coordinates` is also given the
   * two are ALTERNATIVES — a scoped coordinator reaches the screen without
   * holding the institution-wide permission.
   */
  permission?: string;
  /** Visible to anyone coordinating one of these domains. */
  coordinates?: CoordinationDomain[];
  /**
   * Visible only to faculty who actually mentor students on this internship
   * type. A faculty member never made a mentor sees no student list at all.
   */
  mentorsProgram?: "CSSI" | "SUMMER";
  /**
   * Visible only while this semester-gated section applies to the student. The
   * list comes from the server (`student.visible_sections`), so the menu and
   * the endpoints answer to one rule instead of the sidebar advertising a page
   * the API would return empty.
   */
  studentSection?: "minors" | "internships" | "open_electives" | "core_electives" | "nptel";
  children?: NavItem[];
  /** Match nested routes as active (default true for parents). */
  end?: boolean;
}

export interface NavSection {
  title?: string;
  items: NavItem[];
}

const STUDENT: Role[] = ["STUDENT"];
const STAFF: Role[] = [
  "FACULTY", "DEPARTMENT_ADMIN", "INTERNSHIP_COORDINATOR", "HOD", "SUPER_ADMIN",
];
const ADMIN: Role[] = [
  "DEPARTMENT_ADMIN", "INTERNSHIP_COORDINATOR", "CLUB_ADMIN", "SUPER_ADMIN",
];

export const NAVIGATION: NavSection[] = [
  {
    items: [{ label: "Dashboard", to: "/", icon: LayoutDashboard, end: true }],
  },
  {
    title: "Academics",
    items: [
      { label: "Curriculum", to: "/academics/curriculum", icon: Library, roles: STUDENT },
      // Offered from the semester the student's own curriculum first places such
      // a slot in — a first-year sees none of the three.
      {
        label: "Open Electives", to: "/academics/open-electives", icon: BookOpen,
        roles: STUDENT, studentSection: "open_electives",
      },
      {
        label: "Core Electives", to: "/academics/core-electives", icon: Layers,
        roles: STUDENT, studentSection: "core_electives",
      },
      {
        label: "NPTEL / MOOC", to: "/academics/nptel", icon: BadgeCheck,
        roles: STUDENT, studentSection: "nptel",
      },
      {
        label: "Minor Specialisation", to: "/academics/minors", icon: Sparkles,
        roles: STUDENT, studentSection: "minors",
      },
      { label: "Course Catalogue", to: "/academics/courses", icon: Library, roles: STAFF },
      { label: "Curriculum Explorer", to: "/academics/curriculums", icon: Network, roles: STAFF },
    ],
  },
  {
    title: "Internships",
    items: [
      {
        label: "My Internships", to: "/internships", icon: Route, roles: STUDENT,
        end: true, studentSection: "internships",
      },
      {
        label: "CSSI Students", to: "/internships/cssi-students", icon: Users,
        roles: STAFF, mentorsProgram: "CSSI",
      },
      {
        label: "SI Students", to: "/internships/si-students", icon: Users,
        roles: STAFF, mentorsProgram: "SUMMER",
      },
      {
        label: "All Students", to: "/internships/students", icon: Users,
        permission: "internships:manage",
      },
      {
        label: "Assign Mentors", to: "/internships/mentor-assignment", icon: UserCheck,
        permission: "internships:manage",
      },
      {
        label: "Programmes", to: "/internships/programs", icon: ClipboardList,
        permission: "internships:manage",
      },
    ],
  },
  {
    title: "Campus",
    items: [
      { label: "Clubs", to: "/clubs", icon: School },
      { label: "Events", to: "/events", icon: CalendarDays },
      { label: "Calendar", to: "/calendar", icon: CalendarDays },
    ],
  },
  {
    title: "Support",
    items: [
      // A Head of Department has neither a mentor nor mentees.
      { label: "Mentor–Mentee", to: "/mentorship", icon: UserSquare2, excludeRoles: ["HOD"] },
      { label: "Faculty Directory", to: "/faculty", icon: GraduationCap },
      { label: "Announcements", to: "/announcements", icon: Megaphone },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Overview", to: "/admin", icon: BarChart3, roles: ADMIN, end: true },
      {
        label: "Students", to: "/admin/students", icon: Users,
        roles: ADMIN, permission: "students:read",
      },
      {
        label: "Faculty", to: "/admin/faculty", icon: UserCog,
        permission: "faculty:manage",
      },
      {
        label: "Departments", to: "/admin/departments", icon: Building2,
        permission: "academics:manage",
      },
      {
        label: "Curriculum", to: "/admin/curriculum", icon: ScrollText,
        permission: "academics:manage",
      },
      {
        label: "Elective Allocation", to: "/admin/electives", icon: FileStack,
        permission: "electives:manage",
        coordinates: ["OPEN_ELECTIVE", "CORE_ELECTIVE"],
      },
      {
        label: "NPTEL Verification", to: "/admin/nptel", icon: BadgeCheck,
        permission: "mooc:verify", coordinates: ["MOOC"],
      },
      {
        label: "Minor Applications", to: "/admin/minors", icon: Sparkles,
        permission: "minors:manage", coordinates: ["MINOR"],
      },
      {
        label: "Clubs & Events", to: "/admin/events", icon: CalendarDays,
        permission: "events:manage",
      },
      {
        // The Head of Department's screen: appoint and remove their own
        // department's coordinators and mentors.
        label: "Coordinators & Mentors", to: "/admin/roles", icon: UserCog,
        permission: "roles:assign",
      },
      {
        label: "Audit Log", to: "/admin/audit", icon: ScrollText,
        permission: "audit:view",
      },
    ],
  },
];

export const PROFILE_ITEM: NavItem = { label: "Profile", to: "/profile", icon: Settings };

export function visibleSections(
  roles: Role[],
  can: (permission: string) => boolean,
  mentorsProgram: (type: "CSSI" | "SUMMER") => boolean = () => false,
  coordinates: (domain: CoordinationDomain) => boolean = () => false,
  studentSections: string[] | null = null,
): NavSection[] {
  const owned = new Set(roles);
  const allowed = (item: NavItem) => {
    if (item.roles && !item.roles.some((role) => owned.has(role))) return false;
    if (item.excludeRoles?.some((role) => owned.has(role))) return false;
    if (item.mentorsProgram && !mentorsProgram(item.mentorsProgram)) return false;
    // `null` means "not a student" — staff navigation is unaffected.
    if (item.studentSection && studentSections
        && !studentSections.includes(item.studentSection)) return false;

    // permission and coordination are alternatives, so a scoped coordinator
    // reaches the screen without the institution-wide permission.
    const byPermission = item.permission ? can(item.permission) : null;
    const byCoordination = item.coordinates
      ? item.coordinates.some(coordinates)
      : null;
    if (byPermission === null && byCoordination === null) return true;
    return Boolean(byPermission) || Boolean(byCoordination);
  };
  return NAVIGATION
    .map((section) => ({ ...section, items: section.items.filter(allowed) }))
    .filter((section) => section.items.length > 0);
}
