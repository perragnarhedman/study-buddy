## Study Buddy Architecture (Phase 1)

### Goal (MVP skeleton)

- **Chat tab**: WhatsApp-like chat UI that behaves like a performance coach.
- **Plan tab**: persistent weekly overview + one “Best Next Action”.
- **Backend**: simple FastAPI API with stable schemas and stubbed logic.

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

#### Stable endpoints (do not change)

- `GET /health` → `{ "status": "ok" }`
- `POST /chat/send` → stubbed assistant response + optional best next action
- `GET /plan/week` → stubbed weekly plan

### iOS (Phase 1)

- **State**: one observable store holding `[ChatMessage]` + `WeeklyPlan`
- **Debug**: `Use Stub Data` toggle (AppStorage). If ON or network fails, show stub.
- **Networking**: `APIClient` with `health()`, `sendChat()`, `fetchWeeklyPlan()`


