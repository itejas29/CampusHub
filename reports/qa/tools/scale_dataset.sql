-- Grow a synthetic QA database to :target students (default 10,000) for volume tests.
-- Synthetic only: @scale.campushub.example.com, no real people. Run on a COPY.
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE scale_params AS
SELECT (SELECT count(*) FROM students) AS existing,
       10000 - (SELECT count(*) FROM students) AS add_n,
       (SELECT hashed_password FROM users WHERE email = 'aarav.desai.001@campushub.example.com') AS pw,
       (SELECT id FROM departments WHERE code = 'ICT') AS ict,
       (SELECT id FROM programs WHERE code = 'B.TECH-ICT') AS prog;

INSERT INTO users (email, hashed_password, full_name, is_active, created_at, updated_at)
SELECT 'scale' || g || '@scale.campushub.example.com', p.pw, 'Scale Student ' || g, true, now(), now()
FROM scale_params p, generate_series(1, (SELECT add_n FROM scale_params)) g;

INSERT INTO user_roles (user_id, role)
SELECT u.id, 'STUDENT' FROM users u WHERE u.email LIKE '%@scale.campushub.example.com';

INSERT INTO students (user_id, roll_number, program_id, department_id, admission_year, current_semester,
                      division, cpi, backlog_count, status, created_at, updated_at)
SELECT u.id, 'S' || lpad(substring(u.email from 'scale(\d+)@')::text, 7, '0'), p.prog, p.ict,
       2026 - ((n % 8) / 2 + 1), (n % 8) + 1, chr(65 + n % 3), 6 + (n % 40) / 10.0, (CASE WHEN n % 3 = 0 THEN 1 ELSE 0 END), 'ACTIVE', now(), now()
FROM (SELECT u.*, substring(u.email from 'scale(\d+)@')::int AS n FROM users u
      WHERE u.email LIKE '%@scale.campushub.example.com') u, scale_params p;

-- Academic mentors, round robin over the existing mentor pool.
WITH pool AS (SELECT faculty_id, row_number() OVER (ORDER BY faculty_id) - 1 AS k
              FROM (SELECT DISTINCT faculty_id FROM mentor_assignments WHERE is_active) d),
     size AS (SELECT count(*) AS c FROM pool),
     s AS (SELECT st.id, row_number() OVER (ORDER BY st.id) - 1 AS r FROM students st
           JOIN users u ON u.id = st.user_id WHERE u.email LIKE '%@scale.campushub.example.com')
INSERT INTO mentor_assignments (student_id, faculty_id, is_active, assigned_at, created_at, updated_at)
SELECT s.id, pool.faculty_id, true, now(), now(), now() FROM s, size JOIN pool ON true WHERE pool.k = s.r % size.c;

-- Summer Internship enrolments for the new Semester VI and VII students, mentors round robin.
WITH prog AS (SELECT id FROM internship_programs WHERE code = 'SI-2025'),
     pool AS (SELECT mentor_faculty_id AS f, row_number() OVER (ORDER BY mentor_faculty_id) - 1 AS k
              FROM (SELECT DISTINCT mentor_faculty_id FROM internship_enrollments
                    WHERE program_id = (SELECT id FROM prog) AND mentor_faculty_id IS NOT NULL) d),
     size AS (SELECT count(*) AS c FROM pool),
     s AS (SELECT st.id, row_number() OVER (ORDER BY st.id) - 1 AS r FROM students st
           JOIN users u ON u.id = st.user_id WHERE u.email LIKE '%@scale.campushub.example.com'
           AND st.current_semester IN (6, 7))
INSERT INTO internship_enrollments (program_id, student_id, mentor_faculty_id, status, registered_at, created_at, updated_at)
SELECT (SELECT id FROM prog), s.id, pool.f, 'IN_PROGRESS', now(), now(), now()
FROM s, size JOIN pool ON true WHERE pool.k = s.r % size.c;

INSERT INTO enrollment_stage_progress (enrollment_id, stage_id, status, data, created_at, updated_at)
SELECT e.id, st.id, CASE WHEN st.sequence <= 2 THEN 'APPROVED' WHEN st.sequence = 3 THEN 'SUBMITTED' ELSE 'PENDING' END,
       '{}'::json, now(), now()
FROM internship_enrollments e JOIN students s ON s.id = e.student_id JOIN users u ON u.id = s.user_id
JOIN internship_stages st ON st.program_id = e.program_id
WHERE u.email LIKE '%@scale.campushub.example.com';
COMMIT;
SELECT (SELECT count(*) FROM students) students, (SELECT count(*) FROM mentor_assignments) mentor_assignments,
       (SELECT count(*) FROM internship_enrollments) enrolments, (SELECT count(*) FROM enrollment_stage_progress) stage_rows;
