from __future__ import annotations

import hashlib
from html import escape
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    psycopg2 = None
    RealDictCursor = None


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
BUSINESS_PROCESS_ENGAGEMENTS = [
    ("BPRA-NAPP-H001", "Treasury Deparrtment"),
    ("BPRA-NAPP-H002", "Compliance Office"),
    ("BPRA-NAPP-H003", "Branch Cash Handling"),
    ("BPRA-NAPP-H004", "USSC Tax Compliance"),
    ("BPRA-NAPP-H005", "Head Office Accounts Payable"),
    ("BPRA-NAPP-H006", "Regional Office Accounts Payable"),
    ("BPRA-NAPP-H007", "Transaction Reconciliation"),
    ("BPRA-NAPP-H008", "Fleet Management"),
    ("BPRA-NAPP-H009", "Environmental, Occupational Safety, and Health Management"),
    ("BPRA-NAPP-H010", "Business Continuity Management"),
    ("BPRA-NAPP-H011", "Recruitment and Manpower Movement"),
    ("BPRA-NAPP-H012", "Code of Conduct and Employee Relations"),
    ("BPRA-NAPP-H013", "Timekeeping, Compensation and Bdenefits"),
    ("BPRA-NAPP-H014", "Sub-Agent Process"),
    ("BPRA-NAPP-H015", "Prefunding Process"),
    ("BPRA-NAPP-M001", "Branch Opening, Transfer and Closure"),
    ("BPRA-NAPP-M002", "Regional Office and Branch Bank Account Reconciliation"),
    ("BPRA-NAPP-M003", "Head Office Bank Account Reconciliation"),
    ("BPRA-NAPP-M004", "Budgeting"),
    ("BPRA-NAPP-M005", "Loans Payable"),
    ("BPRA-NAPP-M006", "Current and Non -current Receivable"),
    ("BPRA-NAPP-M007", "Investment (Non-Trade Accounts Payable)"),
    ("BPRA-NAPP-M008", "Branch Security Management"),
    ("BPRA-NAPP-M009", "Vendor Accreditation Management"),
    ("BPRA-NAPP-M010", "Performance Appraisal Upgrade and Promotion"),
    ("BPRA-NAPP-M011", "Head Office Assset Management"),
    ("BPRA-NAPP-M012", "Pay1st Merchant Process"),
    ("BPRA-NAPP-M013", "Litigation Management"),
    ("BPRA-NAPP-M014", "Contract Management"),
    ("BPRA-NAPP-M015", "Customer Service Handling"),
    ("BPRA-NAPP-M016", "Branch Support Handling"),
    ("BPRA-NAPP-M017", "Governance"),
    ("BPRA-NAPP-M018", "Branch Funding and Cash Delivery Team"),
    ("BPRA-NAPP-M019", "Purchasing Department Procurement"),
    ("BPRA-NAPP-M020", "Regional Office and Branch Asset Management"),
    ("BPRA-NAPP-M021", "Building Administration and Security"),
    ("BPRA-NAPP-M022", "Revolving Fund and/or Petty Cash"),
    ("BPRA-NAPP-M023", "Ticketing Colleague Process"),
    ("BPRA-NAPP-M024", "Customer Loyalty and Retention Program"),
    ("BPRA-NAPP-L001", "Management Reporting"),
    ("BPRA-NAPP-L002", "Regional Office Revenue Recognition"),
    ("BPRA-NAPP-L003", "Regional Office Procurement"),
    ("BPRA-NAPP-L004", "Brand and Product Campaign and Advertisement"),
    ("BPRA-NAPP-L005", "Product Research and Development"),
    ("BPRA-NAPP-L006", "Employee Incentive Programs"),
]
BRANCH_AUDIT_TYPES = [
    ("BRFA", "Branch Operations Audit: Full Audit"),
    ("BRVA", "Branch Operations Audit: Virtual Full Audit"),
    ("BRCC", "Branch Operations Audit: Cash Count Visit"),
    ("BROC", "Branch Operations Audit: Online Cash Count"),
    ("BRTL", "Branch Operations Audit: Audit Issue Monitoring"),
    ("BRRF", "Branch Operations Red-Flag"),
    ("BRSP", "Branch Operations Special Audit: Hold-up / Robbery / Budol-Budol / Incident Report / Fraud Audit"),
]
BRANCH_AUDIT_ENGAGEMENTS = [
    (f"{main_code}-NAPP-{sequence}", name)
    for main_code, name in BRANCH_AUDIT_TYPES
    for sequence in ("0000",)
]
CATALOG_ENGAGEMENTS = DEFAULT_ENGAGEMENTS + BUSINESS_PROCESS_ENGAGEMENTS + BRANCH_AUDIT_ENGAGEMENTS
CATALOG_MAIN_CODES = sorted({code.split("-")[0] for code, _ in CATALOG_ENGAGEMENTS})
CATALOG_BASE_ENGAGEMENTS = [(f"{main_code}-NAPP-0000", f"{main_code} engagement") for main_code in CATALOG_MAIN_CODES if f"{main_code}-NAPP-0000" not in {code for code, _ in CATALOG_ENGAGEMENTS}]
ALL_CATALOG_ENGAGEMENTS = CATALOG_ENGAGEMENTS + CATALOG_BASE_ENGAGEMENTS
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
AUDIT_TYPE_LABELS = {"it": "IT Audit", "business": "Business Process", "branch": "Branch Audit"}
MAIN_CODE_OPTIONS = {"RDAY", "HDAY", "LBRK", "CSCY", "TRNG", "BMNG", "ADMN", "NAPP", "VLVE", "SLVE", "OLVE", "SDAY", "ITRA", "ITPP", "ITTL", "ITSP", "BPRA", "BRFA", "BRVA", "BRCC", "BROC", "BRTL", "BRRF", "BRSP"}
SUB_CODE_OPTIONS = {"OTRD", "OTHD", "OTEH", "TYRD", "TYHD", "TYEH", "NAPP"}
OVERTIME_SUBCODES = {"OTRD", "OTHD", "OTEH", "TYRD", "TYHD", "TYEH"}
SERIES_CODE_PATTERN = re.compile(r"^(?:0000|[HML]\d{3})$")
CATALOG_MAIN_CODE_PATTERN = re.compile(r"^(?:IT|BP|BR)[A-Z0-9]+$")


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
    if (main_code not in MAIN_CODE_OPTIONS and not CATALOG_MAIN_CODE_PATTERN.fullmatch(main_code)) or sub_code not in SUB_CODE_OPTIONS or not SERIES_CODE_PATTERN.fullmatch(series_code):
        raise ValueError("Use a valid main code, sub code, and series code.")
    return f"{main_code}-{sub_code}-{series_code}"


def engagement_base_code(code):
    parts = code.split("-")
    if len(parts) == 3 and parts[1] in OVERTIME_SUBCODES:
        return f"{parts[0]}-NAPP-{parts[2]}"
    return code


def catalog_table_for_code(code):
    main_code = code.split("-", 1)[0]
    if main_code.startswith("IT"):
        return "it_engagements"
    if main_code.startswith("BP"):
        return "business_process_engagements"
    if main_code.startswith("BR"):
        return "branch_audit_engagements"
    return None


def audit_type_for_engagement(code):
    main_code = code.split("-", 1)[0]
    if main_code.startswith("IT"):
        return "it"
    if main_code.startswith("BP"):
        return "business"
    if main_code.startswith("BR"):
        return "branch"
    return None


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        cur = self.connection.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, params):
        sql = sql.replace("?", "%s")
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        cur = self.connection.cursor(cursor_factory=RealDictCursor)
        cur.executemany(sql, params)
        return cur

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


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
        CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, auditor TEXT NOT NULL DEFAULT '', audit_type TEXT NOT NULL DEFAULT 'it');
        CREATE TABLE IF NOT EXISTS auditors (initials TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', audit_type TEXT NOT NULL DEFAULT 'it');
        CREATE TABLE IF NOT EXISTS codes (code TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026, annual_budget REAL, auditor_budget REAL, PRIMARY KEY (code, kind, year));
        CREATE TABLE IF NOT EXISTS entries (auditor TEXT NOT NULL, work_date TEXT NOT NULL, slot TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY (auditor, work_date, slot));
        CREATE TABLE IF NOT EXISTS engagement_assignments (code TEXT NOT NULL, year INTEGER NOT NULL, auditor TEXT NOT NULL, budget_md REAL, PRIMARY KEY (code, year, auditor));
        CREATE TABLE IF NOT EXISTS it_engagements (engagement_code TEXT PRIMARY KEY, name TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026);
        CREATE TABLE IF NOT EXISTS business_process_engagements (engagement_code TEXT PRIMARY KEY, name TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026);
        CREATE TABLE IF NOT EXISTS branch_audit_engagements (engagement_code TEXT PRIMARY KEY, name TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026);
    """)

    # SQLite-only legacy schema migration guard. PostgreSQL does not expose
    # PRAGMA table_info(codes) metadata and should skip that branch.
    if isinstance(connection, sqlite3.Connection):
        code_columns = connection.execute("PRAGMA table_info(codes)").fetchall()
        primary_key_columns = [column["name"] for column in code_columns if column["pk"]]
        if primary_key_columns == ["code"]:
            connection.execute("ALTER TABLE codes RENAME TO codes_legacy")
            connection.execute("CREATE TABLE codes (code TEXT NOT NULL, description TEXT NOT NULL, kind TEXT NOT NULL, year INTEGER NOT NULL DEFAULT 2026, annual_budget REAL, auditor_budget REAL, PRIMARY KEY (code, kind, year))")
            connection.execute("INSERT INTO codes SELECT code, description, kind, year, annual_budget, auditor_budget FROM codes_legacy")
            connection.execute("DROP TABLE codes_legacy")

    for table_name in ("accounts", "auditors"):
        try:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN audit_type TEXT NOT NULL DEFAULT 'it'")
        except Exception:
            pass
    connection.execute("UPDATE accounts SET audit_type='it' WHERE audit_type IS NULL OR audit_type NOT IN ('it', 'business', 'branch')")

    if connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        connection.execute("INSERT INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, 'admin', '', 'it')", ("admin", password_hash("ChangeMe123!")))
    if connection.execute("SELECT COUNT(*) FROM auditors").fetchone()[0] == 0:
        connection.executemany("INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, 'it')", DEFAULT_AUDITORS)
    if connection.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 0:
        connection.executemany("INSERT INTO codes(code, description, kind, year) VALUES (?, ?, 'engagement', ?)", [(c, d, date.today().year) for c, d in ALL_CATALOG_ENGAGEMENTS])
        connection.executemany("INSERT INTO codes(code, description, kind, year) VALUES (?, ?, 'admin', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ADMIN_CODES])
    connection.executemany("INSERT OR IGNORE INTO codes(code, description, kind, year) VALUES (?, ?, 'engagement', ?)", [(c, d, date.today().year) for c, d in ALL_CATALOG_ENGAGEMENTS])
    connection.executemany("INSERT OR IGNORE INTO codes(code, description, kind, year) VALUES (?, ?, 'admin', ?)", [(c, d, date.today().year) for c, d in DEFAULT_ADMIN_CODES])
    connection.executemany("UPDATE codes SET description=? WHERE code=? AND kind='admin' AND year=?", [(description, code, date.today().year) for code, description in DEFAULT_ADMIN_CODES])
    catalog_tables = (
        ("it_engagements", [(c, d, date.today().year) for c, d in ALL_CATALOG_ENGAGEMENTS if c.startswith("IT")]),
        ("business_process_engagements", [(c, d, date.today().year) for c, d in ALL_CATALOG_ENGAGEMENTS if c.startswith("BP")]),
        ("branch_audit_engagements", [(c, d, date.today().year) for c, d in ALL_CATALOG_ENGAGEMENTS if c.startswith("BR")]),
    )
    for table_name, rows in catalog_tables:
        connection.executemany(f"INSERT OR IGNORE INTO {table_name}(engagement_code, name, year) VALUES (?, ?, ?)", rows)
    branch_audit_codes = tuple(f"{main_code}-NAPP-0000" for main_code, _ in BRANCH_AUDIT_TYPES)
    connection.execute("DELETE FROM branch_audit_engagements WHERE engagement_code NOT IN ({})".format(",".join("?" for _ in branch_audit_codes)), branch_audit_codes)
    connection.execute("DELETE FROM codes WHERE kind='engagement' AND code LIKE 'BR%-NAPP-%' AND code NOT IN ({})".format(",".join("?" for _ in branch_audit_codes)), branch_audit_codes)
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
    token = request.form.get("csrf_token")
    if token != session.get("csrf_token"):
        return "Invalid or missing CSRF token.", 400
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
*{box-sizing:border-box}body{font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--paper);margin:0;min-height:100vh}body:before{content:'';display:block;height:7px;background:linear-gradient(90deg,var(--teal-dark),var(--teal),var(--coral))}.shell{max-width:1240px;margin:0 auto;padding:28px 22px 56px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}.brand{display:flex;align-items:center;gap:12px}.brand-mark{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:var(--ink);color:#fff;font-weight:800;letter-spacing:-1px}.brand h1{font-size:18px;line-height:1.1;margin:0}.brand small{display:block;color:var(--ink-soft);font-size:11px;margin-top:3px;letter-spacing:.04em;text-transform:uppercase}.identity{color:var(--ink-soft);font-size:13px;text-align:right}.identity a{color:var(--coral);font-weight:700;text-decoration:none;margin-left:10px}.nav{display:flex;gap:5px;flex-wrap:wrap;padding:6px;background:#e8efec;border:1px solid var(--line);border-radius:13px;margin-bottom:28px}.nav a{padding:9px 14px;color:var(--ink-soft);text-decoration:none;border-radius:9px;font-weight:650}.nav a:hover{background:#fff;color:var(--teal-dark)}.content{min-width:0}.card{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:22px;margin:16px 0;box-shadow:var(--shadow)}h2{font-size:24px;letter-spacing:-.5px;margin:0 0 18px}h3{font-size:17px}.card>p.muted{margin-top:-10px;margin-bottom:18px}.muted{color:var(--ink-soft)}label{display:inline-flex;flex-direction:column;gap:5px;color:var(--ink-soft);font-size:12px;font-weight:700;min-width:180px;margin:0 8px 14px 0}table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px;overflow:hidden}th,td{border-bottom:1px solid var(--line);padding:10px 9px;text-align:left;white-space:nowrap}th{background:var(--ink);color:#fff;font-size:11px;text-transform:uppercase;letter-spacing:.05em}.auditor-actions{display:flex;align-items:center;gap:8px;flex-wrap:nowrap}.auditor-actions form{display:flex;align-items:center;gap:8px;margin:0}.auditor-actions input{width:150px}.auditor-actions .btn{margin:0}.auditor-delete .btn{margin-left:2px}.auditors-table th:last-child{width:260px}.auditors-table td{vertical-align:middle}.auditor-edit{min-width:320px}.auditor-delete{flex-shrink:0}.brand{display:flex;align-items:center;gap:12px}.brand-logo{width:52px;height:52px;object-fit:contain;border-radius:50%;box-shadow:0 3px 8px rgba(20,43,53,.2);background:#fff;padding:3px}.brand h1{font-size:24px;line-height:1.2;margin:0}.brand small{display:block;color:var(--ink-soft);font-size:11px;margin-top:3px;letter-spacing:.04em;text-transform:uppercase}.footer{font-size:12px;color:var(--ink-soft);text-align:center;padding:20px 0 2px;border-top:1px solid var(--line);margin-top:30px}.footer b{color:var(--teal-dark)}th:first-child{border-radius:8px 0 0 0}th:last-child{border-radius:0 8px 0 0}tr:last-child td{border-bottom:0}tr:hover td{background:#f2f8f5}input,select{font:inherit;width:100%;padding:8px 10px;background:#fff;color:var(--ink);border:1px solid #c8d4d1;border-radius:8px;outline:none}input:focus,select:focus{border-color:var(--teal);box-shadow:0 0 0 3px rgba(8,127,113,.12)}.grid{overflow:auto;border:1px solid var(--line);border-radius:10px}.grid table{min-width:1800px}.grid th,.grid td{padding:7px}.grid td:first-child{background:#f7faf8}.btn{background:var(--teal-dark);color:white;border:0;padding:9px 15px;border-radius:8px;cursor:pointer;font-weight:700}.btn:hover{background:var(--teal)}.error{color:#b23f2d}.login-card{max-width:410px;margin:90px auto}.login-card .brand{margin-bottom:28px}.login-card .btn{width:100%;margin-top:4px}@media(max-width:700px){.shell{padding:20px 12px 40px}.topbar{align-items:flex-start;flex-direction:column;margin-bottom:20px}.identity{text-align:left}.nav{overflow:auto;flex-wrap:nowrap}.nav a{white-space:nowrap}.card{padding:16px;border-radius:12px}h2{font-size:21px}}
</style><style>.module-form{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}.module-form input,.module-form select{min-width:170px}.module-form button{margin-bottom:14px}.account-edit{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.account-edit input,.account-edit select{width:150px}.account-actions{display:flex;align-items:center;gap:8px;white-space:nowrap}.account-actions form{margin:0}.account-actions .btn{margin:0}.accounts-table th:last-child{width:120px}.accounts-table td{vertical-align:middle}.report-chart-wrap{background:#f7faf8;border:1px solid var(--line);border-radius:12px;padding:10px 16px;margin:16px 0}.report-chart{width:100%;min-height:280px;display:block}.chart-axis{stroke:#b8c8c3;stroke-width:1}.chart-axis-label,.chart-label,.chart-value{fill:var(--ink-soft);font-size:12px}.chart-value{fill:var(--ink);font-weight:700}.chart-empty{fill:var(--ink-soft);font-size:14px}.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.report-grid section{min-width:0}.report-grid h3{margin-top:8px}.report-grid table{border:1px solid var(--line)}.danger{background:#a94335!important}.danger:hover{background:#87352b!important}@media(max-width:700px){body{overflow-x:hidden}.shell{width:100%;padding:16px 10px 36px}.topbar{gap:12px}.brand h1{font-size:16px}.identity{font-size:12px}.nav{width:100%;overflow-x:auto}.nav a{padding:9px 11px}.card{width:100%;overflow:hidden;padding:14px}.module-form{display:block}.module-form label{display:flex;width:100%;margin-right:0}.module-form input,.module-form select{min-width:0;margin-bottom:10px}.module-form button{width:100%;margin:2px 0 8px}.account-edit{display:block}.account-edit input,.account-edit select{width:100%;margin-bottom:8px}.account-actions{display:flex;align-items:center;gap:8px}.grid{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.grid table{min-width:1500px}.card>table{display:block;width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.card>table th,.card>table td{white-space:nowrap}.report-grid{grid-template-columns:1fr}.report-chart{min-width:620px}}
</style></head><body><div class='shell'>
{% if user %}<header class='topbar'><div class='brand'><img class='brand-logo' src='{{ url_for("static", filename="logo.png") }}' alt='IA Productivity System'><div><h1>IA Productivity System</h1><small>IT audit operations</small></div></div><div class='identity'>Signed in as <b>{{ user }}</b> · {{ role }}<a href='{{ url_for("logout") }}'>Log out</a></div></header><nav class='nav'>{% for item in tabs %}<a href='?tab={{ item[0] }}'>{{ item[1] }}</a>{% endfor %}</nav>{% endif %}
<main class='content'>{{ content|safe }}</main><footer class='footer'>Created by © Lanz Albert Catabay, 2026. All rights reserved.</footer></div></body></html>"""


def render(content, **context):
    tabs = [("entry", "Time entry"), ("monitoring", "Monitoring"), ("engagements", "Engagements"), ("admin", "Non-engagement codes"), ("auditors", "Auditors")]
    if session.get("role") == "admin": tabs.extend([("report", "Report"), ("accounts", "Accounts")])
    context = {**context, "csrf_token": generate_csrf_token()}
    rendered_content = "<style>.entry-grid select{min-width:190px}.entry-grid table{min-width:1500px}</style>" + render_template_string(content, **context)
    rendered_content += "<script>document.addEventListener('submit',function(event){if(event.target.action.includes('/entry'))sessionStorage.setItem('timeEntryScroll',String(window.scrollY));});window.addEventListener('load',function(){var scroll=sessionStorage.getItem('timeEntryScroll');if(scroll!==null){window.scrollTo(0,Number(scroll));sessionStorage.removeItem('timeEntryScroll');}});</script>"
    return render_template_string(PAGE, content=rendered_content, user=session.get("username"), role=session.get("role", "").title(), tabs=tabs, csrf_token=context["csrf_token"])


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        account = db().execute("SELECT * FROM accounts WHERE lower(username)=lower(?)", (username,)).fetchone()
        if account and password_matches(account["password_hash"], password):
            session.update(username=account["username"], role=account["role"], auditor=account["auditor"])
            return redirect(url_for("home"))
        error = "Incorrect username or password."
    return render_template_string("""<style>:root{--ink:#142b35;--muted:#5f7074;--teal:#07564f;--coral:#e56d50}*{box-sizing:border-box}body{font:14px/1.5 system-ui,sans-serif;background:#f5f7f4;color:var(--ink);margin:0;border-top:7px solid var(--teal)}.login{max-width:410px;margin:90px auto;padding:30px;background:#fff;border:1px solid #d9e1df;border-radius:16px;box-shadow:0 14px 35px rgba(20,43,53,.08)}.login-brand{text-align:center}.brand-img{display:block;width:90px;height:90px;object-fit:contain;border-radius:50%;box-shadow:0 3px 8px rgba(20,43,53,.2);background:#fff;padding:3px;margin:0 auto 8px}.eyebrow{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;text-align:center}.login-title{font-size:24px;margin:12px 0 0;text-align:center}.login-subtitle{color:var(--muted);text-align:center;margin:10px 0 8px}.login-form{text-align:left}.login-form label{display:block;color:var(--muted);font-size:12px;font-weight:700;margin:15px 0 6px}login-form label:first-child{margin-top:0}.login-form input{font:inherit;width:100%;padding:10px;border:1px solid #c8d4d1;border-radius:8px}.login-form button{font:inherit;width:100%;padding:10px;margin-top:20px;border:0;border-radius:8px;background:var(--teal);color:#fff;font-weight:700}.error{color:#b23f2d}.login-logo{display:block;max-width:90px;margin:0 auto;}.login-brand h1{text-align:center}</style><div class='login'><div class='login-brand'><img class='brand-img' src='{{ url_for("static", filename="logo.png") }}' alt='IA Productivity System'></div><div class='eyebrow'>IT Audit Operations</div><h1 class='login-title'>IA Productivity System</h1><p class='login-subtitle'>Sign in to your productivity workspace.</p><p class='error'>{{ error }}</p><form class='login-form' method='post'><input type='hidden' name='csrf_token' value='{{ csrf_token }}'><label>Username</label><input name='username' autofocus><label>Password</label><input name='password' type='password'><button>Log in</button></form></div>""", error=error, csrf_token=generate_csrf_token())


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@signed_in
def home():
    tab = request.args.get("tab", "entry")
    if tab == "entry": return entry_page()
    if tab == "monitoring": return monitoring_page()
    if tab == "report": return report_page()
    if tab in {"engagements", "admin", "overtime"}: return codes_page(tab)
    if tab == "auditors": return auditors_page()
    if tab == "accounts": return accounts_page()
    return redirect(url_for("home"))


def entry_page():
    connection = db(); account = connection.execute("SELECT auditor FROM accounts WHERE username=? AND role='auditor'", (session.get("username"),)).fetchone(); auditor_accounts = connection.execute("SELECT auditor, username FROM accounts WHERE role='auditor' AND auditor <> '' ORDER BY auditor").fetchall(); codes = connection.execute("SELECT * FROM codes ORDER BY kind, code").fetchall()
    assignments = {(row["code"], row["year"], row["auditor"]) for row in connection.execute("SELECT code, year, auditor FROM engagement_assignments").fetchall()}
    selected = account["auditor"] if account else (request.args.get("auditor", "").strip().upper() if session.get("role") == "admin" else "")
    start = week_start(request.args.get("week")); days = [start + timedelta(days=i) for i in range(7)]; slots = [f"{h}-{h+1}" for h in range(6, 24)]
    default_entries = []
    for day in days:
        default_entries.append((selected, day.isoformat(), "12-13", "LBRK-NAPP-0000"))
        if day.weekday() >= 5:
            default_entries.extend((selected, day.isoformat(), slot, "RDAY-NAPP-0000") for slot in slots if slot != "12-13")
    if selected:
        connection.executemany("INSERT OR IGNORE INTO entries(auditor, work_date, slot, code) VALUES (?, ?, ?, ?)", default_entries)
    connection.commit()
    values = {(r["work_date"], r["slot"]): r["code"] for r in connection.execute("SELECT * FROM entries WHERE auditor=? AND work_date BETWEEN ? AND ?", (selected, days[0].isoformat(), days[-1].isoformat())).fetchall()} if selected else {}
    entry_codes = []
    for code in codes:
        if code["year"] == days[0].year:
            assigned = (engagement_base_code(code["code"]), code["year"], selected) in assignments
            is_admin_code = code["kind"] == "admin"
            is_engagement_code = code["kind"] in {"engagement", "overtime"}
            if is_admin_code or (is_engagement_code and (session.get("role") == "admin" or assigned)):
                entry_codes.append(code["code"])
            parts = code["code"].split("-")
            if len(parts) == 3 and parts[1] == "NAPP" and code["kind"] == "engagement" and (session.get("role") == "admin" or assigned):
                entry_codes.extend(f"{parts[0]}-{subcode}-{parts[2]}" for subcode in sorted(OVERTIME_SUBCODES))
    content = """<div class='card'><h2>Time entry</h2>{% if role == 'admin' %}<form method='get'><input type='hidden' name='tab' value='entry'><label>Auditor<select name='auditor' onchange='this.form.submit()'><option value=''>Select auditor account</option>{% for account in auditor_accounts %}<option value='{{account.auditor}}' {% if account.auditor==selected %}selected{% endif %}>{{account.auditor}} ({{account.username}})</option>{% endfor %}</select></label></form>{% endif %}<p class='muted'>Each hour counts as 0.125 MD. Overtime codes are available for registered engagements.</p><div class='grid entry-grid'><table><tr><th>Date</th>{% for slot in slots %}<th>{{slot}}</th>{% endfor %}</tr>{% for day in days %}<tr><td><b>{{day.strftime('%a')}}</b><br>{{day.isoformat()}}</td>{% for slot in slots %}<td><form method='post' action='{{url_for("save_entry")}}'><input type='hidden' name='csrf_token' value='{{ csrf_token }}'><input type='hidden' name='work_date' value='{{day.isoformat()}}'><input type='hidden' name='slot' value='{{slot}}'><select name='code' onchange='this.form.submit()' title='{{values.get((day.isoformat(),slot), "")}}'><option value=''>-</option>{% for code in entry_codes %}<option value='{{code}}' {% if values.get((day.isoformat(),slot))==code %}selected{% endif %}>{{code}}</option>{% endfor %}</select></form></td>{% endfor %}</tr>{% endfor %}</table></div></div>"""
    return render(content, auditor_accounts=auditor_accounts, codes=codes, entry_codes=entry_codes, selected=selected, days=days, slots=slots, values=values, role=session.get("role"))


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
    auditors = connection.execute("SELECT auditor AS initials, username AS name, audit_type FROM accounts WHERE role='auditor' AND auditor <> '' ORDER BY auditor").fetchall() if kind == "engagement" else []
    assignments = connection.execute("SELECT * FROM engagement_assignments ORDER BY year DESC, code, auditor").fetchall() if kind == "engagement" else []
    title = "Engagement codes" if kind == "engagement" else "Non-engagement codes" if kind == "admin" else "Overtime engagement codes"
    fields = "<th>Code</th><th>Description</th>" + ("<th>Year</th><th>Annual budget MD</th><th>Budgeted MD / auditor</th>" if kind == "engagement" else "<th>Year</th>" if kind == "overtime" else "")
    body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{escape(row['description'])}</td>" + (f"<td>{row['year']}</td><td>{row['annual_budget'] or '-'}</td><td>{row['auditor_budget'] or '-'}</td>" if kind == "engagement" else f"<td>{row['year']}</td>" if kind == "overtime" else "") + "</tr>" for row in rows)
    catalog_sections = ""
    if kind == "engagement":
        section_specs = (("IT engagements", "IT"), ("Business process engagements", "BP"), ("Branch audit engagements", "BR"))
        for section_title, prefix in section_specs:
            section_rows = [row for row in rows if row["code"].startswith(prefix)]
            section_body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{escape(row['description'])}</td><td>{row['year']}</td><td>{row['annual_budget'] or '-'}</td><td>{row['auditor_budget'] or '-'}</td></tr>" for row in section_rows)
            catalog_sections += f"<section><h3>{section_title}</h3><table><tr><th>Engagement Code</th><th>Name of Engagement</th><th>Year</th><th>Annual budget MD</th><th>Budgeted MD / auditor</th></tr>{section_body}</table></section>"
    code_parts = "<label>Main code<select name='main_code' required><option value=''>Select</option>" + "".join(f"<option>{code}</option>" for code in sorted(MAIN_CODE_OPTIONS)) + "</select></label><label>Sub code<select name='sub_code' required><option value=''>Select</option>" + "".join(f"<option>{code}</option>" for code in sorted(SUB_CODE_OPTIONS)) + "</select></label><label>Series code<input name='series_code' placeholder='H001 / M001 / 0000' required></label>"
    admin_code_parts = "<label>Main code<select name='main_code' required><option value=''>Select</option>" + "".join(f"<option>{code}</option>" for code in sorted(MAIN_CODE_OPTIONS)) + "</select></label><label>Sub code<select name='sub_code' required><option value='NAPP' selected>NAPP</option></select></label><label>Series code<input name='series_code' value='0000' readonly></label>"
    code_input = code_parts if kind in {"engagement", "overtime"} else admin_code_parts
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
    assignment_form = f"<form class='module-form' method='post' action='{url_for('assign_engagement')}'>{csrf_field()}<label>Engagement code<input name='code' placeholder='ITPP-NAPP-H001' required></label><label>Year<input name='year' type='number' value='{date.today().year}' required></label><label>Auditor<select name='auditor' required>" + "".join(f"<option value='{a['initials']}'>{a['initials']} {a['name']} ({AUDIT_TYPE_LABELS.get(a['audit_type'], 'IT Audit')})</option>" for a in auditors) + "</select></label><button class='btn'>Assign engagement</button></form><p class='muted'>IT, Business Process, and Branch Audit engagements can only be assigned to auditors in the matching account group.</p>" if kind == "engagement" and session.get("role") == "admin" else ""
    assignment_body = "".join(f"<tr><td>{escape(row['code'])}</td><td>{row['year']}</td><td>{escape(row['auditor'])}</td>" + (f"<td><form method='post' action='{url_for('delete_assignment')}'>{csrf_field()}<input type='hidden' name='code' value='{escape(row['code'])}'><input type='hidden' name='year' value='{row['year']}'><input type='hidden' name='auditor' value='{escape(row['auditor'])}'><button class='btn danger'>Delete</button></form></td>" if session.get("role") == "admin" else "") + "</tr>" for row in assignments)
    assignment_actions = "<th>Actions</th>" if session.get("role") == "admin" else ""
    assignment_table = f"<section><h3>Engagement assignments</h3><p class='muted'>Assigned auditors see the engagement and its overtime codes in Time Entry. The budget remains in the main Engagements table.</p>{assignment_form}<table><tr><th>Engagement code</th><th>Year</th><th>Auditor</th>{assignment_actions}</tr>{assignment_body}</table></section>" if kind == "engagement" else ""
    content = f"<div class='card'><h2>{title}</h2>{add_form}{catalog_sections}{overtime_table}{assignment_table}</div>"
    return render(content)


def auditors_page():
    connection = db()
    accounts = connection.execute("SELECT username, auditor, audit_type FROM accounts WHERE role='auditor' ORDER BY audit_type, auditor, username").fetchall()
    grouped = []
    for audit_type, label in AUDIT_TYPE_LABELS.items():
        group_accounts = [account for account in accounts if account["audit_type"] == audit_type]
        rows = "".join(f"<tr><td>{escape(account['auditor'])}</td><td>{escape(account['username'])}</td><td>{escape(label)}</td></tr>" for account in group_accounts)
        grouped.append(f"<section><h3>{escape(label)}</h3><table class='auditors-table'><tr><th>Auditor initials</th><th>Account</th><th>Audit group</th></tr>{rows or '<tr><td colspan=3>No auditor accounts assigned</td></tr>'}</table></section>")
    content = f"<div class='card'><h2>Auditor accounts by audit group</h2><p class='muted'>Auditors are managed through Accounts. The audit group selected there controls how the auditor appears in Reports.</p>{''.join(grouped)}</div>"
    connection.close()
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


@admin_only
def report_page():
    connection = db()
    today = date.today()
    try:
        end_date = date.fromisoformat(request.args.get("end", today.isoformat()))
        start_date = date.fromisoformat(request.args.get("start", (today - timedelta(days=13)).isoformat()))
    except ValueError:
        start_date, end_date = today - timedelta(days=13), today
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    audit_type = request.args.get("audit_type", "all").lower()
    prefix_map = {"it": "IT", "business": "BP", "branch": "BR"}
    auditors = connection.execute("SELECT auditor AS initials, username AS name, audit_type FROM accounts WHERE role='auditor' AND auditor <> '' ORDER BY auditor").fetchall()
    selected_auditor = request.args.get("auditor", "").strip().upper()
    if session.get("role") == "auditor":
        selected_auditor = session.get("auditor", "")
        account = next((row for row in auditors if row["initials"] == selected_auditor), None)
        audit_type = account["audit_type"] if account else "all"
    elif selected_auditor not in {row["initials"] for row in auditors}:
        selected_auditor = ""
    visible_auditors = [row for row in auditors if row["initials"] == selected_auditor] if selected_auditor else auditors
    prefix = prefix_map.get(audit_type)
    code_rows = connection.execute("SELECT code, description, kind FROM codes ORDER BY kind, code").fetchall()
    query = "SELECT auditor, code, COUNT(*) * ? AS md FROM entries WHERE work_date BETWEEN ? AND ?"
    params = [MD_PER_SLOT, start_date.isoformat(), end_date.isoformat(), "RDAY-NAPP-0000", "LBRK-NAPP-0000"]
    query += " AND code NOT IN (?, ?)"
    if selected_auditor:
        query += " AND auditor=?"
        params.append(selected_auditor)
    if prefix:
        query += " AND (code NOT LIKE 'IT%' AND code NOT LIKE 'BP%' AND code NOT LIKE 'BR%' OR code LIKE ?)"
        params.append(f"{prefix}%")
    query += " GROUP BY auditor, code"
    usage_rows = connection.execute(query, params).fetchall()
    totals = {row["initials"]: 0 for row in visible_auditors}
    code_totals = {}
    for row in usage_rows:
        totals[row["auditor"]] = totals.get(row["auditor"], 0) + row["md"]
        code_totals[row["code"]] = code_totals.get(row["code"], 0) + row["md"]
    engagement_codes = {row["code"] for row in code_rows if row["kind"] in {"engagement", "overtime"}}
    max_total = max(totals.values(), default=0)
    chart_width, chart_height, chart_bottom, chart_top = 900, 330, 270, 35
    chart_bars = []
    bar_width = max(36, min(90, 700 // max(1, len(totals))))
    chart_gap = 700 / max(1, len(totals))
    for index, auditor in enumerate(visible_auditors):
        initials = auditor["initials"]
        value = totals.get(initials, 0)
        bar_height = 0 if not max_total else (value / max_total) * (chart_bottom - chart_top)
        x = 100 + index * chart_gap + (chart_gap - bar_width) / 2
        y = chart_bottom - bar_height
        chart_bars.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_width}' height='{bar_height:.1f}' rx='4' fill='#087f71'><title>{escape(initials)}: {value:.3f} MD</title></rect><text x='{x + bar_width / 2:.1f}' y='{max(22, y - 8):.1f}' text-anchor='middle' class='chart-value'>{value:.3f}</text><text x='{x + bar_width / 2:.1f}' y='298' text-anchor='middle' class='chart-label'>{escape(initials)}</text>")
    chart = f"<svg class='report-chart' viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='Engagement usage in man-days per auditor'><line x1='90' y1='{chart_bottom}' x2='850' y2='{chart_bottom}' class='chart-axis'/><line x1='90' y1='{chart_top}' x2='90' y2='{chart_bottom}' class='chart-axis'/><text x='18' y='42' class='chart-axis-label'>MD</text>{''.join(chart_bars) if chart_bars else '<text x="450" y="160" text-anchor="middle" class="chart-empty">No engagement usage in this date range</text>'}</svg>"
    chart_rows = "".join(f"<tr><td>{escape(row['initials'])}</td><td>{escape(row['name'] or '-')}</td><td>{escape(AUDIT_TYPE_LABELS.get(row['audit_type'], 'IT Audit'))}</td><td>{totals.get(row['initials'], 0):.3f}</td></tr>" for row in visible_auditors)
    code_breakdown = "".join(f"<tr><td>{escape(code)}</td><td>{escape(next((row['description'] for row in code_rows if row['code'] == code), '-'))}</td><td>{value:.3f}</td></tr>" for code, value in sorted(code_totals.items()) if code in engagement_codes)
    non_engagement_breakdown = "".join(f"<tr><td>{escape(code)}</td><td>{escape(next((row['description'] for row in code_rows if row['code'] == code), '-'))}</td><td>{value:.3f}</td></tr>" for code, value in sorted(code_totals.items()) if code not in engagement_codes)
    auditor_options = "".join(f"<option value='{escape(row['initials'])}' {'selected' if selected_auditor == row['initials'] else ''}>{escape(row['initials'])} ({escape(row['name'])})</option>" for row in auditors)
    group_options = "".join(f"<option value='{value}' {'selected' if audit_type == value else ''}>{label}</option>" for value, label in (("all", "All groups"), *AUDIT_TYPE_LABELS.items()))
    filter_form = f"<form method='get' class='module-form'><input type='hidden' name='tab' value='report'><label>Auditor<select name='auditor' {'disabled' if session.get('role') == 'auditor' else ''}><option value=''>All auditors</option>{auditor_options}</select></label><label>Audit group<select name='audit_type' {'disabled' if session.get('role') == 'auditor' else ''}>{group_options}</select></label><label>Start date<input type='date' name='start' value='{start_date.isoformat()}' required></label><label>End date<input type='date' name='end' value='{end_date.isoformat()}' required></label><button class='btn'>Generate report</button></form>"
    content = f"<div class='card'><h2>Usage report</h2><p class='muted'>Man-days recorded per auditor for the selected date range.</p>{filter_form}<div class='report-chart-wrap'>{chart}</div><div class='report-grid'><section><h3>Usage by auditor</h3><table><tr><th>Auditor</th><th>Name</th><th>Auditor group</th><th>Total MD</th></tr>{chart_rows}</table></section><section><h3>Engagement usage</h3><table><tr><th>Code</th><th>Engagement</th><th>Total MD</th></tr>{code_breakdown or '<tr><td colspan=3>No engagement usage recorded</td></tr>'}</table><h3>Non-engagement usage</h3><table><tr><th>Code</th><th>Description</th><th>Total MD</th></tr>{non_engagement_breakdown or '<tr><td colspan=3>No non-engagement usage recorded</td></tr>'}</table></section></div></div>"
    connection.close()
    return render(content)


@app.post("/auditors")
@admin_only
def add_auditor():
    initials = request.form["initials"].strip().upper()
    connection = db(); connection.execute("INSERT OR REPLACE INTO auditors(initials, name, audit_type) VALUES (?, ?, 'it')", (initials, request.form.get("name", "").strip())); connection.commit(); connection.close()
    return redirect(url_for("home", tab="auditors"))


@app.post("/codes")
@admin_only
def add_code():
    kind = request.form["kind"]
    try:
        code = build_engagement_code(request.form.get("main_code", ""), request.form.get("sub_code", ""), request.form.get("series_code", "")) if kind in {"engagement", "overtime", "admin"} else request.form["code"].strip()
        if kind == "overtime" and code.split("-")[1] not in OVERTIME_SUBCODES:
            return "Overtime codes must use an overtime subcode.", 400
    except ValueError:
        return "Invalid engagement code parts", 400
    stored_kind = "overtime" if kind == "engagement" and len(code.split("-")) == 3 and code.split("-")[1] in OVERTIME_SUBCODES else kind
    values = (code, request.form["description"].strip(), stored_kind, int(request.form.get("year", date.today().year)), request.form.get("annual_budget") or None, request.form.get("auditor_budget") or None)
    connection = db(); connection.execute("INSERT INTO codes(code, description, kind, year, annual_budget, auditor_budget) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(code, kind, year) DO UPDATE SET description=excluded.description, annual_budget=COALESCE(excluded.annual_budget, codes.annual_budget), auditor_budget=COALESCE(excluded.auditor_budget, codes.auditor_budget)", values)
    catalog_table = catalog_table_for_code(code) if stored_kind == "engagement" else None
    if catalog_table:
        connection.execute(f"INSERT INTO {catalog_table}(engagement_code, name, year) VALUES (?, ?, ?) ON CONFLICT(engagement_code) DO UPDATE SET name=excluded.name, year=excluded.year", (code, request.form["description"].strip(), values[3]))
    connection.commit(); connection.close()
    return redirect(url_for("home", tab="engagements" if kind in {"engagement", "overtime"} else "admin"))


@app.post("/assignments")
@admin_only
def assign_engagement():
    code = request.form["code"].strip().upper(); year = int(request.form["year"]); auditor = request.form["auditor"].strip().upper()
    connection = db(); exists = connection.execute("SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=?", (code, year)).fetchone()
    if not exists:
        connection.close()
        return "Engagement code must exist in the Engagements table before assignment.", 400
    required_audit_type = audit_type_for_engagement(code)
    account = connection.execute("SELECT audit_type FROM accounts WHERE role='auditor' AND auditor=?", (auditor,)).fetchone()
    if required_audit_type and (not account or account["audit_type"] != required_audit_type):
        expected_group = AUDIT_TYPE_LABELS[required_audit_type]
        connection.close()
        return f"{code} can only be assigned to an auditor in the {expected_group} account group.", 400
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
    code = request.form.get("code", "").strip()
    description = request.form["description"].strip()
    if kind in {"engagement", "admin"} and not code:
        code = build_engagement_code(request.form.get("main_code", ""), request.form.get("sub_code", ""), request.form.get("series_code", ""))
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
    connection = db(); accounts = connection.execute("SELECT username, role, auditor, audit_type FROM accounts ORDER BY username").fetchall()
    type_options = lambda selected: "".join(f"<option value='{value}' {'selected' if selected == value else ''}>{label}</option>" for value, label in AUDIT_TYPE_LABELS.items())
    rows = "".join(f"<tr><td>{a['username']}</td><td>{a['role']}</td><td>{a['auditor'] or '-'}</td><td>{AUDIT_TYPE_LABELS.get(a['audit_type'], 'IT Audit')}</td><td><form id='account-{a['username']}' class='account-edit' method='post' action='{url_for('update_account', username=a['username'])}'>{csrf_field()}<input name='password' type='password' placeholder='New password'><select name='role'><option {'selected' if a['role'] == 'auditor' else ''}>auditor</option><option {'selected' if a['role'] == 'admin' else ''}>admin</option><input name='auditor' value='{a['auditor']}' placeholder='Auditor'><select name='audit_type'>{type_options(a['audit_type'])}</select></form></td><td><div class='account-actions'><button class='btn' form='account-{a['username']}'>Save</button>{'' if a['username'] == session.get('username') else f"<button class='btn danger' form='account-{a['username']}' formaction='{url_for('delete_account', username=a['username'])}'>Delete</button>"}</div></td></tr>" for a in accounts)
    content = f"<div class='card'><h2>Accounts</h2><form class='module-form' method='post' action='{url_for('add_account')}'>{csrf_field()}<label>Username<input name='username' placeholder='Username' required></label><label>Password<input name='password' type='password' placeholder='Password' required></label><label>Role<select name='role'><option>auditor</option><option>admin</option></select></label><label>Auditor initials<input name='auditor' placeholder='Auditor initials'></label><label>Audit group<select name='audit_type'>{type_options('it')}</select></label><button class='btn'>Add account</button></form><table class='accounts-table'><tr><th>Username</th><th>Role</th><th>Auditor</th><th>Audit group</th><th>Edit</th><th>Actions</th></tr>{rows}</table></div>"
    return render(content)


@app.post("/accounts")
@admin_only
def add_account():
    username = request.form["username"].strip()
    role = request.form["role"]
    auditor = request.form.get("auditor", "").strip().upper()
    audit_type = request.form.get("audit_type", "it").strip().lower()
    if audit_type not in AUDIT_TYPE_LABELS:
        return "Invalid audit group.", 400
    connection = db()
    if role == "auditor" and not auditor:
        connection.close()
        return "Auditor accounts must be linked to auditor initials.", 400
    if role == "auditor" and auditor:
        existing_auditor_account = connection.execute("SELECT username FROM accounts WHERE role='auditor' AND auditor=?", (auditor,)).fetchone()
        if existing_auditor_account:
            connection.close()
            return f"Auditor initials {auditor} are already linked to account {existing_auditor_account['username']}.", 409
    connection.execute("INSERT INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", (username, password_hash(request.form["password"]), role, auditor, audit_type))
    if role == "auditor" and auditor:
        connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, '', ?) ON CONFLICT(initials) DO UPDATE SET audit_type=excluded.audit_type", (auditor, audit_type))
    connection.commit()
    connection.close()
    return redirect(url_for("home", tab="accounts"))


@app.post("/accounts/<username>/update")
@admin_only
def update_account(username):
    connection = db(); password = request.form.get("password", "")
    role = request.form["role"]
    auditor = request.form.get("auditor", "").strip().upper()
    audit_type = request.form.get("audit_type", "it").strip().lower()
    if audit_type not in AUDIT_TYPE_LABELS:
        return "Invalid audit group.", 400
    if role == "auditor" and not auditor:
        connection.close()
        return "Auditor accounts must be linked to auditor initials.", 400
    if password: connection.execute("UPDATE accounts SET password_hash=? WHERE username=?", (password_hash(password), username))
    connection.execute("UPDATE accounts SET role=?, auditor=?, audit_type=? WHERE username=?", (role, auditor, audit_type, username))
    if role == "auditor" and auditor:
        connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, '', ?) ON CONFLICT(initials) DO UPDATE SET audit_type=excluded.audit_type", (auditor, audit_type))
    connection.commit(); connection.close()
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


if __name__ == "__main__":
    init_db()
    host = os.environ.get("PRODUCTIVITY_HOST", "0.0.0.0")
    port = int(os.environ.get("PRODUCTIVITY_PORT", "5000"))
    debug = os.environ.get("PRODUCTIVITY_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)