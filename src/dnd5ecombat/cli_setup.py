# ruff: noqa: F401
"""Compatibility exports for focused CLI setup modules."""

import os

from .cli_catalog import (
    CHARACTERS_DIR,
    MONSTERS_DIR,
    list_character_files,
    list_monster_files,
    load_target_profile,
    print_monster_profile_notes,
    prompt_monster_profile,
)
from .cli_characters import (
    build_attack_scenarios,
    build_character_presets,
    build_custom_attack_scenarios,
    build_save_scenarios,
    build_turn_plans,
    prompt_custom_build,
)
from .cli_menu import run_interactive_menu


__all__ = tuple(name for name in globals() if not name.startswith("_"))
