import io
from collections import OrderedDict
from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from datetime import date

from rdms import UNIVERSITY_NAME
from rdms.models import Announcement, Attendance, ExamSchedule, LearningResource, ResourceProgress, Result
from rdms.utils import division, gpa, percentage_from_cgpa, role_required

student = Blueprint('student', __name__)


def _published_results(user):
    """Results the student is allowed to see: course published AND marks entered."""
    rows = Result.filter_by(student_id=user.id)
    rows.sort(key=lambda r: r.course_id)
    return [r for r in rows if r.course.published and r.total is not None]


def _by_semester(results):
    sems = OrderedDict()
    for r in sorted(results, key=lambda r: (r.course.semester, r.course.code)):
        sems.setdefault(r.course.semester, []).append(r)
    return sems


def _attendance_summary(user):
    out = []
    for r in Result.filter_by(student_id=user.id):
        rows = Attendance.filter_by(student_id=user.id, course_id=r.course_id)
        if not rows:
            continue
        present = sum(1 for a in rows if a.present)
        pct = round(present * 100 / len(rows), 1)
        out.append(dict(course=r.course, total=len(rows), present=present, pct=pct))
    return out


@student.route('/')
@role_required('student')
def dashboard():
    results = _published_results(current_user)
    sems = _by_semester(results)
    cgpa = gpa(results)
    sgpa_trend = [(s, gpa(rs)) for s, rs in sems.items()]
    attendance = _attendance_summary(current_user)
    notices = sorted((a for a in Announcement.all() if a.audience in ('all', 'student')),
                     key=lambda a: a.created_at, reverse=True)[:5]
    low = [a for a in attendance if a['pct'] < 75]
    return render_template('student/dashboard.html', cgpa=cgpa, sgpa_trend=sgpa_trend,
                           attendance=attendance, notices=notices, low=low,
                           credits=sum(r.course.credits for r in results if r.grade[1] > 0),
                           percentage=percentage_from_cgpa(cgpa), division=division(cgpa))


@student.route('/results')
@role_required('student')
def results():
    results = _published_results(current_user)
    sems = _by_semester(results)
    data = [(s, rs, gpa(rs)) for s, rs in sems.items()]
    cgpa = gpa(results)
    return render_template('student/results.html', data=data, cgpa=cgpa,
                           percentage=percentage_from_cgpa(cgpa), division=division(cgpa))


@student.route('/attendance')
@role_required('student')
def attendance():
    return render_template('student/attendance.html', rows=_attendance_summary(current_user))


@student.route('/courses')
@role_required('student')
def courses():
    rows = Result.filter_by(student_id=current_user.id)
    rows.sort(key=lambda r: (r.course.semester, r.course.code))
    return render_template('student/courses.html', rows=rows)


@student.route('/profile')
@role_required('student')
def profile():
    return render_template('student/profile.html', p=current_user.profile)


@student.route('/exams')
@role_required('student')
def exams():
    """Exam timetable for every course the student is enrolled in."""
    course_ids = {r.course_id for r in Result.filter_by(student_id=current_user.id)}
    rows = [e for e in ExamSchedule.all() if e.course_id in course_ids]
    rows.sort(key=lambda e: (e.exam_date, e.start_time))
    today = date.today()
    upcoming = [e for e in rows if e.exam_date >= today]
    past = [e for e in rows if e.exam_date < today]
    return render_template('student/exams.html', upcoming=upcoming, past=past)


@student.route('/learn')
@role_required('student')
def learn():
    """Course list with learning-material progress, for the online-learning section."""
    rows = Result.filter_by(student_id=current_user.id)
    rows.sort(key=lambda r: (r.course.semester, r.course.code))
    done_ids = {p.resource_id for p in ResourceProgress.filter_by(student_id=current_user.id)}
    cards = []
    for r in rows:
        total = len(r.course.resources)
        if total == 0:
            continue
        done = sum(1 for res in r.course.resources if res.id in done_ids)
        cards.append(dict(course=r.course, total=total, done=done,
                          pct=round(done * 100 / total) if total else 0))
    return render_template('student/learn.html', cards=cards)


@student.route('/learn/<int:course_id>')
@role_required('student')
def learn_course(course_id):
    """Video tutorials and reading material for one enrolled course."""
    enrolled = Result.first_by(student_id=current_user.id, course_id=course_id)
    if not enrolled:
        abort(403)
    course = enrolled.course
    done_ids = {p.resource_id for p in ResourceProgress.filter_by(student_id=current_user.id)}
    return render_template('student/learn_course.html', course=course, done_ids=done_ids)


@student.route('/learn/resource/<int:resource_id>/toggle', methods=['POST'])
@role_required('student')
def toggle_resource(resource_id):
    """Mark a video/reading item as done (or undo it)."""
    resource = LearningResource.get(resource_id) or abort(404)
    enrolled = Result.first_by(student_id=current_user.id, course_id=resource.course_id)
    if not enrolled:
        abort(403)
    existing = ResourceProgress.first_by(student_id=current_user.id, resource_id=resource_id)
    if existing:
        existing.delete()
    else:
        ResourceProgress(student_id=current_user.id, resource_id=resource_id).save()
    return redirect(url_for('student.learn_course', course_id=resource.course_id))


@student.route('/marksheet.pdf')
@role_required('student')
def marksheet():
    """Download a marksheet PDF for one semester (?sem=3) or all semesters."""
    results = _published_results(current_user)
    if not results:
        abort(404)
    sems = _by_semester(results)
    sem = request.args.get('sem', type=int)
    if sem is not None:
        if sem not in sems:
            abort(404)
        sems = OrderedDict([(sem, sems[sem])])
    buf = _build_pdf(current_user, sems, gpa(results))
    fname = f'marksheet_{current_user.profile.enrollment_no}' + (f'_sem{sem}' if sem else '') + '.pdf'
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


def _build_pdf(user, sems, cgpa):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title='Marksheet', author=UNIVERSITY_NAME)
    ss = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=ss['Title'], fontSize=20, textColor=colors.HexColor('#1e3a8a'),
                           spaceAfter=2)
    sub = ParagraphStyle('s', parent=ss['Normal'], alignment=1, textColor=colors.HexColor('#475569'))
    h = ParagraphStyle('h', parent=ss['Heading3'], textColor=colors.HexColor('#1e3a8a'), spaceBefore=10)
    p = user.profile
    story = [Paragraph(UNIVERSITY_NAME.upper(), title),
             Paragraph('Statement of Marks / Grade Card', sub), Spacer(1, 8)]

    info = Table([
        ['Name', user.name, 'Enrollment No.', p.enrollment_no],
        ['Programme', p.program.name, 'Admission Year', str(p.admission_year)],
        ['Email', user.email, 'Date of Issue', datetime.now().strftime('%d %b %Y')],
    ], colWidths=[26 * mm, 62 * mm, 32 * mm, 50 * mm])
    info.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(info)

    for sem, rows in sems.items():
        story.append(Paragraph(f'Semester {sem}', h))
        data = [['Code', 'Course', 'Credits', 'Internal\n(40)', 'External\n(60)', 'Total\n(100)', 'Grade', 'GP']]
        for r in rows:
            g = r.grade
            data.append([r.course.code, r.course.title, r.course.credits, r.internal, r.external,
                         r.total, g[0], g[1]])
        data.append(['', 'Semester GPA (SGPA)', '', '', '', '', '', f'{gpa(rows):.2f}'])
        t = Table(data, colWidths=[18 * mm, 62 * mm, 16 * mm, 18 * mm, 18 * mm, 18 * mm, 14 * mm, 12 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f1f5f9')]),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')),
        ]))
        story.append(t)

    story += [Spacer(1, 12),
              Paragraph(f'<b>Cumulative GPA (CGPA):</b> {cgpa:.2f} &nbsp;&nbsp; '
                        f'<b>Equivalent %:</b> {percentage_from_cgpa(cgpa)} &nbsp;&nbsp; '
                        f'<b>Class:</b> {division(cgpa)}', ss['Normal']),
              Spacer(1, 6),
              Paragraph('Grading: O &ge;90 (10), A+ &ge;80 (9), A &ge;70 (8), B+ &ge;60 (7), B &ge;50 (6), '
                        'C &ge;45 (5), P &ge;40 (4), F &lt;40 (0). Equivalent % = CGPA x 9.5.',
                        ParagraphStyle('f', parent=ss['Normal'], fontSize=7.5,
                                       textColor=colors.HexColor('#64748b'))),
              Spacer(1, 26),
              Paragraph('This is a computer-generated statement of marks and does not require a signature.',
                        ParagraphStyle('c', parent=ss['Normal'], fontSize=7.5, alignment=1,
                                       textColor=colors.HexColor('#94a3b8')))]
    doc.build(story)
    buf.seek(0)
    return buf
