from __future__ import annotations

import hashlib
from html import escape
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta
import time
from functools import wraps

from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    psycopg2 = None
    RealDictCursor = None

try:
    from flask_session import Session
    import redis as _redis
except Exception:
    Session = None
    _redis = None


class PostgresRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return PostgresRow(row) if row else None

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [PostgresRow(row) for row in rows]

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        sql = self.normalize_sql(sql)
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(sql, params)
        return PostgresCursor(cursor)

    def executemany(self, sql, params):
        sql = self.normalize_sql(sql)
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        cursor.executemany(sql, params)
        return PostgresCursor(cursor)

    def executescript(self, sql):
        for statement in [part.strip() for part in sql.split(";") if part.strip()]:
            if statement.upper().startswith("CREATE TABLE"):
                self.connection.cursor().execute(statement)
            elif statement.upper().startswith("INSERT") or statement.upper().startswith("UPDATE"):
                self.connection.cursor().execute(statement)
        self.connection.commit()

    def normalize_sql(self, sql):
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        sql = sql.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        sql = sql.replace("?", "%s")
        return sql

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


app = Flask(__name__)
app.secret_key = os.environ.get("PRODUCTIVITY_SECRET", "change-this-in-production")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("PRODUCTIVITY_COOKIE_SECURE", "false").lower() == "true",
)
# Server-side session configuration (Redis preferred, filesystem fallback)
REDIS_URL = os.environ.get("REDIS_URL")
if Session and _redis:
    if REDIS_URL:
        try:
            redis_client = _redis.from_url(REDIS_URL)
            app.config["SESSION_TYPE"] = "redis"
            app.config["SESSION_REDIS"] = redis_client
        except Exception:
            app.config["SESSION_TYPE"] = "filesystem"
    else:
        app.config["SESSION_TYPE"] = "filesystem"
else:
    app.config["SESSION_TYPE"] = "filesystem"

app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=int(os.environ.get("SESSION_MAX_AGE_DAYS", "1")))
if Session:
    Session(app)
DB_PATH = os.environ.get("PRODUCTIVITY_DB", os.path.join(os.path.dirname(__file__), "productivity.db"))
MD_PER_SLOT = 0.125

DEFAULT_ENGAGEMENTS = [
    ("ITRA-NAPP-H001", "Mobile/Telco Management"),
    ("ITRA-NAPP-H002", "Risk Management and Information Security"),
    ("ITRA-NAPP-H003", "Audit of IT Services"),
    ("ITRA-NAPP-H004", "IT Business Continuity Planning and Management"),
    ("ITRA-NAPP-M001", "IT Outsourcing Process and Third Party Risk Management"),
    ("ITRA-NAPP-M002", "Network Security, Availability, Reliability & Integrity"),
    ("ITRA-NAPP-M003", "User Accounts Management"),
    ("ITRA-NAPP-M004", "Incident Report Creation, Assignment and Resolution"),
    ("ITRA-NAPP-M005", "Database Security and Management"),
    ("ITRA-NAPP-M006", "Applications Control Review - Financial Applications"),
    ("ITRA-NAPP-M007", "IT Asset Inventory & Management"),
    ("ITPP-NAPP-H001", "U Mobile App Revamp (Sprint 3)"),
    ("ITPP-NAPP-H002", "Manila Express - Project Payout"),
    ("ITPP-NAPP-H003", "UBS Payroll"),
    ("ITPP-NAPP-H004", "UBS - Terrapay Integration"),
    ("ITPP-NAPP-H005", "VISA Integration"),
    ("ITPP-NAPP-H006", "UnionPay Card"),
    ("ITPP-NAPP-H007", "Ria Mobile App Integration"),
    ("ITPP-NAPP-H008", "Eccobank savings products (direct to bank API)"),
    ("ITPP-NAPP-H009", "Xpress Money Integration - Branch Access"),
    ("ITPP-NAPP-H010", "WU IMT Outbound Payments via QRPH"),
    ("ITPP-NAPP-H011", "Express Pay Bills Payment"),
    ("ITPP-NAPP-M001", "DSWD Food Stamp"),
    ("ITPP-NAPP-M002", "Jobfix Payroll Project"),
    ("ITPP-NAPP-M003", "Bypro Payroll Disbursement - Onboarding & Enrollment"),
    ("ITPP-NAPP-M004", "CIS API v3"),
    ("ITPP-NAPP-M005", "DA Fertilizer"),
    ("ITPP-NAPP-M006", "DA Seeds/NRP"),
    ("ITPP-NAPP-M007", "USSC x CLSC - IMT Peralink"),
    ("ITPP-NAPP-M008", "Calaca Batangas Card"),
    ("ITPP-NAPP-M009", "U Visa Card Enrollment in MNLX"),
    ("ITPP-NAPP-M010", "USSC x GSIS - Pay1st Enhancement"),
    ("ITPP-NAPP-M011", "SSS Integration"),
]
DEFAULT_ADMIN_CODES = [
    ("RDAY-NAPP-0000", "Restday"),
    ("HDAY-NAPP-0000", "Holiday"),
    ("LBRK-NAPP-0000", "Lunch Break"),
    ("VLVE-NAPP-0000", "Vacation Leave"),
    ("SLVE-NAPP-0000", "Sick Leave"),
    ("OLVE-NAPP-0000", "Other Leaves"),
    ("SDAY-NAPP-0000", "Suspension Days"),
    ("ADMN-NAPP-0000", "Administrative: Filing / Liquidation / Documentation / TKS Application or Approval / Other Task"),
]
DEFAULT_AUDITORS = [("CLL", ""), ("LAC", ""), ("JSL", ""), ("LGA", "")]
MAIN_CODE_OPTIONS = {"RDAY", "HDAY", "LBRK", "CSCY", "TRNG", "BMNG", "ADMN", "NAPP", "VLVE", "SLVE", "OLVE", "SDAY", "ITRA", "ITPP", "ITTL", "ITSP"}
SUB_CODE_OPTIONS = {"OTRD", "OTHD", "OTEH", "TYRD", "TYHD", "TYEH", "NAPP"}
OVERTIME_SUBCODES = {"OTRD", "OTHD", "OTEH", "TYRD", "TYHD", "TYEH"}
SERIES_CODE_PATTERN = re.compile(r"^(?:0000|[HML]\d{3})$")


def password_hash(value: str) -> str:
    return generate_password_hash(value)


def password_matches(stored_hash: str, value: str) -> bool:
    try:
        return check_password_hash(stored_hash, value)
    except ValueError:
        return stored_hash == hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_engagement_code(main_code, sub_code, series_code):
    main_code = main_code.strip().upper()
    sub_code = sub_code.strip().upper()
    series_code = series_code.strip().upper()
    if main_code not in MAIN_CODE_OPTIONS or sub_code not in SUB_CODE_OPTIONS or not SERIES_CODE_PATTERN.fullmatch(series_code):
        raise ValueError("Use a valid main code, sub code, and series code.")
    return f"{main_code}-{sub_code}-{series_code}"


def engagement_base_code(code):
    parts = code.split("-")
    if len(parts) == 3 and parts[1] in OVERTIME_SUBCODES:
        return f"{parts[0]}-NAPP-{parts[2]}"
    return code

def db():
    resource_url = os.environ.get("DATABASE_URL") or os.environ.get("PRODUCTIVITY_DB") or ""
    if resource_url.startswith("postgres") and psycopg2:
        connection = psycopg2.connect(resource_url)
        return PostgresConnection(connection)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_field():
    return f"<input type='hidden' name='csrf_token' value='{escape(generate_csrf_token())}'>"


def seed_year_weekends(connection, year):
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    auditors = connection.execute("SELECT initials FROM auditors").fetchall()
    slots = [f"{hour}-{hour + 1}" for hour in range(6, 24)]
    current = start
    while current < end:
        if current.weekday() >= 5:
            connection.executemany(
                "INSERT OR IGNORE INTO entries(auditor, work_date, slot, code) VALUES (?, ?, ?, ?)",
                [(auditor["initials"], current.isoformat(), slot, "RDAY-NAPP-0000") for auditor in auditors for slot in slots],
            )
        current += timedelta(days=1)


def init_db():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, password_plaintext TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, auditor TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS auditors (initials TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS codes (code TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026, annual_budget REAL, auditor_budget REAL, PRIMARY KEY (code, kind, year));
        CREATE TABLE IF NOT EXISTS entries (auditor TEXT NOT NULL, work_date TEXT NOT NULL, slot TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY (auditor, work_date, slot));
        CREATE TABLE IF NOT EXISTS engagement_assignments (code TEXT NOT NULL, year INTEGER NOT NULL, auditor TEXT NOT NULL, budget_md REAL, PRIMARY KEY (code, year, auditor));
        CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, username TEXT NOT NULL, ua TEXT, ip TEXT, created_at INTEGER, last_active INTEGER, revoked INTEGER DEFAULT 0);
    """)
    code_columns = connection.execute("PRAGMA table_info(codes)").fetchall()
    primary_key_columns = [column["name"] for column in code_columns if column["pk"]]
    if primary_key_columns == ["code"]:
        connection.execute("ALTER TABLE codes RENAME TO codes_legacy")
        connection.execute("CREATE TABLE codes (code TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026, annual_budget REAL, auditor_budget REAL, PRIMARY KEY (code, kind, year))")
        connection.execute("INSERT INTO codes SELECT code, description, kind, year, annual_budget, auditor_budget FROM codes_legacy")
        connection.execute("DROP TABLE codes_legacy")
    account_columns = connection.execute("PRAGMA table_info(accounts)").fetchall()
    account_column_names = {column["name"] for column in account_columns}
    if "password_plaintext" not in account_column_names:
        connection.execute("ALTER TABLE accounts ADD COLUMN password_plaintext TEXT NOT NULL DEFAULT ''")
    if connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        connection.execute("INSERT INTO accounts(username, password_hash, password_plaintext, role, auditor) VALUES (?, ?, ?, 'admin', '')", ("admin", password_hash("ChangeMe123!"), "ChangeMe123!"))
    else:
        connection.execute("UPDATE accounts SET password_plaintext = COALESCE(password_plaintext, '') WHERE password_plaintext IS NULL")
    if connection.execute("SELECT COUNT(*) FROM auditors").fetchone()[0] == 0:
        connection.executemany("INSERT INTO auditors VALUES (?, ?)", DEFAULT_AUDITORS)
    if connection.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 0:
        connection.executemany("INSERT INTO codes(code, description, kind, year) VALUES (?, ?, 'engagement', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ENGAGEMENTS])
        connection.executemany("INSERT INTO codes(code, description, kind, year) VALUES (?, ?, 'admin', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ADMIN_CODES])
    connection.executemany("INSERT OR IGNORE INTO codes(code, description, kind, year) VALUES (?, ?, 'engagement', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ENGAGEMENTS])
    connection.executemany("INSERT OR IGNORE INTO codes(code, description, kind, year) VALUES (?, ?, 'admin', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ADMIN_CODES])
    connection.executemany("UPDATE codes SET description=? WHERE code=? AND kind='admin' AND year=?", [(description, code, date.today().year) for code, description in DEFAULT_ADMIN_CODES])
    for subcode in OVERTIME_SUBCODES:
        connection.execute("UPDATE codes SET kind='overtime' WHERE kind='engagement' AND code LIKE ?", (f"%-{subcode}-%",))
    seed_year_weekends(connection, date.today().year)
    connection.commit()
    connection.close()


init_db()


@app.before_request
def enforce_csrf():
    if request.method != "POST":
        return None
    if request.path.startswith("/static"):
        return None
    # allow API clients to POST JSON without CSRF token
    if request.path.startswith("/api"):
        return None
    token = request.form.get("csrf_token")
    if token != session.get("csrf_token"):
        return "Invalid or missing CSRF token.", 400
    return None


@app.before_request
def session_hardening():
    # skip for static, login, logout, health endpoints
    if request.path.startswith("/static") or request.endpoint in ("login", "logout", "health"):
        return None
    if "username" not in session:
        return None
    ua = request.headers.get('User-Agent', '')[:512]
    ip = request.remote_addr
    # UA/IP enforcement controlled by env vars
    if os.environ.get("ENFORCE_SESSION_UA", "true").lower() == "true" and session.get('ua') and session.get('ua') != ua:
        session.clear()
        return redirect(url_for('login'))
    if os.environ.get("ENFORCE_SESSION_IP", "false").lower() == "true" and session.get('ip') and session.get('ip') != ip:
        session.clear()
        return redirect(url_for('login'))
    now = int(time.time())
    max_idle = int(os.environ.get("SESSION_MAX_IDLE_SECS", str(60 * 60 * 8)))
    max_age = int(os.environ.get("SESSION_MAX_AGE_SECS", str(60 * 60 * 24)))
    if session.get('last_active') and now - int(session['last_active']) > max_idle:
        session.clear()
        return redirect(url_for('login'))
    if session.get('created_at') and now - int(session['created_at']) > max_age:
        session.clear()
        return redirect(url_for('login'))
    session['last_active'] = now
    # update DB metadata and enforce revocation flag
    sid = session.get('sid')
    if sid:
        try:
            conn = db()
            # check revoked
            row = conn.execute("SELECT revoked FROM sessions WHERE sid=?", (sid,)).fetchone()
            if row and row.get('revoked'):
                conn.close()
                session.clear()
                return redirect(url_for('login'))
            conn.execute("INSERT OR REPLACE INTO sessions(sid, username, ua, ip, created_at, last_active, revoked) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT revoked FROM sessions WHERE sid=?), 0))", (sid, session.get('username'), session.get('ua'), session.get('ip'), session.get('created_at'), now, sid))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return None


def signed_in(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return "Admin access required", 403
        return view(*args, **kwargs)
    return wrapped


def week_start(value: str | None) -> date:
    selected = date.fromisoformat(value) if value else date.today()
    return selected - timedelta(days=selected.weekday())


PAGE = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>IT Audit Productivity</title>
<style>
:root{--ink:#142b35;--ink-soft:#5f7074;--line:#d9e1df;--paper:#f5f7f4;--white:#fff;--teal:#087f71;--teal-dark:#07564f;--coral:#e56d50;--shadow:0 14px 35px rgba(20,43,53,.08)}
*{box-sizing:border-box}body{font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--paper);margin:0;min-height:100vh}body:before{content:'';display:block;height:7px;background:linear-gradient(90deg,var(--teal-dark),var(--teal),var(--coral))}.shell{max-width:1240px;margin:0 auto;padding:28px 22px 56px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}.brand{display:flex;align-items:center;gap:12px}.brand-mark{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:var(--ink);color:#fff;font-weight:800;letter-spacing:-1px}.brand h1{font-size:18px;line-height:1.1;margin:0}.brand small{display:block;color:var(--ink-soft);font-size:11px;margin-top:3px;letter-spacing:.04em;text-transform:uppercase}.identity{color:var(--ink-soft);font-size:13px;text-align:right}.identity a{color:var(--coral);font-weight:700;text-decoration:none;margin-left:10px}.nav{display:flex;gap:5px;flex-wrap:wrap;padding:6px;background:#e8efec;border:1px solid var(--line);border-radius:13px;margin-bottom:28px}.nav a{padding:9px 14px;color:var(--ink-soft);text-decoration:none;border-radius:9px;font-weight:650}.nav a:hover{background:#fff;color:var(--teal-dark)}.content{min-width:0}.card{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:22px;margin:16px 0;box-shadow:var(--shadow)}h2{font-size:24px;letter-spacing:-.5px;margin:0 0 18px}h3{font-size:17px}.card>p.muted{margin-top:-10px;margin-bottom:18px}.muted{color:var(--ink-soft)}label{display:inline-flex;flex-direction:column;gap:5px;color:var(--ink-soft);font-size:12px;font-weight:700;min-width:180px;margin:0 8px 14px 0}table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px;overflow:hidden}th,td{border-bottom:1px solid var(--line);padding:10px 9px;text-align:left;white-space:nowrap}th{background:var(--ink);color:#fff;font-size:11px;text-transform:uppercase;letter-spacing:.05em}.auditor-actions{display:flex;align-items:center;gap:8px;flex-wrap:nowrap}.auditor-actions form{display:flex;align-items:center;gap:8px;margin:0}.auditor-actions input{width:150px}.auditor-actions .btn{margin:0}.auditor-delete .btn{margin-left:2px}.auditors-table th:last-child{width:260px}.auditors-table td{vertical-align:middle}.auditor-edit{min-width:320px}.auditor-delete{flex-shrink:0}.brand{display:flex;align-items:center;gap:12px}.brand-logo{width:52px;height:52px;object-fit:contain;border-radius:50%;box-shadow:0 3px 8px rgba(20,43,53,.2);background:#fff;padding:3px}.brand h1{font-size:24px;line-height:1.2;margin:0}.brand small{display:block;color:var(--ink-soft);font-size:11px;margin-top:3px;letter-spacing:.04em;text-transform:uppercase}.footer{font-size:12px;color:var(--ink-soft);text-align:center;padding:20px 0 2px;border-top:1px solid var(--line);margin-top:30px}.footer b{color:var(--teal-dark)}th:first-child{border-radius:8px 0 0 0}th:last-child{border-radius:0 8px 0 0}tr:last-child td{border-bottom:0}tr:hover td{background:#f2f8f5}input,select{font:inherit;width:100%;padding:8px 10px;background:#fff;color:var(--ink);border:1px solid #c8d4d1;border-radius:8px;outline:none}input:focus,select:focus{border-color:var(--teal);box-shadow:0 0 0 3px rgba(8,127,113,.12)}.grid{overflow:auto;border:1px solid var(--line);border-radius:10px}.grid table{min-width:1800px}.grid th,.grid td{padding:7px}.grid td:first-child{background:#f7faf8}.btn{background:var(--teal-dark);color:white;border:0;padding:9px 15px;border-radius:8px;cursor:pointer;font-weight:700}.btn:hover{background:var(--teal)}.error{color:#b23f2d}.login-card{max-width:410px;margin:90px auto}.login-card .brand{margin-bottom:28px}.login-card .btn{width:100%;margin-top:4px}.password-field{position:relative}.password-field input{padding-right:38px}.password-toggle{position:absolute;top:50%;right:10px;transform:translateY(-50%);width:22px;height:22px;padding:0;border:0;background:transparent;color:#4f6169;cursor:pointer;display:grid;place-items:center;line-height:1;border-radius:50%}.password-toggle:hover{background:#edf3f1}.password-toggle svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.password-toggle.active{color:var(--teal-dark)}@media(max-width:700px){.shell{padding:20px 12px 40px}.topbar{align-items:flex-start;flex-direction:column;margin-bottom:20px}.identity{text-align:left}.nav{overflow:auto;flex-wrap:nowrap}.nav a{white-space:nowrap}.card{padding:16px;border-radius:12px}h2{font-size:21px}}
</style><style>.module-form{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}.module-form input,.module-form select{min-width:170px}.module-form button{margin-bottom:14px}.account-edit{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.account-edit input,.account-edit select{width:150px}.account-actions{display:flex;align-items:center;gap:8px;white-space:nowrap}.account-actions form{margin:0}.account-actions .btn{margin:0}.accounts-table th:last-child{width:120px}.accounts-table td{vertical-align:middle}.danger{background:#a94335!important}.danger:hover{background:#87352b!important}@media(max-width:700px){body{overflow-x:hidden}.shell{width:100%;padding:16px 10px 36px}.topbar{gap:12px}.brand h1{font-size:16px}.identity{font-size:12px}.nav{width:100%;overflow-x:auto}.nav a{padding:9px 11px}.card{width:100%;overflow:hidden;padding:14px}.module-form{display:block}.module-form label{display:flex;width:100%;margin-right:0}.module-form input,.module-form select{min-width:0;margin-bottom:10px}.module-form button{width:100%;margin:2px 0 8px}.account-edit{display:block}.account-edit input,.account-edit select{width:100%;margin-bottom:8px}.account-actions{display:flex;align-items:center;gap:8px}.grid{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.grid table{min-width:1500px}.card>table{display:block;width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.card>table th,.card>table td{white-space:nowrap}}
</style></head><body><div class='shell'>
{% if user %}<header class='topbar'><div class='brand'><img class='brand-logo' src='{{ url_for("static", filename="logo.svg") }}' alt='IA Productivity System'><div><h1>IA Productivity System</h1><small>IT audit operations</small></div></div><div class='identity'>Signed in as <b>{{ user }}</b> · {{ role }}<a href='{{ url_for("logout") }}'>Log out</a></div></header><nav class='nav'>{% for item in tabs %}<a href='?tab={{ item[0] }}'>{{ item[1] }}</a>{% endfor %}</nav>{% endif %}
<main class='content'>{{ content|safe }}</main><footer class='footer'>Created by © Lanz Albert Catabay, 2026. All rights reserved.</footer></div><script>
function bindPasswordToggles(){
  document.querySelectorAll('.password-toggle').forEach(function(button){
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', function(){
      var target = document.getElementById(button.dataset.target);
      if (!target) return;
      var isPassword = target.type === 'password';
      target.type = isPassword ? 'text' : 'password';
      button.classList.toggle('active', isPassword);
      button.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
      button.title = isPassword ? 'Hide password' : 'Show password';
      button.innerHTML = isPassword ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18"></path><path d="M10.58 10.58A2 2 0 0 0 13.42 13.42"></path><path d="M9.88 5.08A9.4 9.4 0 0 1 12 5c6.5 0 10 7 10 7a16.1 16.1 0 0 1-4.56 5.72M6.24 6.24A15.7 15.7 0 0 0 2 12s3.5 7 10 7a9.3 9.3 0 0 0 4.2-.96"></path></svg>';
    });
  });
}
window.addEventListener('DOMContentLoaded', bindPasswordToggles);
</script></body></html>"""


def render(content, **context):
    tabs = [("entry", "Time entry"), ("monitoring", "Monitoring"), ("engagements", "Engagements"), ("admin", "Non-engagement codes"), ("auditors", "Auditors")]
    if session.get("role") == "admin": tabs.append(("accounts", "Accounts"))
    context = {**context, "csrf_token": generate_csrf_token()}
    rendered_content = render_template_string(content, **context)
    return render_template_string(PAGE, content=rendered_content, user=session.get("username"), role=session.get("role", "").title(), tabs=tabs, csrf_token=context["csrf_token"])


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        account = db().execute("SELECT * FROM accounts WHERE lower(username)=lower(?)", (username,)).fetchone()
        if account and password_matches(account["password_hash"], password):
            # establish server-side session and bind to client
            sid = secrets.token_hex(16)
            session['sid'] = sid
            session['username'] = account["username"]
            session['role'] = account["role"]
            session['auditor'] = account["auditor"]
            session['ua'] = request.headers.get('User-Agent', '')[:512]
            session['ip'] = request.remote_addr
            now = int(time.time())
            session['created_at'] = now
            session['last_active'] = now
            # persist metadata to DB for admin UI and revocation
            try:
                conn = db()
                conn.execute("INSERT OR REPLACE INTO sessions(sid, username, ua, ip, created_at, last_active, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)", (sid, session['username'], session['ua'], session['ip'], now, now))
                conn.commit()
                conn.close()
            except Exception:
                pass
            return redirect(url_for("home"))
        error = "Incorrect username or password."
    return render_template_string("""<style>:root{--ink:#142b35;--muted:#5f7074;--teal:#07564f;--coral:#e56d50}*{box-sizing:border-box}body{font:14px/1.5 system-ui,sans-serif;background:#f5f7f4;color:var(--ink);margin:0;border-top:7px solid var(--teal)}.login{max-width:410px;margin:90px auto;padding:30px;background:#fff;border:1px solid #d9e1df;border-radius:16px;box-shadow:0 14px 35px rgba(20,43,53,.08)}.login-brand{text-align:center}.brand-img{display:block;width:90px;height:90px;object-fit:contain;border-radius:50%;box-shadow:0 3px 8px rgba(20,43,53,.2);background:#fff;padding:3px;margin:0 auto 8px}.eyebrow{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;text-align:center}.login-title{font-size:24px;margin:12px 0 0;text-align:center}.login-subtitle{color:var(--muted);text-align:center;margin:10px 0 8px}.login-form{text-align:left}.login-form label{display:block;color:var(--muted);font-size:12px;font-weight:700;margin:15px 0 6px}.login-form input{font:inherit;width:100%;padding:10px;border:1px solid #c8d4d1;border-radius:8px}.login-form button{font:inherit;width:100%;padding:10px;margin-top:20px;border:0;border-radius:8px;background:var(--teal);color:#fff;font-weight:700}.error{color:#b23f2d}.login-logo{display:block;max-width:90px;margin:0 auto;}.login-brand h1{text-align:center}.login-form .password-field{position:relative;display:block}.login-form .password-field input{padding-right:38px}.login-form .password-toggle{position:absolute;top:50%;right:10px;transform:translateY(-50%);width:22px;height:22px;padding:0;margin:0;border:0;background:transparent;color:#4f6169;cursor:pointer;display:grid;place-items:center;line-height:1;border-radius:50%;font-size:0}.login-form .password-toggle:hover{background:#edf3f1}.login-form .password-toggle svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.login-form .password-toggle.active{color:var(--teal-dark)}</style><div class='login'><div class='login-brand'><img class='brand-img' src='{{ url_for("static", filename="logo.svg") }}' alt='IA Productivity System'></div><div class='eyebrow'>IT Audit Operations</div><h1 class='login-title'>IA Productivity System</h1><p class='login-subtitle'>Sign in to your productivity workspace.</p><p class='error'>{{ error }}</p><form class='login-form' method='post'><input type='hidden' name='csrf_token' value='{{ csrf_token }}'><label>Username</label><input name='username' autofocus><label>Password</label><div class='password-field'><input id='login-password' name='password' type='password'><button type='button' class='password-toggle' data-target='login-password' aria-label='Show password' title='Show password'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z'></path><circle cx='12' cy='12' r='3'></circle></svg></button></div><button>Log in</button></form></div><script>
function bindPasswordToggles(){
  document.querySelectorAll('.password-toggle').forEach(function(button){
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', function(){
      var target = document.getElementById(button.dataset.target);
      if (!target) return;
      var isPassword = target.type === 'password';
      target.type = isPassword ? 'text' : 'password';
      button.classList.toggle('active', isPassword);
      button.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
      button.title = isPassword ? 'Hide password' : 'Show password';
      button.innerHTML = isPassword ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18"></path><path d="M10.58 10.58A2 2 0 0 0 13.42 13.42"></path><path d="M9.88 5.08A9.4 9.4 0 0 1 12 5c6.5 0 10 7 10 7a16.1 16.1 0 0 1-4.56 5.72M6.24 6.24A15.7 15.7 0 0 0 2 12s3.5 7 10 7a9.3 9.3 0 0 0 4.2-.96"></path></svg>';
    });
  });
}
window.addEventListener('DOMContentLoaded', bindPasswordToggles);
</script>""", error=error, csrf_token=generate_csrf_token())


@app.get("/logout")
def logout():
    # mark session revoked in DB (if present)
    sid = session.get('sid')
    if sid:
        try:
            conn = db()
            conn.execute("UPDATE sessions SET revoked=1 WHERE sid=?", (sid,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@signed_in
def home():
    tab = request.args.get("tab", "entry")
    if tab == "entry": return entry_page()
    if tab == "monitoring": return monitoring_page()
    if tab in {"engagements", "admin", "overtime"}: return codes_page(tab)
    if tab == "auditors": return auditors_page()
    if tab == "accounts": return accounts_page()
    return redirect(url_for("home"))


def entry_page():
    connection = db(); auditors = connection.execute("SELECT * FROM auditors ORDER BY initials").fetchall(); codes = connection.execute("SELECT * FROM codes ORDER BY kind, code").fetchall()
    assignments = {(row["code"], row["year"], row["auditor"]) for row in connection.execute("SELECT code, year, auditor FROM engagement_assignments").fetchall()}
    selected = (request.args.get("auditor") if session.get("role") == "admin" else session.get("auditor")) or session.get("auditor") or (auditors[0]["initials"] if auditors else "")
    start = week_start(request.args.get("week")); days = [start + timedelta(days=i) for i in range(7)]; slots = [f"{h}-{h+1}" for h in range(6, 24)]
    prev_week = (start - timedelta(days=7)).isoformat()
    next_week = (start + timedelta(days=7)).isoformat()
    default_entries = []
    for day in days:
        default_entries.append((selected, day.isoformat(), "12-13", "LBRK-NAPP-0000"))
        if day.weekday() >= 5:
            default_entries.extend((selected, day.isoformat(), slot, "RDAY-NAPP-0000") for slot in slots if slot != "12-13")
    connection.executemany("INSERT OR IGNORE INTO entries(auditor, work_date, slot, code) VALUES (?, ?, ?, ?)", default_entries)
    connection.commit()
    values = {(r["work_date"], r["slot"]): r["code"] for r in connection.execute("SELECT * FROM entries WHERE auditor=? AND work_date BETWEEN ? AND ?", (selected, days[0].isoformat(), days[-1].isoformat()))}
    entry_codes = []
    for code in codes:
        if code["year"] == days[0].year:
            assigned = (engagement_base_code(code["code"]), code["year"], selected) in assignments
            if session.get("role") == "admin" or code["kind"] == "admin" or assigned:
                entry_codes.append(code["code"])
            parts = code["code"].split("-")
            if len(parts) == 3 and parts[1] == "NAPP" and code["kind"] == "engagement" and (session.get("role") == "admin" or assigned):
                entry_codes.extend(f"{parts[0]}-{subcode}-{parts[2]}" for subcode in sorted(OVERTIME_SUBCODES))
    content = """<div class='card'><h2>Time entry</h2><div style='display:flex;gap:8px;align-items:center;margin-bottom:12px;'>
<a href='?tab=entry&week={{ prev_week }}' style='padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;margin-right:auto;'>&larr; Prev week</a>
<a href='?tab=entry&week={{ next_week }}' style='padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;'>Next week &rarr;</a>
</div>{% if role == 'admin' %}<form method='get'><input type='hidden' name='tab' value='entry'><label>Auditor<select name='auditor' onchange='this.form.submit()'>{% for a in auditors %}<option value='{{a.initials}}' {% if a.initials==selected %}selected{% endif %}>{{a.initials}} {{a.name}}</option>{% endfor %}</select></label></form>{% else %}<p><b>Auditor:</b> {{ selected }}</p>{% endif %}<p class='muted'>Each hour counts as 0.125 MD. Overtime codes are available for registered engagements.</p><div class='grid'><table><tr><th>Date</th>{% for slot in slots %}<th>{{slot}}</th>{% endfor %}</tr>{% for day in days %}<tr><td><b>{{day.strftime('%a')}}</b><br>{{day.isoformat()}}</td>{% for slot in slots %}<td><form method='post' action='{{url_for("save_entry")}}'><input type='hidden' name='csrf_token' value='{{ csrf_token }}'><input type='hidden' name='auditor' value='{{selected}}'><input type='hidden' name='work_date' value='{{day.isoformat()}}'><input type='hidden' name='slot' value='{{slot}}'><select name='code' onchange='this.form.submit()'><option value=''>-</option>{% for code in entry_codes %}<option value='{{code}}' {% if values.get((day.isoformat(),slot))==code %}selected{% endif %}>{{code}}</option>{% endfor %}</select></form></td>{% endfor %}</tr>{% endfor %}</table></div></div>"""
    return render(content, auditors=auditors, codes=codes, entry_codes=entry_codes, selected=selected, days=days, slots=slots, values=values, role=session.get("role"), prev_week=prev_week, next_week=next_week)


@app.post("/entry")
@signed_in
def save_entry():
    auditor = session.get("auditor") if session.get("role") == "auditor" else request.form["auditor"]
    code = request.form.get("code", "").strip()
    connection = db(); params = (auditor, request.form["work_date"], request.form["slot"])
    code_year = int(request.form["work_date"][:4])
    registered = connection.execute("SELECT 1 FROM codes WHERE code=? AND year=?", (code, code_year)).fetchone() if code else None
    if not registered and code:
        base_code = engagement_base_code(code)
        if base_code != code:
            registered = connection.execute("SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=?", (base_code, code_year)).fetchone()
    if registered and session.get("role") == "auditor":
        base_code = engagement_base_code(code)
        assigned = connection.execute("SELECT 1 FROM engagement_assignments WHERE code=? AND year=? AND auditor=?", (base_code, code_year, auditor)).fetchone()
        code_kind = connection.execute("SELECT kind FROM codes WHERE code=? AND year=?", (base_code, code_year)).fetchone()
        if code_kind and code_kind["kind"] == "engagement" and not assigned:
            registered = None
    if code and registered: connection.execute("INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?)", (*params, code))
    else: connection.execute("DELETE FROM entries WHERE auditor=? AND work_date=? AND slot=?", params)
    connection.commit(); connection.close()
    return redirect(url_for("home", tab="entry", auditor=auditor, week=request.form["work_date"]))


def codes_page(tab):
    kind = "engagement" if tab == "engagements" else "overtime" if tab == "overtime" else "admin"
    connection = db()
    rows = connection.execute("SELECT * FROM codes WHERE kind=? ORDER BY code", (kind,)).fetchall()
    overtime_rows = connection.execute("SELECT * FROM codes WHERE kind='overtime' ORDER BY code").fetchall() if kind == "engagement" else []
    auditors = connection.execute("SELECT * FROM auditors ORDER BY initials").fetchall() if kind == "engagement" else []
    assignments = connection.execute("SELECT * FROM engagement_assignments ORDER BY year DESC, code, auditor").fetchall() if kind == "engagement" else []
    title = "Engagement codes" if kind == "engagement" else "Non-engagement codes" if kind == "admin" else "Overtime engagement codes"
    fields = "<th>Code</th><th>Description</th>" + ("<th>Year</th><th>Annual budget MD</th><th>Budgeted MD / auditor</th>" if kind == "engagement" else "<th>Year</th>" if kind == "overtime" else "")
    body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{escape(row['description'])}</td>" + (f"<td>{row['year']}</td><td>{row['annual_budget'] or '-'}</td><td>{row['auditor_budget'] or '-'}</td>" if kind == "engagement" else f"<td>{row['year']}</td>" if kind == "overtime" else "") + "</tr>" for row in rows)
    code_parts = "<label>Main code<select name='main_code' required><option value=''>Select</option>" + "".join(f"<option>{code}</option>" for code in sorted(MAIN_CODE_OPTIONS)) + "</select></label><label>Sub code<select name='sub_code' required><option value=''>Select</option>" + "".join(f"<option>{code}</option>" for code in sorted(SUB_CODE_OPTIONS)) + "</select></label><label>Series code<input name='series_code' placeholder='H001 / M001 / 0000' required></label>"
    code_input = code_parts if kind in {"engagement", "overtime"} else "<label>Code<input name='code' required></label>"
    if session.get("role") == "admin":
        if kind == "engagement":
            add_form = f"<form class='module-form' method='post' action='{url_for('add_code')}'>{csrf_field()}<input type='hidden' name='kind' value='{kind}'>{code_input}<label>Description / particulars<input name='description' required></label><label>Year<input name='year' type='number' value='" + str(date.today().year) + "'></label><label>Budget MD<input name='annual_budget'></label><label>Budget / auditor<input name='auditor_budget'></label><button class='btn'>Add / update</button><button class='btn danger' type='submit' formaction='" + url_for("delete_code_by_details") + "'>Delete</button></form>"
        elif kind == "overtime":
            add_form = f"<form class='module-form' method='post' action='{url_for('add_code')}'>{csrf_field()}<input type='hidden' name='kind' value='{kind}'>{code_input}<label>Description / particulars<input name='description' required></label><label>Year<input name='year' type='number' value='" + str(date.today().year) + "'></label><button class='btn'>Add / update</button></form>"
        else:
            add_form = f"<form class='module-form' method='post' action='{url_for('add_code')}'>{csrf_field()}<input type='hidden' name='kind' value='{kind}'>{code_input}<label>Description / particulars<input name='description' required></label><button class='btn'>Add</button><button class='btn danger' type='submit' formaction='" + url_for("delete_code_by_details") + "'>Delete</button></form>"
    else:
        add_form = ""
    overtime_body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{escape(row['description'])}</td><td>{row['year']}</td></tr>" for row in overtime_rows)
    overtime_table = f"<section><h3>Encoded overtime</h3><p class='muted'>Create overtime codes from the form above by selecting an overtime subcode. They appear here and are available in Time Entry.</p><table><tr><th>Code</th><th>Description / particulars</th><th>Year</th></tr>{overtime_body}</table></section>" if kind == "engagement" else ""
    engagement_options = "".join(f"<option value='{escape(row['code'])}'>{escape(row['code'])}</option>" for row in rows)
    auditor_options = "".join(f"<option value='{a['initials']}'>{a['initials']} {a['name']}</option>" for a in auditors)
    assignment_form = (
        f"<form class='module-form' method='post' action='{url_for('assign_engagement')}'>{csrf_field()}"
        f"<label>Engagement code<select name='code' required><option value=''>Select engagement code</option>{engagement_options}</select></label>"
        f"<label>Year<input name='year' type='number' value='{date.today().year}' required></label>"
        f"<label>Auditor<select name='auditor' required>{auditor_options}</select></label>"
        "<button class='btn'>Assign engagement</button></form>"
    ) if kind == "engagement" and session.get("role") == "admin" else ""
    assignment_body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{row['year']}</td><td>{escape(row['auditor'])}</td>" + (f"<td><form method='post' action='{url_for('delete_assignment')}'>{csrf_field()}<input type='hidden' name='code' value='{escape(row['code'])}'><input type='hidden' name='year' value='{row['year']}'><input type='hidden' name='auditor' value='{escape(row['auditor'])}'><button class='btn danger'>Delete</button></form></td>" if session.get("role") == "admin" else "") + "</tr>" for row in assignments)
    assignment_actions = "<th>Actions</th>" if session.get("role") == "admin" else ""
    assignment_table = f"<section><h3>Engagement assignments</h3><p class='muted'>Assigned auditors see the engagement and its overtime codes in Time Entry. The budget remains in the main Engagements table.</p>{assignment_form}<table><tr><th>Engagement code</th><th>Year</th><th>Auditor</th>{assignment_actions}</tr>{assignment_body}</table></section>" if kind == "engagement" else ""
    content = f"<div class='card'><h2>{title}</h2>{add_form}<table><tr>{fields}</tr>{body}</table>{overtime_table}{assignment_table}</div>"
    return render(content)


def auditors_page():
    connection = db()
    rows = connection.execute("SELECT * FROM auditors ORDER BY initials").fetchall()
    admin = session.get("role") == "admin"
    body = []
    for row in rows:
        initials = escape(row['initials'])
        name = escape(row['name'] or '-')
        if admin:
            save_form = f"<form method='post' action='{url_for('update_auditor', initials=row['initials'])}' class='auditor-edit'>{csrf_field()}<input name='new_initials' value='{initials}' required><input name='name' value='{name}'><button class='btn'>Save</button></form>"
            delete_form = f"<form method='post' action='{url_for('delete_auditor', initials=row['initials'])}' class='auditor-delete'>{csrf_field()}<button class='btn danger'>Delete</button></form>"
            body.append(f"<tr><td>{initials}</td><td>{name}</td><td><div class='auditor-actions'>{save_form}{delete_form}</div></td></tr>")
        else:
            body.append(f"<tr><td>{initials}</td><td>{name}</td></tr>")
    add_form = f"<form class='module-form' method='post' action='{url_for('add_auditor')}'>{csrf_field()}<label>Initials<input name='initials' placeholder='Initials' maxlength='8' required></label><label>Name<input name='name' placeholder='Name'></label><button class='btn'>Add auditor</button></form>" if admin else ""
    action_header = "<th>Actions</th>" if admin else ""
    content = f"<div class='card'><h2>Auditors</h2>{add_form}<table class='auditors-table'><tr><th>Initials</th><th>Name</th>{action_header}</tr>{''.join(body)}</table></div>"
    return render(content)


def monitoring_page():
    connection = db(); year = int(request.args.get("year", date.today().year))
    auditors = connection.execute("SELECT * FROM auditors ORDER BY initials").fetchall()
    visible_auditors = [a for a in auditors if a["initials"] == session.get("auditor")] if session.get("role") == "auditor" else auditors
    years = [row["year"] for row in connection.execute("SELECT DISTINCT year FROM codes WHERE kind='engagement' ORDER BY year DESC").fetchall()]
    if year not in years: years.append(year)
    codes = connection.execute("SELECT * FROM codes WHERE kind='engagement' AND year=? ORDER BY code", (year,)).fetchall()
    admin_codes = connection.execute("SELECT * FROM codes WHERE kind='admin' ORDER BY code").fetchall()
    actual_query = "SELECT code, auditor, COUNT(*) * ? AS md FROM entries WHERE substr(work_date,1,4)=?"
    actual_params = [MD_PER_SLOT, str(year)]
    if session.get("role") == "auditor":
        actual_query += " AND auditor=?"
        actual_params.append(session.get("auditor", ""))
    actual_query += " GROUP BY code, auditor"
    actuals = connection.execute(actual_query, actual_params).fetchall()
    totals = {}
    for row in actuals:
        key = (engagement_base_code(row["code"]), row["auditor"])
        totals[key] = totals.get(key, 0) + row["md"]
    actual_header = "".join(f"<th>Actual Budget MDs ({a['initials']})</th>" for a in visible_auditors)
    body_rows = []
    for row in codes:
        budget = float(row["auditor_budget"]) if row["auditor_budget"] is not None else None
        actual_cells = "".join(f"<td>{totals.get((row['code'], a['initials']), 0):.3f}</td>" for a in visible_auditors)
        total_actual = sum(totals.get((row["code"], a["initials"]), 0) for a in visible_auditors)
        variance = "-" if budget is None or total_actual == 0 else f"{budget - total_actual:.3f}"
        body_rows.append(f"<tr><td>{row['code']}</td><td>{row['description']}</td><td>{row['annual_budget'] or '-'}</td><td>{row['auditor_budget'] or '-'}</td>{actual_cells}<td>{variance}</td></tr>")
    body = "".join(body_rows)
    admin_header = "".join(f"<th>{a['initials']} MD used</th>" for a in visible_auditors)
    admin_body = "".join("<tr><td>{}</td><td>{}</td>{}<td>{:.3f}</td></tr>".format(row["code"], row["description"], "".join(f"<td>{totals.get((row['code'], a['initials']), 0):.3f}</td>" for a in visible_auditors), sum(totals.get((row["code"], a["initials"]), 0) for a in visible_auditors)) for row in admin_codes)
    year_picker = "<form method='get' class='module-form'><input type='hidden' name='tab' value='monitoring'><label>Year<select name='year' onchange='this.form.submit()'>" + "".join(f"<option value='{option}' {'selected' if option == year else ''}>{option}</option>" for option in sorted(years, reverse=True)) + "</select></label></form>"
    variance_description = "Variance = Budgeted MD / auditor - your actual MD." if session.get("role") == "auditor" else "Variance = Budgeted MD / auditor - total actual MD across auditors."
    content = f"<div class='card'><h2>Monitoring</h2>{year_picker}<p class='muted'>{variance_description}</p><div class='grid'><table><tr><th>Code</th><th>Description</th><th>Annual budget MD</th><th>Budgeted MD / auditor</th>{actual_header}<th>Variance</th></tr>{body}</table></div></div><div class='card'><h2>Engagement usage</h2><p class='muted'>Time entered against leave, lunch, training, meetings, and other non-budgeted codes.</p><div class='grid'><table><tr><th>Code</th><th>Description</th>{admin_header}<th>Total MD used</th></tr>{admin_body}</table></div></div>"
    return render(content)


@app.post("/auditors")
@admin_only
def add_auditor():
    initials = request.form["initials"].strip().upper()
    connection = db(); connection.execute("INSERT OR REPLACE INTO auditors VALUES (?, ?)", (initials, request.form.get("name", "").strip())); connection.commit(); connection.close()
    return redirect(url_for("home", tab="auditors"))


@app.post("/codes")
@admin_only
def add_code():
    kind = request.form["kind"]
    try:
        code = build_engagement_code(request.form.get("main_code", ""), request.form.get("sub_code", ""), request.form.get("series_code", "")) if kind in {"engagement", "overtime"} else request.form["code"].strip()
        if kind == "overtime" and code.split("-")[1] not in OVERTIME_SUBCODES:
            return "Overtime codes must use an overtime subcode.", 400
    except ValueError:
        return "Invalid engagement code parts", 400
    stored_kind = "overtime" if kind == "engagement" and len(code.split("-")) == 3 and code.split("-")[1] in OVERTIME_SUBCODES else kind
    values = (code, request.form["description"].strip(), stored_kind, int(request.form.get("year", date.today().year)), request.form.get("annual_budget") or None, request.form.get("auditor_budget") or None)
    connection = db(); connection.execute("INSERT INTO codes(code, description, kind, year, annual_budget, auditor_budget) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(code, kind, year) DO UPDATE SET description=excluded.description, annual_budget=COALESCE(excluded.annual_budget, codes.annual_budget), auditor_budget=COALESCE(excluded.auditor_budget, codes.auditor_budget)", values); connection.commit(); connection.close()
    return redirect(url_for("home", tab="engagements" if kind in {"engagement", "overtime"} else "admin"))


@app.post("/assignments")
@admin_only
def assign_engagement():
    code = request.form["code"].strip().upper(); year = int(request.form["year"]); auditor = request.form["auditor"].strip().upper()
    connection = db(); exists = connection.execute("SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=?", (code, year)).fetchone()
    if not exists:
        connection.close()
        return "Engagement code must exist in the Engagements table before assignment.", 400
    existing = connection.execute("SELECT auditor FROM engagement_assignments WHERE code=? AND year=?", (code, year)).fetchone()
    if existing and existing["auditor"] != auditor:
        connection.close()
        return f"This engagement is already assigned to auditor {existing['auditor']} for {year}.", 409
    connection.execute("INSERT INTO engagement_assignments(code, year, auditor) VALUES (?, ?, ?) ON CONFLICT(code, year, auditor) DO NOTHING", (code, year, auditor)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="engagements"))


@app.post("/assignments/delete")
@admin_only
def delete_assignment():
    code = request.form["code"].strip().upper()
    year = int(request.form["year"])
    auditor = request.form["auditor"].strip().upper()
    connection = db()
    connection.execute("DELETE FROM engagement_assignments WHERE code=? AND year=? AND auditor=?", (code, year, auditor))
    connection.commit()
    connection.close()
    return redirect(url_for("home", tab="engagements"))


@app.post("/codes/delete")
@admin_only
def delete_code_by_details():
    kind = request.form.get("kind", "engagement")
    code = request.form["code"].strip()
    description = request.form["description"].strip()
    if kind == "engagement":
        year = int(request.form.get("year", date.today().year))
        connection = db()
        connection.execute("DELETE FROM codes WHERE code=? AND description=? AND year=? AND kind='engagement'", (code, description, year))
        connection.commit(); connection.close()
        return redirect(url_for("home", tab="engagements"))

    connection = db()
    connection.execute("DELETE FROM codes WHERE code=? AND description=? AND kind='admin'", (code, description))
    connection.commit(); connection.close()
    return redirect(url_for("home", tab="admin"))


@app.post("/codes/<path:code>/update")
@admin_only
def update_code(code):
    connection = db(); row = connection.execute("SELECT kind FROM codes WHERE code=?", (code,)).fetchone()
    connection.execute("UPDATE codes SET code=?, description=?, year=?, annual_budget=?, auditor_budget=? WHERE code=?", (request.form["new_code"].strip(), request.form["description"].strip(), int(request.form.get("year", date.today().year)), request.form.get("annual_budget") or None, request.form.get("auditor_budget") or None, code)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="engagements" if row and row["kind"] == "engagement" else "admin"))


@app.post("/codes/<path:code>/delete")
@admin_only
def delete_code(code):
    connection = db(); row = connection.execute("SELECT kind FROM codes WHERE code=?", (code,)).fetchone(); connection.execute("DELETE FROM codes WHERE code=?", (code,)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="engagements" if row and row["kind"] == "engagement" else "admin"))


@app.post("/auditors/<initials>/update")
@admin_only
def update_auditor(initials):
    connection = db(); connection.execute("UPDATE auditors SET initials=?, name=? WHERE initials=?", (request.form["new_initials"].strip().upper(), request.form.get("name", "").strip(), initials)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="auditors"))


@app.post("/auditors/<initials>/delete")
@admin_only
def delete_auditor(initials):
    connection = db(); connection.execute("DELETE FROM auditors WHERE initials=?", (initials,)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="auditors"))


def accounts_page():
    if session.get("role") != "admin": return "Admin access required", 403
    connection = db(); accounts = connection.execute("SELECT username, role, auditor FROM accounts ORDER BY username").fetchall()
    rows = "".join(f"<tr><td>{a['username']}</td><td>{a['role']}</td><td>{a['auditor'] or '-'}</td><td><form id='account-{a['username']}' class='account-edit' method='post' action='{url_for('update_account', username=a['username'])}'>{csrf_field()}<div class='password-field'><input id='account-password-{a['username']}' name='password' type='password' placeholder='New password'><button type='button' class='password-toggle' data-target='account-password-{a['username']}' aria-label='Show password' title='Show password'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z'></path><circle cx='12' cy='12' r='3'></circle></svg></button></div><select name='role'><option {'selected' if a['role'] == 'auditor' else ''}>auditor</option><option {'selected' if a['role'] == 'admin' else ''}>admin</option><input name='auditor' value='{a['auditor']}' placeholder='Auditor'></form></td><td><div class='account-actions'><button class='btn' form='account-{a['username']}'>Save</button>{'' if a['username'] == session.get('username') else f"<button class='btn danger' form='account-{a['username']}' formaction='{url_for('delete_account', username=a['username'])}'>Delete</button>"}</div></td></tr>" for a in accounts)
    content = f"<div class='card'><h2>Accounts</h2><form class='module-form' method='post' action='{url_for('add_account')}'>{csrf_field()}<label>Username<input name='username' placeholder='Username' required></label><label>Password<div class='password-field'><input id='new-account-password' name='password' type='password' placeholder='Password' required><button type='button' class='password-toggle' data-target='new-account-password' aria-label='Show password' title='Show password'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z'></path><circle cx='12' cy='12' r='3'></circle></svg></button></div></label><label>Role<select name='role'><option>auditor</option><option>admin</option></select></label><label>Auditor initials<input name='auditor' placeholder='Auditor initials'></label><button class='btn'>Add account</button></form><table class='accounts-table'><tr><th>Username</th><th>Role</th><th>Auditor</th><th>Edit</th><th>Actions</th></tr>{rows}</table></div>"
    return render(content)


@app.get("/admin/sessions")
@admin_only
def admin_sessions():
    connection = db()
    rows = connection.execute("SELECT sid, username, ua, ip, created_at, last_active, revoked FROM sessions ORDER BY last_active DESC").fetchall()
    body = ""
    for r in rows:
        sid = escape(r['sid'])
        username = escape(r['username'])
        ua = escape(r.get('ua') or '-')
        ip = escape(r.get('ip') or '-')
        created = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(r['created_at']))) if r.get('created_at') else '-'
        last = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(r['last_active']))) if r.get('last_active') else '-'
        revoked = 'Yes' if r.get('revoked') else 'No'
        body += f"<tr><td>{username}</td><td>{sid}</td><td>{created}</td><td>{last}</td><td>{ip}</td><td>{ua}</td><td>{revoked}</td><td><form method='post' action='{url_for('revoke_session')}'><input type='hidden' name='sid' value='{sid}'>{csrf_field()}<button class='btn danger'>Revoke</button></form></td></tr>"
    content = f"<div class='card'><h2>Active Sessions</h2><p class='muted'>List of sessions (revoked sessions are marked). Revoke forces logout on next request.</p><div class='grid'><table><tr><th>User</th><th>SID</th><th>Created</th><th>Last active</th><th>IP</th><th>User-Agent</th><th>Revoked</th><th>Action</th></tr>{body}</table></div></div>"
    return render(content)


@app.post('/admin/sessions/revoke')
@admin_only
def revoke_session():
    sid = request.form.get('sid')
    username = request.form.get('username')
    connection = db()
    if sid:
        connection.execute("UPDATE sessions SET revoked=1 WHERE sid=?", (sid,))
    elif username:
        connection.execute("UPDATE sessions SET revoked=1 WHERE username=?", (username,))
    connection.commit()
    connection.close()
    return redirect(url_for('admin_sessions'))


@app.post("/accounts")
@admin_only
def add_account():
    username = request.form["username"].strip()
    role = request.form["role"]
    auditor = request.form.get("auditor", "").strip().upper()
    connection = db()
    if role == "auditor" and not auditor:
        connection.close()
        return "Auditor accounts must be linked to auditor initials.", 400
    if role == "auditor" and auditor:
        existing_auditor_account = connection.execute("SELECT username FROM accounts WHERE role='auditor' AND auditor=?", (auditor,)).fetchone()
        if existing_auditor_account:
            connection.close()
            return f"Auditor initials {auditor} are already linked to account {existing_auditor_account['username']}.", 409
    plain_password = request.form.get("password", "")
    connection.execute("INSERT INTO accounts(username, password_hash, password_plaintext, role, auditor) VALUES (?, ?, ?, ?, ?)", (username, password_hash(plain_password), plain_password, role, auditor))
    if role == "auditor" and auditor:
        connection.execute("INSERT OR IGNORE INTO auditors(initials, name) VALUES (?, '')", (auditor,))
    connection.commit()
    connection.close()
    return redirect(url_for("home", tab="accounts"))


@app.post("/accounts/<username>/update")
@admin_only
def update_account(username):
    connection = db(); password = request.form.get("password", "")
    role = request.form["role"]
    auditor = request.form.get("auditor", "").strip().upper()
    if role == "auditor" and not auditor:
        connection.close()
        return "Auditor accounts must be linked to auditor initials.", 400
    if password:
        connection.execute("UPDATE accounts SET password_hash=?, password_plaintext=? WHERE username=?", (password_hash(password), password, username))
    connection.execute("UPDATE accounts SET role=?, auditor=? WHERE username=?", (role, auditor, username)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="accounts"))


@app.post("/accounts/<username>/delete")
@admin_only
def delete_account(username):
    if username != session.get("username"):
        connection = db(); connection.execute("DELETE FROM accounts WHERE username=?", (username,)); connection.commit(); connection.close()
    return redirect(url_for("home", tab="accounts"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/data")
def api_data():
    if "username" not in session:
        return {"error": "authentication required"}, 401
    role = session.get("role") or ""
    payload = {}
    conn = db()
    try:
        payload["engagement-codes"] = [
            {"code": row["code"], "description": row["description"], "year": row["year"], "annualBudgetMD": row["annual_budget"], "auditorBudgetMD": row["auditor_budget"]}
            for row in conn.execute("SELECT * FROM codes WHERE kind='engagement' ORDER BY year DESC, code").fetchall()
        ]
        payload["admin-codes"] = [
            {"code": row["code"], "description": row["description"]}
            for row in conn.execute("SELECT * FROM codes WHERE kind='admin' ORDER BY code").fetchall()
        ]
        payload["auditors"] = [
            {"initials": row["initials"], "name": row["name"]}
            for row in conn.execute("SELECT * FROM auditors ORDER BY initials").fetchall()
        ]
        payload["engagement-assignments"] = [
            {"code": row["code"], "year": row["year"], "auditor": row["auditor"]}
            for row in conn.execute("SELECT * FROM engagement_assignments ORDER BY year DESC, code, auditor").fetchall()
        ]
        if role == "admin":
            payload["accounts"] = [
                {"username": row["username"], "passwordHash": row["password_hash"], "passwordText": row["password_plaintext"], "role": row["role"], "auditorInitials": row["auditor"]}
                for row in conn.execute("SELECT * FROM accounts ORDER BY username").fetchall()
            ]
        else:
            payload["accounts"] = [
                {"username": row["username"], "passwordHash": row["password_hash"], "passwordText": "", "role": row["role"], "auditorInitials": row["auditor"], "canViewPassword": False}
                for row in conn.execute("SELECT * FROM accounts WHERE lower(username)=lower(?) OR role='admin' ORDER BY username", (session.get("username"),)).fetchall()
            ]
        entries = {}
        rows = conn.execute("SELECT auditor, work_date, slot, code FROM entries").fetchall()
        for row in rows:
            key = f"{row['auditor']}__{row['work_date']}"
            entries.setdefault(key, {})[row["slot"]] = row["code"]
        payload["time-entries"] = entries
    finally:
        conn.close()
    return payload


@app.post("/api/sync")
def api_sync():
    """Accept JSON payload { key: <str>, value: <any> } and persist to DB.
    Supported keys: 'accounts', 'auditors', 'engagement-codes', 'admin-codes', 'time-entries'.
    This is a best-effort sync endpoint for the SPA localStorage sync.
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return {"error": "Invalid JSON"}, 400
    if not data or "key" not in data:
        return {"error": "Missing key"}, 400
    key = data["key"]
    value = data.get("value")
    # require authentication for API sync
    if "username" not in session:
        return {"error": "authentication required"}, 401
    role = session.get("role") or ""
    # enforce admin-only for sensitive keys
    if role != "admin" and key in ("accounts", "engagement-codes", "admin-codes", "auditors"):
        return {"error": "admin required"}, 403
    conn = db()
    try:
        if key == "accounts" and isinstance(value, list):
            for a in value:
                username = a.get("username")
                pw = a.get("passwordHash") or a.get("password_hash") or ""
                plain_pw = a.get("passwordText") or a.get("passwordPlaintext") or (pw if pw and pw != "" else "")
                role = a.get("role") or "auditor"
                auditor = a.get("auditorInitials") or a.get("auditor") or ""
                if not username:
                    continue
                conn.execute("INSERT OR REPLACE INTO accounts(username, password_hash, password_plaintext, role, auditor) VALUES (?, ?, ?, ?, ?)", (username, pw, plain_pw, role, auditor))
        elif key == "auditors" and isinstance(value, list):
            for ad in value:
                initials = (ad.get("initials") or "").strip().upper()
                name = ad.get("name") or ""
                if not initials:
                    continue
                conn.execute("INSERT OR REPLACE INTO auditors VALUES (?, ?)", (initials, name))
        elif key in ("engagement-codes", "admin-codes") and isinstance(value, list):
            kind = "engagement" if key == "engagement-codes" else "admin"
            for c in value:
                code = c.get("code")
                description = c.get("description") or ""
                year = int(c.get("year") or date.today().year)
                annual = c.get("annualBudgetMD") if c.get("annualBudgetMD") not in ("", None) else c.get("annualBudgetMD")
                auditor_budget = c.get("auditorBudgetMD") if c.get("auditorBudgetMD") not in ("", None) else c.get("auditorBudgetMD")
                # convert empty strings to None
                if annual == "":
                    annual = None
                if auditor_budget == "":
                    auditor_budget = None
                if not code:
                    continue
                conn.execute("INSERT INTO codes(code, description, kind, year, annual_budget, auditor_budget) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(code, kind, year) DO UPDATE SET description=excluded.description, annual_budget=COALESCE(excluded.annual_budget, codes.annual_budget), auditor_budget=COALESCE(excluded.auditor_budget, codes.auditor_budget)", (code, description, kind, year, annual, auditor_budget))
        elif key == "time-entries" and isinstance(value, dict):
            # value is mapping like { 'CLL__2026-09-13': { '12-13': 'LBRK-NAPP-0000', '6-7': 'RDAY-NAPP-0000' }, ... }
            # auditors may only sync their own entries; admins may sync all
            if role == "auditor":
                allowed_auditor = session.get("auditor") or ""
            else:
                allowed_auditor = None
            for composite, slots in value.items():
                if not composite or not isinstance(slots, dict):
                    continue
                parts = composite.split("__")
                if len(parts) != 2:
                    continue
                auditor, work_date = parts[0], parts[1]
                # if an auditor is syncing, ensure they only write their own auditor data
                if allowed_auditor is not None and auditor != allowed_auditor:
                    return {"error": "auditor may only sync their own entries"}, 403
                # replace entries for this auditor/date
                conn.execute("DELETE FROM entries WHERE auditor=? AND work_date=?", (auditor, work_date))
                for slot, code in slots.items():
                    if code:
                        conn.execute("INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?)", (auditor, work_date, slot, code))
        else:
            return {"error": "Unsupported key or invalid value"}, 400
        conn.commit()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"error": str(e)}, 500
    conn.close()
    return {"status": "ok"}


@app.post("/api/login_json")
def api_login_json():
    try:
        data = request.get_json(force=True)
    except Exception:
        return {"error": "Invalid JSON"}, 400
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return {"error": "username and password required"}, 400
    account = db().execute("SELECT * FROM accounts WHERE lower(username)=lower(?)", (username,)).fetchone()
    if not account or not password_matches(account["password_hash"], password):
        return {"error": "invalid credentials"}, 401
    # establish server-side session and bind to client
    sid = secrets.token_hex(16)
    session['sid'] = sid
    session['username'] = account["username"]
    session['role'] = account["role"]
    session['auditor'] = account["auditor"] if account["auditor"] else ""
    session['ua'] = request.headers.get('User-Agent', '')[:512]
    session['ip'] = request.remote_addr
    now = int(time.time())
    session['created_at'] = now
    session['last_active'] = now
    try:
        conn = db()
        conn.execute("INSERT OR REPLACE INTO sessions(sid, username, ua, ip, created_at, last_active, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)", (sid, session['username'], session['ua'], session['ip'], now, now))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return {"status": "ok", "username": session['username'], "role": session['role'], "auditor": session['auditor']}




if __name__ == "__main__":
    init_db()
    host = os.environ.get("PRODUCTIVITY_HOST", "0.0.0.0")
    port = int(os.environ.get("PRODUCTIVITY_PORT", "5000"))
    debug = os.environ.get("PRODUCTIVITY_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)