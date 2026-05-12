import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
TEST_DB = BACKEND_ROOT / "data" / "test_app.db"

os.environ["APP_PIN"] = "123456"
os.environ["APP_PIN_HASH"] = ""
os.environ["SESSION_SECRET"] = "codex-fast-trade-test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
