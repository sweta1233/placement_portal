from flask import Blueprint, request, jsonify, send_from_directory, current_app
from backend.models import get_db, row_to_dict, rows_to_list
from backend.routes.auth import role_required
from datetime import datetime
import os, csv, threading

student_bp = Blueprint('student', __name__)

def _get_student(user_id, db):
    return row_to_dict(db.execute("SELECT * FROM student_profiles WHERE user_id=?", (user_id,)).fetchone())

@student_bp.route('/profile', methods=['GET'])
@role_required('student')
def get_profile():
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    if s:
        s['email']=u['email']; s['username']=u['username']
        s['is_blacklisted']=u['is_blacklisted']; s['is_active']=u['is_active']
    db.close()
    return jsonify(s or {})

@student_bp.route('/profile', methods=['PUT'])
@role_required('student')
def update_profile():
    u = request.current_user
    data = request.get_json()
    db = get_db()
    db.execute("""UPDATE student_profiles SET
        full_name=?,roll_number=?,department=?,branch=?,year=?,cgpa=?,phone=?,skills=?,about=?,
        updated_at=datetime('now') WHERE user_id=?""",
        (data.get('full_name',''), data.get('roll_number',''), data.get('department',''),
         data.get('branch',''), data.get('year',1), data.get('cgpa',0),
         data.get('phone',''), data.get('skills',''), data.get('about',''), u['id']))
    db.commit()
    s = _get_student(u['id'], db); s['email']=u['email']; s['username']=u['username']
    db.close()
    return jsonify(s)

@student_bp.route('/profile/resume', methods=['POST'])
@role_required('student')
def upload_resume():
    if 'resume' not in request.files:
        return jsonify({'error':'No file'}), 400
    file = request.files['resume']
    ext = file.filename.rsplit('.',1)[-1].lower()
    if ext not in ['pdf','doc','docx']:
        return jsonify({'error':'PDF/DOC only'}), 400
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    fname = f"resume_{s['id']}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    file.save(os.path.join(folder, fname))
    db.execute("UPDATE student_profiles SET resume_filename=? WHERE user_id=?", (fname, u['id']))
    db.commit(); db.close()
    return jsonify({'message':'Uploaded','filename':fname})

@student_bp.route('/resume/<filename>', methods=['GET'])
@role_required('student','company','admin')
def get_resume(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@student_bp.route('/drives', methods=['GET'])
@role_required('student')
def get_drives():
    u = request.current_user
    search = request.args.get('search','')
    db = get_db()
    s = _get_student(u['id'], db)
    rows = rows_to_list(db.execute("""
        SELECT pd.*, cp.company_name,
        (SELECT COUNT(*) FROM applications WHERE drive_id=pd.id) AS applicant_count
        FROM placement_drives pd JOIN company_profiles cp ON pd.company_id=cp.id
        WHERE pd.status='approved' AND (pd.drive_name LIKE ? OR pd.job_title LIKE ?)
    """, (f'%{search}%', f'%{search}%')).fetchall())
    for d in rows:
        # eligibility check
        eligible = True
        if d.get('eligibility_cgpa') and s.get('cgpa') and (s['cgpa'] or 0) < d['eligibility_cgpa']:
            eligible = False
        if d.get('eligibility_branch') and s.get('branch'):
            allowed = [b.strip().lower() for b in d['eligibility_branch'].split(',')]
            if s['branch'].lower() not in allowed and 'all' not in allowed:
                eligible = False
        d['eligible'] = eligible
        app_row = db.execute("SELECT status FROM applications WHERE student_id=? AND drive_id=?",
                             (s['id'], d['id'])).fetchone()
        d['applied'] = app_row is not None
        d['application_status'] = app_row[0] if app_row else None
    db.close()
    return jsonify(rows)

@student_bp.route('/drives/<int:did>/apply', methods=['POST'])
@role_required('student')
def apply_drive(did):
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    drive = row_to_dict(db.execute("SELECT * FROM placement_drives WHERE id=?", (did,)).fetchone())
    if not drive: db.close(); return jsonify({'error':'Drive not found'}), 404
    if drive['status'] != 'approved':
        db.close(); return jsonify({'error':'Drive not open'}), 400
    if u['is_blacklisted']:
        db.close(); return jsonify({'error':'Account blacklisted'}), 403
    # deadline
    if drive.get('application_deadline'):
        try:
            dl = datetime.fromisoformat(drive['application_deadline'])
            if datetime.utcnow() > dl:
                db.close(); return jsonify({'error':'Deadline passed'}), 400
        except: pass
    # duplicate check
    if db.execute("SELECT id FROM applications WHERE student_id=? AND drive_id=?", (s['id'], did)).fetchone():
        db.close(); return jsonify({'error':'Already applied'}), 400
    # eligibility
    if drive.get('eligibility_cgpa') and (s.get('cgpa') or 0) < drive['eligibility_cgpa']:
        db.close(); return jsonify({'error':f"Min CGPA required: {drive['eligibility_cgpa']}"}), 400
    if drive.get('eligibility_branch') and s.get('branch'):
        allowed = [b.strip().lower() for b in drive['eligibility_branch'].split(',')]
        if s['branch'].lower() not in allowed and 'all' not in allowed:
            db.close(); return jsonify({'error':'Branch not eligible'}), 400
    cur = db.execute("INSERT INTO applications (student_id, drive_id) VALUES (?,?)", (s['id'], did))
    db.commit()
    aid = cur.lastrowid
    row = row_to_dict(db.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())
    db.close()
    return jsonify({'message':'Application submitted','application':row}), 201

@student_bp.route('/applications', methods=['GET'])
@role_required('student')
def get_applications():
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    rows = rows_to_list(db.execute("""
        SELECT a.*, pd.drive_name, pd.job_title, pd.interview_type, cp.company_name
        FROM applications a
        JOIN placement_drives pd ON a.drive_id=pd.id
        JOIN company_profiles cp ON pd.company_id=cp.id
        WHERE a.student_id=? ORDER BY a.application_date DESC
    """, (s['id'],)).fetchall())
    db.close()
    return jsonify(rows)

@student_bp.route('/history', methods=['GET'])
@role_required('student')
def get_history():
    return get_applications()

@student_bp.route('/export', methods=['POST'])
@role_required('student')
def export_applications():
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    cur = db.execute("INSERT INTO export_jobs (student_id, status) VALUES (?,'pending')", (s['id'],))
    job_id = cur.lastrowid
    db.commit(); db.close()

    def do_export(app_ctx, job_id, student_id):
        with app_ctx:
            db2 = get_db()
            db2.execute("UPDATE export_jobs SET status='processing' WHERE id=?", (job_id,))
            db2.commit()
            try:
                s2 = row_to_dict(db2.execute("SELECT * FROM student_profiles WHERE id=?", (student_id,)).fetchone())
                apps = rows_to_list(db2.execute("""
                    SELECT a.*, pd.drive_name, pd.job_title, cp.company_name
                    FROM applications a
                    JOIN placement_drives pd ON a.drive_id=pd.id
                    JOIN company_profiles cp ON pd.company_id=cp.id
                    WHERE a.student_id=?""", (student_id,)).fetchall())
                export_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'exports')
                os.makedirs(export_dir, exist_ok=True)
                fname = f"export_{student_id}_{job_id}.csv"
                with open(os.path.join(export_dir, fname), 'w', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(['Student ID','Student Name','Company','Drive','Job Title','Status','Applied Date','Interview Date','Remarks'])
                    for a in apps:
                        w.writerow([s2['id'], s2['full_name'], a.get('company_name',''),
                                    a.get('drive_name',''), a.get('job_title',''), a.get('status',''),
                                    (a.get('application_date') or '')[:10],
                                    (a.get('interview_date') or '')[:10], a.get('remarks','')])
                db2.execute("UPDATE export_jobs SET status='done', file_path=?, completed_at=datetime('now') WHERE id=?",
                            (fname, job_id))
            except Exception as e:
                db2.execute("UPDATE export_jobs SET status='failed' WHERE id=?", (job_id,))
            db2.commit(); db2.close()

    t = threading.Thread(target=do_export, args=(current_app.app_context(), job_id, s['id']))
    t.daemon = True; t.start()
    return jsonify({'message':'Export started','job_id':job_id})

@student_bp.route('/export/<int:jid>/status', methods=['GET'])
@role_required('student')
def export_status(jid):
    db = get_db()
    row = row_to_dict(db.execute("SELECT * FROM export_jobs WHERE id=?", (jid,)).fetchone())
    db.close()
    if not row: return jsonify({'error':'Not found'}), 404
    return jsonify(row)

@student_bp.route('/export/<int:jid>/download', methods=['GET'])
@role_required('student')
def download_export(jid):
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)
    job = row_to_dict(db.execute("SELECT * FROM export_jobs WHERE id=? AND student_id=?", (jid, s['id'])).fetchone())
    db.close()
    if not job: return jsonify({'error':'Not found'}), 404
    if job['status'] != 'done': return jsonify({'error':'Not ready'}), 400
    export_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'exports')
    return send_from_directory(export_dir, job['file_path'], as_attachment=True)

@student_bp.route('/companies', methods=['GET'])
@role_required('student')
def get_companies():
    search = request.args.get('search','')
    db = get_db()
    rows = rows_to_list(db.execute("""
        SELECT cp.*, u.email FROM company_profiles cp JOIN users u ON cp.user_id=u.id
        WHERE cp.approval_status='approved' AND cp.company_name LIKE ?
    """, (f'%{search}%',)).fetchall())
    db.close()
    return jsonify(rows)

@student_bp.route('/companies/<int:cid>', methods=['GET'])
@role_required('student')
def get_company_detail(cid):
    db = get_db()
    c = row_to_dict(db.execute("SELECT cp.*, u.email FROM company_profiles cp JOIN users u ON cp.user_id=u.id WHERE cp.id=?", (cid,)).fetchone())
    if not c: db.close(); return jsonify({'error':'Not found'}), 404
    drives = rows_to_list(db.execute("""
        SELECT pd.*,
        (SELECT COUNT(*) FROM applications WHERE drive_id=pd.id) AS applicant_count
        FROM placement_drives pd WHERE pd.company_id=? AND pd.status='approved'
    """, (cid,)).fetchall())
    c['drives'] = drives
    db.close()
    return jsonify(c)
