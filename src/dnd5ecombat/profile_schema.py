"""Versioned JSON Schema loading and profile validation."""

import json
from functools import lru_cache
from importlib.resources import files

from jsonschema import Draft202012Validator


CURRENT_PROFILE_SCHEMA_VERSION = 1
PROFILE_KINDS = frozenset({"native-character", "monster", "roll20-character", "scenario"})


class ProfileValidationError(ValueError):
    """Raised when a profile does not satisfy its declared data contract."""


def _json_path(parts):
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif str(part).isidentifier():
            path += f".{part}"
        else:
            path += f"[{part!r}]"
    return path


@lru_cache(maxsize=None)
def load_profile_schema(profile_kind, version=CURRENT_PROFILE_SCHEMA_VERSION):
    """Load and verify a bundled profile schema."""
    if profile_kind not in PROFILE_KINDS:
        raise ValueError(f"unsupported profile kind: {profile_kind}")
    if version != CURRENT_PROFILE_SCHEMA_VERSION:
        raise ProfileValidationError(
            f"$.schema_version: unsupported {profile_kind} schema version {version}"
        )
    resource = files("dnd5ecombat").joinpath(
        "schemas", f"v{version}", f"{profile_kind}.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_profile(data, profile_kind, source=None):
    """Validate profile data and return a normalized shallow copy.

    Versionless native profiles are treated as version 1 for backward
    compatibility. Roll20 exports use their own ``export_metadata.version`` and
    therefore do not receive a native ``schema_version`` field.
    """
    if not isinstance(data, dict):
        location = f"{source}: " if source else ""
        raise ProfileValidationError(f"{location}$: profile must be a JSON object")

    normalized = dict(data)
    if profile_kind != "roll20-character":
        version = normalized.get("schema_version", CURRENT_PROFILE_SCHEMA_VERSION)
        if not isinstance(version, int) or isinstance(version, bool):
            location = f"{source}: " if source else ""
            raise ProfileValidationError(
                f"{location}$.schema_version: must be an integer"
            )
        if version != CURRENT_PROFILE_SCHEMA_VERSION:
            location = f"{source}: " if source else ""
            raise ProfileValidationError(
                f"{location}$.schema_version: unsupported {profile_kind} "
                f"schema version {version}"
            )
        normalized.setdefault("schema_version", version)
    else:
        version = CURRENT_PROFILE_SCHEMA_VERSION

    validator = Draft202012Validator(load_profile_schema(profile_kind, version))
    errors = sorted(
        validator.iter_errors(normalized),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if errors:
        details = "; ".join(
            f"{_json_path(error.absolute_path)}: {error.message}"
            for error in errors[:5]
        )
        if len(errors) > 5:
            details += f"; and {len(errors) - 5} more error(s)"
        location = f"{source}: " if source else ""
        raise ProfileValidationError(location + details)
    return normalized
