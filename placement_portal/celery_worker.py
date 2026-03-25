"""
Celery worker entry point.
Run with: celery -A celery_worker.celery worker --loglevel=info
Beat scheduler: celery -A celery_worker.celery beat --loglevel=info
"""
from app import create_app
from backend.tasks import make_celery, send_daily_reminders, generate_monthly_report
from celery.schedules import crontab

flask_app = create_app()

try:
    celery = make_celery(flask_app)

    # Register tasks
    @celery.task(name='tasks.send_daily_reminders')
    def task_daily_reminders():
        return send_daily_reminders()

    @celery.task(name='tasks.monthly_report')
    def task_monthly_report():
        return generate_monthly_report()

    # Beat schedule
    celery.conf.beat_schedule = {
        'daily-reminders': {
            'task': 'tasks.send_daily_reminders',
            'schedule': crontab(hour=8, minute=0),  # 8 AM daily
        },
        'monthly-report': {
            'task': 'tasks.monthly_report',
            'schedule': crontab(day_of_month=1, hour=6, minute=0),  # 1st of month
        },
    }
    celery.conf.timezone = 'Asia/Kolkata'

except Exception as e:
    print(f"[WARNING] Celery not available: {e}")
    celery = None
