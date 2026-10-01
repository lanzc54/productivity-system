import os
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
TEST_DATA_DIR = LOCAL_DATA_ROOT / "ProductivitySystemTesting"
TEST_DB_PATH = TEST_DATA_DIR / "productivity-september-2026.db"
START_DATE = date(2026, 9, 1)
END_DATE = date(2026, 9, 30)
TEST_IDENTITIES = ("LANZ", "TINA", "TESS")
TL_IDENTITIES = ("YETTE", "YNA", "GAB")
ALL_TEST_IDENTITIES = TEST_IDENTITIES + TL_IDENTITIES
RANDOM_SEED = 20260901

if os.environ.get("DATABASE_URL"):
    raise SystemExit("Refusing to seed while DATABASE_URL is set. Unset it before using this local-only seed.")

if TEST_DB_PATH.resolve() == (ROOT / "productivity.db").resolve():
    raise SystemExit("Refusing to use the application's default database path.")

TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["PRODUCTIVITY_DB"] = str(TEST_DB_PATH)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, db, password_hash, password_matches, MD_PER_SLOT


TEST_ACCOUNTS = (
    ("yette", "TL1", "TL", "YETTE", "it"),
    ("lanz", "test1", "auditor", "LANZ", "it"),
    ("yna", "TL2", "TL", "YNA", "business"),
    ("tina", "test2", "auditor", "TINA", "business"),
    ("Gab", "TL3", "TL", "GAB", "branch"),
    ("tess", "test3", "auditor", "TESS", "branch"),
)
TL_ENGAGEMENTS = {
    "YETTE": "ITTL-NAPP-0000",
    "YNA": "BPTL-NAPP-0000",
    "GAB": "BRTL-NAPP-0000",
}
TL_SHARED_CODE_SAMPLE = (
    "YETTE",
    "ITRA-NAPP-0000",
    (date(2026, 9, 1), date(2026, 9, 2)),
)
ENGAGEMENTS = {
    "ITRA-NAPP-0000": ("LANZ", 20.0),
    "BPRA-NAPP-M024": ("TINA", 30.0),
}
EXPECTED_ENGAGEMENT_MD = {
    "ITRA-NAPP-0000": 20.0,
    "BPRA-NAPP-M024": 20.75,
}
BRANCH_ENGAGEMENTS = (
    ("BRCC-NAPP-0000", "2026-09-01", "2026-09-01"),
    ("BRRF-NAPP-0000", "2026-09-02", "2026-09-02"),
    ("BRFA-NAPP-0000", "2026-09-03", "2026-09-03"),
    ("BRVA-NAPP-0000", "2026-09-04", "2026-09-04"),
)
NON_ENGAGEMENT_EXCLUSIONS = ("RDAY-NAPP-0000", "LBRK-NAPP-0000")
DAY_SLOTS = [f"{hour}-{hour + 1}" for hour in range(8, 12)] + [f"{hour}-{hour + 1}" for hour in range(13, 17)]


def weekdays_between(start, end):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def week_groups(days):
    groups = defaultdict(list)
    for work_day in days:
        monday = work_day - timedelta(days=work_day.weekday())
        groups[monday].append(work_day)
    return groups


def insert_entry(connection, initials, work_day, slot, code):
    connection.execute(
        "INSERT INTO entries(auditor, work_date, slot, code) VALUES (?, ?, ?, ?)",
        (initials, work_day.isoformat(), slot, code),
    )


def add_month_entries(connection, initials, engagement_code, target_md, non_engagement_per_week, randomizer, non_engagement_codes, extra_engagement_by_day=None):
    work_days = list(weekdays_between(START_DATE, END_DATE))
    target_slots = round(target_md / MD_PER_SLOT)
    extra_engagement_by_day = extra_engagement_by_day or {}
    weekly_non_engagement = {}
    reserved_non_engagement = defaultdict(list)
    if len(non_engagement_codes) < non_engagement_per_week:
        raise RuntimeError("Not enough distinct existing non-engagement codes for the weekly requirement.")

    for week_monday, week_days in week_groups(work_days).items():
        weekly_non_engagement[week_monday] = randomizer.sample(non_engagement_codes, non_engagement_per_week)
        minimum_non_engagement = non_engagement_per_week
        weekly_slots = len(week_days) * len(DAY_SLOTS)
        if weekly_slots < minimum_non_engagement:
            raise RuntimeError(f"The weekly non-engagement requirement cannot fit during the week of {week_monday}.")
        for code in weekly_non_engagement[week_monday]:
            work_day = randomizer.choice(week_days)
            free_slots = [slot for slot in DAY_SLOTS if all(existing_slot != slot for existing_slot, _ in reserved_non_engagement[work_day])]
            slot = randomizer.choice(free_slots)
            reserved_non_engagement[work_day].append((slot, code))

    extra_slots_total = sum(extra_engagement_by_day.values())
    maximum_engagement_slots = (
        len(work_days) * len(DAY_SLOTS)
        - sum(non_engagement_per_week for _ in week_groups(work_days))
        - extra_slots_total
    )
    engagement_slots = min(target_slots, maximum_engagement_slots)
    if engagement_slots > len(work_days) * len(DAY_SLOTS):
        raise RuntimeError("Requested engagement use exceeds the eight-hour-per-day limit.")

    capacity_by_day = {}
    for work_day in work_days:
        assigned_non_engagement = reserved_non_engagement[work_day]
        extra_slots = extra_engagement_by_day.get(work_day, 0)
        if extra_slots + len(assigned_non_engagement) > len(DAY_SLOTS):
            raise RuntimeError(f"The requested entries exceed eight hours on {work_day.isoformat()}.")
        capacity_by_day[work_day] = len(DAY_SLOTS) - len(assigned_non_engagement) - extra_slots

    remaining_engagement_slots = engagement_slots
    for work_day in work_days:
        assigned_non_engagement = reserved_non_engagement[work_day]
        days_remaining = sum(1 for candidate in work_days if candidate >= work_day)
        target_for_day = (remaining_engagement_slots + days_remaining - 1) // days_remaining
        day_engagement_slots = min(capacity_by_day[work_day], target_for_day, remaining_engagement_slots)
        remaining_engagement_slots -= day_engagement_slots
        open_slots = [slot for slot in DAY_SLOTS if all(existing_slot != slot for existing_slot, _ in assigned_non_engagement)]
        extra_slots = extra_engagement_by_day.get(work_day, 0)
        for extra_index in range(extra_slots):
            insert_entry(connection, initials, work_day, open_slots[extra_index], "ITTL-NAPP-0000")
        for slot in open_slots[extra_slots:extra_slots + day_engagement_slots]:
            insert_entry(connection, initials, work_day, slot, engagement_code)
        week_monday = work_day - timedelta(days=work_day.weekday())
        filler_code = weekly_non_engagement[week_monday][0]
        used_slots = {slot for slot, _ in assigned_non_engagement} | set(open_slots[:extra_slots + day_engagement_slots])
        for slot in DAY_SLOTS:
            if slot not in used_slots:
                assigned_non_engagement.append((slot, filler_code))
        for slot, code in assigned_non_engagement:
            insert_entry(connection, initials, work_day, slot, code)
    if remaining_engagement_slots:
        raise RuntimeError("Unable to place the requested engagement slots within daily capacity.")


def add_tl_entries(connection, initials, engagement_code, randomizer, non_engagement_codes):
    work_days = list(weekdays_between(date(2026, 9, 3), date(2026, 9, 10)))
    weekly_codes = {
        monday: randomizer.choice(non_engagement_codes)
        for monday in week_groups(work_days)
    }
    for work_day in work_days:
        insert_entry(connection, initials, work_day, DAY_SLOTS[0], engagement_code)
        filler_code = weekly_codes[work_day - timedelta(days=work_day.weekday())]
        for slot in DAY_SLOTS[1:]:
            insert_entry(connection, initials, work_day, slot, filler_code)


def validate_login(username, password):
    client = app.test_client()
    csrf_token = f"local-seed-{username}"
    with client.session_transaction() as session:
        session["csrf_token"] = csrf_token
    response = client.post("/login", data={"username": username, "password": password, "csrf_token": csrf_token})
    if response.status_code != 302:
        raise AssertionError(f"Local authentication failed for {username}.")


def main():
    randomizer = random.Random(RANDOM_SEED)
    connection = db()
    try:
        initials_placeholders = ",".join("?" for _ in ALL_TEST_IDENTITIES)
        connection.execute(f"DELETE FROM entries WHERE auditor IN ({initials_placeholders})", ALL_TEST_IDENTITIES)
        auditor_placeholders = ",".join("?" for _ in TEST_IDENTITIES)
        connection.execute(f"DELETE FROM engagement_assignments WHERE auditor IN ({auditor_placeholders})", TEST_IDENTITIES)
        connection.execute("DELETE FROM branch_engagement_assignments WHERE auditor=?", ("TESS",))
        connection.execute("DELETE FROM weekly_engagement_assignments WHERE auditor=?", ("TESS",))

        for username, password, role, initials, audit_type in TEST_ACCOUNTS:
            connection.execute(
                "INSERT INTO accounts(username, password_hash, role, auditor, audit_type) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, role=excluded.role, auditor=excluded.auditor, audit_type=excluded.audit_type",
                (username, password_hash(password), role, initials, audit_type),
            )
            if role in {"auditor", "TL"} and initials:
                connection.execute(
                    "INSERT INTO auditors(initials, name, audit_type) VALUES (?, ?, ?) "
                    "ON CONFLICT(initials) DO UPDATE SET name=excluded.name, audit_type=excluded.audit_type",
                    (initials, username, audit_type),
                )

        for code, (initials, budget_md) in ENGAGEMENTS.items():
            code_row = connection.execute(
                "SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=2026", (code,)
            ).fetchone()
            if not code_row:
                raise RuntimeError(f"Required existing engagement {code} is missing for 2026; no substitute was created.")
            connection.execute(
                "UPDATE codes SET annual_budget=?, auditor_budget=? WHERE code=? AND kind='engagement' AND year=2026",
                (budget_md, budget_md, code),
            )
            connection.execute(
                "INSERT INTO engagement_assignments(code, year, auditor, budget_md) VALUES (?, 2026, ?, ?) "
                "ON CONFLICT(code, year, auditor) DO UPDATE SET budget_md=excluded.budget_md",
                (code, initials, budget_md),
            )

        for code, start_date, end_date in BRANCH_ENGAGEMENTS:
            code_row = connection.execute(
                "SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=2026", (code,)
            ).fetchone()
            if not code_row:
                raise RuntimeError(f"Required existing branch engagement {code} is missing for 2026.")
            connection.execute(
                "INSERT INTO branch_engagement_assignments(start_date, end_date, auditor, code) VALUES (?, ?, 'TESS', ?) "
                "ON CONFLICT(start_date, end_date, auditor) DO UPDATE SET code=excluded.code",
                (start_date, end_date, code),
            )

        non_engagement_codes = [
            row["code"]
            for row in connection.execute(
                "SELECT code FROM codes WHERE kind='admin' AND code NOT IN (?, ?) ORDER BY code",
                NON_ENGAGEMENT_EXCLUSIONS,
            ).fetchall()
        ]
        if not non_engagement_codes:
            raise RuntimeError("No existing eligible non-engagement codes are available.")

        it_tl_code = connection.execute(
            "SELECT 1 FROM codes WHERE code='ITTL-NAPP-0000' AND kind='engagement' AND year=2026"
        ).fetchone()
        if not it_tl_code:
            raise RuntimeError("Required IT TL engagement ITTL-NAPP-0000 is missing from the 2026 catalog.")
        add_month_entries(connection, "LANZ", "ITRA-NAPP-0000", 20.0, 1, randomizer, non_engagement_codes)
        add_month_entries(connection, "TINA", "BPRA-NAPP-M024", 30.0, 2, randomizer, non_engagement_codes)
        for initials, tl_engagement_code in TL_ENGAGEMENTS.items():
            code_row = connection.execute(
                "SELECT 1 FROM codes WHERE code=? AND kind='engagement' AND year=2026",
                (tl_engagement_code,),
            ).fetchone()
            if not code_row:
                raise RuntimeError(f"Required TL engagement {tl_engagement_code} is missing from the 2026 catalog.")
            add_tl_entries(connection, initials, tl_engagement_code, randomizer, non_engagement_codes)
        sample_initials, sample_code, sample_days = TL_SHARED_CODE_SAMPLE
        for work_day in sample_days:
            for slot in DAY_SLOTS:
                insert_entry(connection, sample_initials, work_day, slot, sample_code)

        for code, work_day, _ in BRANCH_ENGAGEMENTS:
            work_date = date.fromisoformat(work_day)
            for slot in DAY_SLOTS:
                insert_entry(connection, "TESS", work_date, slot, code)
        branch_non_engagement_code = randomizer.choice(non_engagement_codes)
        for work_day in weekdays_between(START_DATE, END_DATE):
            if work_day not in {date.fromisoformat(row[1]) for row in BRANCH_ENGAGEMENTS}:
                for slot in DAY_SLOTS:
                    insert_entry(connection, "TESS", work_day, slot, branch_non_engagement_code)
        connection.commit()

        for username, password, *_ in TEST_ACCOUNTS:
            account = connection.execute("SELECT password_hash FROM accounts WHERE username=?", (username,)).fetchone()
            if not account or not password_matches(account["password_hash"], password):
                raise AssertionError(f"Stored password hash validation failed for {username}.")
            validate_login(username, password)

        if not connection.execute("SELECT 1 FROM accounts WHERE username='admin' AND role='admin'").fetchone():
            raise AssertionError("The local admin account was not preserved.")
        for username, _, expected_role, expected_initials, expected_group in TEST_ACCOUNTS:
            row = connection.execute(
                "SELECT role, auditor, audit_type FROM accounts WHERE username=?", (username,)
            ).fetchone()
            if not row or (row["role"], row["auditor"], row["audit_type"]) != (expected_role, expected_initials, expected_group):
                raise AssertionError(f"The stored role/group/initials are wrong for {username}.")

        for code, (initials, budget_md) in ENGAGEMENTS.items():
            account = connection.execute("SELECT auditor FROM accounts WHERE username=?", (("lanz" if initials == "LANZ" else "tina"),)).fetchone()
            if not account or account["auditor"] != initials:
                raise AssertionError(f"Engagement {code} is linked to the wrong test account.")
            assignment = connection.execute(
                "SELECT 1 FROM engagement_assignments WHERE code=? AND year=2026 AND auditor=?",
                (code, initials),
            ).fetchone()
            code_budget = connection.execute(
                "SELECT annual_budget, auditor_budget FROM codes WHERE code=? AND kind='engagement' AND year=2026",
                (code,),
            ).fetchone()
            if not assignment or (code_budget["annual_budget"], code_budget["auditor_budget"]) != (budget_md, budget_md):
                raise AssertionError(f"Assignment or budget is incorrect for {code}.")
            actual = connection.execute(
                "SELECT COUNT(*) * ? FROM entries WHERE auditor=? AND code=? AND work_date BETWEEN ? AND ?",
                (MD_PER_SLOT, initials, code, START_DATE.isoformat(), END_DATE.isoformat()),
            ).fetchone()[0]
            expected_actual = EXPECTED_ENGAGEMENT_MD[code]
            if round(actual, 3) != expected_actual or actual > budget_md:
                raise AssertionError(f"{code} actual is {actual} MD, expected {expected_actual} MD without exceeding its {budget_md} MD budget.")

        branch_rows = connection.execute(
            "SELECT code, auditor FROM branch_engagement_assignments WHERE auditor='TESS' AND start_date BETWEEN ? AND ? ORDER BY code",
            (START_DATE.isoformat(), END_DATE.isoformat()),
        ).fetchall()
        if {row["code"] for row in branch_rows} != {row[0] for row in BRANCH_ENGAGEMENTS}:
            raise AssertionError("Branch assignments do not match the requested four engagements.")
        branch_budgets = connection.execute(
            "SELECT annual_budget, auditor_budget FROM codes WHERE code IN (?, ?, ?, ?) AND kind='engagement' AND year=2026",
            tuple(row[0] for row in BRANCH_ENGAGEMENTS),
        ).fetchall()
        if len(branch_budgets) != 4 or any(row["annual_budget"] is not None or row["auditor_budget"] is not None for row in branch_budgets):
            raise AssertionError("Branch engagement budget values must remain unset.")

        identity_placeholders = ",".join("?" for _ in ALL_TEST_IDENTITIES)
        valid_entry_codes = connection.execute(
            f"SELECT COUNT(*) FROM entries e LEFT JOIN codes c ON c.code=e.code AND c.year=2026 WHERE e.auditor IN ({identity_placeholders}) AND e.work_date BETWEEN ? AND ? AND c.code IS NULL",
            (*ALL_TEST_IDENTITIES, START_DATE.isoformat(), END_DATE.isoformat()),
        ).fetchone()[0]
        if valid_entry_codes:
            raise AssertionError("A timekeeping row references a code missing from the 2026 catalog.")

        expected_engagement_codes = {
            "LANZ": {"ITRA-NAPP-0000"},
            "TINA": {"BPRA-NAPP-M024"},
            "TESS": {row[0] for row in BRANCH_ENGAGEMENTS},
            **{initials: {code} for initials, code in TL_ENGAGEMENTS.items()},
        }
        expected_engagement_codes[sample_initials].add(sample_code)
        for initials, expected_codes in expected_engagement_codes.items():
            used_codes = {
                row["code"]
                for row in connection.execute(
                    "SELECT DISTINCT e.code FROM entries e JOIN codes c ON c.code=e.code AND c.year=2026 "
                    "WHERE e.auditor=? AND e.work_date BETWEEN ? AND ? AND c.kind IN ('engagement', 'overtime')",
                    (initials, START_DATE.isoformat(), END_DATE.isoformat()),
                ).fetchall()
            }
            if used_codes != expected_codes:
                raise AssertionError(f"Unexpected engagement codes found for {initials}: {sorted(used_codes)}")

        for work_day in sample_days:
            sample_slots = connection.execute(
                "SELECT COUNT(*) FROM entries WHERE auditor=? AND work_date=? AND code=?",
                (sample_initials, work_day.isoformat(), sample_code),
            ).fetchone()[0]
            daily_slots = connection.execute(
                "SELECT COUNT(*) FROM entries WHERE auditor=? AND work_date=?",
                (sample_initials, work_day.isoformat()),
            ).fetchone()[0]
            if sample_slots != len(DAY_SLOTS) or daily_slots != len(DAY_SLOTS):
                raise AssertionError(f"{sample_initials} must have eight {sample_code} slots and exactly eight total work slots on {work_day}.")

        expected_tl_dates = {day.isoformat() for day in weekdays_between(date(2026, 9, 3), date(2026, 9, 10))}
        for initials, tl_code in TL_ENGAGEMENTS.items():
            tl_entries = connection.execute(
                "SELECT work_date, COUNT(*) AS slots FROM entries WHERE auditor=? AND code=? AND work_date BETWEEN '2026-09-03' AND '2026-09-10' GROUP BY work_date",
                (initials, tl_code),
            ).fetchall()
            if {row["work_date"] for row in tl_entries} != expected_tl_dates or any(row["slots"] != 1 for row in tl_entries):
                raise AssertionError(f"{initials} must have exactly one {tl_code} slot per weekday from Sep 3 through Sep 10.")

        report_totals = {}
        for initials in ALL_TEST_IDENTITIES:
            row = connection.execute(
                "SELECT COUNT(*) * ? FROM entries WHERE auditor=? AND work_date BETWEEN ? AND ? AND code NOT IN (?, ?)",
                (MD_PER_SLOT, initials, START_DATE.isoformat(), END_DATE.isoformat(), *NON_ENGAGEMENT_EXCLUSIONS),
            ).fetchone()
            report_totals[initials] = round(row[0], 3)

        report_checks = (
            ("yette", "it", {"LANZ", "YETTE"}, {"ITRA-NAPP-0000", "ITTL-NAPP-0000"}, {"20.000", "22.000", "2.000", "0.750"}),
            ("yna", "business", {"TINA", "YNA"}, {"BPRA-NAPP-M024", "BPTL-NAPP-0000"}, {"20.750", "0.750"}),
            ("Gab", "branch", {"TESS", "GAB"}, {"BRCC-NAPP-0000", "BRTL-NAPP-0000"}, {"1.000", "0.750"}),
        )
        for username, audit_type, expected_visible_auditors, expected_codes, expected_values in report_checks:
            client = app.test_client()
            with client.session_transaction() as session:
                username_row = connection.execute("SELECT role, auditor FROM accounts WHERE username=?", (username,)).fetchone()
                session.update(username=username, role=username_row["role"], auditor=username_row["auditor"], csrf_token="local-report-check")
            response = client.get(
                "/?tab=report&auditor={}&audit_type={}&start={}&end={}".format(
                    "", "all", START_DATE.isoformat(), END_DATE.isoformat()
                )
            )
            report_html = response.get_data(as_text=True)
            if response.status_code != 200 or any(code not in report_html for code in expected_codes) or any(value not in report_html for value in expected_values) or "Engagement MD" not in report_html or "Non-engagement MD" not in report_html or "Side-by-side engagement" not in report_html or "fill='#087f71'" not in report_html or "fill='#e56d50'" not in report_html:
                raise AssertionError(f"Group-scoped report did not show expected totals for {username}.")
            if "All groups" in report_html or any(other_initial not in report_html for other_initial in expected_visible_auditors):
                raise AssertionError(f"The report scope is incorrect for {username}.")
            other_names = set(ALL_TEST_IDENTITIES) - expected_visible_auditors
            if any(other_name in report_html for other_name in other_names):
                raise AssertionError(f"{username} can see another audit group's report.")

        auditor_client = app.test_client()
        with auditor_client.session_transaction() as session:
            session.update(username="lanz", role="auditor", auditor="LANZ", csrf_token="local-auditor-report")
        auditor_report = auditor_client.get(
            f"/?tab=report&auditor=TINA&audit_type=branch&start={START_DATE.isoformat()}&end={END_DATE.isoformat()}"
        ).get_data(as_text=True)
        if "LANZ" not in auditor_report or any(name in auditor_report for name in ("TINA", "TESS", "YETTE", "YNA", "GAB")) or "All groups" in auditor_report:
            raise AssertionError("An auditor can see another auditor's report or another audit group.")
        if branch_non_engagement_code not in report_html:
            raise AssertionError("Branch report does not show its non-engagement usage breakdown.")

        tl_entry_client = app.test_client()
        with tl_entry_client.session_transaction() as session:
            session.update(username="yette", role="TL", auditor="YETTE", csrf_token="local-entry-week-check")
        tl_entry_html = tl_entry_client.get("/?tab=entry&week=2026-09-08").get_data(as_text=True)
        if "name='week'" not in tl_entry_html or "2026-09-08" not in tl_entry_html or "ITTL-NAPP-0000" not in tl_entry_html:
            raise AssertionError("The IT TL cannot view their own second September week and ITTL entries.")

        auditor_entry_client = app.test_client()
        with auditor_entry_client.session_transaction() as session:
            session.update(username="lanz", role="auditor", auditor="LANZ", csrf_token="local-auditor-week-check")
        auditor_entry_html = auditor_entry_client.get("/?tab=entry&week=2026-09-08").get_data(as_text=True)
        if "2026-09-08" not in auditor_entry_html or "ITRA-NAPP-0000" not in auditor_entry_html:
            raise AssertionError("The IT auditor cannot view their second September week.")
        if "<select name='auditor'" in auditor_entry_html:
            raise AssertionError("The auditor should not be able to select another auditor's time entry.")

        for initials in ALL_TEST_IDENTITIES:
            outside = connection.execute(
                "SELECT COUNT(*) FROM entries WHERE auditor=? AND (work_date<? OR work_date>?)",
                (initials, START_DATE.isoformat(), END_DATE.isoformat()),
            ).fetchone()[0]
            if outside:
                raise AssertionError(f"Found {outside} out-of-September entries for {initials}.")

        valid_non_engagement = set(non_engagement_codes)
        for initials, expected_count, per_week in (("LANZ", 16, 1), ("TINA", 10, 2), ("TESS", 144, None)):
            rows = connection.execute(
                "SELECT code, COUNT(*) AS total FROM entries WHERE auditor=? AND work_date BETWEEN ? AND ? AND code IN ({}) GROUP BY code".format(
                    ",".join("?" for _ in valid_non_engagement)
                ),
                (initials, START_DATE.isoformat(), END_DATE.isoformat(), *sorted(valid_non_engagement)),
            ).fetchall()
            if sum(row["total"] for row in rows) != expected_count:
                raise AssertionError(f"{initials} has the wrong number of non-engagement hourly slots.")
            if per_week:
                week_totals = connection.execute(
                    "SELECT substr(work_date, 1, 10) AS work_date, code FROM entries WHERE auditor=? AND work_date BETWEEN ? AND ? AND code IN ({})".format(
                        ",".join("?" for _ in valid_non_engagement)
                    ),
                    (initials, START_DATE.isoformat(), END_DATE.isoformat(), *sorted(valid_non_engagement)),
                ).fetchall()
                counts_by_week = defaultdict(int)
                for entry in week_totals:
                    entry_date = date.fromisoformat(entry["work_date"])
                    counts_by_week[entry_date - timedelta(days=entry_date.weekday())] += 1
                if len(counts_by_week) != 5 or any(count < per_week for count in counts_by_week.values()):
                    raise AssertionError(f"{initials} does not have the requested non-engagement tags in every September week.")
                unique_codes_by_week = defaultdict(set)
                for entry in week_totals:
                    entry_date = date.fromisoformat(entry["work_date"])
                    unique_codes_by_week[entry_date - timedelta(days=entry_date.weekday())].add(entry["code"])
                if any(len(codes) != per_week for codes in unique_codes_by_week.values()):
                    raise AssertionError(f"{initials} does not use the requested number of random non-engagement codes per week.")

        weekdays = list(weekdays_between(START_DATE, END_DATE))
        tl_weekdays = list(weekdays_between(date(2026, 9, 3), date(2026, 9, 10)))
        for initials in TEST_IDENTITIES:
            for work_day in weekdays:
                entry_count = connection.execute(
                    "SELECT COUNT(*) FROM entries WHERE auditor=? AND work_date=? AND code NOT IN (?, ?)",
                    (initials, work_day.isoformat(), *NON_ENGAGEMENT_EXCLUSIONS),
                ).fetchone()[0]
                if entry_count != 8:
                    raise AssertionError(f"{initials} has {entry_count} work slots on {work_day}; expected exactly eight, excluding auto-filled lunch/restday.")
        for initials in TL_IDENTITIES:
            for work_day in tl_weekdays:
                entry_count = connection.execute(
                    "SELECT COUNT(*) FROM entries WHERE auditor=? AND work_date=? AND code NOT IN (?, ?)",
                    (initials, work_day.isoformat(), *NON_ENGAGEMENT_EXCLUSIONS),
                ).fetchone()[0]
                if entry_count != 8:
                    raise AssertionError(f"{initials} has {entry_count} work slots on {work_day}; expected eight during the TL sample range, excluding auto-filled lunch/restday.")

        print(f"Local test database: {TEST_DB_PATH}")
        print("Seeded accounts: yette, lanz, yna, tina, Gab, tess; existing local admin preserved.")
        print("TL engagement MD: YETTE 2.000 ITRA on Sep 1-2 plus 0.750 ITTL; YNA 0.750 BPTL; GAB 0.750 BRTL. TL entries use separate initials and stay within eight hours per day.")
        print("Auditor engagement MD: LANZ 20.000 ITRA / 20.000 budget; TINA 20.750 / 30.000 (8-hour daily cap); TESS 4.000 across four branch codes.")
        print("Group-scoped reports validated with auditor and TL identities; auditor report validated as self-only. Charts show both usage categories separately.")
        print("LOCAL_TEST_SEED_OK")
    finally:
        connection.close()


if __name__ == "__main__":
    main()