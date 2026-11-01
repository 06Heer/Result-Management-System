"""Grading maths, validators and access-control decorators."""
import re
from functools import wraps

from flask import abort, request
from flask_login import current_user

# (minimum total marks, letter, grade points) -- Indian 10-point scale
GRADE_SCALE = [
    (90, 'O', 10), (80, 'A+', 9), (70, 'A', 8), (60, 'B+', 7),
    (50, 'B', 6), (45, 'C', 5), (40, 'P', 4),
]
PASS_MARK = 40


def grade_for(total):
    """Return (letter, points) for a total out of 100, or None if not graded yet."""
    if total is None:
        return None
    for minimum, letter, points in GRADE_SCALE:
        if total >= minimum:
            return letter, points
    return 'F', 0


def gpa(results):
    """Credit-weighted GPA over Result rows that have marks. Returns None if nothing graded."""
    credits = 0
    weighted = 0
    for r in results:
        g = r.grade
        if g is None:
            continue
        credits += r.course.credits
        weighted += g[1] * r.course.credits
    return round(weighted / credits, 2) if credits else None


def percentage_from_cgpa(cgpa):
    """Common Indian approximation: % = CGPA x 9.5."""
    return round(cgpa * 9.5, 2) if cgpa is not None else None


def division(cgpa):
    if cgpa is None:
        return '-'
    if cgpa >= 7.5:
        return 'First Class with Distinction'
    if cgpa >= 6.0:
        return 'First Class'
    if cgpa >= 5.0:
        return 'Second Class'
    return 'Pass Class'


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                return current_app_login_redirect()
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def current_app_login_redirect():
    from flask import current_app
    return current_app.login_manager.unauthorized()


EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def domain_ok(email, role):
    """All roles use a plain @gmail.com address."""
    from rdms import STUDENT_DOMAIN, FACULTY_DOMAIN, ADMIN_DOMAIN
    email = (email or '').lower()
    if not EMAIL_RE.match(email):
        return False, 'Enter a valid email address.'
    expected = {'student': STUDENT_DOMAIN, 'faculty': FACULTY_DOMAIN, 'admin': ADMIN_DOMAIN}[role]
    if not email.endswith('@' + expected):
        return False, f'{role.title()} email must end with @{expected}'
    return True, ''


def password_problem(pw):
    """Return an error string if the password is weak, else None."""
    if len(pw) < 8:
        return 'Password must be at least 8 characters.'
    if not re.search(r'[A-Za-z]', pw) or not re.search(r'\d', pw):
        return 'Password must contain both letters and numbers.'
    return None


def client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '')[:60]


def safe_next(target):
    """Only allow same-site relative redirects."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None
