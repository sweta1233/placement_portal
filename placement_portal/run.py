#!/usr/bin/env python3
"""
Simple runner for the Placement Portal.
Usage: python run.py
"""
from app import create_app

if __name__ == '__main__':
    app = create_app()
    print("\n" + "="*55)
    print("  🎓  Placement Portal Application")
    print("  URL : http://localhost:5000")
    print("  Admin login: admin / admin123")
    print("="*55 + "\n")
    app.run(debug=True, port=5000, host='0.0.0.0')
