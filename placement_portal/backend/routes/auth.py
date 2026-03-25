from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from backend.models import get_db, row_to_dict, rows_to_list
from datetime import datetime, timedelta
from functools import wraps
import jwt

auth_bp = Blueprint('auth', __name__)

def _gen_token(user_id, role, secret):
    payload = {'user_id': user_id, 'role': role,
               'exp': datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, secret, algorithm='HS256')

def _verify_token(token, secret):
    try:
        return jwt.decode(token, secret, algorithms=['HS256'])
    except Exception:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import current_app
        token = request.headers.get('Authorization','').replace('Bearer ','')
        if not token:
            return jsonify({'error':'Token required'}), 401
        payload = _verify_token(token, current_app.config['JWT_SECRET_KEY'])
        if not payload:
            return jsonify({'error':'Invalid or expired token'}), 401
        db = get_db()
        user = row_to_dict(db.execute("SELECT * FROM users WHERE id=?", (payload['user_id'],)).fetchone())
        db.close()
        if not user or not user['is_active'] or user['is_blacklisted']:
            return jsonify({'error':'Account inactive or blacklisted'}), 403
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask import current_app
            token = request.headers.get('Authorization','').replace('Bearer ','')
            if not token:
                return jsonify({'error':'Token required'}), 401
            payload = _verify_token(token, current_app.config['JWT_SECRET_KEY'])
            if not payload:
                return jsonify({'error':'Invalid or expired token'}), 401
            if payload['role'] not in roles:
                return jsonify({'error':'Unauthorized role'}), 403
            db = get_db()
            user = row_to_dict(db.execute("SELECT * FROM users WHERE id=?", (payload['user_id'],)).fetchone())
            db.close()
            if not user or not user['is_active'] or user['is_blacklisted']:
                return jsonify({'error':'Account inactive'}), 403
            request.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    role = data.get('role','student')
    if role == 'admin':
        return jsonify({'error':'Admin registration not allowed'}), 403
    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (data['username'],)).fetchone():
        db.close(); return jsonify({'error':'Username already exists'}), 400
    if db.execute("SELECT id FROM users WHERE email=?", (data['email'],)).fetchone():
        db.close(); return jsonify({'error':'Email already registered'}), 400
    ph = generate_password_hash(data['password'])
    cur = db.execute("INSERT INTO users (username,email,password_hash,role) VALUES (?,?,?,?)",
                     (data['username'], data['email'], ph, role))
    user_id = cur.lastrowid
    if role == 'student':
        db.execute("""INSERT INTO student_profiles
                      (user_id,full_name,roll_number,department,branch,year,cgpa,phone)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (user_id, data.get('full_name', data['username']),
                    data.get('roll_number',''), data.get('department',''),
                    data.get('branch',''), data.get('year',1),
                    data.get('cgpa',0), data.get('phone','')))
    elif role == 'company':
        db.execute("""INSERT INTO company_profiles
                      (user_id,company_name,hr_name,hr_email,hr_phone,website,description,industry)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (user_id, data.get('company_name', data['username']),
                    data.get('hr_name',''), data.get('hr_email', data['email']),
                    data.get('hr_phone',''), data.get('website',''),
                    data.get('description',''), data.get('industry','')))
    db.commit(); db.close()
    return jsonify({'message':'Registration successful'}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    from flask import current_app
    data = request.get_json()
    db = get_db()
    user = row_to_dict(db.execute("SELECT * FROM users WHERE username=?", (data.get('username',''),)).fetchone())
    if not user or not check_password_hash(user['password_hash'], data.get('password','')):
        db.close(); return jsonify({'error':'Invalid credentials'}), 401
    if not user['is_active']:
        db.close(); return jsonify({'error':'Account deactivated'}), 403
    if user['is_blacklisted']:
        db.close(); return jsonify({'error':'Account blacklisted'}), 403
    profile = {}
    if user['role'] == 'student':
        p = row_to_dict(db.execute("SELECT * FROM student_profiles WHERE user_id=?", (user['id'],)).fetchone())
        if p: p['email'] = user['email']; p['username'] = user['username']; p['is_blacklisted'] = user['is_blacklisted']; p['is_active'] = user['is_active']; profile = p
    elif user['role'] == 'company':
        p = row_to_dict(db.execute("SELECT * FROM company_profiles WHERE user_id=?", (user['id'],)).fetchone())
        if p: p['email'] = user['email']; p['username'] = user['username']; p['is_blacklisted'] = user['is_blacklisted']; p['is_active'] = user['is_active']; profile = p
    db.close()
    token = _gen_token(user['id'], user['role'], current_app.config['JWT_SECRET_KEY'])
    safe_user = {k: user[k] for k in ('id','username','email','role','is_active','is_blacklisted','created_at')}
    return jsonify({'token': token, 'user': safe_user, 'profile': profile})

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_me():
    from flask import current_app
    user = request.current_user
    db = get_db()
    profile = {}
    if user['role'] == 'student':
        p = row_to_dict(db.execute("SELECT * FROM student_profiles WHERE user_id=?", (user['id'],)).fetchone())
        if p: p['email']=user['email']; p['username']=user['username']; p['is_blacklisted']=user['is_blacklisted']; p['is_active']=user['is_active']; profile=p
    elif user['role'] == 'company':
        p = row_to_dict(db.execute("SELECT * FROM company_profiles WHERE user_id=?", (user['id'],)).fetchone())
        if p: p['email']=user['email']; p['username']=user['username']; p['is_blacklisted']=user['is_blacklisted']; p['is_active']=user['is_active']; profile=p
    db.close()
    safe_user = {k: user[k] for k in ('id','username','email','role','is_active','is_blacklisted','created_at')}
    return jsonify({'user': safe_user, 'profile': profile})
