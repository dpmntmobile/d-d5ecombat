"""Character and monster discovery, validation, and import services."""

import json
import shutil
import re
from dataclasses import dataclass
from pathlib import Path

from .character_profiles import (
    build_from_roll20_with_attack,
    import_from_roll20,
    load_custom_build,
)
from .monster_profiles import load_monster_profile
from .storage_paths import (
    PROJECT_DIR,  # noqa: F401 - retained as a public compatibility export
    catalog_roots,
    profile_directory,
)



@dataclass(frozen=True)
class CatalogItem:
    label: str
    value: object
    source: str = ""


@dataclass(frozen=True)
class CatalogIssue:
    path: str
    message: str


@dataclass(frozen=True)
class CatalogResult:
    items: tuple
    issues: tuple = ()


def _read_json_object(path):
    try:
        with open(path, "r", encoding="utf-8") as source_file:
            data = json.load(source_file)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_character_build(path):
    """Load either a saved build or a Roll20 character export."""
    path = Path(path)
    raw_data = _read_json_object(path)
    saved_build_fields = {
        "primary_attack_name",
        "attack_profiles",
        "saving_throw_profiles",
    }
    if raw_data is not None and saved_build_fields.intersection(raw_data):
        build = load_custom_build(path)
        if build is not None:
            return build

    roll20_data = import_from_roll20(path)
    if not roll20_data:
        raise ValueError(f"Could not load character file: {path}")

    attacks = roll20_data.get("attacks", ())
    if attacks:
        selected_name = roll20_data.get("primary_attack_name")
        selected = next(
            (attack for attack in attacks if attack["name"] == selected_name),
            attacks[0],
        )
        attack_bonus = selected["bonus"]
        damage_dice = selected["damage_dice"]
        damage_modifier = selected["damage_modifier"]
        selected_name = selected["name"]
    else:
        attack_bonus = (
            roll20_data["strength_mod"] + roll20_data["proficiency_bonus"]
        )
        damage_dice = "1d8"
        damage_modifier = roll20_data["strength_mod"]
        selected_name = None

    return build_from_roll20_with_attack(
        roll20_data,
        attack_bonus=attack_bonus,
        damage_dice_text=damage_dice,
        damage_modifier=damage_modifier,
        selected_attack_name=selected_name,
    )


def discover_character_catalog(project_dir=None):
    roots = catalog_roots(project_dir)
    items = []
    issues = []
    paths = {
        path.name.lower(): path
        for root in roots
        for path in (root / "characters").glob("*.json")
    }
    for path in sorted(paths.values(), key=lambda candidate: candidate.name.lower()):
        try:
            build = load_character_build(path)
        except (OSError, TypeError, ValueError) as error:
            issues.append(CatalogIssue(str(path), str(error)))
            continue
        items.append(CatalogItem(f"{build.name} — {path.name}", build, str(path)))
    return CatalogResult(tuple(items), tuple(issues))


def discover_monster_catalog(project_dir=None):
    roots = catalog_roots(project_dir)
    items = []
    issues = []
    paths = {
        path.name.lower(): path
        for root in roots
        for path in (root / "monsters").glob("*.json")
    }
    for path in sorted(paths.values(), key=lambda candidate: candidate.name.lower()):
        try:
            monster = load_monster_profile(path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            issues.append(CatalogIssue(str(path), str(error)))
            continue
        items.append(CatalogItem(f"{monster.name} — {path.name}", monster, str(path)))
    return CatalogResult(tuple(items), tuple(issues))


def discover_characters(project_dir=None):
    return discover_character_catalog(project_dir).items


def discover_monsters(project_dir=None):
    return discover_monster_catalog(project_dir).items


def monster_profile_path(name, project_dir=None):
    safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not safe_name:
        raise ValueError("Monster name must contain a letter or number")
    return profile_directory("monsters", project_dir) / f"{safe_name}.json"


def import_character_file(source, project_dir=None, overwrite=False):
    """Validate and copy a character JSON file into the character catalog."""
    source = Path(source).resolve()
    if source.suffix.lower() != ".json":
        raise ValueError("Character files must use the .json extension")
    build = load_character_build(source)

    destination_directory = profile_directory("characters", project_dir)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / source.name
    if destination.exists() and source != destination and not overwrite:
        raise FileExistsError(f"Character file already exists: {destination.name}")
    if source != destination:
        shutil.copy2(source, destination)
    return CatalogItem(
        f"{build.name} — {destination.name}", build, str(destination)
    )
