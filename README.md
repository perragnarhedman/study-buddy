## Study Buddy

Mobile-first study planning assistant for students.

### Repo layout (invariants)

- `/ios/StudyBuddyApp`: iOS app (SwiftUI, iOS 17+)
- `/backend`: FastAPI backend
- `/docs`: product/tech docs

### Backend setup (FastAPI)

- **Create env file**:
  - Copy `backend/.env.example` to `backend/.env` and adjust if needed.
- **Install deps** (in your venv):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

- **Run**:

```bash
cd backend
make run
```

Backend runs at `http://127.0.0.1:8000` by default.

### iOS setup (SwiftUI)

- Open `ios/StudyBuddyApp/StudyBuddyApp.xcodeproj` in Xcode (iOS 17+).
- In the app, open the **gear** icon to configure:
  - **Base URL** (default `http://127.0.0.1:8000`)
  - **Use Stub Data** (fallback when offline / backend not running)

Dev notes:
- `docs/IOS_SIMULATOR_SWEDISH_KEYBOARD.md` (type å/ä/ö in the iOS Simulator)
- `docs/IOS_TESTFLIGHT_FIRST_BUILD.md` (first TestFlight build checklist)

### Tests

```bash
cd backend
make test
```


