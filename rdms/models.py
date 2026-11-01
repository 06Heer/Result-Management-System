"""Plain-Python model classes backed by JSON files (see rdms.jsondb).

Each class mirrors the shape of the old SQLAlchemy model with the same
field names, plus relationship-style properties/helpers that do simple id
lookups against the loaded JSON collections (no lazy ORM magic).
"""
from datetime import date, datetime, time

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from rdms import jsondb
from rdms.utils import grade_for

# field -> 'date' | 'time' | 'datetime' for (de)serialization
_DATE, _TIME, _DATETIME = 'date', 'time', 'datetime'


def _ser(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _deser(value, kind):
    if value is None:
        return None
    if isinstance(value, (date, time, datetime)):
        return value
    if kind == _DATE:
        return date.fromisoformat(value)
    if kind == _TIME:
        return time.fromisoformat(value)
    if kind == _DATETIME:
        return datetime.fromisoformat(value)
    return value


class Model:
    _collection = None
    _fields = []          # list of plain field names on the record
    _kinds = {}            # field -> 'date'/'time'/'datetime' for (de)serialization

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        for f in self._fields:
            setattr(self, f, kwargs.get(f))

    # ------------------------------------------------------------- loading
    @classmethod
    def _rows(cls):
        return jsondb.load(cls._collection)

    @classmethod
    def _from_row(cls, row):
        obj = cls.__new__(cls)
        obj.id = row.get('id')
        for f in cls._fields:
            val = row.get(f)
            kind = cls._kinds.get(f)
            if kind:
                val = _deser(val, kind)
            setattr(obj, f, val)
        return obj

    @classmethod
    def all(cls):
        return [cls._from_row(r) for r in cls._rows()]

    @classmethod
    def get(cls, id):
        if id is None:
            return None
        try:
            id = int(id)
        except (TypeError, ValueError):
            return None
        for r in cls._rows():
            if r.get('id') == id:
                return cls._from_row(r)
        return None

    @classmethod
    def filter_by(cls, **kw):
        out = []
        for r in cls._rows():
            if all(r.get(k) == v for k, v in kw.items()):
                out.append(cls._from_row(r))
        return out

    @classmethod
    def first_by(cls, **kw):
        rows = cls.filter_by(**kw)
        return rows[0] if rows else None

    @classmethod
    def count(cls):
        return len(cls._rows())

    # ------------------------------------------------------------- writing
    def _to_row(self):
        row = {'id': self.id}
        for f in self._fields:
            row[f] = _ser(getattr(self, f, None))
        return row

    def save(self):
        rows = self.__class__._rows()
        if self.id is None:
            self.id = jsondb.next_id(rows)
            rows.append(self._to_row())
        else:
            for i, r in enumerate(rows):
                if r.get('id') == self.id:
                    rows[i] = self._to_row()
                    break
            else:
                rows.append(self._to_row())
        jsondb.save(self.__class__._collection, rows)
        return self

    def delete(self):
        if self.id is None:
            return
        rows = [r for r in self.__class__._rows() if r.get('id') != self.id]
        jsondb.save(self.__class__._collection, rows)


class User(UserMixin, Model):
    _collection = 'users'
    _fields = ['email', 'name', 'password_hash', 'role', 'active', 'failed_attempts',
               'locked_until', 'last_login', 'created_at']
    _kinds = {'locked_until': _DATETIME, 'last_login': _DATETIME, 'created_at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('active', True)
        kwargs.setdefault('failed_attempts', 0)
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_active(self):
        return self.active

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_faculty(self):
        return self.role == 'faculty'

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def profile(self):
        return StudentProfile.first_by(user_id=self.id)

    def __repr__(self):
        return f'<User {self.email}>'


class Department(Model):
    _collection = 'departments'
    _fields = ['code', 'name']

    @property
    def programs(self):
        return sorted(Program.filter_by(department_id=self.id), key=lambda p: p.name)


class Program(Model):
    _collection = 'programs'
    _fields = ['code', 'name', 'duration_semesters', 'department_id']

    def __init__(self, **kwargs):
        kwargs.setdefault('duration_semesters', 8)
        super().__init__(**kwargs)

    @property
    def years(self):
        return self.duration_semesters / 2

    @property
    def department(self):
        return Department.get(self.department_id)

    @property
    def courses(self):
        return Course.filter_by(program_id=self.id)

    @property
    def students(self):
        return StudentProfile.filter_by(program_id=self.id)


class StudentProfile(Model):
    _collection = 'student_profiles'
    _fields = ['user_id', 'enrollment_no', 'program_id', 'semester', 'admission_year',
               'dob', 'gender', 'phone', 'state']
    _kinds = {'dob': _DATE}

    def __init__(self, **kwargs):
        kwargs.setdefault('semester', 1)
        super().__init__(**kwargs)

    @property
    def program(self):
        return Program.get(self.program_id)

    @property
    def user(self):
        return User.get(self.user_id)


class Course(Model):
    _collection = 'courses'
    _fields = ['code', 'title', 'credits', 'semester', 'program_id', 'faculty_id', 'published']

    def __init__(self, **kwargs):
        kwargs.setdefault('credits', 4)
        kwargs.setdefault('published', False)
        super().__init__(**kwargs)

    @property
    def program(self):
        return Program.get(self.program_id)

    @property
    def faculty(self):
        return User.get(self.faculty_id) if self.faculty_id else None

    @property
    def results(self):
        return Result.filter_by(course_id=self.id)

    @property
    def exam_schedules(self):
        return sorted(ExamSchedule.filter_by(course_id=self.id), key=lambda e: e.exam_date)

    @property
    def resources(self):
        return sorted(LearningResource.filter_by(course_id=self.id), key=lambda r: r.position)


class Result(Model):
    _collection = 'results'
    _fields = ['student_id', 'course_id', 'internal', 'external', 'updated_at']
    _kinds = {'updated_at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('updated_at', datetime.utcnow())
        super().__init__(**kwargs)

    def save(self):
        self.updated_at = datetime.utcnow()
        return super().save()

    @property
    def student(self):
        return User.get(self.student_id)

    @property
    def course(self):
        return Course.get(self.course_id)

    @property
    def total(self):
        if self.internal is None or self.external is None:
            return None
        return self.internal + self.external

    @property
    def grade(self):
        return grade_for(self.total)


class Attendance(Model):
    _collection = 'attendance'
    _fields = ['student_id', 'course_id', 'date', 'present']
    _kinds = {'date': _DATE}

    def __init__(self, **kwargs):
        kwargs.setdefault('present', True)
        super().__init__(**kwargs)

    @property
    def course(self):
        return Course.get(self.course_id)

    @property
    def student(self):
        return User.get(self.student_id)


class Announcement(Model):
    _collection = 'announcements'
    _fields = ['title', 'body', 'audience', 'created_at', 'author_id']
    _kinds = {'created_at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('audience', 'all')
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def author(self):
        return User.get(self.author_id) if self.author_id else None


class AuditLog(Model):
    _collection = 'audit_logs'
    _fields = ['at', 'actor', 'action', 'ip']
    _kinds = {'at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('at', datetime.utcnow())
        super().__init__(**kwargs)


class ExamSchedule(Model):
    _collection = 'exam_schedules'
    _fields = ['course_id', 'exam_type', 'exam_date', 'start_time', 'end_time', 'venue']
    _kinds = {'exam_date': _DATE, 'start_time': _TIME, 'end_time': _TIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('exam_type', 'End Semester')
        super().__init__(**kwargs)

    @property
    def course(self):
        return Course.get(self.course_id)


class LearningResource(Model):
    _collection = 'learning_resources'
    _fields = ['course_id', 'kind', 'title', 'url', 'body', 'position', 'added_at']
    _kinds = {'added_at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('kind', 'video')
        kwargs.setdefault('position', 0)
        kwargs.setdefault('added_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def course(self):
        return Course.get(self.course_id)

    @property
    def embed_url(self):
        import re
        u = (self.url or '').strip()
        patterns = [
            r'youtu\.be/([A-Za-z0-9_-]{11})',
            r'[?&]v=([A-Za-z0-9_-]{11})',
            r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
            r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
            r'youtube\.com/live/([A-Za-z0-9_-]{11})',
        ]
        for pat in patterns:
            m = re.search(pat, u)
            if m:
                return f'https://www.youtube.com/embed/{m.group(1)}'
        return None


class ResourceProgress(Model):
    _collection = 'resource_progress'
    _fields = ['student_id', 'resource_id', 'completed_at']
    _kinds = {'completed_at': _DATETIME}

    def __init__(self, **kwargs):
        kwargs.setdefault('completed_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def resource(self):
        return LearningResource.get(self.resource_id)
