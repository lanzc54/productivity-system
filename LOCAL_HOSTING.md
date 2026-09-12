# Local Hosting Guide

This project is configured to run as a Flask app locally and to be reachable on the same local network.

## Run locally

From the project directory:

```powershell
py app.py
```

The app listens on:

```text
http://127.0.0.1:5000
```

It also binds to the machine LAN address, for example:

```text
http://192.168.100.59:5000
```

## Use a LAN URL

Ask your teammate to open the server host machine's local IP address on port 5000, such as:

```text
http://<your-computer-ip>:5000
```

## Security reminders

- Change the default admin password immediately after first login.
- Use a strong `PRODUCTIVITY_SECRET` environment variable.
- Do not expose the app directly to the internet.
- Prefer a private network or VPN if sensitive audit data is involved.

## Environment variables

You can optionally configure the host and port environment variables:

```powershell
$env:PRODUCTIVITY_HOST = "0.0.0.0"
$env:PRODUCTIVITY_PORT = "5000"
$env:PRODUCTIVITY_DEBUG = "false"
$env:PRODUCTIVITY_COOKIE_SECURE = "false"
```

For a real production environment, set `PRODUCTIVITY_COOKIE_SECURE=true` behind HTTPS and do not use the local SQLite file as a shared database.
