from flask import Blueprint, request, jsonify
from backend.models import get_db, row_to_dict, rows_to_list
from backend.routes.auth import role_required
from datetime import datetime

company_bp = Blueprint('company', __name__)

def _get_company(user_id, db):
    return row_to_dict(db.execute("SELECT * FROM company_profiles WHERE user_id=?", (user_id,)).fetchone())

@company_bp.route('/profile', methods=['GET'])
@role_required('company')
def get_profile():
    db = get_db()
    u = request.current_user
    c = _get_company(u['id'], db)
    if c:
        c['email'] = u['email']; c['username'] = u['username']
        c['is_blacklisted'] = u['is_blacklisted']; c['is_active'] = u['is_active']
    db.close()
    return jsonify(c or {})

@company_bp.route('/profile', methods=['PUT'])
@role_required('company')
def update_profile():
    data = request.get_json()
    u = request.current_user
    db = get_db()
    db.execute("""UPDATE company_profiles SET
        company_name=?, hr_name=?, hr_email=?, hr_phone=?, website=?, description=?, industry=?
        WHERE user_id=?""",
        (data.get('company_name',''), data.get('hr_name',''), data.get('hr_email',''),
         data.get('hr_phone',''), data.get('website',''), data.get('description',''),
         data.get('industry',''), u['id']))
    db.commit()
    c = _get_company(u['id'], db); c['email']=u['email']; c['username']=u['username']
    db.close()
    return jsonify(c)

@company_bp.route('/drives', methods=['GET'])
@role_required('company')
def get_drives():
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    if not c: db.close(); return jsonify([])
    rows = rows_to_list(db.execute("""
        SELECT pd.*, cp.company_name,
        (SELECT COUNT(*) FROM applications WHERE drive_id=pd.id) AS applicant_count
        FROM placement_drives pd JOIN company_profiles cp ON pd.company_id=cp.id
        WHERE pd.company_id=?""", (c['id'],)).fetchall())
    db.close()
    return jsonify(rows)

@company_bp.route('/drives', methods=['POST'])
@role_required('company')
def create_drive():
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    if not c: db.close(); return jsonify({'error':'Profile not found'}), 404
    if c['approval_status'] != 'approved':
        db.close(); return jsonify({'error':'Company not approved yet'}), 403
    if u['is_blacklisted']:
        db.close(); return jsonify({'error':'Company is blacklisted'}), 403
    data = request.get_json()
    cur = db.execute("""INSERT INTO placement_drives
        (company_id,drive_name,job_title,job_description,eligibility_branch,
         eligibility_cgpa,eligibility_year,application_deadline,salary,location,interview_type,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending')""",
        (c['id'], data['drive_name'], data['job_title'], data.get('job_description',''),
         data.get('eligibility_branch',''), float(data.get('eligibility_cgpa',0)),
         data.get('eligibility_year',''), data.get('application_deadline',''),
         data.get('salary',''), data.get('location',''), data.get('interview_type','In-person')))
    did = cur.lastrowid
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM placement_drives WHERE id=?", (did,)).fetchone())
    row['company_name'] = c['company_name']; row['applicant_count'] = 0
    db.close()
    return jsonify(row), 201

@company_bp.route('/drives/<int:did>', methods=['PUT'])
@role_required('company')
def update_drive(did):
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    drive = row_to_dict(db.execute("SELECT * FROM placement_drives WHERE id=? AND company_id=?", (did, c['id'])).fetchone())
    if not drive: db.close(); return jsonify({'error':'Not found'}), 404
    data = request.get_json()
    db.execute("""UPDATE placement_drives SET
        drive_name=?, job_title=?, job_description=?, eligibility_branch=?,
        eligibility_cgpa=?, eligibility_year=?, application_deadline=?,
        salary=?, location=?, interview_type=?, status=?
        WHERE id=?""",
        (data.get('drive_name', drive['drive_name']),
         data.get('job_title', drive['job_title']),
         data.get('job_description', drive['job_description']),
         data.get('eligibility_branch', drive['eligibility_branch']),
         float(data.get('eligibility_cgpa', drive['eligibility_cgpa'] or 0)),
         data.get('eligibility_year', drive['eligibility_year']),
         data.get('application_deadline', drive['application_deadline']),
         data.get('salary', drive['salary']),
         data.get('location', drive['location']),
         data.get('interview_type', drive['interview_type']),
         data.get('status', drive['status']), did))
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM placement_drives WHERE id=?", (did,)).fetchone())
    row['company_name'] = c['company_name']
    row['applicant_count'] = db.execute("SELECT COUNT(*) FROM applications WHERE drive_id=?", (did,)).fetchone()[0]
    db.close()
    return jsonify(row)

@company_bp.route('/drives/<int:did>/applications', methods=['GET'])
@role_required('company')
def get_drive_applications(did):
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    drive = db.execute("SELECT id FROM placement_drives WHERE id=? AND company_id=?", (did, c['id'])).fetchone()
    if not drive: db.close(); return jsonify({'error':'Not found'}), 404
    rows = rows_to_list(db.execute("""
        SELECT a.*, sp.full_name AS student_name, sp.department AS student_department,
               sp.branch, sp.cgpa, sp.roll_number,
               pd.drive_name, pd.job_title, pd.interview_type, cp.company_name
        FROM applications a
        JOIN student_profiles sp ON a.student_id=sp.id
        JOIN placement_drives pd ON a.drive_id=pd.id
        JOIN company_profiles cp ON pd.company_id=cp.id
        WHERE a.drive_id=?""", (did,)).fetchall())
    db.close()
    return jsonify(rows)

@company_bp.route('/applications/<int:aid>', methods=['PUT'])
@role_required('company')
def update_application(aid):
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    # verify ownership
    app_row = row_to_dict(db.execute("""
        SELECT a.* FROM applications a
        JOIN placement_drives pd ON a.drive_id=pd.id
        WHERE a.id=? AND pd.company_id=?""", (aid, c['id'])).fetchone())
    if not app_row: db.close(); return jsonify({'error':'Not found'}), 404
    data = request.get_json()
    db.execute("""UPDATE applications SET status=?, remarks=?, interview_date=?, updated_at=datetime('now')
                  WHERE id=?""",
               (data.get('status', app_row['status']),
                data.get('remarks', app_row['remarks']),
                data.get('interview_date', app_row['interview_date']), aid))
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())
    db.close()
    return jsonify(row)
