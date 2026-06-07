import os
import io
import base64
import datetime
import json
from functools import wraps

from flask import Flask, request, jsonify, send_file, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import numpy as np
from PIL import Image
import face_recognition
import io as _io
import boto3
from botocore.exceptions import BotoCoreError, ClientError
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from supabase import create_client
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Use service role key on the server-side for storage operations
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

try:
    # simple connectivity check
    supabase.storage.list_buckets()
    print("Supabase connected successfully")
except Exception as e:
    print("Supabase connection failed:", e)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'dataset')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL") or 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'dev-secret')

db = SQLAlchemy(app)

# Storage configuration
STORAGE = os.environ.get('STORAGE_BACKEND', 'supabase')  # 'supabase', 'local', 's3', 'cloudinary'

if STORAGE == 's3':
    S3_BUCKET = os.environ.get('AWS_S3_BUCKET')
    S3_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    s3_client = boto3.client('s3', region_name=S3_REGION)
elif STORAGE == 'cloudinary':
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )


def upload_image_to_supabase(pil_image, folder='captures'):
    buf = io.BytesIO()
    pil_image.save(buf, format='JPEG', quality=85)
    buf.seek(0)

    # filename at root of the captures bucket
    filename = f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

    try:
        supabase.storage.from_('captures').upload(
            path=filename,
            file=buf.getvalue(),
            file_options={"content-type": "image/jpeg"}
        )

        res = supabase.storage.from_('captures').get_public_url(filename)
        if isinstance(res, dict):
            url = res.get('publicUrl') or res.get('public_url') or None
        else:
            url = str(res)

        print('Uploaded:', url)
        return url

    except Exception as e:
        print('Supabase upload error:', e)
        return None


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=True)
    embedding_path = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class CapturedPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_name = db.Column(db.String, nullable=True)
    image_path = db.Column(db.String, nullable=True)
    image_url = db.Column(db.String, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    confidence = db.Column(db.Float, nullable=True)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)


class RecognitionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String, nullable=True)
    detected = db.Column(db.Boolean, default=False)
    confidence = db.Column(db.Float, nullable=True)
    ip_address = db.Column(db.String, nullable=True)
    note = db.Column(db.String, nullable=True)


def init_db():
    db.create_all()
    # ensure new columns exist in existing SQLite DBs (simple migration)
    try:
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        if 'captured_photo' in insp.get_table_names():
            cols = [c['name'] for c in insp.get_columns('captured_photo')]
            if 'image_url' not in cols:
                # add image_url column
                with db.engine.connect() as conn:
                    conn.execute("ALTER TABLE captured_photo ADD COLUMN image_url VARCHAR;")
    except Exception:
        # best-effort migration; ignore failures
        pass


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_admin = Admin.query.filter_by(id=data['id']).first()
        except Exception:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_admin, *args, **kwargs)
    return decorated


def decode_base64_image(data_url):
    if data_url.startswith('data:'):
        header, data = data_url.split(',', 1)
    else:
        data = data_url
    image_data = base64.b64decode(data)
    return Image.open(io.BytesIO(image_data)).convert('RGB')


def upload_image_to_s3(pil_image, key_prefix='captures'):
    buf = _io.BytesIO()
    pil_image.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    fname = f"{key_prefix}/{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    try:
        s3_client.upload_fileobj(buf, S3_BUCKET, fname, ExtraArgs={'ACL': 'public-read', 'ContentType': 'image/jpeg'})
        url = f'https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{fname}'
        return url
    except (BotoCoreError, ClientError) as e:
        print('S3 upload error', e)
        return None


def upload_image_to_cloudinary(pil_image, folder='captures'):
    buf = _io.BytesIO()
    pil_image.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    try:
        res = cloudinary.uploader.upload(buf, folder=folder)
        return res.get('secure_url')
    except Exception as e:
        print('Cloudinary upload error', e)
        return None


def save_image(pil_image, subfolder=''):
    """Save image according to STORAGE setting. Returns a dict with keys: path (local) and url (cloud)."""
    out = {'path': None, 'url': None}
    if STORAGE == 'supabase':
        # upload to Supabase Storage (bucket name == folder)
        url = upload_image_to_supabase(pil_image, subfolder or 'captures')
        out['url'] = url
    elif STORAGE == 's3':
        url = upload_image_to_s3(pil_image)
        out['url'] = url
    elif STORAGE == 'cloudinary':
        url = upload_image_to_cloudinary(pil_image)
        out['url'] = url
    else:
        user_folder = os.path.join(UPLOAD_DIR, subfolder) if subfolder else UPLOAD_DIR
        os.makedirs(user_folder, exist_ok=True)
        fname = f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        path = os.path.join(user_folder, fname)
        pil_image.save(path, format='JPEG', quality=85)
        out['path'] = path
        out['url'] = None
    return out


def image_to_np(img: Image.Image):
    return np.array(img)


def compute_embedding(pil_image):
    arr = image_to_np(pil_image)
    encs = face_recognition.face_encodings(arr)
    if len(encs) == 0:
        return None
    return encs[0]


def load_all_embeddings():
    users = User.query.all()
    data = []
    for u in users:
        if u.embedding_path and os.path.exists(u.embedding_path):
            try:
                emb = np.load(u.embedding_path)
                data.append((u.id, u.name, emb))
            except Exception:
                continue
    return data


@app.route('/register', methods=['POST'])
def register():
    payload = request.get_json()
    name = payload.get('name')
    email = payload.get('email')
    images = payload.get('images', [])
    if not name or not images:
        return jsonify({'error': 'name and images are required'}), 400
    user = User(name=name, email=email)
    db.session.add(user)
    db.session.commit()
    user_folder = os.path.join(DATA_DIR, f'user_{user.id}')
    os.makedirs(user_folder, exist_ok=True)
    embeddings = []
    for idx, data_url in enumerate(images):
        try:
            img = decode_base64_image(data_url)
        except Exception:
            continue
        # upload enrollment image to storage (optional)
        save_image(img)
        emb = compute_embedding(img)
        if emb is not None:
            embeddings.append(emb)
    if len(embeddings) == 0:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'error': 'No face found in provided images'}), 400
    emb_path = os.path.join(user_folder, 'embeddings.npy')
    np.save(emb_path, np.stack(embeddings))
    user.embedding_path = emb_path
    db.session.commit()
    return jsonify({'message': 'registered', 'user_id': user.id})


@app.route('/recognize', methods=['POST'])
def recognize():
    payload = request.get_json()
    image_data = payload.get('image')
    if not image_data:
        return jsonify({'error': 'image required'}), 400
    img = decode_base64_image(image_data)
    emb = compute_embedding(img)
    if emb is None:
        return jsonify({'name': None, 'confidence': 0.0, 'status': 'no_face'})
    candidates = load_all_embeddings()
    best_name = 'Unknown'
    best_conf = 0.0
    best_user_id = None
    threshold = 0.6
    for uid, name, user_embs in candidates:
        # user_embs shape (N,128)
        dists = np.linalg.norm(user_embs - emb, axis=1)
        min_dist = float(np.min(dists))
        conf = max(0.0, 1.0 - (min_dist / 0.6))
        if min_dist < threshold and conf > best_conf:
            best_conf = conf
            best_name = name
            best_user_id = uid
    status = 'verified' if best_name != 'Unknown' else 'unverified'
    # log recognition
    try:
        ip = request.remote_addr
        log = RecognitionLog(user_id=(best_user_id if best_name != 'Unknown' else None), user_name=best_name, detected=True if emb is not None else False, confidence=best_conf * 100.0, ip_address=ip, note=status)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'name': best_name, 'confidence': round(best_conf * 100, 2), 'status': status})


@app.route('/capture', methods=['POST'])
def capture():
    payload = request.get_json()
    image_data = payload.get('image')
    user_name = payload.get('user_name')
    user_id = payload.get('user_id')
    confidence = payload.get('confidence')
    if not image_data:
        return jsonify({'error': 'image required'}), 400
    img = decode_base64_image(image_data)
    # save to configured storage
    saved = save_image(img)
    # verify upload for cloud backends
    if STORAGE in ('supabase', 's3', 'cloudinary') and not saved.get('url'):
        return jsonify({'error': 'Upload failed'}), 500
    photo = CapturedPhoto(user_id=user_id, user_name=user_name, image_path=saved.get('path'), image_url=saved.get('url'), confidence=confidence)
    db.session.add(photo)
    db.session.commit()
    # log capture event
    try:
        ip = request.remote_addr
        log = RecognitionLog(user_id=user_id, user_name=user_name, detected=True, confidence=(confidence or 0.0), ip_address=ip, note='capture')
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'message': 'uploaded', 'photo_id': photo.id})


@app.route('/admin/change_password', methods=['POST'])
@token_required
def admin_change_password(current_admin):
    data = request.get_json()
    old = data.get('old_password')
    new = data.get('new_password')
    if not old or not new:
        return jsonify({'error': 'old and new password required'}), 400
    if not check_password_hash(current_admin.password_hash, old):
        return jsonify({'error': 'old password incorrect'}), 403
    current_admin.password_hash = generate_password_hash(new)
    db.session.commit()
    return jsonify({'message': 'password_changed'})


@app.route('/admin/stats', methods=['GET'])
@token_required
def admin_stats(current_admin):
    total_users = User.query.count()
    total_photos = CapturedPhoto.query.count()
    today = datetime.datetime.utcnow().date()
    todays_photos = CapturedPhoto.query.filter(CapturedPhoto.timestamp >= datetime.datetime.combine(today, datetime.time())).count()
    unknowns = CapturedPhoto.query.filter((CapturedPhoto.user_name == None) | (CapturedPhoto.user_name == 'Unknown')).count()
    return jsonify({'total_users': total_users, 'total_photos': total_photos, 'todays_photos': todays_photos, 'unknowns': unknowns})


@app.route('/admin/users', methods=['GET'])
@token_required
def admin_list_users(current_admin):
    users = User.query.order_by(User.created_at.desc()).all()
    out = [{'id': u.id, 'name': u.name, 'email': u.email, 'created_at': u.created_at.isoformat()} for u in users]
    return jsonify(out)


@app.route('/photos', methods=['GET'])
@token_required
def list_photos(current_admin):
    # pagination and filters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    user = request.args.get('user')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    min_conf = request.args.get('min_conf')
    q = CapturedPhoto.query
    if user:
        q = q.filter(CapturedPhoto.user_name.ilike(f"%{user}%"))
    if date_from:
        try:
            df = datetime.datetime.fromisoformat(date_from)
            q = q.filter(CapturedPhoto.timestamp >= df)
        except Exception:
            pass
    if date_to:
        try:
            dt = datetime.datetime.fromisoformat(date_to)
            q = q.filter(CapturedPhoto.timestamp <= dt)
        except Exception:
            pass
    if min_conf:
        try:
            mc = float(min_conf)
            q = q.filter(CapturedPhoto.confidence >= mc)
        except Exception:
            pass
    total = q.count()
    photos = q.order_by(CapturedPhoto.timestamp.desc()).offset((page-1)*per_page).limit(per_page).all()
    out = []
    for p in photos:
        out.append({'id': p.id, 'user_id': p.user_id, 'user_name': p.user_name, 'timestamp': p.timestamp.isoformat(), 'confidence': p.confidence})
    return jsonify({'total': total, 'page': page, 'per_page': per_page, 'items': out})


@app.route('/photo/<int:photo_id>/image', methods=['GET'])
@token_required
def photo_image(current_admin, photo_id):
    p = CapturedPhoto.query.get(photo_id)
    if not p or not os.path.exists(p.image_path):
        if p and p.image_url:
            return redirect(p.image_url)
        return jsonify({'error': 'not found'}), 404
    if p.image_url:
        return redirect(p.image_url)
    return send_file(p.image_path, mimetype='image/jpeg')


@app.route('/logs', methods=['GET'])
@token_required
def get_logs(current_admin):
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    user = request.args.get('user')
    detected = request.args.get('detected')
    q = RecognitionLog.query
    if user:
        q = q.filter(RecognitionLog.user_name.ilike(f"%{user}%"))
    if detected is not None:
        if detected.lower() in ['1','true','yes']:
            q = q.filter(RecognitionLog.detected == True)
        elif detected.lower() in ['0','false','no']:
            q = q.filter(RecognitionLog.detected == False)
    total = q.count()
    logs = q.order_by(RecognitionLog.timestamp.desc()).offset((page-1)*per_page).limit(per_page).all()
    out = []
    for l in logs:
        out.append({'id': l.id, 'timestamp': l.timestamp.isoformat(), 'user_id': l.user_id, 'user_name': l.user_name, 'detected': l.detected, 'confidence': l.confidence, 'ip': l.ip_address, 'note': l.note})
    return jsonify({'total': total, 'page': page, 'per_page': per_page, 'items': out})


@app.route('/photo/<int:photo_id>', methods=['DELETE'])
@token_required
def delete_photo(current_admin, photo_id):
    p = CapturedPhoto.query.get(photo_id)
    if not p:
        return jsonify({'error': 'not found'}), 404
    try:
        if p.image_path and os.path.exists(p.image_path):
            os.remove(p.image_path)
        # if stored in Supabase, remove object from bucket as well
        if p.image_url and STORAGE == 'supabase':
            try:
                # extract path after '/captures/' in the public url
                if '/captures/' in p.image_url:
                    file_name = p.image_url.split('/captures/')[-1]
                else:
                    # fallback: last segment
                    file_name = p.image_url.rstrip('/').split('/')[-1]
                supabase.storage.from_('captures').remove([file_name])
            except Exception as e:
                print('Supabase delete error:', e)
    except Exception:
        pass
    db.session.delete(p)
    db.session.commit()
    return jsonify({'message': 'deleted'})


@app.route('/photo/<int:photo_id>/download', methods=['GET'])
@token_required
def download_photo(current_admin, photo_id):
    p = CapturedPhoto.query.get(photo_id)
    if not p or not os.path.exists(p.image_path):
        if p and p.image_url:
            return redirect(p.image_url)
        return jsonify({'error': 'not found'}), 404
    if p.image_url:
        return redirect(p.image_url)
    return send_file(p.image_path, as_attachment=True)


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    admin = Admin.query.filter_by(username=username).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode({'id': admin.id, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12)}, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({'token': token})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin.html')
def admin_page():
    return render_template('admin.html')


if __name__ == '__main__':
    with app.app_context():
        init_db()

        # create admin from environment if none exists
        if Admin.query.count() == 0:
            admin_user = os.getenv('ADMIN_USERNAME', 'admin')
            admin_pw = os.getenv('ADMIN_PASSWORD', None)
            if not admin_pw:
                print('WARNING: ADMIN_PASSWORD not set; defaulting to "adminpass" (not safe for production)')
                admin_pw = 'adminpass'
            a = Admin(
                username=admin_user,
                password_hash=generate_password_hash(admin_pw)
            )
            db.session.add(a)
            db.session.commit()
            print(f'Created admin -> username={admin_user}')

    app.run(host='0.0.0.0', port=5000, debug=False)