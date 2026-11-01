"""Demo data so the app is usable on first run. Only runs when the store is empty."""
import random
from datetime import date, timedelta

from rdms.models import (Announcement, Attendance, Course, Department, Program, Result,
                         StudentProfile, User)

DEMO_ADMIN_PW = 'Admin@123'
DEMO_FACULTY_PW = 'Faculty@123'
DEMO_STUDENT_PW = 'Student@123'

DEPARTMENTS = [
    ('CSE', 'Computer Science & Engineering'),
    ('ECE', 'Electronics & Communication Engineering'),
    ('MGT', 'Management Studies'),
    ('COM', 'Commerce'),
]

PROGRAMS = [  # code, name, semesters, dept
    ('BTCS', 'B.Tech Computer Science & Engineering', 8, 'CSE'),
    ('BTEC', 'B.Tech Electronics & Communication', 8, 'ECE'),
    ('BCA', 'Bachelor of Computer Applications', 6, 'CSE'),
    ('MBA', 'Master of Business Administration', 4, 'MGT'),
    ('BCOM', 'B.Com (Honours)', 6, 'COM'),
]

COURSES = {  # program: [(semester, code, title, credits)]
    'BTCS': [(1, 'CS101', 'Programming in C', 4), (1, 'MA101', 'Engineering Mathematics I', 4),
             (1, 'PH101', 'Engineering Physics', 3), (2, 'CS102', 'Data Structures', 4),
             (2, 'MA102', 'Engineering Mathematics II', 4), (2, 'EE101', 'Basic Electrical Engineering', 3),
             (3, 'CS201', 'Object Oriented Programming', 4), (3, 'CS202', 'Digital Logic Design', 3),
             (3, 'CS203', 'Discrete Mathematics', 4)],
    'BTEC': [(1, 'EC101', 'Electronic Devices', 4), (1, 'MA111', 'Engineering Mathematics I', 4),
             (2, 'EC102', 'Network Analysis', 4), (2, 'MA112', 'Engineering Mathematics II', 4),
             (3, 'EC201', 'Analog Circuits', 4), (3, 'EC202', 'Signals & Systems', 4)],
    'BCA': [(1, 'CA101', 'Computer Fundamentals', 4), (1, 'CA102', 'Programming in Python', 4),
            (2, 'CA103', 'Database Management Systems', 4), (2, 'CA104', 'Web Technologies', 4),
            (3, 'CA201', 'Java Programming', 4), (3, 'CA202', 'Operating Systems', 4)],
    'MBA': [(1, 'MB101', 'Principles of Management', 4), (1, 'MB102', 'Managerial Economics', 4),
            (2, 'MB103', 'Marketing Management', 4), (2, 'MB104', 'Financial Management', 4)],
    'BCOM': [(1, 'BC101', 'Financial Accounting', 4), (1, 'BC102', 'Business Law', 3),
             (2, 'BC103', 'Corporate Accounting', 4), (2, 'BC104', 'Business Statistics', 3)],
}

FACULTY = [
    ('Dr. Rajesh Sharma', 'rajesh.sharma'), ('Dr. Meera Iyer', 'meera.iyer'),
    ('Prof. Anil Verma', 'anil.verma'), ('Dr. Sunita Rao', 'sunita.rao'),
    ('Prof. Vikram Singh', 'vikram.singh'), ('Dr. Kavita Nair', 'kavita.nair'),
]

STUDENTS = [
    ('Aarav Sharma', 'Male', 'Delhi'), ('Diya Patel', 'Female', 'Gujarat'),
    ('Rohan Gupta', 'Male', 'Uttar Pradesh'), ('Ananya Reddy', 'Female', 'Telangana'),
    ('Arjun Nair', 'Male', 'Kerala'), ('Ishita Banerjee', 'Female', 'West Bengal'),
    ('Kabir Singh', 'Male', 'Punjab'), ('Priya Iyer', 'Female', 'Tamil Nadu'),
    ('Vivaan Joshi', 'Male', 'Maharashtra'), ('Saanvi Kulkarni', 'Female', 'Karnataka'),
    ('Aditya Verma', 'Male', 'Madhya Pradesh'), ('Meera Das', 'Female', 'Odisha'),
    ('Krishna Yadav', 'Male', 'Bihar'), ('Riya Chauhan', 'Female', 'Rajasthan'),
    ('Harsh Mehta', 'Male', 'Gujarat'), ('Nisha Kapoor', 'Female', 'Haryana'),
    ('Yash Malhotra', 'Male', 'Delhi'), ('Tanvi Deshmukh', 'Female', 'Maharashtra'),
    ('Manav Bhatt', 'Male', 'Uttarakhand'), ('Sneha Pillai', 'Female', 'Kerala'),
]


def seed_if_empty():
    if User.all():
        return
    rnd = random.Random(2026)

    admin = User(email='registrar@gmail.com', name='University Registrar', role='admin')
    admin.set_password(DEMO_ADMIN_PW)
    admin.save()

    depts = {}
    for code, name in DEPARTMENTS:
        depts[code] = Department(code=code, name=name).save()

    progs = {}
    for code, name, sems, dcode in PROGRAMS:
        progs[code] = Program(code=code, name=name, duration_semesters=sems,
                              department_id=depts[dcode].id).save()

    faculty = []
    for name, local in FACULTY:
        f = User(email=f'{local}@gmail.com', name=name, role='faculty')
        f.set_password(DEMO_FACULTY_PW)
        f.save()
        faculty.append(f)

    courses = {}
    i = 0
    for pcode, items in COURSES.items():
        courses[pcode] = []
        for sem, code, title, cr in items:
            c = Course(code=code, title=title, credits=cr, semester=sem,
                       program_id=progs[pcode].id, faculty_id=faculty[i % len(faculty)].id,
                       published=(sem < 3)).save()
            courses[pcode].append(c)
            i += 1

    plist = list(progs.keys())
    for n, (name, gender, state) in enumerate(STUDENTS):
        pcode = plist[n % len(plist)]
        prog = progs[pcode]
        sem = 3 if n % 2 == 0 else 2
        year = 2025 - (sem // 2)
        email = f"{name.lower().replace(' ', '.')}@gmail.com"
        u = User(email=email, name=name, role='student')
        u.set_password(DEMO_STUDENT_PW)
        u.save()
        StudentProfile(
            user_id=u.id, enrollment_no=f'UOI{year}{pcode}{n + 1:03d}', program_id=prog.id,
            semester=sem, admission_year=year, gender=gender, state=state,
            dob=date(2003 + rnd.randint(0, 2), rnd.randint(1, 12), rnd.randint(1, 28)),
            phone=f'9{rnd.randint(100000000, 999999999)}').save()
        ability = rnd.uniform(52, 92)
        for c in courses[pcode]:
            if c.semester > sem:
                continue
            r = Result(student_id=u.id, course_id=c.id)
            if c.semester < sem or c.published:
                total = max(15, min(100, int(rnd.gauss(ability, 10))))
                r.internal = min(40, round(total * 0.4 + rnd.uniform(-2, 2)))
                r.external = max(0, min(60, total - r.internal))
            r.save()
            # a few weeks of attendance for current-semester courses
            if c.semester == sem:
                for d in range(12):
                    day = date.today() - timedelta(days=(12 - d) * 2)
                    Attendance(student_id=u.id, course_id=c.id, date=day,
                              present=rnd.random() < 0.85).save()

    Announcement(
        title='Welcome to the UoI Result Portal',
        body='Sign in with your university email. Students can view results, attendance and '
             'download marksheets. Faculty can enter marks and attendance for their courses.',
        audience='all', author_id=admin.id).save()
    Announcement(
        title='End-semester examinations',
        body='Semester 3 end-semester examinations begin next month. Check your attendance '
             '- a minimum of 75% is required to sit the exam.',
        audience='student', author_id=admin.id).save()
    Announcement(
        title='Marks entry deadline',
        body='Faculty must complete internal marks entry for the current semester by month-end.',
        audience='faculty', author_id=admin.id).save()
