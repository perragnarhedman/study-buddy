## Google OAuth + Classroom (Phase 4)

### 1) Create OAuth client in Google Cloud Console

- Create/choose a Google Cloud project.
- Enable **Google Classroom API** for the project.
- Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.

Use a **Web application** client for local development.

### 2) Configure redirect URI

Set the **Authorized redirect URI** to your backend callback URL:

- `http://127.0.0.1:8000/auth/google/callback`

If you run the backend on a different host/port, update this URI and your `.env`.

### 3) Backend environment variables

Copy `backend/.env.example` to `backend/.env` and fill:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET` (required for “Web application” clients)
- `GOOGLE_REDIRECT_URI` (must match the authorized redirect URI)
- `SESSION_SECRET` (random string)
- `SQLITE_PATH` (path to a sqlite file)

### 4) iOS flow (local dev)

- In the iOS app Settings (gear icon), tap **Connect Google Classroom**.
- The app opens Safari for Google sign-in.
- After consent, Google redirects to the backend callback, and the backend redirects to:
  - `studybuddy://auth?token=<SESSION_TOKEN>`
- The app stores the session token and can call:
  - `GET /classroom/assignments` with `Authorization: Bearer <SESSION_TOKEN>`


