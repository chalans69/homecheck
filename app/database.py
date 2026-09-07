import json, sqlite3
from datetime import datetime, timezone
from .config import DB_PATH

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS cache (
      key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analyses (
      id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
      address TEXT NOT NULL, work_address TEXT NOT NULL, score INTEGER,
      summary TEXT NOT NULL, warnings TEXT NOT NULL, request TEXT NOT NULL, result TEXT NOT NULL);
    """)
    return db

def init_db():
    with connect() as db:
        db.execute("SELECT 1")

def cache_get(key):
    with connect() as db:
        row = db.execute("SELECT value FROM cache WHERE key=? AND expires_at>?", (key, datetime.now(timezone.utc).isoformat())).fetchone()
        return json.loads(row[0]) if row else None

def cache_set(key, value, expires_at):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, json.dumps(value, ensure_ascii=False), expires_at.isoformat()))

def save_analysis(request, result):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        cur = db.execute("INSERT INTO analyses(created_at,address,work_address,score,summary,warnings,request,result) VALUES(?,?,?,?,?,?,?,?)",
          (now, request["property_address"], request["work_address"], result["score"], result["label"], json.dumps(result["warnings"], ensure_ascii=False), json.dumps(request, ensure_ascii=False), json.dumps(result, ensure_ascii=False)))
        return cur.lastrowid

def get_analysis(analysis_id):
    with connect() as db:
        row = db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row: return None
        return {**dict(row), "request": json.loads(row["request"]), "result": json.loads(row["result"])}

def list_analyses():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT id,created_at,address,work_address,score,summary,warnings FROM analyses ORDER BY id DESC LIMIT 100")]
