import csv
import io
import secrets
from datetime import date, datetime

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from rdms.models import (Announcement, Attendance, AuditLog, Course, Department, ExamSchedule, Program,
                         Result, StudentProfile, User)
from rdms.routes import audit
from rdms.utils import domain_ok, gpa, password_problem, role_required

admin_bp = Blueprint('admin', __name__)
STATES = ['Andhra Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Delhi', 'Goa', 'Gujarat', 'Haryana',
          'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
          'Odisha', 'Punjab', 'Rajasthan', 'Tamil Nadu', 'Telangana', 'Uttar Pradesh',
          'Uttarakhand', 'West Bengal', 'Other']


class ListPagination:
    """Paginates a plain Python list with the same interface as Flask-SQLAlchemy's
    Pagination object, so templates/admin/_pager.html works for report data too."""

    def __init__(self, items, page, per_page):
        self.page = max(1, page)
        self.per_page = per_page
        self.total = len(items)
        self.pages = max(1, (self.total + per_page - 1) // per_page)
        self.page = min(self.page, self.pages)
        start = (self.page - 1) * per_page
        self.items = items[start:start + per_page]

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1

    @property
    def next_num(self):
        return self.page + 1

    def iter_pages(self, left_edge=1, left_current=1, right_current=2, right_edge=1):
        last = 0
        for num in range(1, self.pages + 1):
            if (num <= left_edge or num > self.pages - right_edge
                    or (self.page - left_current - 1 < num < self.page + right_current)):
                if last + 1 != num:
                    yield None
                yield num
                last = num


def enrol_student(user):
    """Create Result rows for every course in the student's programme up to their semester."""
    p = user.profile
    have = {r.course_id for r in Result.filter_by(student_id=user.id)}
    added = 0
    for c in Course.filter_by(program_id=p.program_id):
        if c.semester <= p.semester and c.id not in have:
            Result(student_id=user.id, course_id=c.id).save()
            added += 1
    return added


# ---------------------------------------------------------------- dashboard
@admin_bp.route('/')
@role_required('admin')
def dashboard():
    counts = dict(students=len(User.filter_by(role='student')),
                  faculty=len(User.filter_by(role='faculty')),
                  programs=Program.count(), courses=Course.count())
    by_prog = []
    for prog in sorted(Program.all(), key=lambda p: p.name):
        by_prog.append((prog.name, len(StudentProfile.filter_by(program_id=prog.id))))
    # grade distribution across all graded results
    dist = {}
    for r in Result.all():
        g = r.grade
        if g:
            dist[g[0]] = dist.get(g[0], 0) + 1
    order = ['O', 'A+', 'A', 'B+', 'B', 'C', 'P', 'F']
    grade_dist = [(k, dist.get(k, 0)) for k in order]
    pending = sum(1 for c in Course.all() if not c.published)
    logs = sorted(AuditLog.all(), key=lambda l: l.at, reverse=True)[:8]
    return render_template('admin/dashboard.html', counts=counts, by_prog=by_prog,
                           grade_dist=grade_dist, pending=pending, logs=logs)


# ---------------------------------------------------------------- users
@admin_bp.route('/users')
@role_required('admin')
def users():
    role = request.args.get('role', '')
    q = (request.args.get('q') or '').strip().lower()
    rows = User.all()
    if role in ('student', 'faculty', 'admin'):
        rows = [u for u in rows if u.role == role]
    if q:
        def matches(u):
            if q in (u.name or '').lower() or q in (u.email or '').lower():
                return True
            p = u.profile
            return bool(p and q in (p.enrollment_no or '').lower())
        rows = [u for u in rows if matches(u)]
    rows.sort(key=lambda u: (u.role, u.name))
    page = request.args.get('page', 1, type=int)
    pagination = ListPagination(rows, page, per_page=10)
    return render_template('admin/users.html', pagination=pagination, role=role, q=q)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def user_form(user_id=None):
    user = User.get(user_id) if user_id else None
    if user_id and not user:
        abort(404)
    programs = sorted(Program.all(), key=lambda p: p.name)
    if request.method == 'POST':
        f = request.form
        role = f.get('role', 'student') if not user else user.role
        name = f.get('name', '').strip()
        email = f.get('email', '').strip().lower()
        password = f.get('password', '')
        err = None
        ok, msg = domain_ok(email, role)
        if not name:
            err = 'Name is required.'
        elif not ok:
            err = msg
        elif any(u.email == email and u.id != (user.id if user else 0) for u in User.all()):
            err = 'That email is already registered.'
        elif not user and password_problem(password):
            err = password_problem(password)
        elif role == 'student':
            try:
                program_id = int(f.get('program_id'))
                semester = int(f.get('semester'))
                year = int(f.get('admission_year'))
                prog = Program.get(program_id)
                assert prog and 1 <= semester <= prog.duration_semesters
            except (TypeError, ValueError, AssertionError):
                err = 'Choose a valid programme and a semester within its duration.'
        if err:
            flash(err, 'danger')
            return render_template('admin/user_form.html', user=user, programs=programs, states=STATES,
                                   form=f, today_year=date.today().year)
        if not user:
            user = User(role=role, email=email, name=name)
            user.set_password(password)
            user.save()
        else:
            user.name, user.email = name, email
            user.save()
        if role == 'student':
            p = user.profile or StudentProfile(user_id=user.id)
            p.program_id, p.semester, p.admission_year = program_id, semester, year
            p.enrollment_no = (f.get('enrollment_no') or '').strip() or p.enrollment_no or \
                f'UOI{year}{prog.code}{user.id:03d}'
            p.gender, p.state, p.phone = f.get('gender'), f.get('state'), f.get('phone')
            if f.get('dob'):
                try:
                    p.dob = datetime.strptime(f['dob'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            p.save()
            enrol_student(user)
        audit(f'{"Updated" if user_id else "Created"} {role} account {email}')
        flash(f'{role.title()} account saved.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user, programs=programs, states=STATES,
                           form={}, today_year=date.today().year)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@role_required('admin')
def user_toggle(user_id):
    u = User.get(user_id) or abort(404)
    if u.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
    else:
        u.active = not u.active
        u.save()
        audit(f'{"Activated" if u.active else "Deactivated"} {u.email}')
        flash(f'{u.name} is now {"active" if u.active else "deactivated"}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@role_required('admin')
def user_reset(user_id):
    u = User.get(user_id) or abort(404)
    temp = secrets.token_urlsafe(6) + '7'
    u.set_password(temp)
    u.failed_attempts, u.locked_until = 0, None
    u.save()
    audit(f'Reset password for {u.email}')
    flash(f'Temporary password for {u.email}: {temp}  (share it securely; ask them to change it)', 'warning')
    return redirect(request.referrer or url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/promote', methods=['POST'])
@role_required('admin')
def user_promote(user_id):
    u = User.get(user_id) or abort(404)
    if not u.profile:
        abort(404)
    p = u.profile
    if p.semester >= p.program.duration_semesters:
        flash('Student is already in the final semester.', 'info')
    else:
        p.semester += 1
        p.save()
        n = enrol_student(u)
        audit(f'Promoted {u.email} to semester {p.semester}')
        flash(f'{u.name} moved to semester {p.semester} and enrolled in {n} new course(s).', 'success')
    return redirect(request.referrer or url_for('admin.users'))


# ---------------------------------------------------------------- academics
@admin_bp.route('/academics', methods=['GET', 'POST'])
@role_required('admin')
def academics():
    if request.method == 'POST':
        kind = request.form.get('kind')
        try:
            if kind == 'department':
                code = request.form['code'].strip().upper()
                assert code and not Department.filter_by(code=code)
                Department(code=code, name=request.form['name'].strip()).save()
            elif kind == 'program':
                code = request.form['code'].strip().upper()
                assert code and not Program.filter_by(code=code)
                Program(code=code, name=request.form['name'].strip(),
                       duration_semesters=int(request.form['duration']),
                       department_id=int(request.form['department_id'])).save()
            else:
                raise ValueError('unknown kind')
            audit(f'Added {kind} {request.form.get("code")}')
            flash(f'{kind.title()} added.', 'success')
        except Exception:
            flash('Could not save: check the fields and make sure the code is unique.', 'danger')
        return redirect(url_for('admin.academics'))
    return render_template('admin/academics.html',
                           departments=sorted(Department.all(), key=lambda d: d.name),
                           programs=sorted(Program.all(), key=lambda p: p.name))


@admin_bp.route('/courses')
@role_required('admin')
def courses():
    pid = request.args.get('program', type=int)
    rows = Course.all()
    if pid:
        rows = [c for c in rows if c.program_id == pid]
    rows.sort(key=lambda c: (c.program_id, c.semester, c.code))
    page = request.args.get('page', 1, type=int)
    pagination = ListPagination(rows, page, per_page=10)
    return render_template('admin/courses.html', pagination=pagination,
                           programs=sorted(Program.all(), key=lambda p: p.name), pid=pid)


@admin_bp.route('/courses/new', methods=['GET', 'POST'])
@admin_bp.route('/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def course_form(course_id=None):
    course = Course.get(course_id) if course_id else None
    if course_id and not course:
        abort(404)
    programs = sorted(Program.all(), key=lambda p: p.name)
    faculty = sorted((u for u in User.all() if u.role == 'faculty' and u.active), key=lambda u: u.name)
    if request.method == 'POST':
        f = request.form
        try:
            code = f['code'].strip().upper()
            title = f['title'].strip()
            credits, semester = int(f['credits']), int(f['semester'])
            program_id = int(f['program_id'])
            faculty_id = int(f['faculty_id']) if f.get('faculty_id') else None
            prog = Program.get(program_id)
            assert code and title and 1 <= credits <= 10 and prog and 1 <= semester <= prog.duration_semesters
            dup = any(c.code == code and c.id != (course.id if course else 0) for c in Course.all())
            assert not dup
        except (KeyError, ValueError, AssertionError):
            flash('Invalid input. Check the course code is unique, credits are 1-10 and the semester '
                  'is within the programme duration.', 'danger')
            return render_template('admin/course_form.html', course=course, programs=programs, faculty=faculty)
        if not course:
            course = Course()
        course.code, course.title, course.credits = code, title, credits
        course.semester, course.program_id, course.faculty_id = semester, program_id, faculty_id
        course.save()
        # enrol existing students of that programme/semester range
        for p in StudentProfile.filter_by(program_id=program_id):
            if p.semester >= semester and not Result.first_by(student_id=p.user_id, course_id=course.id):
                Result(student_id=p.user_id, course_id=course.id).save()
        audit(f'Saved course {code}')
        flash('Course saved and eligible students enrolled.', 'success')
        return redirect(url_for('admin.courses'))
    return render_template('admin/course_form.html', course=course, programs=programs, faculty=faculty)


@admin_bp.route('/courses/<int:course_id>/publish', methods=['POST'])
@role_required('admin')
def course_publish(course_id):
    c = Course.get(course_id) or abort(404)
    c.published = not c.published
    c.save()
    audit(f'{"Published" if c.published else "Unpublished"} results for {c.code}')
    flash(f'{c.code} results {"published" if c.published else "hidden"}.', 'success')
    return redirect(request.referrer or url_for('admin.courses'))


# ---------------------------------------------------------------- exam schedule
@admin_bp.route('/exams')
@role_required('admin')
def exams():
    page = request.args.get('page', 1, type=int)
    rows = sorted(ExamSchedule.all(), key=lambda e: (e.exam_date, e.start_time))
    pagination = ListPagination(rows, page, per_page=10)
    return render_template('admin/exams.html', pagination=pagination)


@admin_bp.route('/exams/new', methods=['GET', 'POST'])
@admin_bp.route('/exams/<int:exam_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def exam_form(exam_id=None):
    exam = ExamSchedule.get(exam_id) if exam_id else None
    if exam_id and not exam:
        abort(404)
    courses = sorted(Course.all(), key=lambda c: (c.program_id, c.semester, c.code))
    if request.method == 'POST':
        f = request.form
        try:
            course_id = int(f['course_id'])
            exam_date = datetime.strptime(f['exam_date'], '%Y-%m-%d').date()
            start_time = datetime.strptime(f['start_time'], '%H:%M').time()
            end_time = datetime.strptime(f['end_time'], '%H:%M').time()
            assert Course.get(course_id) and end_time > start_time
        except (KeyError, ValueError, AssertionError):
            flash('Choose a course, a valid date, and an end time after the start time.', 'danger')
            return render_template('admin/exam_form.html', exam=exam, courses=courses)
        if not exam:
            exam = ExamSchedule()
        exam.course_id = course_id
        exam.exam_type = (f.get('exam_type') or 'End Semester').strip()
        exam.exam_date, exam.start_time, exam.end_time = exam_date, start_time, end_time
        exam.venue = (f.get('venue') or '').strip() or None
        exam.save()
        audit(f'Saved exam schedule for {exam.course.code} on {exam_date}')
        flash('Exam schedule saved.', 'success')
        return redirect(url_for('admin.exams'))
    return render_template('admin/exam_form.html', exam=exam, courses=courses)


@admin_bp.route('/exams/<int:exam_id>/delete', methods=['POST'])
@role_required('admin')
def exam_delete(exam_id):
    exam = ExamSchedule.get(exam_id) or abort(404)
    course_code = exam.course.code
    exam.delete()
    audit(f'Removed exam schedule for {course_code}')
    flash('Exam schedule removed.', 'success')
    return redirect(url_for('admin.exams'))


# ---------------------------------------------------------------- announcements
@admin_bp.route('/announcements', methods=['GET', 'POST'])
@role_required('admin')
def announcements():
    if request.method == 'POST':
        title, body = request.form.get('title', '').strip(), request.form.get('body', '').strip()
        aud = request.form.get('audience', 'all')
        if title and body and aud in ('all', 'student', 'faculty'):
            Announcement(title=title, body=body, audience=aud, author_id=current_user.id).save()
            audit(f'Posted announcement: {title}')
            flash('Announcement posted.', 'success')
        else:
            flash('Title and message are required.', 'danger')
        return redirect(url_for('admin.announcements'))
    return render_template('admin/announcements.html',
                           items=sorted(Announcement.all(), key=lambda a: a.created_at, reverse=True))


@admin_bp.route('/announcements/<int:aid>/delete', methods=['POST'])
@role_required('admin')
def announcement_delete(aid):
    a = Announcement.get(aid) or abort(404)
    a.delete()
    flash('Announcement removed.', 'success')
    return redirect(url_for('admin.announcements'))


# ---------------------------------------------------------------- reports
@admin_bp.route('/reports')
@role_required('admin')
def reports():
    course_stats = []
    for c in sorted(Course.all(), key=lambda c: (c.program_id, c.semester)):
        graded = [r for r in c.results if r.total is not None]
        if not graded:
            continue
        passed = sum(1 for r in graded if r.total >= 40)
        course_stats.append(dict(course=c, n=len(graded),
                                 avg=round(sum(r.total for r in graded) / len(graded), 1),
                                 pass_pct=round(passed * 100 / len(graded))))
    toppers = []
    for u in User.filter_by(role='student'):
        rs = [r for r in Result.filter_by(student_id=u.id) if r.total is not None]
        if rs:
            toppers.append((u, gpa(rs)))
    toppers.sort(key=lambda t: -t[1])
    page = request.args.get('page', 1, type=int)
    pagination = ListPagination(course_stats, page, per_page=10)
    return render_template('admin/reports.html', pagination=pagination, toppers=toppers[:10])


@admin_bp.route('/export/results.csv')
@role_required('admin')
def export_results():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Enrollment No', 'Student', 'Email', 'Programme', 'Semester', 'Course Code', 'Course',
                'Credits', 'Internal', 'External', 'Total', 'Grade', 'Grade Points', 'Published'])
    rows = Result.all()
    rows.sort(key=lambda r: (r.course.code, r.student.name))
    for r in rows:
        p = r.student.profile
        g = r.grade
        w.writerow([p.enrollment_no, r.student.name, r.student.email, p.program.code, r.course.semester,
                    r.course.code, r.course.title, r.course.credits, r.internal, r.external, r.total,
                    g[0] if g else '', g[1] if g else '', 'Yes' if r.course.published else 'No'])
    audit('Exported results CSV')
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=uoi_results.csv'})


@admin_bp.route('/audit')
@role_required('admin')
def audit_log():
    page = request.args.get('page', 1, type=int)
    rows = sorted(AuditLog.all(), key=lambda l: l.at, reverse=True)
    pg = ListPagination(rows, page, per_page=10)
    return render_template('admin/audit.html', pagination=pg)
