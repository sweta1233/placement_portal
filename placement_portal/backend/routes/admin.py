from flask import Blueprint, request, jsonify
from backend.models import get_db, row_to_dict, rows_to_list
from backend.routes.auth import role_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard', methods=['GET'])
@role_required('admin')
def dashboard():
    db = get_db()
    stats = {
        'total_students':    db.execute("SELECT COUNT(*) FROM student_profiles").fetchone()[0],
        'total_companies':   db.execute("SELECT COUNT(*) FROM company_profiles").fetchone()[0],
        'total_drives':      db.execute("SELECT COUNT(*) FROM placement_drives").fetchone()[0],
        'total_applications':db.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
        'selected_students': db.execute("SELECT COUNT(*) FROM applications WHERE status='selected'").fetchone()[0],
        'pending_companies': db.execute("SELECT COUNT(*) FROM company_profiles WHERE approval_status='pending'").fetchone()[0],
        'pending_drives':    db.execute("SELECT COUNT(*) FROM placement_drives WHERE status='pending'").fetchone()[0],
    }
    db.close()
    return jsonify(stats)

@admin_bp.route('/companies', methods=['GET'])
@role_required('admin')
def get_companies():
    search = request.args.get('search','')
    status = request.args.get('status','')
    db = get_db()
    q = """SELECT cp.*, u.email, u.username, u.is_blacklisted, u.is_active
           FROM company_profiles cp JOIN users u ON cp.user_id=u.id
           WHERE cp.company_name LIKE ? """
    params = [f'%{search}%']
    if status:
        q += " AND cp.approval_status=?"; params.append(status)
    rows = rows_to_list(db.execute(q, params).fetchall())
    db.close()
    return jsonify(rows)

@admin_bp.route('/companies/<int:cid>/approve', methods=['POST'])
@role_required('admin')
def approve_company(cid):
    db = get_db()
    db.execute("UPDATE company_profiles SET approval_status='approved' WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({'message':'Company approved'})

@admin_bp.route('/companies/<int:cid>/reject', methods=['POST'])
@role_required('admin')
def reject_company(cid):
    db = get_db()
    db.execute("UPDATE company_profiles SET approval_status='rejected' WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({'message':'Company rejected'})

@admin_bp.route('/companies/<int:cid>/blacklist', methods=['POST'])
@role_required('admin')
def blacklist_company(cid):
    db = get_db()
    row = db.execute("SELECT user_id FROM company_profiles WHERE id=?", (cid,)).fetchone()
    if not row: db.close(); return jsonify({'error':'Not found'}), 404
    uid = row[0]
    cur_bl = db.execute("SELECT is_blacklisted FROM users WHERE id=?", (uid,)).fetchone()[0]
    new_bl = 0 if cur_bl else 1
    db.execute("UPDATE users SET is_blacklisted=? WHERE id=?", (new_bl, uid))
    if new_bl:
        db.execute("UPDATE placement_drives SET status='closed' WHERE company_id=? AND status NOT IN ('closed')", (cid,))
    db.commit(); db.close()
    return jsonify({'message': 'Company blacklisted' if new_bl else 'Company unblacklisted'})

@admin_bp.route('/students', methods=['GET'])
@role_required('admin')
def get_students():
    search = request.args.get('search','')
    db = get_db()
    rows = rows_to_list(db.execute("""
        SELECT sp.*, u.email, u.username, u.is_blacklisted, u.is_active
        FROM student_profiles sp JOIN users u ON sp.user_id=u.id
        WHERE sp.full_name LIKE ? OR sp.roll_number LIKE ?
    """, (f'%{search}%', f'%{search}%')).fetchall())
    db.close()
    return jsonify(rows)

@admin_bp.route('/students/<int:sid>/blacklist', methods=['POST'])
@role_required('admin')
def blacklist_student(sid):
    db = get_db()
    uid = db.execute("SELECT user_id FROM student_profiles WHERE id=?", (sid,)).fetchone()
    if not uid: db.close(); return jsonify({'error':'Not found'}), 404
    uid = uid[0]
    cur = db.execute("SELECT is_blacklisted FROM users WHERE id=?", (uid,)).fetchone()[0]
    new_bl = 0 if cur else 1
    db.execute("UPDATE users SET is_blacklisted=? WHERE id=?", (new_bl, uid))
    db.commit(); db.close()
    return jsonify({'message': 'Student blacklisted' if new_bl else 'Student unblacklisted'})

@admin_bp.route('/students/<int:sid>/deactivate', methods=['POST'])
@role_required('admin')
def deactivate_student(sid):
    db = get_db()
    uid = db.execute("SELECT user_id FROM student_profiles WHERE id=?", (sid,)).fetchone()
    if not uid: db.close(); return jsonify({'error':'Not found'}), 404
    uid = uid[0]
    cur = db.execute("SELECT is_active FROM users WHERE id=?", (uid,)).fetchone()[0]
    new_active = 0 if cur else 1
    db.execute("UPDATE users SET is_active=? WHERE id=?", (new_active, uid))
    db.commit(); db.close()
    return jsonify({'message': 'Student deactivated' if not new_active else 'Student activated'})

@admin_bp.route('/drives', methods=['GET'])
@role_required('admin')
def get_drives():
    status = request.args.get('status','')
    db = get_db()
    q = """SELECT pd.*, cp.company_name,
           (SELECT COUNT(*) FROM applications WHERE drive_id=pd.id) AS applicant_count
           FROM placement_drives pd JOIN company_profiles cp ON pd.company_id=cp.id"""
    params = []
    if status:
        q += " WHERE pd.status=?"; params.append(status)
    rows = rows_to_list(db.execute(q, params).fetchall())
    db.close()
    return jsonify(rows)

@admin_bp.route('/drives/<int:did>/approve', methods=['POST'])
@role_required('admin')
def approve_drive(did):
    db = get_db()
    db.execute("UPDATE placement_drives SET status='approved' WHERE id=?", (did,))
    db.commit(); db.close()
    return jsonify({'message':'Drive approved'})

@admin_bp.route('/drives/<int:did>/reject', methods=['POST'])
@role_required('admin')
def reject_drive(did):
    db = get_db()
    db.execute("UPDATE placement_drives SET status='rejected' WHERE id=?", (did,))
    db.commit(); db.close()
    return jsonify({'message':'Drive rejected'})

@admin_bp.route('/applications', methods=['GET'])
@role_required('admin')
def get_all_applications():
    db = get_db()
    rows = rows_to_list(db.execute("""
        SELECT a.*, sp.full_name AS student_name, sp.department AS student_department,
               pd.drive_name, pd.job_title, pd.interview_type, cp.company_name
        FROM applications a
        JOIN student_profiles sp ON a.student_id=sp.id
        JOIN placement_drives pd ON a.drive_id=pd.id
        JOIN company_profiles cp ON pd.company_id=cp.id
    """).fetchall())
    db.close()
    return jsonify(rows)

@admin_bp.route('/stats', methods=['GET'])
@role_required('admin')
def get_stats():
    db = get_db()
    apps_by_status = {}
    for row in db.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall():
        apps_by_status[row[0]] = row[1]
    drives_by_status = {}
    for row in db.execute("SELECT status, COUNT(*) FROM placement_drives GROUP BY status").fetchall():
        drives_by_status[row[0]] = row[1]
    top_companies = []
    for row in db.execute("""
        SELECT cp.company_name, COUNT(pd.id) AS drive_count
        FROM company_profiles cp JOIN placement_drives pd ON pd.company_id=cp.id
        GROUP BY cp.id ORDER BY drive_count DESC LIMIT 5
    """).fetchall():
        top_companies.append({'name': row[0], 'drives': row[1]})
    db.close()
    return jsonify({'apps_by_status': apps_by_status,
                    'drives_by_status': drives_by_status,
                    'top_companies': top_companies})

@admin_bp.route('/report/monthly', methods=['GET'])
@role_required('admin')
def monthly_report():
    from datetime import datetime
    db = get_db()
    now = datetime.utcnow()
    if now.month == 1:
        start = now.replace(year=now.year-1, month=12, day=1, hour=0, minute=0, second=0)
    else:
        start = now.replace(month=now.month-1, day=1, hour=0, minute=0, second=0)
    end = now.replace(day=1, hour=0, minute=0, second=0)
    s, e = start.isoformat(), end.isoformat()
    drives = db.execute("SELECT COUNT(*) FROM placement_drives WHERE created_at>=? AND created_at<?", (s,e)).fetchone()[0]
    apps   = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<?", (s,e)).fetchone()[0]
    sel    = db.execute("SELECT COUNT(*) FROM applications WHERE application_date>=? AND application_date<? AND status='selected'", (s,e)).fetchone()[0]
    db.close()
    return jsonify({'month': start.strftime('%B %Y'),
                    'drives_conducted': drives,
                    'students_applied': apps,
                    'students_selected': sel})
