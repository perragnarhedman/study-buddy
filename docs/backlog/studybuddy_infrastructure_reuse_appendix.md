# StudyBuddy Infrastructure Appendix

## Purpose

This appendix only documents the infrastructure currently in place for StudyBuddy and the configuration needed to run or deploy it.

## Infrastructure In Place

StudyBuddy currently has the following infrastructure:

- `FastAPI` backend
- `Uvicorn` application server
- `Docker` containerization for the backend
- `Render` as the hosted backend platform
- `SQLite` as the application database
- `Render Persistent Disk` for keeping SQLite data across restarts and deploys
- `OpenAI Responses API` for chat and planning features
- `Google OAuth` for authentication and Google API access
- `Meta WhatsApp Cloud API` for the optional WhatsApp channel

## Runtime Components

### Backend

The backend is a Python service with these main dependencies:

- `fastapi`
- `uvicorn`
- `pydantic`
- `pydantic-settings`
- `httpx`
- `itsdangerous`

### Database

The backend uses `SQLite`.

The database stores operational state such as:

- OAuth tokens
- session-related state
- chat history
- user state
- PKCE OAuth state
- WhatsApp link and deduplication state

### LLM Provider

The backend calls the `OpenAI Responses API` directly.

Current model configuration in code:

- chat model: `gpt-5.2`
- plan model: `gpt-5-mini`

### Hosting

The backend is configured to run on `Render` as a Docker-based web service.

### External Integrations

Configured external integrations include:

- `Google OAuth`
- `Google Classroom`
- `Meta WhatsApp Cloud API`

## Required Configuration

### Core Required Environment Variables

These are required for the backend to function in its main hosted setup:

- `SESSION_SECRET`
- `OPENAI_API_KEY`

### Optional or Deployment-Specific Environment Variables

These are used depending on environment and enabled features:

- `SQLITE_PATH`
- `API_HOST`
- `API_PORT`
- `CORS_ORIGINS`
- `DEBUG_EXPORT_ENABLED`
- `DEBUG_EXPORT_DIR`
- `PUBLIC_BASE_URL`
- `PROMPTS_HOT_RELOAD`
- `OPENAI_CHAT_MODEL`
- `OPENAI_PLAN_MODEL`
- `OPENAI_CHAT_TIMEOUT_SECONDS`
- `OPENAI_PLAN_TIMEOUT_SECONDS`
- `SQLITE_TIMEOUT_SECONDS`
- `SQLITE_WAL_ENABLED`
- `SQLITE_SYNCHRONOUS_NORMAL`
- `CLASSROOM_MAX_CONCURRENCY`
- `CLASSROOM_CACHE_TTL_SECONDS`
- `OAUTH_PKCE_TTL_SECONDS`

### Google OAuth and Classroom Configuration

Set these when Google sign-in and Google API access are needed:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`

If `GOOGLE_REDIRECT_URI` is not set explicitly, the app can derive it from:

- `PUBLIC_BASE_URL`

Expected callback path:

- `/auth/google/callback`

### WhatsApp Configuration

Set these when the WhatsApp integration is enabled:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

## Render Configuration

StudyBuddy's backend is configured on `Render` with:

- service type: `web`
- environment: `docker`
- Dockerfile path: `backend/Dockerfile`
- health check path: `/health`
- auto deploy: enabled

Recommended persistent storage setup on Render:

- attach a `Persistent Disk`
- mount storage at `/var/data`
- set `SQLITE_PATH=/var/data/backend.sqlite3`

## Docker Runtime Configuration

The backend Docker container:

- uses `python:3.11-slim`
- installs dependencies from `backend/requirements.txt`
- copies the backend app into `/app`
- exposes port `8000`
- starts with `uvicorn` on host `0.0.0.0` and port `8000`

## Local Runtime Defaults

When running locally, the main defaults are:

- `API_HOST=127.0.0.1`
- `API_PORT=8000`
- `SQLITE_PATH=backend.sqlite3`
- `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`

## Operational Notes

### Persistence

Because the backend uses `SQLite`, hosted deployments need shared persistent storage if state must survive deploys and restarts.

This is especially relevant for:

- OAuth tokens
- user state
- PKCE state
- chat-related persistence

### OAuth Callback Reliability

For OAuth start and callback to work reliably across restarts, backend instances need access to the same SQLite database path or equivalent shared storage.

### Health Check

The backend exposes:

- `GET /health`

Expected response:

- `{ "status": "ok" }`

## Minimal Setup Checklist

For the current backend stack, the minimum hosted setup is:

1. Deploy the backend as a Docker service.
2. Set `SESSION_SECRET`.
3. Set `OPENAI_API_KEY`.
4. Attach persistent storage if using hosted `SQLite`.
5. Set `SQLITE_PATH` to the mounted persistent disk path.
6. Configure `PUBLIC_BASE_URL` or `GOOGLE_REDIRECT_URI` if Google OAuth is enabled.
7. Add Google credentials if Google APIs are enabled.
8. Add WhatsApp credentials only if the WhatsApp channel is enabled.
