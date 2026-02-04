## Deployment (backend)

This project’s backend is a FastAPI app in `backend/`.

### Required environment variables
- `SESSION_SECRET`: required for auth/session token signing
- `OPENAI_API_KEY`: required for chat + plan endpoints

### Render (recommended for pilot)
This repo is a monorepo, so if Render uses the **repo root** as build context:
- **Dockerfile path**: `backend/Dockerfile`

#### Persistent storage (SQLite) — pilot default
For a 10–20 user pilot, we use **SQLite** with a **Render Persistent Disk** so auth tokens and `user_state` survive deploys.

- **Attach a Persistent Disk** to the Render service
- **Mount path**: `/var/data`
- **Set** `SQLITE_PATH=/var/data/backend.sqlite3` (no trailing slash)

##### How to verify persistence across redeploy
1) Connect Google Classroom in the iOS app (this stores OAuth tokens + user state in SQLite).
2) Confirm `GET /classroom/assignments` returns 200 with your session token.
3) Trigger a redeploy (or restart) in Render.
4) Confirm that, after redeploy:
   - `GET /classroom/assignments` still returns 200 (tokens persisted)
   - Chat state (e.g. last selection) still behaves as expected

### Optional environment variables
- `SQLITE_PATH`: defaults to `backend.sqlite3` (relative to backend working dir)
- `API_HOST`: defaults to `127.0.0.1` (local use)
- `API_PORT`: defaults to `8000`
- `CORS_ORIGINS`: defaults to `http://localhost:3000,http://127.0.0.1:3000`
- `DEBUG_EXPORT_ENABLED`: `true|false` (default false)
- `DEBUG_EXPORT_DIR`: default `debug_exports`
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`
- `OPENAI_TIMEOUT_SECONDS`: defaults to `30.0`

### Docker build/run (platform-agnostic)

Build:

```bash
cd backend
docker build -t study-buddy-backend:latest .
```

Run (example):

```bash
docker run --rm -p 8000:8000 \
  -e SESSION_SECRET="change-me" \
  -e OPENAI_API_KEY="..." \
  -e SQLITE_PATH="/data/backend.sqlite3" \
  -v "$PWD/data:/data" \
  study-buddy-backend:latest
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

### Render env var checklist (no secrets in git)
Core:
- `SESSION_SECRET` (required)
- `SQLITE_PATH=/var/data/backend.sqlite3` (required for persistence)
- `DEBUG_EXPORT_ENABLED=false` (recommended for pilot)

OpenAI:
- `OPENAI_API_KEY` (required for `/chat/send` + `/plan/week`)
- `OPENAI_MODEL` (optional)
- `OPENAI_TIMEOUT_SECONDS` (optional)

Google OAuth / Classroom (if enabled for pilot):
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI=https://<your-render-domain>/auth/google/callback`

### Release checklist
- Ensure secrets are configured in the deployment platform (never commit `.env`)
- Confirm `/health` returns `{"status":"ok"}`
- Smoke test:
  - `GET /plan/week` (authenticated)
  - `POST /chat/send` (authenticated)

### Minimal observability (recommended)
- **Request correlation**: add/request-id header logging (so you can trace a user request end-to-end)
- **Structured logs**: log key events like auth failures, OpenAI 503s, and unexpected exceptions
- **No secrets in logs**: never log tokens or API keys

### Rollback
- Roll back by deploying the previous container image/tag from your deployment platform.
- After rollback, verify `/health` and repeat the smoke test above.


