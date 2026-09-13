# IT Audit Productivity System

## Cloud-ready public deployment path

This repository now includes a deployment configuration for a cloud Flask runtime and a structured path away from the local SQLite design.

The app is a Flask project in `app.py` and should move to an environment-backed PostgreSQL database for public access.

## Run the Python version locally

The Flask version is in `app.py` and stores data in SQLite (`productivity.db`) by default.
Install the dependencies and run it with:

```
py -m pip install -r requirements.txt
py app.py
```

Then open http://127.0.0.1:5000. It uses the same initial admin credentials below.

## Public cloud deployment

The repository ships with the following deployment files:

- `render.yaml` for Render
- `Procfile` for `gunicorn`
- `requirements.txt` with Python host/runtime packages

Set the following environment variables when deploying:

```
PRODUCTIVITY_SECRET=<strong-random-secret>
PRODUCTIVITY_DB=<database-url-or-sqlite-path>
PRODUCTIVITY_HOST=0.0.0.0
PRODUCTIVITY_PORT=10000
PRODUCTIVITY_DEBUG=false
PRODUCTIVITY_COOKIE_SECURE=true
```

Use a hosted PostgreSQL database instead of the local SQLite file for public access.

## Legacy Vite client

```
npm install
npm run dev
```

Then open the URL Vite prints (usually http://localhost:5173).

## First login

An admin account is seeded automatically the first time the app loads:

- Username: `admin`
- Password: `ChangeMe123!`

Log in, then go to the **Accounts** tab and reset that password immediately, and add
accounts for your auditors and any other admins.

## Data storage

This local version stores all data (engagements, auditors, time entries, accounts) in
your browser's `localStorage`. That means:

- Data is **per-browser, per-machine** — it will not sync between different computers
  or between you and your team, unlike the shared version running inside Claude.
- Clearing your browser data will erase everything. Consider adding an export/import
  feature or a real backend (e.g. a small Node/Express API + database) before rolling
  this out to a team.

## Persistence (recommended)

Short version: for production use a managed Postgres database and set `DATABASE_URL`.
If you want minimal friction locally, set `PRODUCTIVITY_DB` to an absolute path on
persistent storage instead of relying on ephemeral containers.

Recommended (production / shared team):

- Provision a Postgres instance (Render, Heroku, AWS RDS, Supabase, etc.).
- Set the `DATABASE_URL` env var to the Postgres connection string (e.g. `postgres://user:pass@host:5432/dbname`).
- Run the included migration to copy an existing SQLite data file into Postgres:

```bash
export DATABASE_URL="postgres://user:pass@host:5432/dbname"
export PRODUCTIVITY_DB="./productivity.db" # path to your sqlite file (if migrating)
python scripts/migrate_sqlite_to_postgres.py
```

- Start the app (it will use `DATABASE_URL` when present):

```bash
export PRODUCTIVITY_SECRET="$(openssl rand -hex 32)"
python app.py
```

Quick local fix (minimal effort):

- Keep using SQLite but point `PRODUCTIVITY_DB` to a stable path that is not ephemeral
  (for example a directory on the host or a mounted volume in your container):

```powershell
$env:PRODUCTIVITY_DB = "C:\data\productivity.db"
py app.py
```

Notes:
- The SPA now attempts a best-effort sync of its `localStorage` keys to the server via
  `POST /api/sync`. For full safety and multi-user deployments use Postgres + `DATABASE_URL`.
- If you want, I can make the `/api/sync` require authentication (recommended for public deployments).

## Project structure

```
index.html          Vite entry HTML
src/main.jsx         React root
src/App.jsx           The whole application (tabs, login, all logic)
vite.config.js       Vite + React plugin config
package.json          Dependencies and scripts
```
