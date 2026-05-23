"""Persistent user settings stored as JSON."""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_SETTINGS_PATH = Path.home() / ".pdfextractor" / "settings.json"


def load_settings() -> dict:
    """Load settings from disk. Returns empty dict on missing or corrupt file."""
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict) -> None:
    """Write settings to disk, creating the directory if needed."""
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    except OSError:
        log.warning("Could not save settings to %s", _SETTINGS_PATH)
