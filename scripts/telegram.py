"""Manual Telegram helper; run using backend Python from the repository root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.integrations.telegram.manage import main

if __name__ == "__main__":
    raise SystemExit(main())
