"""Canonical project and per-user storage locations."""

import os
import sys
from pathlib import Path


PROJECT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
USER_PROJECT_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Dnd5eCombatSimulator"
    if getattr(sys, "frozen", False)
    else PROJECT_DIR
)


def catalog_roots(project_dir=None):
    if project_dir is not None:
        return (Path(project_dir),)
    return tuple(dict.fromkeys((PROJECT_DIR, USER_PROJECT_DIR)))


def profile_directory(kind, project_dir=None):
    if kind not in {"characters", "monsters"}:
        raise ValueError(f"unsupported profile directory: {kind}")
    return Path(project_dir or USER_PROJECT_DIR).resolve() / kind
