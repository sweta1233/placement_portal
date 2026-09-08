import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'placement_portal_production_secret_key_default_32chars_min'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'placement_portal_jwt_secret_key_default_32chars_min'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@placement.edu')

    # DB lives in /opt/render/project/data on Render (persistent disk),
    # /tmp on Vercel (serverless ephemeral), or next to this file locally.
    if os.environ.get('VERCEL'):
        _base = os.environ.get('INSTANCE_DIR', '/tmp')
    else:
        _base = os.environ.get('INSTANCE_DIR', os.path.join(os.path.dirname(__file__), 'instance'))
    DATABASE = os.path.join(_base, 'placement_portal.db')

    # Uploads: same persistent directory so resumes survive restarts
    UPLOAD_FOLDER = os.path.join(_base, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
