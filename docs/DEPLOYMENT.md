## Deployment (backend)

This project’s backend is a FastAPI app in `backend/`.

### Required environment variables
- `SESSION_SECRET`: required for auth/session token signing
- `OPENAI_API_KEY`: required for chat + plan endpoints

### Optional environment variables
- `SQLITE_PATH`: defaults to `backend.sqlite3` (relative to backend working dir)
- `API_HOST`: defaults to `127.0.0.1` (local use)
- `API_PORT`: defaults to `8000`
- `CORS_ORIGINS`: defaults to `http://localhost:3000,http://127.0.0.1:3000`
- `DEBUG_EXPORT_ENABLED`: `true|false` (default false)
- `DEBUG_EXPORT_DIR`: default `debug_exports`

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


