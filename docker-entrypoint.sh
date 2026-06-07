#!/bin/bash
set -euo pipefail

echo "[entrypoint] initializing database and admin user if needed"

# Run DB init and ensure an admin user exists using the conda environment
conda run -n appenv --no-capture-output python - <<'PY'
from app import init_db
from app import db
from app import Admin
from werkzeug.security import generate_password_hash
import os

init_db()
username = os.environ.get('ADMIN_USERNAME', 'admin')
password = os.environ.get('ADMIN_PASSWORD', 'adminpass')
if Admin.query.filter_by(username=username).first() is None:
    a = Admin(username=username, password_hash=generate_password_hash(password))
    db.session.add(a)
    db.session.commit()
    print(f'[entrypoint] created admin user: {username}')
else:
    print(f'[entrypoint] admin user {username} already exists')
PY

echo "[entrypoint] done; executing CMD"

exec "$@"
