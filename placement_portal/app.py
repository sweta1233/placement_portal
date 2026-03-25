"""Placement Portal Application - Main Flask entry point"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory
from config import Config
from backend.models import init_db, seed_admin


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # CORS
    try:
        from flask_cors import CORS
        CORS(app, supports_credentials=True)
    except ImportError:
        pass

    # Register blueprints
    from backend.routes.auth    import auth_bp
    from backend.routes.admin   import admin_bp
    from backend.routes.company import company_bp
    from backend.routes.student import student_bp
    from backend.routes.reports import pdf_bp

    app.register_blueprint(auth_bp,    url_prefix='/api/auth')
    app.register_blueprint(admin_bp,   url_prefix='/api/admin')
    app.register_blueprint(company_bp, url_prefix='/api/company')
    app.register_blueprint(student_bp, url_prefix='/api/student')
    app.register_blueprint(pdf_bp,     url_prefix='/api')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Init DB and seed
    init_db()
    seed_admin()

    frontend_dir = os.path.join(app.root_path, 'frontend_embedded')

    @app.route('/')
    def index():
        return send_from_directory(frontend_dir, 'index.html')

    @app.errorhandler(404)
    def not_found(e):
        try:
            return send_from_directory(frontend_dir, 'index.html')
        except Exception:
            return {'error': 'Not found'}, 404

    return app


if __name__ == '__main__':
    app = create_app()
    print("\n" + "="*55)
    print("  Placement Portal  ->  http://localhost:5000")
    print("  Admin login : admin / admin123")
    print("="*55 + "\n")
    app.run(debug=True, port=5000, host='0.0.0.0')
