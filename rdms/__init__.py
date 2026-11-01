import os
from datetime import timedelta

from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
csrf = CSRFProtect()

UNIVERSITY_NAME = 'University of India'
UNIVERSITY_SHORT = 'UoI'
STUDENT_DOMAIN = 'gmail.com'
FACULTY_DOMAIN = 'gmail.com'
ADMIN_DOMAIN = 'gmail.com'


def create_app():
    app = Flask(__name__)
    base = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config.update(
        # Set SECRET_KEY as an environment variable in production!
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-only-change-me-in-production'),
        DATA_DIR=os.environ.get('DATA_DIR', os.path.join(base, 'data')),
        REMEMBER_COOKIE_DURATION=timedelta(days=7),
        REMEMBER_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
        MAX_FAILED_LOGINS=5,
        LOCKOUT_MINUTES=15,
    )

    from rdms import jsondb
    jsondb.init_store(app.config['DATA_DIR'])

    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Please sign in to continue.'
    login_manager.login_message_category = 'warning'

    from rdms.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    from rdms.routes import main
    from rdms.student import student
    from rdms.faculty import faculty
    from rdms.admin import admin_bp
    app.register_blueprint(main)
    app.register_blueprint(student, url_prefix='/student')
    app.register_blueprint(faculty, url_prefix='/faculty')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.context_processor
    def inject_globals():
        return dict(UNI=UNIVERSITY_NAME, UNI_SHORT=UNIVERSITY_SHORT,
                    STUDENT_DOMAIN=STUDENT_DOMAIN, FACULTY_DOMAIN=FACULTY_DOMAIN,
                    ADMIN_DOMAIN=ADMIN_DOMAIN)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.after_request
    def security_headers(resp):
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
        resp.headers['Referrer-Policy'] = 'same-origin'
        return resp

    with app.app_context():
        from rdms.seed import seed_if_empty
        seed_if_empty()

    return app
