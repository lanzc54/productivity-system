# Local Test Environment

This isolated dataset is for local verification only. It uses the existing Flask app, its SQLite schema, Werkzeug password hashing, engagement codes, assignment tables, time-entry rules, and reports. It does not change `app.py`, Render settings, or the production database.

## Architecture Notes

- The app is Python/Flask. It uses SQLite locally and can use PostgreSQL when `DATABASE_URL` is set.
- `DATABASE_URL` takes precedence over `PRODUCTIVITY_DB`; both local scripts refuse to run when `DATABASE_URL` is present.
- The test database is stored at `%LOCALAPPDATA%\ProductivitySystemTesting\productivity-september-2026.db`, outside the repository.
- Accounts are stored in `accounts`. Auditor accounts use role `auditor`, initials in `auditor`, and `audit_type` of `it`, `business`, or `branch`. Team leaders use the existing `TL` role, the corresponding audit group, and a separate optional initials identity for personal timekeeping.
- Werkzeug hashes passwords before they are stored. The existing admin account in the new local database is preserved; a fresh database gets the application's normal seeded `admin` account.
- Engagement budgets live on the 2026 `codes` rows. Annual assignments use `engagement_assignments`; branch access uses `branch_engagement_assignments`.
- Timekeeping is one row per auditor, date, and hourly slot. Each slot counts as 0.125 MD. The app offers hourly slots from 06:00 through 23:00, pre-fills weekends as restday, and inserts lunch defaults when a week is viewed. There is no enforced daily-hours limit, approval workflow, or holiday calendar.
- Reports are scoped to the signed-in account's audit group. TLs can report across their group's linked auditor and TL identities; auditor accounts are forced to their own initials. There is no `All groups` filter. Reports include valid non-engagement entries while excluding other groups' engagement codes. The chart shows two adjacent bars per identity: engagement MD and non-engagement MD.
- The branch assignment table and route do not allow overlapping assignments for the same auditor. The four requested engagements therefore have consecutive, non-overlapping dates within Sep 1-7: BRCC Sep 1, BRRF Sep 2, BRFA Sep 3, and BRVA Sep 4.
- The existing project has smoke tests but no seed-data mechanism. This guide adds a repeatable local seed.

## Seed and Run

From the project directory in PowerShell, first seed the dedicated database:

```powershell
py scripts/seed_local_test_data.py
```

Then run the local-only server in a separate terminal:

```powershell
py scripts/run_local_test.py
```

Open <http://127.0.0.1:5001>. The runner forces the local test database path in its own process, refuses to run if `DATABASE_URL` is set, and removes automatic out-of-September entries for all six timekeeping identities. It does not change your persistent environment variables. Stop the server with Ctrl+C.

On Time Entry, use **Previous week** and **Next week**, or choose any date in **Week containing** to display that date's week. TLs can select the auditor in the same navigation form; auditor accounts remain limited to their own time entries. September test records can be browsed across the full month.

## Local Login Accounts

| Audit group | Account | Password | App role |
| --- | --- | --- | --- |
| IT TL | `yette` | `TL1` | TL |
| IT auditor | `lanz` | `test1` | auditor |
| Business Process TL | `yna` | `TL2` | TL |
| Business Process auditor | `tina` | `test2` | auditor |
| Branch TL | `Gab` | `TL3` | TL |
| Branch auditor | `tess` | `test3` | auditor |
| Local admin | `admin` | `ChangeMe123!` | admin |

The app links auditor logins to initials `LANZ`, `TINA`, and `TESS`, and TL logins to separate initials `YETTE`, `YNA`, and `GAB`. TL entries are attributed to those TL initials, not to the auditors.

## Seeded Assignments and Expected Totals

- Auditor identities have exactly eight logged hourly slots on every September weekday. TL identities have eight slots per weekday from Sep 3 through Sep 10; YETTE also has eight `ITRA-NAPP-0000` slots on Sep 1 and Sep 2. The app does not enforce this limit on arbitrary manual submissions; the seed dataset follows it.
- `LANZ`: `ITRA-NAPP-0000`, annual budget 20 MD, budgeted MD/auditor 20 MD, assigned for 2026. LANZ records 20.000 MD (160 slots). YETTE also logs 16 slots (2.000 MD) to the same code on Sep 1-2, so combined ITRA actual usage is 22.000 MD, 2 MD over the annual budget.
- `YETTE` has `ITTL-NAPP-0000` time on Sep 3-4 and Sep 7-10 (one hour per weekday, 0.750 MD), plus valid non-engagement hours. This remains separate from YETTE's 2.000 MD of ITRA time. `YNA` similarly has `BPTL-NAPP-0000`, and `GAB` has `BRTL-NAPP-0000`. TL entries are stored under each TL's own initials and appear alongside their group's auditors in reports.
- `TINA`: `BPRA-NAPP-M024`, annual budget 30 MD, budgeted MD/auditor 30 MD, assigned for 2026. The September daily capacity is 176 hours, and two non-engagement slots per each of five calendar weeks reserve 10 hours; therefore engagement can reach at most 166 hours (20.750 MD), not the 30 MD budget, without violating the eight-hour daily rule.
- `TESS`: `BRCC-NAPP-0000`, `BRRF-NAPP-0000`, `BRFA-NAPP-0000`, and `BRVA-NAPP-0000`, assigned on Sep 1-4, 2026, within the first week. The branch codes have no invented budgets. Engagement entries total 4.000 MD; the same selected non-engagement code fills eight hours on the remaining September weekdays.
- IT auditor LANZ uses one selected valid non-engagement code per calendar week (16 slots / 2.000 MD); IT TL YETTE records 2.000 MD ITRA, 0.750 MD ITTL, and 5.250 MD non-engagement. Business Process auditor TINA uses two different non-engagement codes per calendar week (10 slots / 1.250 MD); BP TL YNA records 0.750 MD BPTL and 5.250 MD non-engagement. Branch auditor TESS uses one selected valid code (144 slots / 18.000 MD); Branch TL GAB records 0.750 MD BRTL and 5.250 MD non-engagement.
- All-code report totals excluding lunch/restday are 30.000 MD for IT, 28.000 MD for Business Process, and 28.000 MD for Branch. IT splits into LANZ 20.000 MD ITRA + 2.000 MD non-engagement and YETTE 2.000 MD ITRA + 0.750 MD ITTL + 5.250 MD non-engagement. Business Process splits into TINA 20.750 MD engagement + 1.250 MD non-engagement and YNA 0.750 MD BPTL + 5.250 MD non-engagement. Branch splits into TESS 4.000 MD Branch engagements + 18.000 MD non-engagement and GAB 0.750 MD BRTL + 5.250 MD non-engagement. The chart displays each code separately for each account identity.
- The seed prints the independently calculated totals and checks authentication, budgets, assignments, date bounds, code validity, and non-engagement counts.

## Reset Only This Test Dataset

Stop the local server first. To reseed, rerun `py scripts/seed_local_test_data.py`; it is idempotent for the six test accounts and their entries/assignments. To remove the local test database entirely:

```powershell
Remove-Item "$env:LOCALAPPDATA\ProductivitySystemTesting\productivity-september-2026.db" -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\ProductivitySystemTesting\productivity-september-2026.db-wal" -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\ProductivitySystemTesting\productivity-september-2026.db-shm" -ErrorAction SilentlyContinue
```

These commands remove only the dedicated local test database files. They do not touch `productivity.db`, any configured PostgreSQL database, GitHub, or Render.

## Manual Checklist

- [ ] Login as `yette`
- [ ] Login as `lanz`
- [ ] Verify IT Audit engagement and 20 MD budget
- [ ] Verify YETTE's `ITTL-NAPP-0000` entries for Sep 3-10 appear as a separate identity in the All IT auditors report
- [ ] Verify 20 MD engagement timekeeping, eight logged hours per weekday, and one selected non-engagement code per week
