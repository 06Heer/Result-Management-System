# University of India — Result Management & Academic Portal

A Flask web app for managing student results, attendance and courses.
Three roles: Student, Faculty, Admin. Data is stored as plain JSON files
(no database server needed).

## Setup from scratch (local machine)

Follow these steps in order if you're starting on a fresh computer with
nothing installed yet.

### 1. Install Python

- Go to https://www.python.org/downloads/ and download **Python 3.11 or newer**.
- Run the installer. On Windows, **tick the "Add python.exe to PATH" checkbox**
  on the first screen before clicking Install — this is the most commonly
  missed step.
- Confirm it installed correctly by opening a terminal (Command Prompt /
  PowerShell / Terminal) and running:
  ```
  python --version
  ```
  You should see something like `Python 3.11.x`. If you get "command not
  found", Python wasn't added to PATH — reinstall and tick that box, or
  search "add Python to PATH" for your OS.
- `pip` (Python's package installer) comes bundled with Python automatically
  — check it with:
  ```
  pip --version
  ```

### 2. Get the project files

**If you received this project as a ZIP file:**
- Right-click the `.zip` file → **Extract All** (Windows) or double-click it
  (Mac) → choose a location (e.g. Desktop or Documents) → Extract.
- Don't run files directly from inside the zip — always extract it first, or
  things like file paths can misbehave.

**If you're getting it from GitHub instead:**
- Install Git (https://git-scm.com/downloads) and clone the repo:
  ```
  git clone <your-repo-url>
  cd Result-Management-System-main
  ```

### 3. Open a terminal in the project folder

- Windows: open the folder in File Explorer, click the address bar, type
  `cmd`, press Enter.
- Or in VS Code: open the folder, then Terminal → New Terminal.

### 4. Create a virtual environment (recommended, not required)

A virtual environment keeps this project's packages separate from other
Python projects on your machine.
```
python -m venv .venv
```
Activate it:
- Windows: `.venv\Scripts\activate`
- Mac/Linux: `source .venv/bin/activate`

You'll know it worked when your terminal prompt shows `(.venv)` at the start.

### 5. Install the project's dependencies

With the virtual environment active, run:
```
pip install -r requirements.txt
```
This installs everything the app needs: Flask, Flask-Login, Flask-WTF,
reportlab, and gunicorn.

### 6. Run the app

```
python run.py
```

You should see output saying the server is running. Open a browser to:
```
http://127.0.0.1:5000
```

On first run, a `data/` folder is created automatically and filled with
demo accounts and sample data — no manual setup needed. To start
completely fresh later, delete the `data/` folder and run again.

### 7. Stop the app

Press `Ctrl+C` in the terminal. To leave the virtual environment, type
`deactivate`.

## Demo logins

| Role    | Email                    | Password    |
|---------|--------------------------|-------------|
| Admin   | registrar@gmail.com      | Admin@123   |
| Faculty | rajesh.sharma@gmail.com  | Faculty@123 |
| Student | aarav.sharma@gmail.com   | Student@123 |

All other demo students/faculty use `firstname.lastname@gmail.com` with
the password matching their role above. Change these before real use.

## Features

- Single sign-in for Student / Faculty / Admin, change password, admin password reset
- Hashed passwords, CSRF protection, lockout after 5 failed logins, deactivate accounts, audit log
- Multiple programmes with departments, semesters, credits and courses
- Indian 10-point grading, automatic SGPA/CGPA, marksheet PDF download
- Faculty: marks entry, attendance, publish/unpublish results, course learning material
- Student: results, attendance (with 75% shortage warning), courses, exam timetable, course content
- Admin: user management, courses/departments/programmes, exam schedule, announcements, reports, CSV export

## Deploying (Railway)

1. Push this project to a GitHub repo (see `.gitignore` for what to exclude).
2. On [railway.app](https://railway.app): New Project → Deploy from GitHub repo.
3. Add a persistent volume mounted at `/app/data`.
4. Set environment variables:
   - `SECRET_KEY` — a long random string
   - `DATA_DIR` — `/app/data`
5. Deploy. Railway uses the included `Procfile` to start the app with gunicorn.

## Production notes

Always set `SECRET_KEY` via environment variable in production — never use the
default. Make sure `DATA_DIR` points at persistent storage, or all data will be
lost when the server restarts.
