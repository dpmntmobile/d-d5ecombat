"""Monster selection and profile-listing helpers for the CLI."""

import os

from .monster_profiles import load_monster_profile
from .scenario_factory import format_damage_profile as format_scenario_damage
from .storage_paths import PROJECT_DIR


CHARACTERS_DIR = str(PROJECT_DIR / "characters")
MONSTERS_DIR = str(PROJECT_DIR / "monsters")


def load_target_profile(filename):
    """Backward-compatible name for loading a monster target profile."""
    return load_monster_profile(filename)


def list_character_files():
    """List all JSON files in the characters directory."""
    if not os.path.isdir(CHARACTERS_DIR):
        return []

    json_files = []
    for filename in os.listdir(CHARACTERS_DIR):
        if filename.lower().endswith('.json'):
            json_files.append(filename)

    return sorted(json_files)


def list_monster_files():
    """List all JSON files in the monsters directory."""
    if not os.path.isdir(MONSTERS_DIR):
        return []

    return sorted(
        filename
        for filename in os.listdir(MONSTERS_DIR)
        if filename.lower().endswith(".json")
    )


def prompt_monster_profile(input_func=input, output_func=print):
    monster_files = list_monster_files()
    if not monster_files:
        output_func("No monster files found in monsters/; using a generic target.")
        return None

    output_func(f"\nChoose an enemy ({len(monster_files)} found):")
    for index, filename in enumerate(monster_files, start=1):
        output_func(f"  {index}) {filename}")
    output_func("  0) Use a generic target")
    output_func("  M) Enter file path manually")

    choice = input_func("Choose an enemy [1]: ").strip().lower() or "1"
    if choice in {"m", "manual"}:
        filename = input_func("Path to monster JSON: ").strip()
        if not filename:
            raise ValueError("Monster file path cannot be empty.")
    elif choice in {filename.lower() for filename in monster_files}:
        selected_filename = next(
            filename
            for filename in monster_files
            if filename.lower() == choice
        )
        filename = os.path.join(MONSTERS_DIR, selected_filename)
    else:
        try:
            monster_index = int(choice)
        except ValueError as error:
            raise ValueError(
                "Please choose a monster number, filename, or M."
            ) from error
        if monster_index == 0:
            return None
        if not 1 <= monster_index <= len(monster_files):
            raise ValueError("Selected monster is out of range.")
        filename = os.path.join(MONSTERS_DIR, monster_files[monster_index - 1])

    monster = load_monster_profile(filename)
    output_func(
        f"Loaded {monster.name} (AC {monster.armor_class}, "
        f"{monster.max_hp} HP, initiative {monster.initiative_bonus:+d})."
    )
    print_monster_profile_notes(monster, output_func)
    return monster


def print_monster_profile_notes(monster, output_func=print):
    if monster.ruleset:
        output_func(f"Ruleset: {monster.ruleset}")
    if monster.source_url:
        output_func(f"Source: {monster.source_url}")
    if monster.unmodeled_traits:
        output_func(
            "Warning - not modeled: " + ", ".join(monster.unmodeled_traits)
        )
    if monster.attack_profiles:
        output_func("Attacks:")
        for attack in monster.attack_profiles:
            distance_parts = []
            if attack.reach_feet is not None:
                distance_parts.append(f"reach {attack.reach_feet} ft.")
            if attack.normal_range_feet is not None:
                range_text = str(attack.normal_range_feet)
                if attack.long_range_feet is not None:
                    range_text += f"/{attack.long_range_feet}"
                distance_parts.append(f"range {range_text} ft.")
            distance_text = (
                f", {', '.join(distance_parts)}" if distance_parts else ""
            )
            damage_type_text = f" {attack.damage_type}" if attack.damage_type else ""
            output_func(
                f"  {attack.name}: {attack.attack_bonus:+d} to hit, "
                f"{format_scenario_damage(attack)}{damage_type_text}{distance_text}"
            )
            if attack.unmodeled_effects:
                output_func(
                    f"  Warning - {attack.name} effect not modeled: "
                    + ", ".join(attack.unmodeled_effects)
                )
