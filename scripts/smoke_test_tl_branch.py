import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

DB_FILE = Path(tempfile.gettempdir()) / "productivity_tl_branch_smoke.db"
DB_FILE.unlink(missing_ok=True)
os.environ["PRODUCTIVITY_DB"] = str(DB_FILE)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, db, init_db, password_hash, week_start


init_db()
connection = db()
connection.execute("DELETE FROM accounts WHERE username='tl-created'")
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("tl-smoke", password_hash("test"), "TL", "", "branch"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("tl-it-smoke", password_hash("test"), "TL", "", "it"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("tl-business-smoke", password_hash("test"), "TL", "", "business"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("branch-smoke", password_hash("test"), "auditor", "B01", "branch"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("legacy-branch-smoke", password_hash("test"), "auditor", "B02", "branch"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("it-smoke", password_hash("test"), "auditor", "I01", "it"))
connection.execute("INSERT OR REPLACE INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?)", ("business-smoke", password_hash("test"), "auditor", "P01", "business"))
connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, ?) ON CONFLICT(initials) DO UPDATE SET name=excluded.name, audit_type=excluded.audit_type", ("B01", "Branch Smoke", "branch"))
connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, ?) ON CONFLICT(initials) DO UPDATE SET name=excluded.name, audit_type=excluded.audit_type", ("B02", "Legacy Branch Smoke", "branch"))
connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, ?) ON CONFLICT(initials) DO UPDATE SET name=excluded.name, audit_type=excluded.audit_type", ("I01", "IT Smoke", "it"))
connection.execute("INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, ?) ON CONFLICT(initials) DO UPDATE SET name=excluded.name, audit_type=excluded.audit_type", ("P01", "Business Smoke", "business"))
branch_codes = connection.execute("SELECT code, description, year FROM codes WHERE kind='engagement' AND code LIKE 'BR%' ORDER BY code").fetchall()
assert branch_codes, "No branch engagement codes were initialized"
branch_code = branch_codes[0]
other_branch_code = branch_codes[1]["code"] if len(branch_codes) > 1 else "BR_UNASSIGNED"
it_code = connection.execute("SELECT code, year FROM codes WHERE kind='engagement' AND code LIKE 'IT%' ORDER BY code LIMIT 1").fetchone()
assert it_code, "No IT engagement code was initialized"
connection.commit()
connection.close()

client = app.test_client()
csrf = "tl-branch-smoke-token"


def set_session(role, username, auditor=""):
    with client.session_transaction() as session:
        session.clear()
        session.update(username=username, role=role, auditor=auditor, csrf_token=csrf)


def post_as(role, username, auditor, path, data):
    set_session(role, username, auditor)
    return client.post(path, data={**data, "csrf_token": csrf})


set_session("TL", "tl-smoke")
accounts_page = client.get("/?tab=accounts")
assert accounts_page.status_code == 200
assert b"Team Leader (TL)" in accounts_page.data
assert b"/accounts/admin/delete" not in accounts_page.data
assert client.post("/accounts/admin/delete", data={"csrf_token": csrf}).status_code == 403

add_tl = post_as("TL", "tl-smoke", "", "/accounts", {"username": "tl-created", "password": "test", "role": "TL", "audit_type": "branch"})
assert add_tl.status_code == 302, add_tl.status_code

post_code = post_as("TL", "tl-smoke", "", "/codes", {
    "kind": "engagement",
    "code": branch_code["code"],
    "description": branch_code["description"],
    "year": str(branch_code["year"]),
    "annual_budget": "90",
    "auditor_budget": "9",
})
assert post_code.status_code == 302, post_code.status_code
connection = db()
budgets = connection.execute("SELECT annual_budget, auditor_budget FROM codes WHERE code=? AND kind='engagement' AND year=?", (branch_code["code"], branch_code["year"])).fetchone()
assert budgets["annual_budget"] is None and budgets["auditor_budget"] is None, "Branch budgets must be unset"
connection.close()

monday = week_start(date.today().isoformat())
range_start = monday + timedelta(days=2)
range_end = monday + timedelta(days=11)
connection = db()
connection.execute("INSERT INTO weekly_engagement_assignments(week_start, auditor, code) VALUES (?, ?, ?)", (monday.isoformat(), "B02", branch_code["code"]))
connection.commit()
connection.close()
init_db()
connection = db()
migrated = connection.execute("SELECT start_date, end_date FROM branch_engagement_assignments WHERE auditor=? AND code=?", ("B02", branch_code["code"])).fetchone()
assert migrated and migrated["start_date"] == monday.isoformat() and migrated["end_date"] == (monday + timedelta(days=6)).isoformat(), "Existing weekly assignments should migrate to seven-day ranges"
connection.close()
assignment = post_as("TL", "tl-smoke", "", "/assignments", {
    "code": branch_code["code"],
    "start_date": range_start.isoformat(),
    "end_date": range_end.isoformat(),
    "auditor": "B01",
})
assert assignment.status_code == 302, assignment.get_data(as_text=True)
set_session("TL", "tl-smoke")
branch_manager_page = client.get("/?tab=engagements")
assert b"name='start_date'" in branch_manager_page.data and b"name='end_date'" in branch_manager_page.data
assert b"name='start_week'" not in branch_manager_page.data and b"name='end_week'" not in branch_manager_page.data
assert b"IT annual assignments" not in branch_manager_page.data and b"Business Process annual assignments" not in branch_manager_page.data
wrong_group = post_as("TL", "tl-smoke", "", "/assignments", {
    "code": it_code["code"],
    "year": str(it_code["year"]),
    "auditor": "I01",
})
assert wrong_group.status_code == 403, wrong_group.status_code
overlap = post_as("TL", "tl-smoke", "", "/assignments", {
    "code": branch_code["code"],
    "start_date": (range_start + timedelta(days=2)).isoformat(),
    "end_date": (range_end + timedelta(days=2)).isoformat(),
    "auditor": "B01",
})
assert overlap.status_code == 409, overlap.status_code
legacy_assignment = post_as("TL", "tl-it-smoke", "", "/assignments", {
    "code": it_code["code"],
    "year": str(it_code["year"]),
    "auditor": "I01",
})
assert legacy_assignment.status_code == 302
set_session("TL", "tl-it-smoke")
it_manager_page = client.get("/?tab=engagements")
assert b"IT annual assignments" in it_manager_page.data
assert b"Business Process annual assignments" not in it_manager_page.data
assert b"name='start_date'" not in it_manager_page.data
set_session("TL", "tl-business-smoke")
business_manager_page = client.get("/?tab=engagements")
assert b"Business Process annual assignments" in business_manager_page.data
assert b"IT annual assignments" not in business_manager_page.data
set_session("admin", "admin")
admin_manager_page = client.get("/?tab=engagements")
assert b"IT annual assignments" in admin_manager_page.data
assert b"Business Process annual assignments" in admin_manager_page.data
assert b"Branch date-range assignments" in admin_manager_page.data

set_session("auditor", "branch-smoke", "B01")
week_page = client.get(f"/?week={monday.isoformat()}")
assert week_page.status_code == 200
assert branch_code["code"].encode() in week_page.data
if len(branch_codes) > 1:
    assert other_branch_code.encode() not in week_page.data, "Unassigned branch code should not be suggested"
middle_week_page = client.get(f"/?week={(monday + timedelta(days=7)).isoformat()}")
assert branch_code["code"].encode() in middle_week_page.data, "The range should grant access in later weeks"

entry_date = range_start
entry = post_as("auditor", "branch-smoke", "B01", "/entry", {
    "auditor": "B01",
    "work_date": entry_date.isoformat(),
    "slot": "6-7",
    "typed_code": branch_code["code"],
})
assert entry.status_code == 302
end_date_entry = post_as("auditor", "branch-smoke", "B01", "/entry", {
    "auditor": "B01",
    "work_date": range_end.isoformat(),
    "slot": "7-8",
    "typed_code": branch_code["code"],
})
assert end_date_entry.status_code == 302
unassigned = post_as("auditor", "branch-smoke", "B01", "/entry", {
    "auditor": "B01",
    "work_date": (range_end + timedelta(days=1)).isoformat(),
    "slot": "6-7",
    "typed_code": branch_code["code"],
})
assert unassigned.status_code == 302
connection = db()
assert connection.execute("SELECT 1 FROM entries WHERE auditor=? AND work_date=? AND slot=? AND code=?", ("B01", entry_date.isoformat(), "6-7", branch_code["code"])).fetchone(), "Assigned branch entry was not saved"
assert connection.execute("SELECT 1 FROM entries WHERE auditor=? AND work_date=? AND slot=? AND code=?", ("B01", range_end.isoformat(), "7-8", branch_code["code"])).fetchone(), "The branch assignment end date must be inclusive"
assert not connection.execute("SELECT 1 FROM entries WHERE auditor=? AND work_date=? AND slot=? AND code=?", ("B01", (range_end + timedelta(days=1)).isoformat(), "6-7", branch_code["code"])).fetchone(), "Entry after the branch assignment end date must be rejected"
connection.close()
legacy_entry = post_as("auditor", "it-smoke", "I01", "/entry", {
    "auditor": "I01",
    "work_date": entry_date.isoformat(),
    "slot": "6-7",
    "typed_code": it_code["code"],
})
assert legacy_entry.status_code == 302
connection = db()
assert connection.execute("SELECT 1 FROM entries WHERE auditor=? AND work_date=? AND slot=? AND code=?", ("I01", entry_date.isoformat(), "6-7", it_code["code"])).fetchone(), "Legacy annual assignment no longer permits non-branch entry"
non_engagement = connection.execute("SELECT code FROM codes WHERE kind='admin' AND code NOT IN (?, ?) LIMIT 1", ("RDAY-NAPP-0000", "LBRK-NAPP-0000")).fetchone()
if non_engagement:
    connection.execute("INSERT OR REPLACE INTO entries(auditor, work_date, slot, code) VALUES (?, ?, ?, ?)", ("B01", entry_date.isoformat(), "7-8", non_engagement["code"]))
connection.commit()
connection.close()

set_session("TL", "tl-smoke")
report = client.get(f"/?tab=report&auditor=B01&start={entry_date.isoformat()}&end={entry_date.isoformat()}")
report_html = report.get_data(as_text=True)
assert report.status_code == 200
assert branch_code["code"].encode() in report.data
if non_engagement:
    assert non_engagement["code"].encode() not in report.data, "Branch report must exclude non-engagement codes"

admin_delete = post_as("admin", "admin", "", "/accounts/tl-created/delete", {})
assert admin_delete.status_code == 302, admin_delete.status_code

print("TL_BRANCH_SMOKE_OK")
