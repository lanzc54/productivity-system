#!/usr/bin/env python3
"""Migrate local SQLite `productivity.db` into a Postgres database.

Usage:
  Set the environment variable `DATABASE_URL` to the target Postgres connection string
  (e.g. postgres://user:pass@host:5432/dbname) and optionally `PRODUCTIVITY_DB` to the
  path of your local SQLite file. Then run:

    python scripts/migrate_sqlite_to_postgres.py

This script will:
  - Connect to the local SQLite DB (default: ./productivity.db)
  - Connect to Postgres using `DATABASE_URL`
  - Create the required tables in Postgres if missing
  - Copy rows from SQLite tables: accounts, auditors, codes, entries, engagement_assignments

Notes:
  - Ensure `psycopg2` is installed in your environment.
  - This script attempts idempotent inserts (INSERT ... ON CONFLICT DO NOTHING) so
    it can be re-run safely.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from urllib.parse import urlparse

try:
    import psycopg2
    from psycopg2.extras import execute_values
except Exception as e:
    print("Missing dependency: psycopg2. Install with `pip install psycopg2-binary`.")
    raise


def get_sqlite_conn(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQLite file not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_conn(database_url: str):
    # psycopg2 accepts the URL directly
    return psycopg2.connect(database_url)


def ensure_postgres_schema(pg):
    cur = pg.cursor()
    # Create tables similar to app.init_db()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
      username TEXT PRIMARY KEY,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL,
      auditor TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS auditors (
      initials TEXT PRIMARY KEY,
      name TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS codes (
      code TEXT NOT NULL,
      description TEXT NOT NULL,
      kind TEXT NOT NULL,
      year INTEGER NOT NULL DEFAULT EXTRACT(YEAR FROM CURRENT_DATE),
      annual_budget REAL,
      auditor_budget REAL,
      PRIMARY KEY (code, kind, year)
    );

    CREATE TABLE IF NOT EXISTS entries (
      auditor TEXT NOT NULL,
      work_date TEXT NOT NULL,
      slot TEXT NOT NULL,
      code TEXT NOT NULL,
      PRIMARY KEY (auditor, work_date, slot)
    );

    CREATE TABLE IF NOT EXISTS engagement_assignments (
      code TEXT NOT NULL,
      year INTEGER NOT NULL,
      auditor TEXT NOT NULL,
      budget_md REAL,
      PRIMARY KEY (code, year, auditor)
    );
    """)
    pg.commit()


def copy_table(sqlite_conn, pg_conn, table, columns, conflict_cols=None):
    s_cur = sqlite_conn.cursor()
    s_cur.execute(f"SELECT {', '.join(columns)} FROM {table}")
    rows = s_cur.fetchall()
    if not rows:
        print(f"No rows to copy for {table}")
        return
    vals = [[row[col] for col in columns] for row in rows]
    placeholders = ','.join(['%s'] * len(columns))
    cols_sql = ','.join(columns)
    if conflict_cols:
        conflict_sql = ','.join(conflict_cols)
        insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES %s ON CONFLICT ({conflict_sql}) DO NOTHING"
    else:
        insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES %s"
    pcur = pg_conn.cursor()
    execute_values(pcur, insert_sql, vals)
    pg_conn.commit()
    print(f"Copied {len(vals)} rows into {table}")


def main():
    sqlite_path = os.environ.get('PRODUCTIVITY_DB', os.path.join(os.path.dirname(__file__), '..', 'productivity.db'))
    sqlite_path = os.path.abspath(sqlite_path)
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print('Set the DATABASE_URL environment variable (postgres://user:pass@host:port/db)')
        sys.exit(1)

    print('Connecting to SQLite:', sqlite_path)
    sconn = get_sqlite_conn(sqlite_path)
    print('Connecting to Postgres:', database_url)
    pg = get_postgres_conn(database_url)

    ensure_postgres_schema(pg)

    # Copy in order: auditors, accounts, codes, engagement_assignments, entries
    copy_table(sconn, pg, 'auditors', ['initials', 'name'], conflict_cols=['initials'])
    copy_table(sconn, pg, 'accounts', ['username', 'password_hash', 'role', 'auditor'], conflict_cols=['username'])
    copy_table(sconn, pg, 'codes', ['code', 'description', 'kind', 'year', 'annual_budget', 'auditor_budget'], conflict_cols=['code','kind','year'])
    copy_table(sconn, pg, 'engagement_assignments', ['code', 'year', 'auditor', 'budget_md'], conflict_cols=['code','year','auditor'])
    copy_table(sconn, pg, 'entries', ['auditor', 'work_date', 'slot', 'code'], conflict_cols=['auditor','work_date','slot'])

    sconn.close()
    pg.close()
    print('Migration complete.')


if __name__ == '__main__':
    main()
