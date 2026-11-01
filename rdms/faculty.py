from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from rdms.models import Announcement, Attendance, Course, ExamSchedule, LearningResource, Result
from rdms.routes import audit
from rdms.utils import gpa, role_required

faculty = Blueprint('faculty', __name__)


def _my_course(course_id):
    c = Course.get(course_id) or abort(404)
    if c.faculty_id != current_user.id:
        abort(403)
    return c


@faculty.route('/')
@role_required('faculty')
def dashboard():
    courses = Course.filter_by(faculty_id=current_user.id)
    courses.sort(key=lambda c: (c.semester, c.code))
    cards = []
    for c in courses:
        rows = c.results
        graded = [r for r in rows if r.total is not None]
        avg = round(sum(r.total for r in graded) / len(graded), 1) if graded else None
        passed = sum(1 for r in graded if r.total >= 40)
        cards.append(dict(course=c, enrolled=len(rows), graded=len(graded), avg=avg,
                          pass_pct=round(passed * 100 / len(graded)) if graded else None))
    notices = sorted((a for a in Announcement.all() if a.audience in ('all', 'faculty')),
                     key=lambda a: a.created_at, reverse=True)[:5]
    return render_template('faculty/dashboard.html', cards=cards, notices=notices)


@faculty.route('/course/<int:course_id>', methods=['GET', 'POST'])
@role_required('faculty')
def marks(course_id):
    c = _my_course(course_id)
    rows = Result.filter_by(course_id=c.id)
    rows.sort(key=lambda r: r.student_id)
    if request.method == 'POST':
        errors, saved = [], 0
        for r in rows:
            i_raw = request.form.get(f'internal_{r.id}', '').strip()
            e_raw = request.form.get(f'external_{r.id}', '').strip()
            try:
                internal = int(i_raw) if i_raw != '' else None
                external = int(e_raw) if e_raw != '' else None
            except ValueError:
                errors.append(f'{r.student.name}: marks must be whole numbers.')
                continue
            if internal is not None and not 0 <= internal <= 40:
                errors.append(f'{r.student.name}: internal must be 0-40.')
                continue
            if external is not None and not 0 <= external <= 60:
                errors.append(f'{r.student.name}: external must be 0-60.')
                continue
            if (internal, external) != (r.internal, r.external):
                r.internal, r.external = internal, external
                r.save()
                saved += 1
        audit(f'Saved marks for {c.code} ({saved} changed)')
        for e in errors:
            flash(e, 'danger')
        if saved:
            flash(f'Saved marks for {saved} student(s).', 'success')
        elif not errors:
            flash('No changes to save.', 'info')
        return redirect(url_for('faculty.marks', course_id=c.id))
    graded = [r.total for r in rows if r.total is not None]
    stats = dict(count=len(rows), graded=len(graded),
                 avg=round(sum(graded) / len(graded), 1) if graded else None,
                 high=max(graded) if graded else None, low=min(graded) if graded else None)
    return render_template('faculty/marks.html', course=c, rows=rows, stats=stats)


@faculty.route('/course/<int:course_id>/publish', methods=['POST'])
@role_required('faculty')
def publish(course_id):
    c = _my_course(course_id)
    if not c.published and any(r.total is None for r in c.results):
        flash('Enter internal and external marks for every student before publishing.', 'danger')
    else:
        c.published = not c.published
        c.save()
        audit(f'{"Published" if c.published else "Unpublished"} results for {c.code}')
        flash('Results are now visible to students.' if c.published
              else 'Results hidden from students.', 'success')
    return redirect(url_for('faculty.marks', course_id=c.id))


@faculty.route('/course/<int:course_id>/attendance', methods=['GET', 'POST'])
@role_required('faculty')
def attendance(course_id):
    c = _my_course(course_id)
    rows = Result.filter_by(course_id=c.id)
    rows.sort(key=lambda r: r.student_id)
    students = [r.student for r in rows]
    try:
        day = datetime.strptime(request.values.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        day = date.today()
    if day > date.today():
        flash('Cannot mark attendance for a future date.', 'danger')
        day = date.today()
    existing = {a.student_id: a for a in Attendance.filter_by(course_id=c.id, date=day.isoformat())}
    if request.method == 'POST':
        present_ids = set(request.form.getlist('present'))
        for s in students:
            is_present = str(s.id) in present_ids
            rec = existing.get(s.id)
            if rec:
                rec.present = is_present
                rec.save()
            else:
                Attendance(student_id=s.id, course_id=c.id, date=day, present=is_present).save()
        audit(f'Marked attendance for {c.code} on {day}')
        flash(f'Attendance saved for {day.strftime("%d %b %Y")}.', 'success')
        return redirect(url_for('faculty.attendance', course_id=c.id, date=day.isoformat()))
    # overall percentage per student
    pct = {}
    for s in students:
        arows = Attendance.filter_by(course_id=c.id, student_id=s.id)
        pct[s.id] = round(sum(1 for a in arows if a.present) * 100 / len(arows)) if arows else None
    return render_template('faculty/attendance.html', course=c, students=students, day=day,
                           existing=existing, pct=pct, today=date.today())


@faculty.route('/course/<int:course_id>/exams')
@role_required('faculty')
def exams(course_id):
    c = _my_course(course_id)
    rows = sorted(ExamSchedule.filter_by(course_id=c.id), key=lambda e: e.exam_date)
    return render_template('faculty/exams.html', course=c, rows=rows)


@faculty.route('/course/<int:course_id>/learn', methods=['GET', 'POST'])
@role_required('faculty')
def learning(course_id):
    """Add/remove video tutorials and reading material for this course."""
    c = _my_course(course_id)
    if request.method == 'POST':
        kind = request.form.get('kind', 'video')
        title = (request.form.get('title') or '').strip()
        url_val = (request.form.get('url') or '').strip()
        body = (request.form.get('body') or '').strip()
        if not title or (kind == 'video' and not url_val) or (kind == 'reading' and not url_val and not body):
            flash('A title is required, plus a link (video) or a link/notes (reading).', 'danger')
        else:
            existing = LearningResource.filter_by(course_id=c.id)
            next_pos = (max((r.position for r in existing), default=0)) + 1
            LearningResource(course_id=c.id, kind=kind, title=title, url=url_val or None,
                             body=body or None, position=next_pos).save()
            audit(f'Added {kind} resource to {c.code}: {title}')
            flash('Added to course content.', 'success')
        return redirect(url_for('faculty.learning', course_id=c.id))
    resources = sorted(LearningResource.filter_by(course_id=c.id), key=lambda r: r.position)
    return render_template('faculty/learning.html', course=c, resources=resources)


@faculty.route('/course/<int:course_id>/learn/<int:resource_id>/delete', methods=['POST'])
@role_required('faculty')
def learning_delete(course_id, resource_id):
    c = _my_course(course_id)
    r = LearningResource.first_by(id=resource_id, course_id=c.id) or abort(404)
    title = r.title
    r.delete()
    audit(f'Removed resource from {c.code}: {title}')
    flash('Removed.', 'success')
    return redirect(url_for('faculty.learning', course_id=c.id))
