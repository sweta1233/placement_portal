# Placement Portal Application (PPA)

A full-stack Campus Recruitment System built with **Flask** (backend) + **Vue 3** (frontend, CDN) + **SQLite** (database).

---

## Tech Stack

| Layer       | Technology                     |
|-------------|--------------------------------|
| Backend     | Python 3.11 · Flask 3.x        |
| Frontend    | Vue 3 (CDN) · Bootstrap 5      |
| Database    | SQLite (via Python `sqlite3`)  |
| Auth        | JWT (PyJWT)                    |
| Charts      | Chart.js (CDN)                 |
| PDF Reports | ReportLab                      |
| Async Jobs  | Python `threading` (Celery-ready) |
| Caching     | Redis / Flask-Caching (optional) |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example env file and edit secrets before deploying:
```bash
cp .env.example .env   # edit SECRET_KEY, JWT_SECRET_KEY, MAIL_* etc.
```
A working `.env` with safe dev defaults is already included so the app runs out of the box locally.

### 3. Run the server

**Local development:**
```bash
python run.py
# or
python app.py
```

**Production (gunicorn):**
```bash
gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"
```

Open **http://localhost:5000**

### 4. One-click deploy

- **Render.com**: push this repo and Render will auto-detect `render.yaml`.
- **Heroku / Railway**: the included `Procfile` works out of the box.
- Any Python host: just run the gunicorn command above; the SQLite DB and `uploads/` folder are auto-created under `instance/` and `uploads/` on first run.

---

## Default Credentials

| Role  | Username | Password  |
|-------|----------|-----------|
| Admin | `admin`  | `admin123`|

Admin is pre-seeded automatically on first run.

---

## Project Structure

```
placement_portal/
├── app.py                  # Flask app factory (serves API + SPA + /assets)
├── run.py                  # Convenience runner
├── config.py               # Configuration
├── celery_worker.py        # Celery entry point
├── requirements.txt
├── Procfile                # Heroku/Railway deploy command
├── render.yaml             # Render.com one-click deploy config
├── .env                    # Local dev environment variables (safe defaults)
├── .env.example            # Template for production secrets
├── .gitignore
│
├── backend/
│   ├── models.py           # SQLite schema + helpers
│   ├── tasks.py            # Celery / background tasks
│   ├── routes/
│   │   ├── auth.py         # Login / Register / JWT
│   │   ├── admin.py        # Admin APIs
│   │   ├── company.py      # Company APIs
│   │   ├── student.py      # Student APIs
│   │   └── reports.py      # PDF report generation
│   └── utils/
│       └── pdf_report.py   # ReportLab PDF builder
│
├── frontend_embedded/
│   ├── index.html          # Single-file Vue 3 SPA (no build step needed)
│   └── assets/             # Role-specific dashboard background images
│       ├── bg-login.jpg
│       ├── bg-admin.jpg
│       ├── bg-company.jpg
│       └── bg-student.jpg
│
├── instance/                # SQLite database (auto-created at runtime)
└── uploads/                  # Uploaded resumes + CSV exports (auto-created)
```

> The previous `frontend/` Vue-CLI scaffold (unused/unbuilt, not wired to the backend) and an empty stray folder from a packaging error have been removed to keep the project lean and deploy-ready.

### Dashboard backgrounds
Each role gets its own low-opacity background image behind the dashboard content (cards stay solid/white so text remains fully readable):
- **Login page** – welcoming collaborative workspace scene
- **Admin** – executive office / skyline
- **Company** – corporate campus
- **Student** – vibrant student collaboration space

---

## Roles & Features

### Admin
- Dashboard with live stats + Chart.js charts
- Approve / Reject company registrations
- Approve / Reject placement drives
- Blacklist / Deactivate students or companies
- View all applications
- Monthly PDF report download (`/api/admin/report/monthly/pdf`)
- Search companies and students

### Company
- Register company profile (pending admin approval)
- Create placement drives (pending admin approval)
- View student applications per drive
- Update application status: Applied → Shortlisted → Waiting → Selected / Rejected
- Dashboard with drive and applicant stats

### Student
- Self-register with full profile
- Browse approved placement drives
- Eligibility-based filtering (CGPA, branch, year)
- Apply to drives (duplicate prevention + eligibility validation)
- Track application status
- View full placement history
- Upload resume (PDF/DOC)
- Export placement history as CSV (async background job)

---

## API Reference (38 endpoints)

### Auth
| Method | Endpoint              | Description        |
|--------|-----------------------|--------------------|
| POST   | `/api/auth/register`  | Register student/company |
| POST   | `/api/auth/login`     | Login (any role)   |
| GET    | `/api/auth/me`        | Get current user   |

### Admin
| Method | Endpoint                              |
|--------|---------------------------------------|
| GET    | `/api/admin/dashboard`                |
| GET    | `/api/admin/companies`                |
| POST   | `/api/admin/companies/:id/approve`    |
| POST   | `/api/admin/companies/:id/reject`     |
| POST   | `/api/admin/companies/:id/blacklist`  |
| GET    | `/api/admin/students`                 |
| POST   | `/api/admin/students/:id/blacklist`   |
| POST   | `/api/admin/students/:id/deactivate`  |
| GET    | `/api/admin/drives`                   |
| POST   | `/api/admin/drives/:id/approve`       |
| POST   | `/api/admin/drives/:id/reject`        |
| GET    | `/api/admin/applications`             |
| GET    | `/api/admin/stats`                    |
| GET    | `/api/admin/report/monthly`           |
| GET    | `/api/admin/report/monthly/pdf`       |

### Company
| Method | Endpoint                                  |
|--------|-------------------------------------------|
| GET/PUT| `/api/company/profile`                    |
| GET/POST| `/api/company/drives`                    |
| PUT    | `/api/company/drives/:id`                 |
| GET    | `/api/company/drives/:id/applications`    |
| PUT    | `/api/company/applications/:id`           |

### Student
| Method | Endpoint                              |
|--------|---------------------------------------|
| GET/PUT| `/api/student/profile`                |
| POST   | `/api/student/profile/resume`         |
| GET    | `/api/student/drives`                 |
| POST   | `/api/student/drives/:id/apply`       |
| GET    | `/api/student/applications`           |
| GET    | `/api/student/history`                |
| GET    | `/api/student/companies`              |
| GET    | `/api/student/companies/:id`          |
| POST   | `/api/student/export`                 |
| GET    | `/api/student/export/:id/status`      |
| GET    | `/api/student/export/:id/download`    |

---

## Background Jobs

### Option A: Python Threading (default, no Redis needed)
The CSV export runs in a background thread automatically.

### Option B: Celery + Redis (full setup)
```bash
# Start Redis
redis-server

# Start Celery worker
celery -A celery_worker.celery worker --loglevel=info

# Start Celery beat (for scheduled jobs)
celery -A celery_worker.celery beat --loglevel=info
```

Scheduled jobs:
- **Daily 8 AM** → sends deadline reminders to students
- **1st of month 6 AM** → generates monthly activity report

---

## Database Schema (ER Summary)

```
users (id, username, email, password_hash, role, is_active, is_blacklisted)
  └── student_profiles (user_id FK, full_name, roll_number, department, branch, year, cgpa, phone, resume, skills)
  └── company_profiles (user_id FK, company_name, hr_name, industry, approval_status, website)
        └── placement_drives (company_id FK, drive_name, job_title, eligibility_*, deadline, status)
              └── applications (student_id FK, drive_id FK, status, interview_date, remarks)
export_jobs (student_id FK, status, file_path)
```

---

## Folder Structure for Vue Build (optional)

If you want to build the Vue frontend separately:
```bash
cd frontend
npm install
npm run build
# dist/ folder is then served by Flask
```

The embedded `frontend_embedded/index.html` works without any build step.
