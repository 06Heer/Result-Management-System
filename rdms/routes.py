from datetime import datetime, timedelta

from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user

from rdms.models import Announcement, AuditLog, Course, Department, Program, User
from rdms.utils import client_ip, password_problem, safe_next

main = Blueprint('main', __name__)


def audit(action, actor=None):
    who = actor or (current_user.email if current_user.is_authenticated else 'anonymous')
    AuditLog(actor=who, action=action, ip=client_ip()).save()


def home_for(user):
    return url_for({'student': 'student.dashboard', 'faculty': 'faculty.dashboard',
                    'admin': 'admin.dashboard'}[user.role])


@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    stats = dict(programs=Program.count(), courses=Course.count(),
                 students=len(User.filter_by(role='student')),
                 faculty=len(User.filter_by(role='faculty')))
    notices = sorted(Announcement.filter_by(audience='all'), key=lambda a: a.created_at,
                     reverse=True)[:3]
    return render_template('home.html', stats=stats, notices=notices)


@main.route('/login', methods=['GET', 'POST'])
def login():
    """Single sign-in for students, faculty and admins; the role comes from the account."""
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.first_by(email=email)
        now = datetime.utcnow()
        generic = 'Invalid email or password.'

        if user and user.locked_until and user.locked_until > now:
            mins = int((user.locked_until - now).total_seconds() // 60) + 1
            flash(f'Account temporarily locked after too many failed attempts. '
                  f'Try again in {mins} minute(s).', 'danger')
        elif user and user.check_password(password):
            if not user.active:
                flash('This account has been deactivated. Contact the administrator.', 'danger')
                return render_template('login.html')
            user.failed_attempts = 0
            user.locked_until = None
            user.last_login = now
            user.save()
            login_user(user, remember=bool(request.form.get('remember')))
            audit('Signed in', actor=user.email)
            return redirect(safe_next(request.args.get('next')) or home_for(user))
        else:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= current_app.config['MAX_FAILED_LOGINS']:
                    user.locked_until = now + timedelta(minutes=current_app.config['LOCKOUT_MINUTES'])
                    user.failed_attempts = 0
                user.save()
            audit(f'Failed sign-in for {email}', actor='anonymous')
            flash(generic, 'danger')
    return render_template('login.html')


@main.route('/logout', methods=['POST'])
@login_required
def logout():
    audit('Signed out')
    logout_user()
    flash('You have been signed out.', 'success')
    return redirect(url_for('main.index'))


@main.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current', '')
        new = request.form.get('new', '')
        confirm = request.form.get('confirm', '')
        if not current_user.check_password(current):
            flash('Current password is incorrect.', 'danger')
        elif new != confirm:
            flash('New passwords do not match.', 'danger')
        elif password_problem(new):
            flash(password_problem(new), 'danger')
        else:
            current_user.set_password(new)
            current_user.save()
            audit('Changed own password')
            flash('Password updated successfully.', 'success')
            return redirect(home_for(current_user))
    return render_template('change_password.html')


@main.route('/about')
def about():
    depts = sorted(Department.all(), key=lambda d: d.name)
    return render_template('about.html', depts=depts)


@main.route('/programs')
def programs():
    progs = sorted(Program.all(), key=lambda p: p.name)
    return render_template('programs.html', programs=progs)


@main.route('/contact')
def contact():
    return render_template('contact.html')
