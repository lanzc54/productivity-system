import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, db
import time

client = app.test_client()
headers = {"User-Agent": "smoke-test-agent"}
with client.session_transaction() as sess:
    now = int(time.time())
    sess["username"] = "admin"
    sess["role"] = "admin"
    sess["auditor"] = ""
    sess["csrf_token"] = "abc123"
    sess["sid"] = "smoke-session"
    sess["ua"] = "smoke-test-agent"
    sess["ip"] = "127.0.0.1"
    sess["created_at"] = now
    sess["last_active"] = now

    response = client.get("/?tab=engagements", headers=headers)
    html = response.get_data(as_text=True)
    assert response.status_code == 200, response.status_code
    assert "csrf_token" in html, "CSRF field missing from engagement page"

    code = "ITPP-NAPP-H999"
    overtime_code = "ITPP-OTHD-H999"

    engagement_post = client.post(
        "/codes",
        data={
            "kind": "engagement",
            "main_code": "ITPP",
            "sub_code": "NAPP",
            "series_code": "H999",
            "description": "Smoke engagement",
            "year": "2026",
            "annual_budget": "100",
            "auditor_budget": "10",
            "csrf_token": "abc123",
        },
        follow_redirects=False,
        headers=headers,
    )
    assert engagement_post.status_code in (200, 302), engagement_post.status_code

    overtime_post = client.post(
        "/codes",
        data={
            "kind": "overtime",
            "main_code": "ITPP",
            "sub_code": "OTHD",
            "series_code": "H999",
            "description": "Smoke overtime",
            "year": "2026",
            "csrf_token": "abc123",
        },
        follow_redirects=False,
        headers=headers,
    )
    assert overtime_post.status_code in (200, 302), overtime_post.status_code

    assignment_post = client.post(
        "/assignments",
        data={
            "code": code,
            "year": "2026",
            "auditor": "CLL",
            "csrf_token": "abc123",
        },
        follow_redirects=False,
        headers=headers,
    )
    assert assignment_post.status_code in (200, 302), assignment_post.status_code

    conn = db()
    try:
        engagement_row = conn.execute("SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=?", (code, 2026)).fetchone()
        overtime_row = conn.execute("SELECT 1 FROM codes WHERE code=? AND kind='overtime' AND year=?", (overtime_code, 2026)).fetchone()
        assignment_row = conn.execute("SELECT 1 FROM engagement_assignments WHERE code=? AND year=? AND auditor=?", (code, 2026, "CLL")).fetchone()
    finally:
        conn.close()

    assert engagement_row is not None, "Engagement code was not persisted"
    assert overtime_row is not None, "Overtime code was not persisted"
    assert assignment_row is not None, "Assignment was not persisted"

print("SMOKE_TEST_OK")
