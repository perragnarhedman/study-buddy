import sys
from pathlib import Path

# Ensure `backend/` is on the import path so tests can `import app...`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


