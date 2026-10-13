"""Demo dataset definitions. All names, roll numbers and organisations are fictional."""
from __future__ import annotations

# Departments, with the school each actually belongs to. Verified against the
# university's own course catalogue: Electrical, Chemical, Petroleum and
# Biotechnology sit under the School of Energy Technology, not the School of
# Technology. See docs/PHASE3B-RESEARCH.md.
#
# The engineering departments here are also created by the curriculum import;
# listing them keeps the codes in one place and adds the non-engineering
# schools, which contribute Open Elective courses but run no B.Tech programme.
DEPARTMENTS = [
    ("ICT", "Information and Communication Technology", "ICT", "SoT"),
    ("CSE", "Computer Science and Engineering", "CSE", "SoT"),
    ("ECE", "Electronics and Communication Engineering", "ECE", "SoT"),
    ("MEC", "Mechanical Engineering", "Mechanical", "SoT"),
    ("CIV", "Civil Engineering", "Civil", "SoT"),
    ("MATH", "Department of Mathematics", "Mathematics", "SoT"),
    ("CHM", "Chemical Engineering", "Chemical", "SoET"),
    ("EE", "Electrical Engineering", "Electrical", "SoET"),
    ("PTE", "Petroleum Engineering", "Petroleum", "SoET"),
    ("BIO", "Biotechnology", "Biotechnology", "SoET"),
    ("SLS", "School of Liberal Studies", "Liberal Studies", "SLS"),
    ("SOM", "School of Management", "Management", "SoM"),
]

#: Programmes are no longer declared here — they come from the researched
#: curriculum documents under `backend/curriculum/`, so the portal can never
#: invent a programme the university does not run. (The earlier seed listed a
#: "B.Tech in Computer Science and Engineering", which is not a PDEU programme
#: name: CSE is the *department*, and the programme it runs is Computer
#: Engineering.)
PROGRAMS: list[tuple[str, str, str]] = []

FACULTY = [
    # (name, email, employee code, dept, designation, cabin, specialization, extra roles)
    ("Dr. Anand Mehta", "anand.mehta@campushub.example.com", "ICT-F-101", "ICT",
     "Associate Professor", "6-201 B", "Computer Networks, Network Security", []),
    ("Dr. Priya Nair", "priya.nair@campushub.example.com", "ICT-F-102", "ICT",
     "Assistant Professor", "6-118", "Machine Learning, Computer Vision", []),
    ("Dr. Rakesh Bhatt", "rakesh.bhatt@campushub.example.com", "ICT-F-103", "ICT",
     "Professor", "6-014", "VLSI Design, Embedded Systems", []),
    ("Prof. Sneha Iyer", "sneha.iyer@campushub.example.com", "ICT-F-104", "ICT",
     "Assistant Professor", "6-207", "Signal Processing, Wireless Communication", []),
    ("Dr. Meera Krishnan", "meera.krishnan@campushub.example.com", "ICT-F-105", "ICT",
     "Assistant Professor", "6-121", "Human-Computer Interaction", []),
    # Internship mentors who also run the two elective families — holding both
    # kinds of role at once, which the portal resolves as the union.
    ("Dr. Vikram Joshi", "vikram.joshi@campushub.example.com", "ICT-F-106", "ICT",
     "Assistant Professor", "6-125", "Data Engineering, Databases", []),
    ("Prof. Leena Nambiar", "leena.nambiar@campushub.example.com", "ICT-F-107", "ICT",
     "Assistant Professor", "6-129", "Software Engineering, HCI", []),
    ("Dr. Kunal Shah", "kunal.shah@campushub.example.com", "CSE-F-201", "CSE",
     "Associate Professor", "5-112", "Distributed Systems, Cloud Computing", []),
    ("Dr. Farah Ansari", "farah.ansari@campushub.example.com", "CSE-F-202", "CSE",
     "Assistant Professor", "5-108", "Cyber Security, Cryptography", []),
    ("Dr. Suresh Pillai", "suresh.pillai@campushub.example.com", "MEC-F-301", "MEC",
     "Professor", "3-004", "Robotics, Mechatronics", []),
    # ── the other verified programmes ──
    ("Dr. Nandita Bose", "nandita.bose@campushub.example.com", "ECE-F-401", "ECE",
     "Associate Professor", "4-116", "VLSI, Embedded Systems", []),
    ("Dr. Imran Qureshi", "imran.qureshi@campushub.example.com", "ECE-F-402", "ECE",
     "Assistant Professor", "4-121", "Antennas, RF Engineering", []),
    ("Dr. Sunita Rathore", "sunita.rathore@campushub.example.com", "CIV-F-501", "CIV",
     "Professor", "2-011", "Structural Engineering, Earthquake Engineering", []),
    ("Prof. Devang Solanki", "devang.solanki@campushub.example.com", "CIV-F-502", "CIV",
     "Assistant Professor", "2-018", "Transportation, GIS", []),
    ("Dr. Alok Ranjan", "alok.ranjan@campushub.example.com", "CHM-F-601", "CHM",
     "Associate Professor", "7-105", "Process Design, Separation Sciences", []),
    ("Dr. Rupal Vasa", "rupal.vasa@campushub.example.com", "EE-F-701", "EE",
     "Associate Professor", "8-042", "Power Systems, Smart Grid", []),
    ("Dr. Hardik Chauhan", "hardik.chauhan@campushub.example.com", "PTE-F-801", "PTE",
     "Professor", "9-006", "Reservoir Engineering, Drilling", []),
    ("Dr. Ayesha Siddiqui", "ayesha.siddiqui@campushub.example.com", "BIO-F-901", "BIO",
     "Assistant Professor", "10-014", "Bioprocess Engineering", []),
]

# Coordination is scoped: (employee code, domain, department code or None).
# Deliberately split across faculty and departments so the scope rules are
# visible in the demo — the ICT summer coordinator cannot touch CSE's programme,
# and CSSI has a different coordinator from Summer Internship.
#: (employee code, assigned role, module/domain, department)
#: Coordinator and Mentor are independent grants. Nobody here holds both for the
#: same module by accident — the pairs that do exist are deliberate, so the
#: distinction is visible in the demo.
#: Head of each department, by employee code. The HoD appoints that
#: department's coordinators, holds no coordinator or mentor role, and has no
#: mentees — so the person named here appears nowhere in ROLE_ASSIGNMENTS and in
#: no mentor pool. ICT only for now; other departments follow.
HEADS_OF_DEPARTMENT = {
    "ICT": "ICT-F-103",   # Dr. Rakesh Bhatt
}

#: Department office accounts: day-to-day data administration, separate from the
#: HoD. They cannot appoint coordinators and are never offered as mentors.
DEPARTMENT_OFFICES = [
    # (name, email, employee code, dept)
    ("ICT Department Office", "ict.office@campushub.example.com", "ICT-A-001", "ICT"),
]

ROLE_ASSIGNMENTS = [
    # ── ICT coordinators — appointed by the HoD, Dr. Rakesh Bhatt ──
    ("ICT-F-102", "COORDINATOR", "SUMMER_INTERNSHIP", "ICT"),  # Dr. Priya Nair
    ("ICT-F-104", "COORDINATOR", "CSSI",              "ICT"),  # Prof. Sneha Iyer
    ("ICT-F-105", "COORDINATOR", "MOOC",              "ICT"),  # Dr. Meera Krishnan
    ("ICT-F-102", "COORDINATOR", "MINOR",             "ICT"),  # Dr. Priya Nair
    ("ICT-F-106", "COORDINATOR", "OPEN_ELECTIVE",     "ICT"),  # Dr. Vikram Joshi
    ("ICT-F-107", "COORDINATOR", "CORE_ELECTIVE",     "ICT"),  # Prof. Leena Nambiar
    ("ICT-F-101", "COORDINATOR", "MENTORSHIP",        "ICT"),  # Dr. Anand Mehta
    # ── ICT mentors — separate grants, different people ──
    ("ICT-F-101", "MENTOR",      "CSSI",              "ICT"),  # mentor, not CSSI lead
    ("ICT-F-106", "MENTOR",      "SUMMER_INTERNSHIP", "ICT"),
    ("ICT-F-101", "MENTOR",      "SUMMER_INTERNSHIP", "ICT"),
    ("ICT-F-107", "MENTOR",      "CSSI",              "ICT"),
    ("ICT-F-106", "MENTOR",      "CSSI",              "ICT"),
    # Dr. Meera Krishnan coordinates MOOC *and* mentors Summer students —
    # a user holding two roles at once, resolved as the union of both.
    ("ICT-F-105", "MENTOR",      "SUMMER_INTERNSHIP", "ICT"),
    # ── CSE — different people for the same domains ──
    ("CSE-F-201", "COORDINATOR", "SUMMER_INTERNSHIP", "CSE"),  # Dr. Kunal Shah
    ("CSE-F-202", "COORDINATOR", "CSSI",              "CSE"),  # Dr. Farah Ansari
    ("CSE-F-202", "COORDINATOR", "MOOC",              "CSE"),
    ("CSE-F-201", "COORDINATOR", "MINOR",             "CSE"),
    # ── Mechanical — partial on purpose, so the admin matrix shows gaps ──
    ("MEC-F-301", "COORDINATOR", "SUMMER_INTERNSHIP", "MEC"),
    ("MEC-F-301", "COORDINATOR", "MINOR",             "MEC"),
    # ── the other verified programmes; still deliberately uneven ──
    ("ECE-F-401", "COORDINATOR", "OPEN_ELECTIVE",     "ECE"),
    ("ECE-F-401", "COORDINATOR", "CORE_ELECTIVE",     "ECE"),
    ("ECE-F-402", "COORDINATOR", "CSSI",              "ECE"),
    ("ECE-F-402", "MENTOR",      "SUMMER_INTERNSHIP", "ECE"),
    ("CIV-F-501", "COORDINATOR", "SUMMER_INTERNSHIP", "CIV"),
    ("CIV-F-501", "COORDINATOR", "MINOR",             "CIV"),
    ("CIV-F-502", "MENTOR",      "CSSI",              "CIV"),
    ("CHM-F-601", "COORDINATOR", "MINOR",             "CHM"),
    ("EE-F-701",  "COORDINATOR", "OPEN_ELECTIVE",     "EE"),
    ("PTE-F-801", "COORDINATOR", "MINOR",             "PTE"),
    # Biotechnology has no coordinator: its curriculum is still a draft, and the
    # admin matrix should show that honestly rather than inventing cover.
]

#: Kept so older imports keep working; coordinators are a subset of the above.
COORDINATOR_ASSIGNMENTS = [
    (code, domain, dept) for code, role, domain, dept in ROLE_ASSIGNMENTS
    if role == "COORDINATOR"
]

# ── cohort generation ─────────────────────────────────────────────────────
# The elective rules only mean something at scale: a course needs 40 students
# to run and an Open Elective section holds 75, so a 14-student demo cannot
# show a second section opening. ICT therefore gets four realistic divisions.
ICT_DIVISIONS = ["A", "B", "C", "D"]
# 50 per division x 4 divisions = ~200 per year group, which is what makes
# the 40-minimum and 75-per-section rules observable in the demo.
STUDENTS_PER_DIVISION = 50

FIRST_NAMES = [
    "Aarav", "Ananya", "Vivaan", "Diya", "Aditya", "Ishita", "Arjun", "Saanvi",
    "Kabir", "Meera", "Rohan", "Tara", "Neel", "Riya", "Karan", "Nisha",
    "Yash", "Priya", "Dev", "Anika", "Rahul", "Sneha", "Manav", "Kavya",
    "Siddharth", "Aditi", "Varun", "Pooja", "Nikhil", "Shreya", "Om", "Isha",
    "Harsh", "Naina", "Raghav", "Simran", "Aryan", "Trisha", "Kunal", "Payal",
    "Vikram", "Anjali", "Rishi", "Divya", "Sameer", "Nandini", "Tanish", "Rhea",
    "Parth", "Gauri", "Aman", "Lavanya", "Krish", "Sanya", "Ved", "Mira",
    "Ishaan", "Aarohi", "Reyansh", "Myra",
]
SURNAMES = [
    "Desai", "Rao", "Kulkarni", "Joshi", "Patel", "Menon", "Sethi", "Bhatnagar",
    "Verma", "Kapoor", "Trivedi", "Chauhan", "Rane", "Pillai", "Shah", "Iyer",
    "Nair", "Mehta", "Reddy", "Gupta", "Malhotra", "Bose", "Chopra", "Sinha",
    "Agarwal", "Banerjee", "Naidu", "Deshmukh", "Ghosh", "Saxena",
]

#: (year group label, admission year, current semester)
#: Semester III carries CSSI and Semester II sees it as announced, so both
#: phases of the programme are visible in the demo data.
YEAR_GROUPS = [
    ("21BIT", 2021, 7),
    ("22BIT", 2022, 6),
    ("23BIT", 2023, 4),
    ("24BIT", 2024, 3),
    ("25BIT", 2025, 2),
]

# Named students kept stable so the demo credentials in the README keep working.
NAMED_STUDENTS = [
    # (name, roll, semester, division, cpi, backlogs, admission year)
    ("Aarav Desai", "22BIT001", 6, "A", 8.42, 0, 2022),
    ("Ishita Rao", "22BIT002", 6, "A", 9.11, 0, 2022),
    ("Rohan Kulkarni", "22BIT003", 6, "A", 7.28, 1, 2022),
    ("Meera Joshi", "22BIT004", 6, "B", 8.95, 0, 2022),
    ("Vivaan Patel", "22BIT005", 6, "B", 6.84, 2, 2022),
    ("Ananya Menon", "23BIT011", 4, "A", 8.63, 0, 2023),
    ("Kabir Sethi", "23BIT012", 4, "A", 7.95, 0, 2023),
    ("Diya Bhatnagar", "23BIT013", 4, "B", 9.32, 0, 2023),
    ("Arjun Verma", "21BIT021", 7, "A", 8.07, 0, 2021),
    ("Saanvi Kapoor", "21BIT022", 7, "A", 8.88, 0, 2021),
    ("Neel Trivedi", "21BIT023", 7, "B", 7.41, 1, 2021),
    # Semester III — CSSI is live for these students.
    ("Riya Chauhan", "24BIT031", 3, "A", 8.10, 0, 2024),
    ("Aditya Rane", "24BIT032", 3, "A", 7.62, 0, 2024),
    ("Tara Pillai", "24BIT033", 3, "B", 8.74, 0, 2024),
    # Semester II — CSSI has been floated to them but is not yet open.
    ("Ishaan Bhatt", "25BIT041", 2, "A", 8.22, 0, 2025),
    ("Nisha Rawal", "25BIT042", 2, "B", 7.88, 0, 2025),
    # Semester I — Freshers Induction & Foundation core. No CPI: it is
    # cumulative over completed semesters, and a first-semester student has
    # no results on record yet.
    ("Devansh Joshi", "25BIT091", 1, "A", None, 0, 2025),
    # Semester V — Program Core Elective & MOOC credits.
    ("Kavya Patel", "23BIT051", 5, "A", 8.35, 0, 2023),
    # Semester VIII — Capstone Project & Degree Completion.
    ("Pooja Shah", "21BIT081", 8, "A", 8.92, 0, 2021),
]


# ── demo cohorts for the other verified programmes ────────────────────────
# ICT keeps its full 814-student cohort — the Open Elective rules (40 to run,
# 75 per section) only become observable at that scale. The other programmes get
# enough students to exercise dashboards, curriculum, electives and faculty
# views without multiplying the seed by ten.
#
# Batches are chosen so each cohort sits on a curriculum that genuinely governs
# it. ECE and Electrical get 2022 batches, which the 2020-24 structures cover and
# which therefore reach Semester VII; the 2024-28 programmes get 2024 and 2025
# batches, the only ones those versions legitimately apply to. No cohort is
# placed on a curriculum its admission year falls outside of.
#
# (programme code, roll prefix, department, [(admission year, semester, per-division count)])
PROGRAM_COHORTS = [
    ("B.TECH-CE",    "BCE", "CSE", [(2024, 4, 22), (2025, 2, 18)]),
    ("B.TECH-CSBS",  "BCB", "CSE", [(2024, 4, 20), (2025, 2, 16)]),
    ("B.TECH-ECE",   "BEC", "ECE", [(2022, 7, 20), (2024, 4, 20), (2025, 2, 15)]),
    ("B.TECH-MECH",  "BME", "MEC", [(2024, 4, 20), (2025, 2, 15)]),
    ("B.TECH-CIVIL", "BCL", "CIV", [(2024, 4, 18), (2025, 2, 14)]),
    ("B.TECH-CHEM",  "BCH", "CHM", [(2024, 4, 18), (2025, 2, 14)]),
    ("B.TECH-ELEC",  "BEE", "EE",  [(2022, 7, 18), (2023, 5, 16)]),
    ("B.TECH-PETRO", "BPE", "PTE", [(2024, 4, 16), (2025, 2, 12)]),
    ("B.TECH-BIO",   "BBT", "BIO", [(2025, 2, 14)]),
]

#: Named accounts kept stable so they can be quoted as demo credentials.
#: (programme, name, roll, semester, division, cpi, backlogs, admission year)
NAMED_PROGRAM_STUDENTS = [
    ("B.TECH-CE", "Rhea Kulkarni", "24BCE001", 4, "A", 8.71, 0, 2024),
    ("B.TECH-CSBS", "Aditya Ghosh", "24BCB001", 4, "A", 8.34, 0, 2024),
    # Two ECE students, four semesters and two *different curricula* apart —
    # the clearest demonstration that batch, not department, picks the rules.
    ("B.TECH-ECE", "Naina Sheth", "22BEC001", 7, "A", 8.05, 0, 2022),
    ("B.TECH-ECE", "Kabir Malhotra", "24BEC001", 4, "A", 7.92, 0, 2024),
    ("B.TECH-MECH", "Ira Deshmukh", "24BME001", 4, "A", 8.18, 0, 2024),
    ("B.TECH-CIVIL", "Yash Parekh", "24BCL001", 4, "A", 7.64, 1, 2024),
    ("B.TECH-CHEM", "Sara Qureshi", "24BCH001", 4, "A", 8.88, 0, 2024),
    ("B.TECH-ELEC", "Mihir Rane", "22BEE001", 7, "A", 7.41, 0, 2022),
    ("B.TECH-PETRO", "Anvi Bhargava", "24BPE001", 4, "A", 8.52, 0, 2024),
    ("B.TECH-BIO", "Tanvi Shirke", "25BBT001", 2, "A", 8.26, 0, 2025),
]


def generate_program_cohort(rng, prefix, admission_year, semester, divisions,
                            per_division, taken_rolls, seen_names) -> list[tuple]:
    """Fill out one programme-batch across its configured divisions.

    Divisions come from the programme's own configuration, so a one-division
    programme like CSBS produces one division and Computer Engineering four.
    """
    students = []
    counter = 100
    for division in divisions:
        for _ in range(per_division):
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
            while name in seen_names:
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
            seen_names.add(name)
            counter += 1
            roll = f"{str(admission_year)[2:]}{prefix}{counter:03d}"
            while roll in taken_rolls:
                counter += 1
                roll = f"{str(admission_year)[2:]}{prefix}{counter:03d}"
            taken_rolls.add(roll)
            students.append((
                name, roll, semester, division,
                round(rng.uniform(6.0, 9.6), 2),
                rng.choices([0, 0, 0, 1, 2], k=1)[0],
                admission_year,
            ))
    return students


def generate_cohort(rng) -> list[tuple]:
    """Named students first, then a filled-out cohort across four divisions.

    Returns (name, roll, semester, division, cpi, backlogs, admission_year).
    CPI is generated for the student profile only — it is never an input to
    elective selection.
    """
    students = list(NAMED_STUDENTS)
    taken_rolls = {s[1] for s in students}
    seen_names = {s[0] for s in students}

    for prefix, admission_year, semester in YEAR_GROUPS:
        counter = 100          # generated rolls start at 100 to avoid clashes
        for division in ICT_DIVISIONS:
            for _ in range(STUDENTS_PER_DIVISION):
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
                while name in seen_names:
                    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
                seen_names.add(name)

                counter += 1
                roll = f"{prefix}{counter:03d}"
                while roll in taken_rolls:
                    counter += 1
                    roll = f"{prefix}{counter:03d}"
                taken_rolls.add(roll)

                students.append((
                    name, roll, semester, division,
                    round(rng.uniform(6.0, 9.6), 2),
                    rng.choices([0, 0, 0, 1, 2], k=1)[0],
                    admission_year,
                ))
    return students

# ── ICT curriculum, exactly as supplied by the department ────────────────
# (semester, code, title, component_type, source_scope, scope_label, credits, elective)
ICT_CURRICULUM = [
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL",
     "From Other School", 3, True),
    (5, "OE2-NPTEL", "Open Elective 2 — NPTEL / SWAYAM / MOOC", "MOOC",
     "EXTERNAL_PLATFORM", "NPTEL / SWAYAM certified course", 3, True),
    (5, "PCE1", "Program Core Elective 1", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT",
     "ICT specialisation track", 3, True),
    (6, "OE3", "Open Elective 3", "OPEN_ELECTIVE", "OTHER_DEPARTMENT_FOET",
     "From Other Department of FoET", 3, True),
    (6, "PCE2", "Program Core Elective 2", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT",
     "ICT specialisation track", 3, True),
    (6, "PCE3", "Program Core Elective 3", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT",
     "ICT specialisation track", 3, True),
    (7, "SI", "Summer Internship", "INTERNSHIP", "ANY", "Industry / research host",
     4, False),
    (7, "OE4", "Open Elective 4", "OPEN_ELECTIVE", "OTHER_DEPARTMENT_FOET",
     "From Other Department of FoET", 3, True),
    (7, "PCE4", "Program Core Elective 4", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT",
     "ICT specialisation track", 3, True),
    (7, "PCE5", "Program Core Elective 5", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT",
     "ICT specialisation track", 3, True),
    (8, "MP", "Major / Comprehensive Project", "PROJECT", "SAME_DEPARTMENT",
     "Department-supervised project", 12, False),
    # Compulsory first-year social internship.
    (2, "CSSI", "Community and Social Service Internship", "INTERNSHIP", "ANY",
     "NGO / social organisation", 2, False),
]

SPECIALIZATIONS = [
    "Software and Networks",
    "Artificial Intelligence",
    "Communication and Signal Processing",
    "Embedded and VLSI",
]

# (code, title, credits, specialization area)
PROGRAM_CORE_ELECTIVES = [
    ("ICT301", "Advanced Computer Networks", 3, "Software and Networks"),
    ("ICT302", "Cloud and Distributed Computing", 3, "Software and Networks"),
    ("ICT303", "Software Architecture and Design Patterns", 3, "Software and Networks"),
    ("ICT311", "Machine Learning", 3, "Artificial Intelligence"),
    ("ICT312", "Deep Learning and Neural Networks", 3, "Artificial Intelligence"),
    ("ICT313", "Natural Language Processing", 3, "Artificial Intelligence"),
    ("ICT321", "Digital Signal Processing", 3, "Communication and Signal Processing"),
    ("ICT322", "Wireless and Mobile Communication", 3,
     "Communication and Signal Processing"),
    ("ICT323", "Information Theory and Coding", 3,
     "Communication and Signal Processing"),
    ("ICT331", "Embedded System Design", 3, "Embedded and VLSI"),
    ("ICT332", "VLSI Design and Verification", 3, "Embedded and VLSI"),
    ("ICT333", "Internet of Things Architecture", 3, "Embedded and VLSI"),
]

# Open electives offered by *other* schools (for Sem IV "From Other School")
OPEN_ELECTIVES_OTHER_SCHOOL = [
    ("SLS201", "Psychology of Everyday Life", 3, "SLS", "School of Liberal Studies"),
    ("SLS202", "Introduction to Philosophy", 3, "SLS", "School of Liberal Studies"),
    ("SLS203", "Environmental Studies and Sustainability", 3, "SLS",
     "School of Liberal Studies"),
    ("SOM201", "Principles of Management", 3, "SOM", "School of Management"),
    ("SOM202", "Financial Literacy and Personal Finance", 3, "SOM",
     "School of Management"),
    ("SOM203", "Entrepreneurship and New Venture Creation", 3, "SOM",
     "School of Management"),
]

# Open electives from other FoET departments (Sem VI / VII)
OPEN_ELECTIVES_FOET = [
    ("MEC301", "Robotics and Automation", 3, "MEC"),
    ("MEC302", "Additive Manufacturing", 3, "MEC"),
    ("CIV301", "Smart Cities and Urban Infrastructure", 3, "CIV"),
    ("EE301", "Renewable Energy Systems", 3, "EE"),
    ("EE302", "Electric Vehicle Technology", 3, "EE"),
    ("CSE301", "Cyber Security Essentials", 3, "CSE"),
    ("PTE301", "Energy Economics and Policy", 3, "PTE"),
]

# NPTEL / SWAYAM catalogue
MOOC_COURSES = [
    ("NPTEL-CS01", "Programming in Modern C++", 3, 12,
     "https://onlinecourses.nptel.ac.in/noc/cpp"),
    ("NPTEL-CS02", "Data Structures and Algorithms", 3, 12,
     "https://onlinecourses.nptel.ac.in/noc/dsa"),
    ("NPTEL-CS03", "Introduction to Machine Learning", 3, 12,
     "https://onlinecourses.nptel.ac.in/noc/iml"),
    ("NPTEL-EC01", "Principles of Digital Communication", 3, 8,
     "https://onlinecourses.nptel.ac.in/noc/pdc"),
    ("SWAYAM-MG01", "Design Thinking for Innovation", 2, 8,
     "https://swayam.gov.in/courses/design-thinking"),
]

# ── Minor Specialisation — the six PDEU actually offers ───────────────────
# CONFIRMED from B.Tech. Academic Rules (batch 2024 onward), Annexure II. Every
# threshold below is quoted policy, not an assumption:
#
#   "The III semester student of any Department of the Schools of Technology
#    and School of Energy Technology can apply to register for a minor
#    specialization of other Department."
#   "Student with minimum CPI of 7.5 at the end of second semester without any
#    course backlog pending at the time of applying is eligible to apply."
#   "A maximum intake of 75 students in a division per minor specialization."
#   "The admission to the Minor specialization will be as per merit based on
#    latest CPI and on pro rata basis."
#
# CPI appears here and nowhere else. It is not, and must not become, an input to
# Open Elective or Program Core Elective allocation.
MINOR_MIN_CPI = 7.5
MINOR_MAX_BACKLOGS = 0
MINOR_SEATS = 75
MINOR_FROM_SEMESTER = 3
MINOR_CREDITS = 18

# (code, name, owning department, credits, min cpi, max backlogs, capacity)
MINOR_PROGRAMS = [
    ("MIN-CDS", "Computational Data Science", "CSE",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
    ("MIN-SSI", "Smart and Sustainable Infrastructure", "CIV",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
    ("MIN-IOT", "Internet of Things", "ICT",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
    ("MIN-ROB", "Robotics", "MEC",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
    ("MIN-SUS", "Sustainability Engineering", "CHM",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
    ("MIN-COE", "Coastal & Offshore Engineering", "PTE",
     MINOR_CREDITS, MINOR_MIN_CPI, MINOR_MAX_BACKLOGS, MINOR_SEATS),
]

#: Course lists exactly as printed in Annexure II, with the semester the rules
#: say each is "preferably" offered in.
MINOR_COURSES = {
    "MIN-CDS": [("MIN-CDS-01", "Essential Mathematics for Data Science", 3, 3),
                ("MIN-CDS-02", "Machine Learning for Beginners", 3, 4),
                ("MIN-CDS-03", "Machine Learning for Beginners Lab", 1, 4),
                ("MIN-CDS-04", "Time Series Analysis & Data Assimilation", 4, 5),
                ("MIN-CDS-05", "Statistical and Computational Optimization", 3, 6),
                ("MIN-CDS-06", "Advance Data Science with Capstone Project", 3, 7),
                ("MIN-CDS-07", "Advance Data Science with Capstone Project Lab", 1, 7)],
    "MIN-SSI": [("MIN-SSI-01", "Remote Sensing (RS) and GIS for Sustainable Infrastructure", 3, 3),
                ("MIN-SSI-02", "Remote Sensing (RS) and GIS for Sustainable Infrastructure - Lab", 1, 3),
                ("MIN-SSI-03", "Big data for Environmental Management", 3, 4),
                ("MIN-SSI-04", "Intelligent Transportation System", 4, 5),
                ("MIN-SSI-05", "Building Information Modelling", 2, 6),
                ("MIN-SSI-06", "Building Information Modelling - Lab", 2, 6),
                ("MIN-SSI-07", "Smart Infrastructure and Cities", 3, 7)],
    "MIN-IOT": [("MIN-IOT-01", "Introduction to IoT", 3, 3),
                ("MIN-IOT-02", "IoT Networks and Protocols", 3, 4),
                ("MIN-IOT-03", "IoT Networks and Protocols Lab", 1, 4),
                ("MIN-IOT-04", "Data Analytics and Visualization for IoT", 3, 5),
                ("MIN-IOT-05", "Data Analytics and Visualization for IoT Lab", 1, 5),
                ("MIN-IOT-06", "Embedded Systems for IoT", 3, 6),
                ("MIN-IOT-07", "Embedded Systems for IoT Lab", 1, 6),
                ("MIN-IOT-08", "IoT Security", 3, 7)],
    "MIN-ROB": [("MIN-ROB-01", "Introduction to Robotics", 4, 3),
                ("MIN-ROB-02", "Mechanics of Robots", 3, 4),
                ("MIN-ROB-03", "Microprocessor & Embedded Systems", 3, 5),
                ("MIN-ROB-04", "Microprocessor & Embedded Systems Laboratory", 1, 5),
                ("MIN-ROB-05", "Control of Robotic Systems", 3, 6),
                ("MIN-ROB-06", "Project in Robotics", 4, 7)],
    "MIN-SUS": [("MIN-SUS-01", "Waste Technology", 3, 3),
                ("MIN-SUS-02", "Waste Technology Laboratory", 1, 3),
                ("MIN-SUS-03", "Green Technology and Sustainable Engineering", 3, 4),
                ("MIN-SUS-04", "Biofuels and Bioprocesses Technology", 3, 5),
                ("MIN-SUS-05", "Basics of Separation Sciences", 3, 6),
                ("MIN-SUS-06", "Basics of Separation Sciences Laboratory", 1, 6),
                ("MIN-SUS-07", "Nanotechnology for Energy Applications", 3, 7),
                ("MIN-SUS-08", "Nanotechnology for Energy Applications Laboratory", 1, 7)],
    "MIN-COE": [("MIN-COE-01", "Marine Geosciences", 3, 3),
                ("MIN-COE-02", "Marine Geosciences Laboratory", 1, 3),
                ("MIN-COE-03", "Physical oceanography and modelling", 3, 4),
                ("MIN-COE-04", "Ocean Engineering and Technology", 4, 5),
                ("MIN-COE-05", "Design of coastal structures and pipelines", 3, 6),
                ("MIN-COE-06", "Advanced design and monitoring of offshore energy systems", 4, 7)],
}

#: Computational Data Science is run jointly by Computer Engineering and
#: Mathematics. Recorded so the joint ownership is not lost.
MINOR_PARTNER_DEPARTMENTS = {"MIN-CDS": ["MATH"]}

CSSI_STAGES = [
    ("NGO_SELECTION", "NGO Selection & Registration",
     "Choose an approved NGO and register your placement.", True, None, "STUDENT"),
    ("INTERNSHIP", "Internship Period",
     "Complete the on-site community service period.", False, None, "STUDENT"),
    ("NGO_DETAILS", "NGO / Internship Details",
     "Record organisation details and your project statement.", False, None, "STUDENT"),
    ("PROOF_OF_WORK", "Proof of Work",
     "Upload photographs and evidence of the work carried out.", True, "PHOTO",
     "STUDENT"),
    ("CERTIFICATE", "Certificate",
     "Upload the completion certificate issued by the NGO.", True, "CERTIFICATE",
     "STUDENT"),
    ("POSTER", "Poster", "Submit the summary poster for review.", True, "POSTER",
     "STUDENT"),
    ("PRESENTATION", "Presentation",
     "Present your work to the assigned faculty panel.", True, "PRESENTATION",
     "STUDENT"),
    ("EVALUATION", "Faculty Evaluation",
     "Faculty mentor records marks against the rubric.", False, None, "FACULTY"),
]

SUMMER_STAGES = [
    ("REGISTRATION", "Registration",
     "Register your internship and host organisation.", False, None, "STUDENT"),
    ("MENTOR_ALLOCATION", "Mentor Allocation",
     "A faculty mentor is assigned by the coordinator.", False, None, "COORDINATOR"),
    ("OFFER_LETTER", "Offer Letter",
     "Upload the offer or joining letter from the organisation.", True,
     "OFFER_LETTER", "STUDENT"),
    ("IN_PROGRESS", "Internship In Progress",
     "Submit periodic reports for the configured cadence.", False, None, "STUDENT"),
    ("FINAL_REPORT", "Final Report", "Submit the consolidated final report.", True,
     "REPORT", "STUDENT"),
    ("CERTIFICATE", "Certificate",
     "Upload the completion certificate.", True, "CERTIFICATE", "STUDENT"),
    ("PRESENTATION", "Presentation",
     "Present the internship outcome to the panel.", True, "PRESENTATION", "STUDENT"),
    ("EVALUATION", "Evaluation",
     "Faculty and coordinator record the final evaluation.", False, None, "FACULTY"),
]

# Rubrics are data — the frontend renders whatever rows exist.
CSSI_CRITERIA = [
    ("ENGAGEMENT", "Community Engagement",
     "Depth and consistency of engagement with the host organisation.", 10, 1),
    ("PROBLEM", "Problem Understanding",
     "Clarity of the problem statement and social context.", 10, 1),
    ("EXECUTION", "Execution & Contribution",
     "Quality of the work actually carried out.", 10, 1),
    ("DOCUMENTATION", "Documentation & Poster",
     "Completeness of the report, poster and evidence.", 10, 1),
    ("PRESENTATION", "Presentation & Communication",
     "Clarity of the final presentation and responses.", 10, 1),
]

# Confirmed Summer Internship rubric: four components of 25, total 100.
# Stored as data — the evaluation form renders whatever rows exist here.
SUMMER_CRITERIA = [
    ("FINAL_REPORT", "Final Report",
     "Structure, rigour and clarity of the final report.", 25, 1),
    ("PRESENTATION", "Presentation",
     "Presentation quality and defence of the work.", 25, 1),
    ("WEEKLY", "Weekly Submissions",
     "Regularity and quality of the weekly reports, assessed as a whole.",
     25, 1),
    ("INDUSTRY", "Industry Mentor",
     "Assessment supplied by the industry mentor. Entered by the faculty "
     "mentor or coordinator on the mentor's behalf — never by the student.",
     25, 1),
]

NGOS = [
    ("Prayas Foundation", "Education for underprivileged children", "Gandhinagar",
     "Gandhinagar", "Gujarat"),
    ("Sahyog Seva Sansthan", "Rural healthcare awareness", "Ahmedabad",
     "Ahmedabad", "Gujarat"),
    ("Green Roots Collective", "Urban afforestation and waste management",
     "Gandhinagar", "Gandhinagar", "Gujarat"),
    ("Disha Skill Trust", "Vocational skilling for women", "Vadodara", "Vadodara",
     "Gujarat"),
    ("Anandi Child Welfare", "Child nutrition and welfare", "Surat", "Surat",
     "Gujarat"),
]

COMPANIES = [
    ("Nimbus Analytics", "COMPANY", "Data engineering and analytics", "Pune",
     "Maharashtra"),
    ("Vertex Semiconductors", "COMPANY", "VLSI design services", "Bengaluru",
     "Karnataka"),
    ("BlueWave Networks", "COMPANY", "Network infrastructure", "Ahmedabad",
     "Gujarat"),
    ("Helios Research Lab", "RESEARCH_LAB", "Applied AI research", "Hyderabad",
     "Telangana"),
]

CLUBS = [
    ("Codegeeks", "TECHNICAL", "The competitive programming and dev community",
     "Build. Break. Repeat.", "https://instagram.com/codegeeks.pdeu", 2014),
    ("Robotics Society", "TECHNICAL", "Hands-on robotics, drones and automation",
     "Machines that think", "https://instagram.com/robotics.pdeu", 2016),
    ("Aavaran", "CULTURAL", "The cultural and performing arts club",
     "Where campus finds its voice", "https://instagram.com/aavaran.pdeu", 2011),
    ("E-Cell", "ENTREPRENEURSHIP", "Student entrepreneurship cell",
     "From idea to venture", "https://instagram.com/ecell.pdeu", 2013),
    ("Lensmen", "OTHER", "Photography and campus media",
     "Every frame tells a story", "https://instagram.com/lensmen.pdeu", 2015),
    ("Debsoc", "LITERARY", "Debating and public speaking society",
     "Argue well, listen better", "https://instagram.com/debsoc.pdeu", 2012),
]

EVENTS = [
    # (title, club, type, days_from_now, venue, capacity, speaker, summary)
    ("HackTheCampus 2.0", "Codegeeks", "COMPETITION", 12, "Innovation Hub, Block 6",
     150, None,
     "A 24-hour hackathon on campus infrastructure problems. Teams of up to four."),
    ("Intro to Kubernetes", "Codegeeks", "WORKSHOP", 5, "Lab 6-204", 40,
     "Rohit Sinha, Platform Engineer",
     "Hands-on session covering pods, services and deployments."),
    ("Line Follower Championship", "Robotics Society", "COMPETITION", 20,
     "Robotics Lab", 60, None,
     "Build and race an autonomous line-following robot."),
    ("Drone Assembly Workshop", "Robotics Society", "WORKSHOP", 9,
     "Robotics Lab", 30, "Dr. Rakesh Bhatt",
     "Assemble and calibrate a quadcopter from a component kit."),
    ("Aavaran Annual Night", "Aavaran", "EVENT", 30, "Main Auditorium", 600, None,
     "The flagship cultural evening — music, dance and theatre."),
    ("Startup Pitch Day", "E-Cell", "EVENT", 16, "Seminar Hall 2", 120,
     "Panel of three investors",
     "Pitch your venture to a panel and win incubation support."),
    ("Founder Fireside: Building in Public", "E-Cell", "SEMINAR", 3,
     "Seminar Hall 1", 100, "Meghna Iyer, Founder — Tiller",
     "An honest conversation about the first two years of a startup."),
    ("Campus Photowalk", "Lensmen", "MEETUP", 7, "Meet at Main Gate", 35, None,
     "A guided golden-hour photowalk across campus. Any camera welcome."),
    ("Parliamentary Debate Open", "Debsoc", "COMPETITION", 24, "Seminar Hall 3",
     64, None, "British Parliamentary format, open to all semesters."),
    ("Careers in Signal Processing", "Codegeeks", "SEMINAR", -6, "Seminar Hall 1",
     90, "Prof. Sneha Iyer",
     "A look at industry and research paths in DSP and communications."),
    ("Git & GitHub for Beginners", "Codegeeks", "WORKSHOP", -14, "Lab 6-201", 45,
     None, "Version control fundamentals for first-year students."),
]

# (title, body, category, priority, audience, pinned, audience reference)
# The reference is a semester number for SEMESTER and an internship programme
# code for INTERNSHIP_PROGRAM. A notice about one semester's slot, or one
# programme's reports, is addressed to those students — not broadcast to a
# first-year who has neither.
ANNOUNCEMENTS = [
    ("Open Elective preference window is now open",
     "The preference window for Open Elective 3 (Semester VI) is open until the end "
     "of this month. Submit your ranked preferences from Academics → Open Electives. "
     "Preferences submitted after the deadline will not be considered.",
     "ACADEMIC", "HIGH", "SEMESTER", True, 6),
    ("NPTEL Semester V registration guidelines",
     "Students in Semester V must register for an NPTEL or SWAYAM course of at least "
     "8 weeks. Record your platform registration ID in the portal and upload the "
     "certificate once results are declared. Exam fees are paid directly on the "
     "NPTEL portal.",
     "ACADEMIC", "NORMAL", "SEMESTER", False, 5),
    ("CSSI group allocations published",
     "Faculty group allocations for the Community and Social Service Internship have "
     "been published. Check Internships → CSSI to see your assigned faculty mentor "
     "and group.",
     "INTERNSHIP", "NORMAL", "INTERNSHIP_PROGRAM", False, "CSSI-2025"),
    ("Summer Internship: weekly report cadence",
     "Weekly reports are due every Monday for the duration of the internship. Your "
     "faculty mentor reviews each submission; unreviewed reports do not count toward "
     "the reporting criterion.",
     "INTERNSHIP", "NORMAL", "INTERNSHIP_PROGRAM", False, "SI-2025"),
    ("Minor specialisation applications open from Semester III",
     "Applications for minor specialisations are open to students from Semester III "
     "onward. A minor must be taken in a department other than your own. Eligibility "
     "thresholds are listed against each minor.",
     "ACADEMIC", "NORMAL", "ALL", False, None),
]



def mentors_for(domain: str, department: str) -> list[str]:
    """Employee codes holding a Mentor grant over that scope.

    The CSSI groups are led by these people, so the seed cannot drift from the
    rule it is meant to demonstrate: the module *coordinator* is not
    automatically one of them.
    """
    return [
        code for code, role, dom, dept in ROLE_ASSIGNMENTS
        if role == "MENTOR" and dom == domain and dept == department
    ]
