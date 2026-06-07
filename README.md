# Face Recognition & Photo Capture Web App

This project is a starter full-stack application using a browser webcam + Flask backend to perform face recognition, capture photos, and provide an admin dashboard.

Requirements
- Python 3.8+
- System dependencies for face_recognition (dlib) — see face_recognition docs

Install

pip install -r requirements.txt

Run

python app.py

Open
- Frontend: http://localhost:5000/
- Admin: http://localhost:5000/admin.html

Notes
- The backend uses `face_recognition` to compute embeddings from uploaded images during registration.
- The frontend performs a simple motion-based liveness check before upload.
- The app creates a default admin user on first run: username `admin`, password `adminpass`.
- For production, set `APP_SECRET` env var and use PostgreSQL, HTTPS, Docker, and stronger liveness checks.

Cloud storage
- Set `STORAGE_BACKEND` to `s3` or `cloudinary` to store uploaded images in the cloud. Default is `local` (filesystem).

S3 env vars (for `STORAGE_BACKEND=s3`):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_BUCKET`
- `AWS_REGION` (optional)

Cloudinary env vars (for `STORAGE_BACKEND=cloudinary`):
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

When using cloud storage, the admin UI will serve thumbnails and download links from the cloud URLs.

Install new deps after editing `requirements.txt`:

pip install -r requirements.txt

### Docker / Production

There is a sample `Dockerfile` and `docker-compose.yml` for running the app with Postgres + nginx.

Quick steps (copy `.env.example` -> `.env` and fill values):

```bash
docker build -t faceapp:latest .
docker compose up -d
```

Notes:
- The Docker image uses conda to install `dlib` and other native deps from `conda-forge`.
- For production, set a strong `APP_SECRET` and provide credentials for storage (S3/Cloudinary) if used.
- Migrate your schema to Postgres and avoid shipping an SQLite `app.db` into production.

