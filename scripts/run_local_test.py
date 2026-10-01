import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
TEST_DB_PATH = LOCAL_DATA_ROOT / "ProductivitySystemTesting" / "productivity-september-2026.db"
START_DATE = "2026-09-01"
END_DATE = "2026-09-30"
TEST_IDENTITIES = ("LANZ", "TINA", "TESS", "YETTE", "YNA", "GAB")

if os.environ.get("DATABASE_URL"):
    raise SystemExit("Refusing to start the local test app while DATABASE_URL is set.")
if not TEST_DB_PATH.is_file():
    raise SystemExit("Local test database not found. Run: py scripts/seed_local_test_data.py")

os.environ["PRODUCTIVITY_DB"] = str(TEST_DB_PATH)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, db


connection = db()
try:
    placeholders = ",".join("?" for _ in TEST_IDENTITIES)
    connection.execute(
        f"DELETE FROM entries WHERE auditor IN ({placeholders}) AND (work_date<? OR work_date>?)",
        (*TEST_IDENTITIES, START_DATE, END_DATE),
    )
    connection.commit()
finally:
    connection.close()

print(f"Local test environment: {TEST_DB_PATH}")
print("Open http://127.0.0.1:5001")
app.run(host="127.0.0.1", port=5001, debug=False)