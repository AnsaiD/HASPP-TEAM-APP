# HASPP Team App

Multi-user team workspace: shared kanban boards (like Trello), login,
and admin-controlled permissions. Built for the HASPP management team
working from different locations.

**Af-Soomaali:** App kooxeed — boards la wadaago (sida Trello), login,
admin-kuna wuxuu maamulaa cidda soo gasha. Kooxdu meel kasta ha joogtee
way isticmaali kartaa marka la deploy-gareeyo.

## Features

- Sign up / Log in (first registered user automatically becomes **admin**)
- Kanban boards: create lists, cards, drag & drop between lists
- Card details: description, assignee, due date (overdue highlighted)
- Admin panel: promote/demote users, activate/deactivate accounts
- Board members: admin invites members to boards, assigns board roles
- Bilingual UI: Somali / English toggle

## Run locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

## Deploy (so the team can use it from anywhere)

**Si kooxdu meel kasta uga gasho, app-ka waa in la dhigaa hosting.**

### Option A — Render.com (free, easiest)

1. Create a free account at render.com and push this folder to a GitHub repo.
2. In Render: **New → Web Service** → connect the repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT --app-dir .`
   - Environment → add `SECRET_KEY` = any long random string (keep it secret).
3. Add a **persistent disk** (Render dashboard → Disks) mounted at
   `/opt/render/project/src/backend` so the SQLite database survives restarts.
   Without a disk, data is lost when the service restarts.
4. Deploy → you get a public URL like `https://haspp-team.onrender.com`.
5. Open the URL, **sign up first** — that account becomes admin.
   Then invite the team (they sign up, you activate/promote them in Admin panel).

### Option B — Railway / Fly.io / VPS

Same code works anywhere Docker runs:

```bash
docker build -t haspp-team-app .
docker run -p 8000:8000 -e SECRET_KEY=your-long-secret \
  -v haspp-data:/app/backend haspp-team-app
```

## Security notes

- Change `SECRET_KEY` per deployment (env var). Never commit a real secret.
- Passwords are hashed with PBKDF2-SHA256 (200k iterations).
- Deactivated users cannot log in; removing a board member revokes access.
- For production, serve behind HTTPS (Render/Railway do this automatically).
