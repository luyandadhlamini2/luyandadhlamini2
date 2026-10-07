"""Load and save a user's Preferences (their rules and edits) as JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .classifier import Preferences

# Set FINANCES_PREFS_FILE=none when the app is shared by several people, so
# nobody's rules (which can contain payee names) are written to a shared disk.
DEFAULT_PATH = Path.home() / ".finances_app" / "preferences.json"


def preferences_path() -> Path | None:
    configured = os.environ.get("FINANCES_PREFS_FILE", "").strip()
    if configured.lower() in ("none", "off", "0"):
        return None
    return Path(configured).expanduser() if configured else DEFAULT_PATH


def load(path: Path | None) -> Preferences:
    if path is None or not path.exists():
        return Preferences()
    try:
        return Preferences.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError, KeyError):
        return Preferences()  # a corrupt file shouldn't stop the app


def save(preferences: Preferences, path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(preferences), encoding="utf-8")


def dumps(preferences: Preferences) -> str:
    return json.dumps(preferences.to_dict(), indent=2, sort_keys=True)


def loads(text: str) -> Preferences:
    return Preferences.from_dict(json.loads(text))
