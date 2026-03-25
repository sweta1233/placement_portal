from flask import Blueprint, send_file, jsonify
from backend.routes.auth import role_required
from backend.models import get_db, rows_to_list
from datetime import datetime
import os, tempfile

pdf_bp = Blueprint('pdf', __name__)

@pdf_bp.route('/admin/report/monthly/pdf', methods=['GET'])
@role_required('admin')
def monthly_report_pdf():
    from backend.utils.pdf_report import generate_monthly_pdf
    db = get_db()
    now = datetime.utcnow()
    if now.month == 1:
        start = now.replace(year=now.year-1, month=12, day=1, hour=0, minute=0, second=0)
    else:
        start = now.replace(month=now.month-1, day=1, hour=0, minute=0, second=0)
    end = now.replace(day=1, hour=0, minute=0, second=0)
    s, e = start.isoformat(), end.isoformat()
    drives = rows_to_list(db.execute("""
        SELECT pd.*, cp.company_name,
        (SELECT COUNT(*) FROM applications WHERE drive_id=pd.id) AS applicant_count
        FROM placement_drives pd JOIN company_profiles cp ON pd.company_id=cp.id
        WHERE pd.created_at>=? AND pd.created_at<?""", (s,e)).fetchall())
    apps  = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<?", (s,e)).fetchone()[0]
    sel   = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<? AND status='selected'", (s,e)).fetchone()[0]
    db.close()
    report_data = {
        'month': start.strftime('%B %Y'),
        'drives_conducted': len(drives),
        'students_applied': apps,
        'students_selected': sel,
        'drives': drives,
    }
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    generate_monthly_pdf(report_data, tmp.name)
    return send_file(tmp.name, as_attachment=True,
                     download_name=f"report_{start.strftime('%Y_%m')}.pdf",
                     mimetype='application/pdf')
