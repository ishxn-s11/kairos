"""WSGI entrypoint for the Vercel backend service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))

from serve_api import app  # noqa: E402,F401
