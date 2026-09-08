"""
Database models using Python's built-in sqlite3.
No Flask-SQLAlchemy dependency required.
"""
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

_default_dir = '/tmp' if os.environ.get('VERCEL') else os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance')
DB_PATH = os.path.join(
    os.environ.get('INSTANCE_DIR', _default_dir),
    'placement_portal.db'
)

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Create all tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        is_blacklisted INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS student_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        full_name TEXT NOT NULL,
        roll_number TEXT UNIQUE,
        department TEXT,
        branch TEXT,
        year INTEGER,
        cgpa REAL DEFAULT 0,
        phone TEXT,
        resume_filename TEXT,
        skills TEXT,
        about TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS company_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_name TEXT NOT NULL,
        hr_name TEXT,
        hr_email TEXT,
        hr_phone TEXT,
        website TEXT,
        description TEXT,
        industry TEXT,
        approval_status TEXT DEFAULT 'pending',
        logo_filename TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS placement_drives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
        drive_name TEXT NOT NULL,
        job_title TEXT NOT NULL,
        job_description TEXT,
        eligibility_branch TEXT,
        eligibility_cgpa REAL DEFAULT 0,
        eligibility_year TEXT,
        application_deadline TEXT,
        salary TEXT,
        location TEXT,
        interview_type TEXT DEFAULT 'In-person',
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
        drive_id INTEGER NOT NULL REFERENCES placement_drives(id) ON DELETE CASCADE,
        application_date TEXT DEFAULT (datetime('now')),
        status TEXT DEFAULT 'applied',
        interview_date TEXT,
        remarks TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(student_id, drive_id)
    );

    CREATE TABLE IF NOT EXISTS export_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER REFERENCES student_profiles(id),
        status TEXT DEFAULT 'pending',
        file_path TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
        company_id INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
        student_id INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        meeting_link TEXT,
        scheduled_at TEXT NOT NULL,
        duration_minutes INTEGER DEFAULT 30,
        notes TEXT,
        status TEXT DEFAULT 'scheduled',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(application_id)
    );

    CREATE TABLE IF NOT EXISTS oa_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drive_id INTEGER NOT NULL REFERENCES placement_drives(id) ON DELETE CASCADE,
        company_id INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        question_source TEXT DEFAULT 'leetcode',
        scheduled_at TEXT NOT NULL,
        duration_minutes INTEGER DEFAULT 90,
        instructions TEXT,
        status TEXT DEFAULT 'scheduled',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS oa_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        oa_id INTEGER NOT NULL REFERENCES oa_schedules(id) ON DELETE CASCADE,
        difficulty TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        link TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS oa_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        oa_id INTEGER NOT NULL REFERENCES oa_schedules(id) ON DELETE CASCADE,
        student_id INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
        status TEXT DEFAULT 'not_started',
        questions_json TEXT,
        responses_json TEXT,
        score INTEGER DEFAULT 0,
        total_questions INTEGER DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        UNIQUE(oa_id, student_id)
    );
    """)

    # Defensive migration: add any columns missing on a DB created by an
    # earlier version of this app (CREATE TABLE IF NOT EXISTS won't add
    # columns to a table that already exists).
    for col_def in (
        "ALTER TABLE oa_attempts ADD COLUMN responses_json TEXT",
        "ALTER TABLE oa_attempts ADD COLUMN score INTEGER DEFAULT 0",
        "ALTER TABLE oa_attempts ADD COLUMN total_questions INTEGER DEFAULT 0",
    ):
        try:
            c.execute(col_def)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def seed_admin():
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not row:
        ph = generate_password_hash('admin123')
        conn.execute(
            "INSERT INTO users (username,email,password_hash,role) VALUES (?,?,?,?)",
            ('admin','admin@placement.edu',ph,'admin')
        )
        conn.commit()
        print("[SEED] Admin created: username=admin  password=admin123")
    conn.close()

# ─── helpers ────────────────────────────────────────────────────────────────

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows):
    return [dict(r) for r in rows]
