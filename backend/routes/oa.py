"""
Meeting scheduling + Online Assessment (OA) scheduling routes.

Companies can:
  - Schedule an interview meeting for a specific application.
  - Schedule an OA for a placement drive (all applicants of that drive
    can then take it), choosing either 'leetcode' (auto-sourced
    questions) or 'company' (their own questions) as the question
    source.
  - Add / remove their own OA questions (tagged by difficulty).

Students can:
  - See meetings scheduled for their applications.
  - See OAs scheduled for drives they applied to.
  - Start an OA once it opens: this verifies eligibility/timing, then
    hands back exactly 1 easy + 1 medium + 1 hard question, pulled from
    the company's own bank first (filling any missing difficulty from
    LeetCode automatically).
"""
import json
import random
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify

from backend.models import get_db, row_to_dict, rows_to_list
from backend.routes.auth import role_required
from backend.utils.leetcode import fetch_random_question

oa_bp = Blueprint('oa', __name__)

DIFFICULTIES = ['easy', 'medium', 'hard']


def _get_company(user_id, db):
    return row_to_dict(db.execute("SELECT * FROM company_profiles WHERE user_id=?", (user_id,)).fetchone())


def _get_student(user_id, db):
    return row_to_dict(db.execute("SELECT * FROM student_profiles WHERE user_id=?", (user_id,)).fetchone())


def _parse_dt(value):
    """Parse an ISO datetime string into a timezone-aware UTC datetime.

    The frontend always sends timezone-aware ISO strings (it converts the
    browser's local datetime-local input to UTC before sending). This is
    defensive: it also copes with a trailing 'Z' (which older Python
    fromisoformat versions reject) and with plain naive strings (treated
    as already being UTC)."""
    if not value:
        return None
    v = value.strip()
    if v.endswith('Z'):
        v = v[:-1] + '+00:00'
    dt = None
    try:
        dt = datetime.fromisoformat(v)
    except Exception:
        try:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


# ─────────────────────────── Company: Meetings ─────────────────────────────

@oa_bp.route('/company/applications/<int:aid>/meeting', methods=['GET'])
@role_required('company')
def get_application_meeting(aid):
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    app_row = db.execute("""
        SELECT a.* FROM applications a JOIN placement_drives pd ON a.drive_id = pd.id
        WHERE a.id=? AND pd.company_id=?""", (aid, c['id'])).fetchone()
    if not app_row:
        db.close(); return jsonify({'error': 'Not found'}), 404
    m = row_to_dict(db.execute("SELECT * FROM meetings WHERE application_id=?", (aid,)).fetchone())
    db.close()
    return jsonify(m or {})


@oa_bp.route('/company/applications/<int:aid>/meeting', methods=['POST'])
@role_required('company')
def schedule_meeting(aid):
    """Create or reschedule (upsert) the interview meeting for an application."""
    u = request.current_user
    data = request.get_json() or {}
    if not data.get('scheduled_at'):
        return jsonify({'error': 'scheduled_at is required'}), 400
    db = get_db()
    c = _get_company(u['id'], db)
    app_row = row_to_dict(db.execute("""
        SELECT a.* FROM applications a JOIN placement_drives pd ON a.drive_id = pd.id
        WHERE a.id=? AND pd.company_id=?""", (aid, c['id'])).fetchone())
    if not app_row:
        db.close(); return jsonify({'error': 'Application not found'}), 404

    existing = db.execute("SELECT id FROM meetings WHERE application_id=?", (aid,)).fetchone()
    title = data.get('title') or 'Interview'
    link = data.get('meeting_link', '')
    duration = int(data.get('duration_minutes', 30) or 30)
    notes = data.get('notes', '')
    status = data.get('status', 'scheduled')

    if existing:
        db.execute("""UPDATE meetings SET title=?, meeting_link=?, scheduled_at=?, duration_minutes=?,
                      notes=?, status=?, updated_at=datetime('now') WHERE application_id=?""",
                   (title, link, data['scheduled_at'], duration, notes, status, aid))
    else:
        db.execute("""INSERT INTO meetings
            (application_id, company_id, student_id, title, meeting_link, scheduled_at, duration_minutes, notes, status)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (aid, c['id'], app_row['student_id'], title, link, data['scheduled_at'], duration, notes, status))

    # Keep the applications.interview_date field in sync so the existing
    # student "My Applications" view also reflects the scheduled meeting.
    db.execute("UPDATE applications SET interview_date=?, updated_at=datetime('now') WHERE id=?",
               (data['scheduled_at'], aid))
    db.commit()
    m = row_to_dict(db.execute("SELECT * FROM meetings WHERE application_id=?", (aid,)).fetchone())
    db.close()
    return jsonify(m), 201


@oa_bp.route('/company/drives/<int:did>/meetings', methods=['GET'])
@role_required('company')
def list_drive_meetings(did):
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    drive = db.execute("SELECT id FROM placement_drives WHERE id=? AND company_id=?", (did, c['id'])).fetchone()
    if not drive:
        db.close(); return jsonify({'error': 'Not found'}), 404
    rows = rows_to_list(db.execute("""
        SELECT m.*, sp.full_name AS student_name, sp.roll_number
        FROM meetings m
        JOIN applications a ON m.application_id = a.id
        JOIN student_profiles sp ON m.student_id = sp.id
        WHERE a.drive_id=? ORDER BY m.scheduled_at""", (did,)).fetchall())
    db.close()
    return jsonify(rows)


# ─────────────────────────── Company: OA scheduling ────────────────────────

@oa_bp.route('/company/drives/<int:did>/oa', methods=['GET'])
@role_required('company')
def list_drive_oa(did):
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    drive = db.execute("SELECT id FROM placement_drives WHERE id=? AND company_id=?", (did, c['id'])).fetchone()
    if not drive:
        db.close(); return jsonify({'error': 'Not found'}), 404
    rows = rows_to_list(db.execute("""
        SELECT o.*, (SELECT COUNT(*) FROM oa_questions WHERE oa_id=o.id) AS question_count,
        (SELECT COUNT(*) FROM oa_attempts WHERE oa_id=o.id) AS attempt_count,
        (SELECT COUNT(*) FROM oa_attempts WHERE oa_id=o.id AND status='completed') AS completed_count
        FROM oa_schedules o WHERE o.drive_id=? ORDER BY o.scheduled_at DESC""", (did,)).fetchall())
    db.close()
    return jsonify(rows)


@oa_bp.route('/company/drives/<int:did>/oa', methods=['POST'])
@role_required('company')
def create_oa(did):
    u = request.current_user
    data = request.get_json() or {}
    if not data.get('title') or not data.get('scheduled_at'):
        return jsonify({'error': 'title and scheduled_at are required'}), 400
    source = data.get('question_source', 'leetcode')
    if source not in ('leetcode', 'company'):
        return jsonify({'error': "question_source must be 'leetcode' or 'company'"}), 400
    db = get_db()
    c = _get_company(u['id'], db)
    drive = db.execute("SELECT id FROM placement_drives WHERE id=? AND company_id=?", (did, c['id'])).fetchone()
    if not drive:
        db.close(); return jsonify({'error': 'Drive not found'}), 404
    cur = db.execute("""INSERT INTO oa_schedules
        (drive_id, company_id, title, question_source, scheduled_at, duration_minutes, instructions, status)
        VALUES (?,?,?,?,?,?,?,'scheduled')""",
        (did, c['id'], data['title'], source, data['scheduled_at'],
         int(data.get('duration_minutes', 90) or 90), data.get('instructions', '')))
    oid = cur.lastrowid
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM oa_schedules WHERE id=?", (oid,)).fetchone())
    row['question_count'] = 0
    db.close()
    return jsonify(row), 201


def _oa_owned_by_company(oid, company_id, db):
    return db.execute("SELECT * FROM oa_schedules WHERE id=? AND company_id=?", (oid, company_id)).fetchone()


@oa_bp.route('/company/oa/<int:oid>', methods=['PUT'])
@role_required('company')
def update_oa(oid):
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    oa = row_to_dict(_oa_owned_by_company(oid, c['id'], db))
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    data = request.get_json() or {}
    db.execute("""UPDATE oa_schedules SET title=?, question_source=?, scheduled_at=?,
                  duration_minutes=?, instructions=?, status=? WHERE id=?""",
        (data.get('title', oa['title']), data.get('question_source', oa['question_source']),
         data.get('scheduled_at', oa['scheduled_at']),
         int(data.get('duration_minutes', oa['duration_minutes']) or oa['duration_minutes']),
         data.get('instructions', oa['instructions']), data.get('status', oa['status']), oid))
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM oa_schedules WHERE id=?", (oid,)).fetchone())
    db.close()
    return jsonify(row)


@oa_bp.route('/company/oa/<int:oid>', methods=['DELETE'])
@role_required('company')
def delete_oa(oid):
    u = request.current_user
    db = get_db()
    c = _get_company(u['id'], db)
    oa = _oa_owned_by_company(oid, c['id'], db)
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    db.execute("DELETE FROM oa_schedules WHERE id=?", (oid,))
    db.commit(); db.close()
    return jsonify({'message': 'OA deleted'})


@oa_bp.route('/company/oa/<int:oid>/questions', methods=['GET'])
@role_required('company')
def list_oa_questions(oid):
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    oa = _oa_owned_by_company(oid, c['id'], db)
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    rows = rows_to_list(db.execute("SELECT * FROM oa_questions WHERE oa_id=? ORDER BY difficulty", (oid,)).fetchall())
    db.close()
    return jsonify(rows)


@oa_bp.route('/company/oa/<int:oid>/questions', methods=['POST'])
@role_required('company')
def add_oa_question(oid):
    u = request.current_user
    data = request.get_json() or {}
    difficulty = (data.get('difficulty') or '').lower()
    if difficulty not in DIFFICULTIES:
        return jsonify({'error': "difficulty must be one of: easy, medium, hard"}), 400
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400
    db = get_db()
    c = _get_company(u['id'], db)
    oa = _oa_owned_by_company(oid, c['id'], db)
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    cur = db.execute("""INSERT INTO oa_questions (oa_id, difficulty, title, description, link)
                        VALUES (?,?,?,?,?)""",
        (oid, difficulty, data['title'], data.get('description', ''), data.get('link', '')))
    qid = cur.lastrowid
    db.commit()
    row = row_to_dict(db.execute("SELECT * FROM oa_questions WHERE id=?", (qid,)).fetchone())
    db.close()
    return jsonify(row), 201


@oa_bp.route('/company/oa/<int:oid>/questions/<int:qid>', methods=['DELETE'])
@role_required('company')
def delete_oa_question(oid, qid):
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    oa = _oa_owned_by_company(oid, c['id'], db)
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    db.execute("DELETE FROM oa_questions WHERE id=? AND oa_id=?", (qid, oid))
    db.commit(); db.close()
    return jsonify({'message': 'Question removed'})


# ─────────────────────────── Student: Meetings ──────────────────────────────

@oa_bp.route('/student/meetings', methods=['GET'])
@role_required('student')
def student_meetings():
    db = get_db()
    s = _get_student(request.current_user['id'], db)
    rows = rows_to_list(db.execute("""
        SELECT m.*, pd.drive_name, pd.job_title, cp.company_name
        FROM meetings m
        JOIN applications a ON m.application_id = a.id
        JOIN placement_drives pd ON a.drive_id = pd.id
        JOIN company_profiles cp ON pd.company_id = cp.id
        WHERE m.student_id=? ORDER BY m.scheduled_at""", (s['id'],)).fetchall())
    db.close()
    return jsonify(rows)


# ─────────────────────────── Student: OA ────────────────────────────────────

def _oa_visible_to_student(oid, student_id, db):
    """OA is visible if the student has an (active) application to its drive."""
    return db.execute("""
        SELECT o.* FROM oa_schedules o
        JOIN placement_drives pd ON o.drive_id = pd.id
        JOIN applications a ON a.drive_id = pd.id
        WHERE o.id=? AND a.student_id=? AND a.status != 'rejected'""",
        (oid, student_id)).fetchone()


@oa_bp.route('/student/oa', methods=['GET'])
@role_required('student')
def student_oa_list():
    db = get_db()
    s = _get_student(request.current_user['id'], db)
    rows = rows_to_list(db.execute("""
        SELECT o.*, pd.drive_name, pd.job_title, cp.company_name,
               oa2.status AS attempt_status, oa2.started_at, oa2.completed_at,
               oa2.score AS score, oa2.total_questions AS total_questions
        FROM oa_schedules o
        JOIN placement_drives pd ON o.drive_id = pd.id
        JOIN company_profiles cp ON pd.company_id = cp.id
        JOIN applications a ON a.drive_id = pd.id AND a.student_id=?
        LEFT JOIN oa_attempts oa2 ON oa2.oa_id = o.id AND oa2.student_id=?
        WHERE a.status != 'rejected'
        ORDER BY o.scheduled_at""", (s['id'], s['id'])).fetchall())

    now = datetime.now(timezone.utc)
    for r in rows:
        start = _parse_dt(r['scheduled_at'])
        end = start + timedelta(minutes=r['duration_minutes'] or 90) if start else None
        r['is_open'] = bool(start and end and start <= now <= end)
        r['is_upcoming'] = bool(start and now < start)
        r['is_expired'] = bool(end and now > end)
        r['attempt_status'] = r['attempt_status'] or 'not_started'
    db.close()
    return jsonify(rows)


def _build_question_set(oa, db):
    """1 easy + 1 medium + 1 hard. Uses the company's own bank first for
    'company'-sourced OAs, filling any missing difficulty from LeetCode."""
    questions = []
    company_qs = {}
    if oa['question_source'] == 'company':
        rows = rows_to_list(db.execute("SELECT * FROM oa_questions WHERE oa_id=?", (oa['id'],)).fetchall())
        for diff in DIFFICULTIES:
            company_qs[diff] = [q for q in rows if q['difficulty'] == diff]

    for diff in DIFFICULTIES:
        pool = company_qs.get(diff) or []
        if pool:
            q = random.choice(pool)
            questions.append({
                'difficulty': diff.capitalize(),
                'title': q['title'],
                'description': q.get('description', ''),
                'link': q.get('link', ''),
                'source': 'company',
            })
        else:
            questions.append(fetch_random_question(diff))
    return questions


@oa_bp.route('/student/oa/<int:oid>/start', methods=['POST'])
@role_required('student')
def start_oa(oid):
    """Verify eligibility + timing, then hand back (or resume) the
    student's 3-question set: 1 easy, 1 medium, 1 hard."""
    u = request.current_user
    db = get_db()
    s = _get_student(u['id'], db)

    oa = row_to_dict(_oa_visible_to_student(oid, s['id'], db))
    if not oa:
        db.close(); return jsonify({'error': 'OA not found or you are not eligible for it'}), 404
    if u['is_blacklisted'] or not u['is_active']:
        db.close(); return jsonify({'error': 'Your account is not eligible to take this OA'}), 403

    start = _parse_dt(oa['scheduled_at'])
    end = start + timedelta(minutes=oa['duration_minutes'] or 90) if start else None
    now = datetime.now(timezone.utc)
    if start and now < start:
        db.close(); return jsonify({'error': 'This OA has not started yet', 'scheduled_at': oa['scheduled_at']}), 400
    if end and now > end:
        db.close(); return jsonify({'error': 'The window for this OA has closed'}), 400

    existing = row_to_dict(db.execute("SELECT * FROM oa_attempts WHERE oa_id=? AND student_id=?", (oid, s['id'])).fetchone())
    if existing and existing['status'] == 'completed':
        db.close(); return jsonify({'error': 'You have already completed this OA'}), 400

    if existing and existing['status'] == 'in_progress' and existing['questions_json']:
        questions = json.loads(existing['questions_json'])
    else:
        questions = _build_question_set(oa, db)
        if existing:
            db.execute("""UPDATE oa_attempts SET status='in_progress', questions_json=?, started_at=datetime('now')
                          WHERE oa_id=? AND student_id=?""", (json.dumps(questions), oid, s['id']))
        else:
            db.execute("""INSERT INTO oa_attempts (oa_id, student_id, status, questions_json, started_at)
                          VALUES (?,?, 'in_progress', ?, datetime('now'))""",
                       (oid, s['id'], json.dumps(questions)))
        db.commit()

    attempt = row_to_dict(db.execute("SELECT * FROM oa_attempts WHERE oa_id=? AND student_id=?", (oid, s['id'])).fetchone())
    db.close()
    return jsonify({
        'verified': True,
        'oa': {'id': oa['id'], 'title': oa['title'], 'instructions': oa['instructions'],
               'duration_minutes': oa['duration_minutes'], 'scheduled_at': oa['scheduled_at']},
        'questions': questions,
        'started_at': attempt['started_at'],
        'status': attempt['status'],
    })


@oa_bp.route('/student/oa/<int:oid>/attempt', methods=['GET'])
@role_required('student')
def get_oa_attempt(oid):
    db = get_db()
    s = _get_student(request.current_user['id'], db)
    attempt = row_to_dict(db.execute("SELECT * FROM oa_attempts WHERE oa_id=? AND student_id=?", (oid, s['id'])).fetchone())
    db.close()
    if not attempt:
        return jsonify({'status': 'not_started'})
    attempt['questions'] = json.loads(attempt['questions_json']) if attempt['questions_json'] else []
    attempt['responses'] = json.loads(attempt['responses_json']) if attempt['responses_json'] else []
    return jsonify(attempt)


VALID_RESPONSE_STATUSES = {'solved', 'attempted', 'skipped'}


@oa_bp.route('/student/oa/<int:oid>/complete', methods=['POST'])
@role_required('student')
def complete_oa(oid):
    """Student submits the OA. They self-report, per question, whether they
    solved / attempted / skipped it and paste the code they wrote (e.g.
    copied from their LeetCode submission) so the company can review it.
    There is no legitimate way to pull a student's code directly off
    LeetCode without their own session, so this is the honest channel for
    that information to reach the company."""
    db = get_db()
    s = _get_student(request.current_user['id'], db)
    attempt = row_to_dict(db.execute("SELECT * FROM oa_attempts WHERE oa_id=? AND student_id=?", (oid, s['id'])).fetchone())
    if not attempt:
        db.close(); return jsonify({'error': 'You have not started this OA'}), 400
    if attempt['status'] == 'completed':
        db.close(); return jsonify({'error': 'You have already submitted this OA'}), 400

    questions = json.loads(attempt['questions_json']) if attempt['questions_json'] else []
    data = request.get_json() or {}
    incoming = data.get('responses') or []
    by_title = {r.get('title'): r for r in incoming if isinstance(r, dict)}

    responses = []
    score = 0
    for q in questions:
        r = by_title.get(q['title'], {})
        status = (r.get('status') or 'skipped').lower()
        if status not in VALID_RESPONSE_STATUSES:
            status = 'skipped'
        code = (r.get('code') or '').strip()[:20000]  # sane cap
        language = (r.get('language') or '').strip()[:40]
        if status == 'solved':
            score += 1
        responses.append({
            'title': q['title'], 'difficulty': q['difficulty'], 'link': q.get('link', ''),
            'status': status, 'code': code, 'language': language,
        })

    db.execute("""UPDATE oa_attempts SET status='completed', responses_json=?, score=?, total_questions=?,
                  completed_at=datetime('now') WHERE oa_id=? AND student_id=?""",
               (json.dumps(responses), score, len(questions), oid, s['id']))
    db.commit(); db.close()
    return jsonify({'message': 'OA submitted successfully', 'score': score, 'total_questions': len(questions)})


# ─────────────────────────── Company: OA submissions ───────────────────────

@oa_bp.route('/company/oa/<int:oid>/attempts', methods=['GET'])
@role_required('company')
def list_oa_attempts(oid):
    """All students' attempts/submissions for one OA, with their self-reported
    per-question status and the code they pasted in."""
    db = get_db()
    c = _get_company(request.current_user['id'], db)
    oa = _oa_owned_by_company(oid, c['id'], db)
    if not oa:
        db.close(); return jsonify({'error': 'Not found'}), 404
    rows = rows_to_list(db.execute("""
        SELECT at.*, sp.full_name AS student_name, sp.roll_number, sp.branch, sp.department, sp.cgpa
        FROM oa_attempts at
        JOIN student_profiles sp ON at.student_id = sp.id
        WHERE at.oa_id=? ORDER BY at.status DESC, at.completed_at DESC""", (oid,)).fetchall())
    for r in rows:
        r['questions'] = json.loads(r['questions_json']) if r['questions_json'] else []
        r['responses'] = json.loads(r['responses_json']) if r['responses_json'] else []
        del r['questions_json']; del r['responses_json']
    db.close()
    return jsonify(rows)
