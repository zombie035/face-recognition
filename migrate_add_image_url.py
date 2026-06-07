import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'app.db')

if not os.path.exists(DB_PATH):
    print('No app.db found at', DB_PATH)
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
try:
    c.execute("ALTER TABLE captured_photo ADD COLUMN image_url VARCHAR;")
    print('image_url column added')
except Exception as e:
    print('no change / error:', e)
conn.commit()
conn.close()
import sqlite3
conn = sqlite3.connect('app.db')
c = conn.cursor()
try:
    c.execute("ALTER TABLE captured_photo ADD COLUMN image_url VARCHAR")
    print('image_url column added')
except Exception as e:
    print('no change / error:', e)
conn.commit()
conn.close()