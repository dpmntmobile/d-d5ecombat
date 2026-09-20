"""Reusable encounter settings shared by the CLI and desktop interface."""

import json
from dataclasses import asdict, fields
from pathlib import Path

from .application_service import SimulationSettings
from .profile_schema import validate_profile


def settings_from_arguments(arguments):
    """Read the shared settings from a parsed command line."""
    return SimulationSettings(**{
        field.name: getattr(arguments, field.name, field.default)
        for field in fields(SimulationSettings)
    })


def load_scenario(filename):
    """Load validated settings; omitted fields use application defaults."""
    path = Path(filename)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"{path}: invalid scenario JSON: {error}") from error
    data = validate_profile(data, "scenario", source=path)
    return SimulationSettings(**data["settings"])


def save_scenario(settings, filename):
    """Save all encounter settings without embedding combatant profiles."""
    path = Path(filename)
    data = {"schema_version": 1, "settings": asdict(settings)}
    validate_profile(data, "scenario", source=path)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
