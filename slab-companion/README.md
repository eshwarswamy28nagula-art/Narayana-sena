# Waypoint: AI Web Companion

A focused SLAB Track 06 demo for students and first-time internet users. Waypoint takes any natural-language goal, operates a controlled multi-section campus website, shows its actions, recovers from changed navigation labels, and remembers feedback.

## Run locally

The easiest Windows option is to double-click `run_waypoint.bat`. It installs the dependencies, starts the server, and opens the dashboard.

```powershell
cd slab-companion
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5050. Playwright is optional at runtime: without a browser binary, the app uses the same controlled demo page through a safe HTTP transport so the five-minute presentation remains reliable. To enable the real browser path:

```powershell
playwright install chromium
```

Use `http://127.0.0.1:5050/health` to confirm the backend is running. It should return `{ "ok": true, "service": "waypoint", "demo": true }`.

The app stores task history, preferences, strategies, and feedback in the local SQLite database `waypoint.db`. An existing `memory.json` is imported once for backward compatibility. Local state files are intentionally not committed.

## Demo flow

1. Run any task, such as `Find the hostel application process.` or `Find the exam timetable.`.
2. Enable **Demo adaptation mode** and run it again. The controlled site changes related labels, such as `Hostel` to `Residential Life`; the activity log and adaptation panel show recovery.
3. Submit feedback such as `Give me shorter explanations.`
4. Run the task again and see the shorter answer plus the learned preference in Memory.

No private accounts, CAPTCHA bypasses, payment credentials, or irreversible actions are involved.
