"""Expose the existing Flask application as a Vercel Python Function."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402,F401
