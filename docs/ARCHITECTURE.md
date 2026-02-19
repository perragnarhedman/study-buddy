## Study Buddy Architecture

### Goal

- **Chat tab**: WhatsApp-like chat UI that behaves like a performance coach.
- **Plan tab**: persistent weekly overview + one “Best Next Action”.
- **Backend**: FastAPI API using OpenAI-backed planning/coaching and Google Classroom data.

### Monorepo layout (invariants)

- `ios/StudyBuddyApp`: iOS (SwiftUI, iOS 17+, no external deps)
- `backend`: FastAPI
- `docs`: documentation

### Backend

#### Module layout

- `backend/app/main.py`: FastAPI app + CORS + route registration
- `backend/app/routes`: endpoint handlers
- `backend/app/models/schemas.py`: shared API schemas (Pydantic)
- `backend/app/core/config.py`: environment-based config loader
- `backend/app/core/db.py`: SQLite storage (tokens, chat state, assignment status, PKCE state)
- `backend/app/services/planning.py`: primary production planning path (LLM-driven)

#### Stable endpoints (do not change)

- `GET /health` → `{ "status": "ok" }`
- `POST /chat/send` → OpenAI coach decision + assistant response (+ optional assignment cards)
- `GET /plan/week` → OpenAI-generated weekly plan
- `GET /auth/google/start` / `GET /auth/google/callback` → Google OAuth + session issuance

#### Planner architecture

- Production uses a single planner path: `services/planning.py` (`generate_weekly_plan_openai_required`).
- Assignment fallback data (fixture + deterministic local stub) lives in `services/assignment_source.py`.
- Tests may monkeypatch data sources, but production behavior is OpenAI-required and auth-required.

#### Reliability controls

- Classroom assignment loading uses bounded concurrency and per-user short TTL caching.
- SQLite is configured with `busy_timeout`, optional WAL, and `synchronous=NORMAL` for API workloads.
- PKCE OAuth state is persisted in DB (`oauth_pkce_state`) with TTL and one-time use semantics.
- Request logs include a request id (`X-Request-ID`) for correlation across API paths.

#### Deployment assumption for OAuth callback

- For reliable OAuth start/callback behavior across restarts, backend instances must share the same SQLite DB path/volume (or equivalent shared storage).
- Callback routing does not need sticky sessions when DB state is shared.

### iOS (Phase 1)

- **State**: one observable store holding `[ChatMessage]` + `WeeklyPlan`
- **Debug**: `Use Stub Data` toggle (AppStorage). If ON or network fails, show stub.
- **Networking**: `APIClient` with `health()`, `sendChat()`, `fetchWeeklyPlan()`


