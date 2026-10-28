"""Root Vercel entrypoint for the SentinelPulse FastAPI dashboard."""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent / "bda-project"
sys.path.insert(0, str(APP_DIR))

from webapp import app  # noqa: E402
