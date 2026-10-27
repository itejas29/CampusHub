/** Shapes mirroring the FastAPI response models. */

export type Role =
  | "STUDENT" | "FACULTY" | "DEPARTMENT_ADMIN"
  | "INTERNSHIP_COORDINATOR" | "CLUB_ADMIN" | "HOD" | "SUPER_ADMIN";

export interface StudentContext {
  id: number; roll_number: string; program_id: number; program_name: string | null;
  department_id: number; department_code: string | null; current_semester: number;
  division: string | null; batch: string | null; cpi: number | null;
  backlog_count: number; admission_year: number;
  /** Semester-gated sections currently applicable — see lib/navigation.ts. */
  visible_sections: string[];
}

export type CoordinationDomain =
  | "CSSI" | "SUMMER_INTERNSHIP" | "MINOR" | "MOOC" | "PROJECT" | "MAJOR_PROJECT"
  | "OPEN_ELECTIVE" | "CORE_ELECTIVE" | "MENTORSHIP";

export interface Coordination {
  domain: CoordinationDomain;
  department_id: number | null;
  department_code: string | null;
  department_name: string | null;
  is_institution_wide: boolean;
  /** The HoD covering a seat nobody is appointed to — not an appointment. */
  acting?: boolean;
}

export interface FacultyContext {
  id: number; employee_code: string; department_id: number;
  department_code: string | null; designation: string; cabin: string | null;
  is_mentor: boolean;
  /** Set for a Head of Department: the one department they appoint for. */
  hod_department_id: number | null;
  hod_department_code: string | null;
  hod_department_name: string | null;
  /** Domains this faculty coordinates, and over which department. */
  coordinations: Coordination[];
  /** Internship types they actually mentor students for ("CSSI" | "SUMMER"). */
  mentors_programs: string[];
}

/** Coordinator and Mentor are independent grants over the same scope shape. */
export type AssignedRole = "COORDINATOR" | "MENTOR";

export interface RoleAssignment {
  id: number; faculty_id: number; faculty_name: string | null;
  employee_code: string | null; faculty_department_code: string | null;
  designation: string | null;
  role: AssignedRole; role_label: string | null;
  domain: CoordinationDomain; domain_label: string | null;
  department_id: number | null; department_code: string | null;
  department_name: string | null; is_institution_wide: boolean;
  academic_year_id: number | null; academic_year_label: string | null;
  assigned_by_name: string | null; assigned_at: string | null;
  starts_on: string | null; ends_on: string | null;
  is_active: boolean;
  /** Active *and* inside its validity window — what Status shows. */
  is_current: boolean;
  notes: string | null;
}

export interface DomainCoverage {
  domain: CoordinationDomain; domain_label: string | null;
  department_id: number | null;
  department_code: string | null; department_name: string | null;
  coordinators: RoleAssignment[];
  mentors: RoleAssignment[];
}

export interface FacultyRoleSummary {
  faculty_id: number; name: string; employee_code: string;
  designation: string; department_code: string | null; roles: Role[];
  /** The HoD appoints; they are never offered as an appointee. */
  is_hod: boolean;
  /** Every grant this person holds, of every role — the union. */
  coordinations: {
    id: number; role: AssignedRole; role_label: string;
    domain: string; domain_label: string; department_code: string;
    is_current: boolean;
  }[];
}

export interface RoleMatrix {
  domains: string[];
  coverage: DomainCoverage[];
  gaps: { domain: string; domain_label: string; department_id: number;
          department_code: string; department_name: string;
          /** The department's HoD, who covers the module until someone is appointed. */
          acting_hod?: string | null }[];
  faculty_summary: FacultyRoleSummary[];
}

export interface CurrentUser {
  id: number; email: string; full_name: string; phone: string | null;
  avatar_url: string | null; is_active: boolean; roles: Role[]; permissions: string[];
  student: StudentContext | null; faculty: FacultyContext | null;
  academic_year: string | null; current_semester_label: string | null;
  last_login_at: string | null;
  /** A one-time password is in use; nothing else works until it is replaced. */
  must_change_password?: boolean;
}

export interface TokenPair {
  access_token: string; refresh_token: string; token_type: string; expires_in: number;
}
export interface AuthResponse { tokens: TokenPair; user: CurrentUser }

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

// ── academics ──────────────────────────────────────────────────────────
export type ComponentType =
  | "CORE" | "OPEN_ELECTIVE" | "PROGRAM_CORE_ELECTIVE" | "MOOC" | "MINOR"
  | "INTERNSHIP" | "PROJECT";

export interface CurriculumComponent {
  id: number; curriculum_id: number; semester_number: number; code: string;
  title: string; component_type: ComponentType; source_scope: string;
  scope_label: string | null; credits: number; sequence: number; is_elective: boolean;
  description: string | null; elective_type_id: number | null;
  elective_type_code: string | null; config: Record<string, unknown>;
  /** Declarative cross-programme rules — eligible schools/departments/programmes. */
  eligibility: Record<string, unknown>;
  selection_mode: string | null;
  /** Fixed course filling a non-choice slot (core, or a prescribed elective). */
  course_code: string | null; course_title: string | null;
  course_category: string | null; delivery_mode: string | null;
  /** Set when the official source was ambiguous or two documents disagreed. */
  source_confidence: string | null; source_note: string | null;
  is_unlocked: boolean | null; status_label: string | null;
  allocated_course: string | null; offering_count: number | null;
  /** The round governing this slot for the student; one two-stage round
   *  covering a semester's slots means they are chosen together. */
  round_id: number | null; round_two_stage: boolean | null;
}

export interface CurriculumSemester {
  semester_number: number; label: string; is_current: boolean; is_completed: boolean;
  components: CurriculumComponent[]; total_credits: number;
}

export type CurriculumStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

/** Where a curriculum version came from. Curriculum data is university policy
 *  data, so the document behind a rule is always shown. */
export interface CurriculumSource {
  url: string | null; title: string | null; publisher: string | null;
  retrieved_at: string | null; academic_year: string | null;
  confidence: string | null; verified_at: string | null;
  verified_by: string | null; review_notes: string | null;
}

export interface Curriculum {
  id: number; program_id: number; program_name: string | null;
  program_code: string | null; department_code: string | null; school: string | null;
  name: string; version: string;
  effective_from_year: number; effective_to_year: number | null;
  /** "2020–2023 batches" / "2024 batch onward". */
  batch_label: string | null;
  total_credits: number | null; status: CurriculumStatus; is_active: boolean;
  published_at: string | null; source: CurriculumSource | null;
  component_count: number; flagged_component_count: number;
  semesters: CurriculumSemester[];
}

/** A degree programme. `school` matters because Open Elective eligibility is
 *  written in schools, not departments. */
export interface Program {
  id: number; code: string; name: string; short_name: string | null;
  degree_type: string; duration_years: number; total_semesters: number;
  department_id: number; department_code: string | null; school: string | null;
  curriculum_versions: number; is_active: boolean;
}

export interface ProgramDivision {
  id: number; program_id: number; admission_year: number; name: string;
  capacity: number | null; is_active: boolean; student_count: number;
  notes: string | null;
}

export interface Course {
  id: number; code: string; title: string; credits: number;
  department_id: number | null; department_code: string | null;
  department_name: string | null; offering_school: string | null;
  lecture_hours: number; tutorial_hours: number; practical_hours: number;
  description: string | null; prerequisites: string | null; syllabus_url: string | null;
  specialization_area: string | null; platform: string | null;
  provider_url: string | null; duration_weeks: number | null; is_active: boolean;
}

export interface CourseSection {
  id: number; course_offering_id: number; name: string;
  /** null = no ceiling (Program Core Electives). */
  capacity: number | null;
  seats_filled: number; seats_available: number | null; is_full: boolean;
  faculty_id: number | null; faculty_name: string | null;
  venue: string | null; schedule_note: string | null; is_active: boolean;
  division_breakdown: { division: string; count: number }[];
}

export interface CourseOffering {
  id: number; course: Course; semester_id: number; semester_number: number | null;
  curriculum_component_id: number | null; component_code: string | null;
  component_title: string | null; elective_type_id: number | null;
  /** Minimum students for the course to run at all (40). */
  min_students_to_run: number;
  /** Per-SECTION ceiling (75 for Open Electives); null = no limit. */
  section_capacity: number | null;
  allow_multiple_sections: boolean;
  eligible_divisions: string[];
  seats_filled: number; sections_needed: number; is_viable: boolean;
  sections: CourseSection[];
  status: string;
  registration_opens_at: string | null; registration_closes_at: string | null;
  venue: string | null; schedule_note: string | null; coordinator_name: string | null;
  notes: string | null; is_open: boolean | null; my_preference_order: number | null;
}

export interface Viability {
  offering_id: number; course_code: string; course_title: string;
  demand: number; min_students_to_run: number; section_capacity: number | null;
  allow_multiple_sections: boolean; runs: boolean; shortfall: number;
  planned_sections: number[]; existing_sections: number;
  division_breakdown: { division: string; count: number }[];
  eligible_divisions: string[]; reason: string;
}

export interface DistributeResult {
  sections: number; assigned: number; detail: CourseSection[];
}

export interface Preference {
  id: number; curriculum_component_id: number; component_code: string | null;
  course_offering_id: number; course_code: string | null; course_title: string | null;
  preference_order: number; status: string; submitted_at: string | null;
}

export interface Allocation {
  id: number; student_id: number; student_name: string | null;
  roll_number: string | null; division: string | null;
  section_id: number | null; section_name: string | null;
  curriculum_component_id: number;
  component_code: string | null; component_title: string | null;
  course_offering_id: number; course_code: string | null; course_title: string | null;
  status: string; allocation_round: number; strategy: string | null;
  preference_order_granted: number | null; is_manual_override: boolean;
  allocated_at: string | null; remarks: string | null;
}

export interface ElectiveWorkspace {
  component: CurriculumComponent; eligible: boolean; eligibility_notes: string[];
  /** The backend's decision on whether this student may write right now. */
  window_open: boolean;
  opens_at: string | null; closes_at: string | null;
  registration_state: StudentRegistrationState;
  registration_label: string | null;
  /** Why the student cannot act, when they cannot. */
  registration_reason: string | null;
  window_title: string | null;
  min_preferences: number;
  max_preferences: number; offerings: CourseOffering[]; my_preferences: Preference[];
  my_allocation: Allocation | null;
  /** Set when the round is two-stage: tick subjects here instead of ranking. */
  round: StudentRound | null;
}

export type RoundSelectionMode = "RANKED" | "TWO_STAGE";
export type RoundStage = "INTEREST" | "FINAL";

export interface RoundSubject {
  course_id: number; code: string; title: string; credits: number | null;
}

export interface StudentRound {
  id: number; title: string; stage: RoundStage; pick_count: number;
  opens_at: string | null; closes_at: string | null;
  can_submit: boolean; reason: string | null;
  subjects: RoundSubject[]; my_course_ids: number[]; submitted_at: string | null;
  my_interest_course_ids: number[];
  /** The curriculum slots this round fills, e.g. PE2 and PE3. */
  slot_codes: string[]; slot_titles: string[];
}

export interface InterestTally {
  stage: RoundStage; voters: number; eligible_student_count: number;
  interest_pick_count: number | null; slot_count: number;
  subjects: { course_id: number; code: string; title: string; votes: number; in_round: boolean }[];
}

export interface FinaliseResult {
  dry_run: boolean; minimum: number; pick_count: number;
  subjects: { course_id: number; code: string; title: string; demand: number;
    runs: boolean; seated: number }[];
  students_placed: number; by_choice: number; replaced_withdrawn: number;
  placed_no_submission: number; unplaced: number; seats_written: number; notes: string[];
}

export interface Subject {
  offering_id: number; course_id: number; code: string; title: string;
  credits: number | null; description: string | null; component_id: number;
  registration_window_id: number | null;
}

export interface AllocationStrategy {
  key: string; label: string; description: string; is_available: boolean;
}

export interface AllocationRunResult {
  strategy: string; dry_run: boolean; allocated: number; waitlisted: number;
  unallocated: number; notes: string[]; preview: Allocation[];
}

export interface MoocRegistration {
  id: number; student_id: number; student_name: string | null;
  roll_number: string | null; course_offering_id: number | null; course_code: string | null;
  option: MoocOption; mooc_round_id: number | null;
  course_title: string | null; platform: string; platform_registration_id: string | null;
  course_url: string | null; status: string; exam_date: string | null;
  exam_city: string | null; exam_fee_paid: boolean; exam_fee_reference: string | null;
  certificate_url: string | null; verification_status: string; verified_at: string | null;
  final_score: number | null; grade: string | null; remarks: string | null;
}

export type MoocOption = "NPTEL" | "NCC";
export type MoocRoundStatus = "DRAFT" | "OPEN" | "LOCKED" | "CLOSED";
export type MoocOutcome = "CLEARED" | "CARRIED_OVER" | "BACKLOG";

export interface MoocCourse {
  course_id: number; code: string; title: string; weeks: number | null;
  credits: number | null; url: string | null; discipline: string | null;
  instructors: string | null; institute: string | null;
  coordinating_institute: string | null; chosen_count: number | null;
}

export interface MoocRound {
  id: number; title: string; message: string | null; status: MoocRoundStatus;
  department_id: number | null; curriculum_component_id: number;
  component_code: string | null; component_title: string | null;
  component_semester: number | null; eligible_semesters: number[];
  opens_at: string | null; closes_at: string | null; platform_deadline: string | null;
  locked_at: string | null; closed_at: string | null; is_open: boolean;
  is_past_deadline: boolean; course_count: number; covered_count: number;
  carry_over_count: number; chosen_count: number; nptel_count: number; ncc_count: number;
  certificates_waiting: number; verified_count: number; failed_count: number;
  can_manage: boolean;
}

export interface MoocChoice {
  registration_id: number; option: MoocOption; course: MoocCourse | null;
  status: string; verification_status: string; certificate_url: string | null;
  remarks: string | null; updated_at: string | null;
}

export interface StudentMoocRound {
  id: number; title: string; message: string | null; status: MoocRoundStatus;
  opens_at: string | null; closes_at: string | null; platform_deadline: string | null;
  can_choose: boolean; reason: string | null; carry_over: boolean;
  courses: MoocCourse[]; choice: MoocChoice | null; can_submit_result: boolean;
}

export interface StudentMoocStanding {
  component_id: number | null; component_code: string | null;
  component_title: string | null; component_semester: number | null;
  standing: MoocOutcome | null; round: StudentMoocRound | null;
}

export interface MoocRosterRow {
  student_id: number; student_name: string | null; roll_number: string | null;
  semester: number | null; carry_over: boolean; registration_id: number | null;
  option: MoocOption | null; course_code: string | null; course_title: string | null;
  status: string | null; verification_status: string | null; certificate_url: string | null;
}

export interface MoocSlot {
  component_id: number; code: string; title: string; semester_number: number;
  program_code: string; curriculum_version: string; department_id: number | null;
}

export interface MoocEligibility {
  eligible: boolean; reasons: string[];
  component: { id: number; code: string; title: string; semester_number: number;
    credits: number; scope_label: string | null } | null;
}

// ── minors ─────────────────────────────────────────────────────────────
export interface MinorCourse {
  id: number; course_id: number; course_code: string | null;
  course_title: string | null; credits: number | null; sequence: number;
  semester_offset: number; is_mandatory: boolean; is_completed: boolean;
}

export interface MinorProgram {
  id: number; code: string; name: string; description: string | null;
  department_id: number; department_name: string | null; total_credits: number;
  capacity: number; seats_filled: number; seats_available: number;
  eligible_from_semester: number; min_cpi: number | null; max_backlogs: number | null;
  allocation_strategy: string; application_opens_at: string | null;
  application_closes_at: string | null; coordinator_name: string | null;
  is_active: boolean; courses: MinorCourse[]; is_eligible: boolean | null;
  eligibility_notes: string[]; my_application_status: string | null;
  // Published rules, sourced from the programme record rather than restated
  // in the UI, so the portal never states a policy the data does not carry.
  continuation_rule: string | null; rule_source: string | null;
  rule_source_url: string | null; offered_semesters: number[];
  window_open: boolean;
  /** Whether the signed-in person coordinates this minor. */
  can_manage?: boolean;
  /** Semesters in which students apply (the first eligible one by default). */
  application_semesters?: number[];
  /** Fee per semester, set by the coordinator; empty until announced. */
  fees?: { semester: number; amount: number; due_on: string | null; note: string | null }[];
}

export interface MinorApplication {
  id: number; student_id: number; student_name: string | null;
  roll_number: string | null; minor_program_id: number; minor_name: string | null;
  minor_department: string | null; preference_order: number; status: string;
  cpi_at_application: number | null; backlogs_at_application: number | null;
  semester_at_application: number | null; motivation: string | null;
  allocation_score: number | null; submitted_at: string | null;
  decided_at: string | null; remarks: string | null;
}

export interface CourseSyllabus {
  units: { title: string; topics: string[]; hours: number | null }[];
  outcomes: string[]; references: string[];
  hours: { lecture: number; tutorial: number; practical: number };
  file_url: string | null; link: string | null; updated_at: string | null;
}

export interface MinorPlanSemester {
  semester: number; when: "past" | "current" | "upcoming";
  courses: {
    minor_course_id: number; code: string; title: string; credits: number;
    result: { marks: number | null; grade: string | null; status: "IN_PROGRESS" | "PASSED" | "FAILED" } | null;
    /** As the offering department publishes it; null until published. */
    syllabus: CourseSyllabus | null;
  }[];
  fee: { amount: number; due_on: string | null; note: string | null } | null;
  payment: { amount: number; reference: string | null; paid_on: string | null } | null;
}

export interface MinorEnrollment {
  id: number; minor_program_id: number; minor_name: string | null;
  minor_department: string | null; status: string; started_semester: number | null;
  credits_completed: number; total_credits: number | null; progress_percent: number;
  courses: MinorCourse[];
  /** Semester by semester: courses with results, and that semester's fee. */
  plan?: MinorPlanSemester[];
  current_semester?: number | null;
}

export interface MinorWorkspace {
  is_eligible: boolean; eligibility_notes: string[]; programs: MinorProgram[];
  applications: MinorApplication[]; enrollment: MinorEnrollment | null;
}

// ── internships ────────────────────────────────────────────────────────
export interface Organization {
  id: number; name: string; type: string; field_of_work: string | null;
  description: string | null; address: string | null; city: string | null;
  district: string | null; state: string | null; country: string;
  pincode: string | null; phone: string | null; email: string | null;
  website: string | null; contact_person: string | null;
  contact_designation: string | null; is_verified: boolean;
}

export interface Stage {
  id: number; code: string; name: string; description: string | null; sequence: number;
  is_mandatory: boolean; requires_document: boolean; document_type: string | null;
  owner_role: string;
}

export type StageStatus =
  | "LOCKED" | "PENDING" | "IN_PROGRESS" | "SUBMITTED" | "APPROVED" | "REJECTED" | "SKIPPED";

export interface StageProgress {
  stage: Stage; status: StageStatus; submitted_at: string | null;
  reviewed_at: string | null; remarks: string | null; is_current: boolean;
}

export interface EvaluationCriteria {
  id: number; code: string; name: string; description: string | null;
  max_marks: number; weight: number; sequence: number; evaluator_role: string;
  /** Industry-mentor component — sourced outside the institution. */
  is_external: boolean;
}

export interface EvaluationScore {
  id: number; criteria_id: number; criteria_name: string | null;
  max_marks: number | null; marks: number | null; is_absent: boolean;
  comments: string | null;
}

export interface Evaluation {
  id: number; enrollment_id: number; evaluator_user_id: number | null;
  evaluator_name: string | null; evaluator_role: string; evaluation_round: number;
  status: string; is_absent: boolean; total_marks: number | null;
  max_marks: number | null; grade: string | null; comments: string | null;
  submitted_at: string | null; scores: EvaluationScore[];
}

export interface InternshipProgram {
  id: number; code: string; name: string; type: string; description: string | null;
  department_id: number | null; target_semester: number | null; credits: number;
  /** First semester the programme is shown in (CSSI: II, the semester before it runs). */
  announce_from_semester?: number | null;
  /** Where the programme stands for the signed-in student. */
  phase?: "HIDDEN" | "ANNOUNCED" | "ACTIVE" | "CONCLUDED";

  requires_group: boolean; default_group_size: number; requires_organization: boolean;

  /** Students per mentor; `confirmed` is false while it is the portal default. */
  mentor_capacity: number; mentor_capacity_confirmed: boolean;
  /** Whether the signed-in person may manage it (their coordinator scope). */
  can_manage?: boolean;
  /** The coordinator role that runs this programme. */
  coordination_domain?: CoordinationDomain | null;
  /** Ways to take the programme (Semester VIII), with what each asks for. */
  tracks?: ProgramTrack[];
  /** "for students admitted in 2024 or later"; null when every batch. */
  batch_note?: string | null;
  /** What the department still has to confirm, e.g. ["stages", "rubric"]. */
  needs_confirmation?: string[];
  /** Set once the coordinator locks the mentor allocation. */
  mentor_allocation_locked_at?: string | null;
  /** The mentors in a locked allocation; empty while unlocked. */
  mentor_allocation_ids?: number[];
  allowed_organization_types: string[]; report_frequency: string;
  expected_report_count: number; requires_industry_mentor: boolean;
  registration_opens_at: string | null; registration_closes_at: string | null;
  start_date: string | null; end_date: string | null; status: string;
  coordinator_name: string | null; stages: Stage[]; criteria: EvaluationCriteria[];
  enrolled_count: number; completed_count: number; group_count: number;
  my_enrollment_id: number | null; can_enroll: boolean;
  enroll_blocked_reason: string | null;
  /** Coordinator-run windows this programme uses; empty = semester rules only. */
  window_kinds: InternshipWindowKind[];
}

export type InternshipWindowKind = "REGISTRATION" | "PRESENTATION";
export type InternshipWindowState = "SCHEDULED" | "OPEN" | "CLOSED";

export interface InternshipWindow {
  id: number; program_id: number; kind: InternshipWindowKind; title: string;
  message: string; opens_at: string; closes_at: string;
  cohort_semester: number | null; submission_due_at: string | null;
  presentation_from: string | null; presentation_to: string | null;
  closed_early_at: string | null;
  /** Computed by the server at request time. */
  state: InternshipWindowState;
}

export interface ProgramWindows {
  kinds: InternshipWindowKind[]; windows: InternshipWindow[]; can_manage: boolean;
  registered_count: number; unassigned_count: number;
}

export interface MentorRosterGroup {
  faculty_id: number; name: string; designation: string | null; email: string | null;
  cabin: string | null; roll_range: string;
  students: { roll_number: string; name: string }[];
}

export interface InternshipGroup {
  id: number; program_id: number; name: string; faculty_id: number | null;
  faculty_name: string | null; faculty_designation: string | null;
  faculty_cabin: string | null; faculty_email: string | null; capacity: number;
  member_count: number; meeting_schedule: string | null;
}

export interface ProjectTeam {
  id: number; name: string; leader_enrollment_id: number | null; is_fixed: boolean;
  members: { enrollment_id: number; name: string; roll_number: string }[];
}

export interface ProgramTrack {
  key: string; label: string; description: string | null;
  requires_organization: boolean; organization_types: string[]; requires_supervisor: boolean;
  /** Stage codes this track runs; the rest are skipped for its students. */
  stages?: string[];
}

export interface EnrollmentSummary {
  id: number; program_id: number; program_code: string | null; student_id: number;
  program_type?: string | null;
  program_name?: string | null; track?: string | null; track_label?: string | null;
  /** Project team (Semester VII / VIII). */
  team?: ProjectTeam | null;
  /** Guides ranked by the student or their team, most preferred first. */
  guide_preferences?: { faculty_id: number; name: string }[];
  student_name: string | null; roll_number: string | null;
  department_code: string | null; division: string | null; semester: number | null;
  avatar_url: string | null; group_id: number | null; group_name: string | null;
  mentor_faculty_id: number | null; mentor_name: string | null;
  organization_id: number | null; organization_name: string | null; status: string;
  current_stage: string | null; progress_percent: number;
  evaluation_status: string | null; final_marks: number | null;
  final_grade: string | null;
}

export interface InternshipDocument {
  id: number; document_type: string; title: string | null; file_id: number;
  file_name: string | null; file_url: string | null; content_type: string | null;
  size_bytes: number | null; status: string; stage_id: number | null;
  remarks: string | null; created_at: string;
}

export interface InternshipReport {
  id: number; report_type: string; sequence_number: number; title: string | null;
  period_start: string | null; period_end: string | null; summary: string | null;
  tasks_completed: string | null; challenges: string | null; next_plan: string | null;
  hours_spent: number | null; file_url: string | null; status: string;
  submitted_at: string | null; reviewed_at: string | null; feedback: string | null;
}

export interface ProjectDetail {
  title: string | null; problem_statement: string | null; approach: string | null;
  outcomes: string | null; technologies: string | null; beneficiaries: string | null;
  extra: Record<string, unknown>;
}

export interface MentorSummary {
  id: number; name: string; designation: string; department: string | null;
  cabin: string | null; email: string | null; phone: string | null;
  specialization: string | null; avatar_url: string | null;
}

export interface MentorCapacity {
  faculty_id: number;
  /** In the locked allocation (always false while it is unlocked). */
  in_allocation?: boolean;
  name: string;
  employee_code: string | null;
  department_code: string | null;
  designation: string | null;
  avatar_url: string | null;
  assigned_count: number;
  max_capacity: number;
  /** False while max_capacity is the portal default, not a confirmed figure. */
  capacity_confirmed: boolean;
  remaining_capacity: number;
  is_full: boolean;
}

export type DocumentStatus =
  | "NOT_SUBMITTED" | "DRAFT" | "SUBMITTED" | "UNDER_REVIEW"
  | "VERIFIED" | "REJECTED" | "APPROVED" | "REVISION_REQUESTED";

export interface ExpectedDocument {
  key: string; label: string; kind: "stage" | "report";
  status: DocumentStatus;
  is_mandatory: boolean; is_submitted: boolean; is_satisfied: boolean;
  awaits_review: boolean;
  document_type: string | null; stage_id: number | null;
  stage_code: string | null; week_number: number | null;
  document_id: number | null; report_id: number | null; file_id: number | null;
  file_name: string | null;
  /** Authorised API route; null when nothing has been submitted. */
  file_url: string | null;
  size_bytes: number | null; content_type: string | null;
  submitted_at: string | null; reviewed_at: string | null;
  reviewed_by: string | null; review_comment: string | null;
  revision: number;
  period_start: string | null; period_end: string | null;
}

export interface DocumentGroup {
  title: string; submitted: number; satisfied: number; total: number;
  items: ExpectedDocument[];
}

export interface InternshipProgress {
  completed: number; total: number; percent: number; blockers: string[];
}

export interface EnrollmentDetail extends EnrollmentSummary {
  /** {min, max} when this student may work in a team; null otherwise. */
  team_limits?: { min?: number; max?: number } | null;
  /** How many guides may be ranked; 0 when the programme takes none. */
  preference_limit?: number;
  report_frequency?: string | null;
  email: string | null; phone: string | null; guardian_name: string | null;
  guardian_phone: string | null; start_date: string | null; end_date: string | null;
  location: string | null; stipend: number | null; industry_mentor_name: string | null;
  industry_mentor_email: string | null; industry_mentor_phone: string | null;
  industry_mentor_designation: string | null; industry_mentor_feedback: string | null;
  coordinator_remarks: string | null; organization: Organization | null;
  project: ProjectDetail | null; stages: StageProgress[];
  documents: InternshipDocument[]; reports: InternshipReport[];
  evaluations: Evaluation[]; criteria: EvaluationCriteria[];
  mentor: MentorSummary | null;
  report_schedule: { sequence_number: number; report_type: string;
    period_start: string; period_end: string }[];
  document_groups: DocumentGroup[];
  progress: InternshipProgress | null;
}

// ── community ──────────────────────────────────────────────────────────
export interface Club {
  id: number; name: string; slug: string; category: string; tagline: string | null;
  description: string | null; logo_url: string | null; instagram_url: string | null;
  linkedin_url: string | null; website_url: string | null; email: string | null;
  founded_year: number | null; faculty_advisor_id: number | null;
  faculty_advisor_name: string | null; is_active: boolean; member_count: number;
  upcoming_event_count: number; head_name: string | null; is_member: boolean | null;
}

export interface ClubMember {
  id: number; student_id: number; student_name: string | null;
  roll_number: string | null; avatar_url: string | null; role: string;
  position_title: string | null; joined_at: string | null;
}

export interface CampusEvent {
  id: number; title: string; slug: string; event_type: string; summary: string | null;
  description: string | null; start_at: string; end_at: string | null;
  venue: string | null; mode: string; meeting_url: string | null;
  registration_required: boolean; registration_deadline: string | null;
  capacity: number | null; poster_url: string | null; external_url: string | null;
  speaker: string | null; tags: string[]; status: string; club_id: number | null;
  club_name: string | null; club_slug: string | null; registration_count: number;
  interest_count: number; seats_available: number | null; is_full: boolean;
  registration_open: boolean; my_registration_status: string | null;
  am_i_interested: boolean;
}

export interface ClubDetail extends Club { members: ClubMember[]; events: CampusEvent[] }

export interface EventRegistrationRow {
  id: number; event_id: number; event_title: string | null; student_id: number;
  student_name: string | null; roll_number: string | null;
  department_code: string | null; semester: number | null; email: string | null;
  status: string; registered_at: string | null;
}

export interface CalendarItem {
  id: string; title: string; start_at: string; end_at: string | null;
  all_day: boolean; kind: string; category: string | null; location: string | null;
  link: string | null; status: string | null;
}

// ── people & engagement ────────────────────────────────────────────────
export interface StudentRow {
  id: number; user_id: number; full_name: string; email: string; phone: string | null;
  avatar_url: string | null; roll_number: string; enrollment_number: string | null;
  program_id: number; program_name: string | null; department_id: number;
  department_code: string | null; admission_year: number; current_semester: number;
  division: string | null; batch: string | null; cpi: number | null;
  backlog_count: number; status: string;
}

export interface FacultyRow {
  id: number; user_id: number; full_name: string; email: string;
  employee_code: string; department_id: number; department_code: string | null;
  department_name: string | null; designation: string; cabin: string | null;
  public_email: string | null; public_phone: string | null;
  specialization: string | null; qualification: string | null;
  avatar_url: string | null; bio: string | null; is_mentor: boolean;
  is_active: boolean; mentee_count: number;
  /** A fictional demo persona, not a real PDEU faculty member. */
  is_demo: boolean;
  /** Where the published details came from. */
  profile_url: string | null;
}

export interface DepartmentRow {
  id: number; code: string; name: string; short_name: string | null; school: string;
  description: string | null; is_active: boolean; student_count: number;
  faculty_count: number; program_count: number;
  hod_faculty_id: number | null; hod_name: string | null;
}

export interface MentorProfile {
  faculty_id: number; full_name: string; designation: string;
  department_name: string | null; department_code: string | null;
  cabin: string | null; email: string | null; phone: string | null;
  specialization: string | null; qualification: string | null;
  avatar_url: string | null; bio: string | null;
}

export interface MenteeRow {
  student_id: number; full_name: string; roll_number: string; email: string | null;
  phone: string | null; department_code: string | null; program_name: string | null;
  semester: number; division: string | null; cpi: number | null;
  backlog_count: number; avatar_url: string | null; open_meetings: number;
}

export interface Meeting {
  id: number; student_id: number; student_name: string | null;
  roll_number: string | null; faculty_id: number; faculty_name: string | null;
  title: string; agenda: string | null; requested_at: string | null;
  proposed_slot: string | null; scheduled_at: string | null; duration_minutes: number;
  mode: string; location: string | null; status: string; outcome_notes: string | null;
}

export interface Announcement {
  id: number; title: string; body: string; category: string; priority: string;
  audience_type: string; audience_ref_id: number | null;
  audience_label: string | null; published_by_user_id: number | null;
  published_by_name: string | null; published_at: string | null;
  expires_at: string | null; is_pinned: boolean; is_published: boolean;
  link_url: string | null; attachment_url: string | null;
}

export interface Notification {
  id: number; type: string; title: string; message: string | null;
  link: string | null; priority: string; is_read: boolean; read_at: string | null;
  created_at: string;
}

export interface NotificationSummary { unread: number; items: Notification[] }

// ── dashboards ─────────────────────────────────────────────────────────
export interface StatCard {
  key: string; label: string; value: number; hint: string | null;
  trend_label: string | null; link: string | null;
}
export interface BreakdownItem { label: string; value: number; total: number | null }
export interface DeadlineItem {
  title: string; due_at: string | null; context: string | null;
  link: string | null; kind: string;
}
export interface ProgressItem {
  label: string; completed: number; total: number; link: string | null;
  /** The programme type (CSSI, SUMMER, SEMINAR, MAJOR_PROJECT, …) or MINOR. */
  kind?: string | null;
  status?: string | null;
  stage?: string | null;
  unit?: "stages" | "credits";
}
export interface ActivityItem {
  id: number; actor: string | null; action: string; entity_type: string;
  entity_id: number | null; description: string | null; created_at: string;
}

export interface DashboardEvent {
  id: number; title: string; start_at: string; venue: string | null;
  club: string | null; event_type: string; is_registered: boolean;
}
export interface DashboardAnnouncement {
  id: number; title: string; category: string; priority: string;
  published_at: string | null; excerpt: string;
}

export interface AllocatedElective {
  id: number;
  component_id: number;
  component_code: string | null;
  component_title: string | null;
  component_type: string | null;
  course_offering_id: number;
  course_code: string | null;
  course_title: string | null;
  credits: number;
  section_name: string | null;
  preference_order_granted: number | null;
  status: string;
  link: string | null;
}

export interface StudentDashboard {
  stats: StatCard[];
  curriculum_semester: {
    semester_number: number; total_credits: number;
    components: {
      id: number; code: string; title: string; component_type: string;
      scope_label: string | null; credits: number; status: string;
      /** The server's judgement that the slot waits on the student. */
      needs_action?: boolean;
      allocated_course_code?: string | null;
      allocated_course_title?: string | null;
      allocated_section?: string | null;
      preference_order_granted?: number | null;
    }[];
  } | null;
  allocated_electives?: AllocatedElective[];
  action_items: DeadlineItem[]; progress: ProgressItem[];
  upcoming_events: DashboardEvent[]; announcements: DashboardAnnouncement[];
  mentor: MentorSummary | null;
}

export interface FacultyDashboard {
  stats: StatCard[];
  pending_reviews: { type: string; id: number; enrollment_id: number; student: string;
    roll_number: string; label: string; submitted_at: string | null; link: string }[];
  mentees_preview: { student_id: number; name: string; roll_number: string;
    semester: number; cpi: number | null; avatar_url: string | null }[];
  internship_groups: { id: number; name: string; program_id: number;
    program: string | null; capacity: number; member_count: number }[];
  upcoming_meetings: { id: number; title: string; student: string; status: string;
    scheduled_at: string | null; proposed_slot: string | null }[];
  announcements: DashboardAnnouncement[];
  /** One per coordinated module (one per programme for internships). */
  portfolios: FacultyPortfolio[];
}

export interface PortfolioStat {
  label: string; value: number; hint: string | null;
  tone: "default" | "warning" | "success";
}

export interface FacultyPortfolio {
  domain: CoordinationDomain;
  department_id: number | null; department_code: string | null;
  department_name: string | null; is_institution_wide: boolean;
  /** Set for CSSI / Summer Internship: the programme this entry describes. */
  program_id: number | null; program_name: string | null;
  stats: PortfolioStat[];
  /** For a window-run programme (CSSI): each step's state, in order. */
  windows?: { kind: InternshipWindowKind; state: InternshipWindowState | "NOT_STARTED";
    closes_at: string | null }[];
}

export interface HodDashboard {
  department: { id: number; code: string; name: string };
  /** Who heads the department. */
  hod_name?: string | null;

  stats: StatCard[];
  /** One row per module: who coordinates it, or that nobody does. */
  modules: {
    domain: CoordinationDomain; label: string;
    coordinators: { assignment_id: number; faculty_id: number; name: string;
      designation: string }[];
    mentor_count: number; is_covered: boolean;
    /** Nobody is appointed, so the HoD runs it until someone is. */
    covered_by_hod?: boolean;
  }[];
  rounds: {
    id: number; code: string; title: string; component_type: string; status: string;
    opens_at: string | null; closes_at: string | null; is_accepting: boolean;
    eligible_student_count: number;
  }[];
  announcements: DashboardAnnouncement[];
}

export interface AdminDashboard {
  stats: StatCard[]; students_by_semester: BreakdownItem[];
  internship_progress: BreakdownItem[]; pending_actions: StatCard[];
  recent_activity: ActivityItem[]; upcoming_events: DashboardEvent[];
}

export interface AuditLogRow {
  id: number; actor_user_id: number | null; actor_label: string | null;
  action: string; entity_type: string; entity_id: number | null;
  description: string | null; meta: Record<string, unknown>;
  ip_address: string | null; created_at: string;
}


export interface RankedApplicant {
  application_id: number; student_id: number;
  student_name: string; roll_number: string; department: string | null;
  cpi: number | null; backlog_count: number | null;
  preference_order: number; submitted_at: string | null;
  rank: number; within_capacity: boolean; note: string | null;
}

export interface RankingCriterion {
  field: string; direction: string; label: string | null;
}

/** A dry run of a minor allocation round — nothing is written. */
export interface MinorAllocationPreview {
  program_id: number; program_name: string;
  capacity: number; seats_filled: number; seats_available: number;
  applicants: number; would_allocate: number;
  criteria: RankingCriterion[];
  ranking: RankedApplicant[];
}

export interface MinorAllocationResult {
  program_id: number; allocated: number; waitlisted: number;
  seats_filled: number; ranking: RankedApplicant[];
}


/** A role an administrator may grant, and what it permits inside a scope. */
export interface RoleDefinition {
  value: string;
  label: string;
  description: string;
}

// ── registration rounds ────────────────────────────────────────────────────
/** What a student may do in an elective round right now. Derived by the
 *  backend from the round, the clock and their own rows — the UI reflects this
 *  decision rather than making its own from a countdown. */
export type StudentRegistrationState =
  | "NOT_OPEN" | "OPEN" | "SUBMITTED" | "LOCKED" | "ALLOCATED" | "CLOSED";

export type RegistrationWindowStatus =
  | "DRAFT" | "OPEN" | "LOCKED" | "ALLOCATED" | "PUBLISHED" | "CLOSED";

export interface RegistrationWindow {
  id: number; code: string; title: string; description: string | null;
  component_type: ComponentType; status: RegistrationWindowStatus;
  department_id: number | null; department_code: string | null;
  academic_year_id: number | null; semester_id: number | null;
  opens_at: string | null; closes_at: string | null;
  eligible_semesters: number[];
  eligible_program_ids: number[]; eligible_program_codes: string[];
  eligible_divisions: string[];
  min_preferences: number | null; max_preferences: number | null;
  locked_at: string | null; allocated_at: string | null; published_at: string | null;
  notes: string | null;
  offering_count: number; eligible_student_count: number;
  submitted_student_count: number; allocated_count: number;
  /** True when the clock has passed the deadline, whatever the status says. */
  is_past_deadline: boolean;
  is_accepting: boolean;
  /** The curriculum slots this round's courses belong to. */
  slots: { id: number; code: string; title: string; semester_number: number;
    curriculum_id: number }[];
  /** Semester of those slots; a round for the semester before is choosing ahead. */
  slot_semester: number | null;
  /** False for a Head of Department, who reads rounds but does not drive them. */
  can_manage: boolean;
  selection_mode: RoundSelectionMode; stage: RoundStage | null;
  interest_pick_count: number | null; final_pick_count: number | null;
  min_students_to_run: number | null; section_capacity: number | null;
  interest_closed_at: string | null;
}

/** A curriculum slot a coordinator may open a round for, with its courses. */
export interface RoundSlot {
  component_id: number; code: string; title: string; component_type: ComponentType;
  semester_number: number; scope_label: string | null; credits: number;
  curriculum_id: number; curriculum_version: string;
  program_id: number; program_code: string; program_name: string;
  department_id: number;
  /** Programme data — never a fixed A–D. */
  divisions: string[];
  offerings: { id: number; course_code: string; course_title: string;
    department_code: string | null; registration_window_id: number | null;
    /** Which year's offering, e.g. 2026-27 — the same course recurs each year. */
    academic_year: string | null;
    /** Students already seated in it (an earlier cohort). */
    seats_taken: number }[];
}

// ── unified student profile ────────────────────────────────────────────────
export interface ProfilePersonal {
  student_id: number; full_name: string; email: string; phone: string | null;
  roll_number: string; enrollment_number: string | null;
  program_name: string | null; program_code: string | null;
  department_code: string | null; school: string | null;
  batch: string | null; division: string | null;
  admission_year: number; current_semester: number; status: string;
}

export interface ProfileAcademic {
  curriculum_name: string | null; curriculum_version: string | null;
  curriculum_status: string | null; batch_label: string | null;
  cpi: number | null; backlog_count: number;
  current_semester_components: {
    code: string; title: string; type: string; credits: number; is_elective: boolean;
  }[];
  elective_allocations: {
    component: string | null; component_code: string | null;
    course_code: string; course_title: string; section: string | null; status: string;
  }[];
  mooc_registrations: {
    course: string | null; platform: string; status: string; verification: string;
  }[];
  minor_name: string | null; minor_status: string | null;
}

export interface ProfileInternship {
  enrollment_id: number; program_name: string; program_type: string | null;
  status: string; organization: string | null; faculty_mentor: string | null;
  progress_percent: number; completed_items: number; total_items: number;
}

export interface ProfileDocument {
  enrollment_id: number; group: string | null; label: string;
  document_type: string | null; week: number | null;
  status: string; is_mandatory: boolean;
  file_id: number | null; file_url: string | null;
  submitted_at: string | null; reviewer_comment: string | null;
}

export interface ProfileEvaluation {
  enrollment_id: number; evaluator_role: string; status: string;
  total_marks: number | null; max_marks: number | null;
  remarks: string | null; grade: string | null;
  scores: {
    criterion: string | null; marks: number | null;
    max_marks: number | null; comment: string | null;
  }[];
}

export interface ProfileMentor {
  faculty_id: number; full_name: string | null; email: string | null;
  cabin: string | null; designation: string | null; department_code: string | null;
  meetings_visible: boolean;
  recent_meetings: {
    title: string; status: string; requested_at: string | null;
    scheduled_at: string | null; mode: string | null;
  }[];
}

export interface StudentProfile {
  personal: ProfilePersonal;
  academic: ProfileAcademic | null;
  internships: ProfileInternship[];
  documents: ProfileDocument[];
  evaluations: ProfileEvaluation[];
  mentor: ProfileMentor | null;
  /** Which sections this viewer was allowed to see, so a gap can be explained
   *  rather than looking like missing data. */
  visible_sections: string[];
}

export interface ChatActionLink {
  title: string;
  path: string;
}

export interface ChatMessageItem {
  role: "user" | "assistant";
  content: string;
}

export interface ChatQueryResponse {
  reply: string;
  role_context: string;
  suggestions: string[];
  action_links: ChatActionLink[];
  is_confidential_block: boolean;
  timestamp: string;
}

export interface ChatInitialConfigResponse {
  role_context: string;
  user_name: string;
  greeting: string;
  suggestions: string[];
}


// ── Faculty performance score ─────────────────────────────────────────────
export type ScoreCategory = "REVIEW" | "MARKS" | "MEETING";
export type ScoreOutcome = "ON_TIME" | "LATE" | "OVERDUE" | "MISSED";

export interface ScoreEntry {
  when: string; category: ScoreCategory; label: string; outcome: ScoreOutcome;
  points: number; days: number | null;
}

export interface FacultyScore {
  faculty_id: number; name: string; designation: string | null; is_demo: boolean;
  /** False for real faculty until the department switches scoring on. */
  is_scored: boolean;
  /** Out of 100: the average item, worst outcome 0 to best 100. */
  score: number | null;
  points: number; on_time: number; late: number; overdue: number; missed: number;
  /** Waiting, still within time — not scored yet. */
  pending: number; scored: number;
  on_time_rate: number | null;
  band: "Excellent" | "Good" | "Needs attention" | "At risk" | "Not enough activity"
    | "Not scored yet";
  by_category: Partial<Record<ScoreCategory, number>>;
  entries: ScoreEntry[];
}

export type ScorePolicy = Record<string, number>;

export interface DepartmentScores {
  department_code: string; department_name: string;
  policy: ScorePolicy; scores_real_faculty: boolean; faculty: FacultyScore[];
}
