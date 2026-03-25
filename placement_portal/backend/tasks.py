"""
Celery tasks for background jobs.
Runs with Redis broker. Falls back gracefully if Redis is unavailable.
"""
from datetime import datetime


def make_celery(app):
    try:
        from celery import Celery
        celery = Celery(
            app.import_name,
            broker=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
            backend=app.config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
        )
        celery.conf.update(app.config)

        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask
        return celery
    except Exception as e:
        print(f"[CELERY] Not available: {e}")
        return None


def send_daily_reminders():
    """Send daily reminders to students about upcoming deadlines (runs via Celery beat or cron)."""
    from backend.models import get_db, rows_to_list
    from datetime import timedelta
    db = get_db()
    tomorrow = (datetime.utcnow() + timedelta(days=1)).isoformat()
    now = datetime.utcnow().isoformat()
    upcoming = rows_to_list(db.execute(
        "SELECT * FROM placement_drives WHERE status='approved' AND application_deadline<=? AND application_deadline>=?",
        (tomorrow, now)
    ).fetchall())
    students = rows_to_list(db.execute(
        "SELECT sp.*, u.email FROM student_profiles sp JOIN users u ON sp.user_id=u.id WHERE u.is_active=1 AND u.is_blacklisted=0"
    ).fetchall())
    db.close()

    count = 0
    for drive in upcoming:
        for student in students:
            db2 = get_db()
            existing = db2.execute(
                "SELECT id FROM applications WHERE student_id=? AND drive_id=?",
                (student['id'], drive['id'])
            ).fetchone()
            db2.close()
            if not existing:
                # In production: send email/SMS/webhook here
                print(f"[REMINDER] {student['full_name']} → '{drive['drive_name']}' deadline: {drive['application_deadline']}")
                count += 1
    print(f"[SCHEDULER] {count} reminders sent")
    return count


def generate_monthly_report():
    """Generate monthly PDF report and (optionally) email to admin."""
    from backend.models import get_db, rows_to_list
    db = get_db()
    now = datetime.utcnow()
    if now.month == 1:
        start = now.replace(year=now.year-1, month=12, day=1, hour=0, minute=0, second=0)
    else:
        start = now.replace(month=now.month-1, day=1, hour=0, minute=0, second=0)
    end = now.replace(day=1, hour=0, minute=0, second=0)
    s, e = start.isoformat(), end.isoformat()

    drives = rows_to_list(db.execute(
        "SELECT pd.*, cp.company_name FROM placement_drives pd JOIN company_profiles cp ON pd.company_id=cp.id WHERE pd.created_at>=? AND pd.created_at<?",
        (s, e)
    ).fetchall())
    apps   = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<?", (s,e)).fetchone()[0]
    sel    = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<? AND status='selected'", (s,e)).fetchone()[0]
    db.close()

    report = {
        'month': start.strftime('%B %Y'),
        'drives_conducted': len(drives),
        'students_applied': apps,
        'students_selected': sel,
        'drives': drives,
    }
    print(f"[MONTHLY REPORT] {report['month']}: {len(drives)} drives, {apps} applied, {sel} selected")
    return report
