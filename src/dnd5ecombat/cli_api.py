# ruff: noqa: F401
"""Stable public imports shared by current and legacy CLI entry points."""

import os

from .character_models import CharacterBuild
from .character_profiles import (
    build_from_roll20_with_attack,
    get_build_file_path,
    import_from_roll20,
    load_custom_build,
    parse_damage_dice,
    save_custom_build,
)
from .cli_arguments import parse_args
from .cli_reporting import print_attack_summary, print_save_summary, print_turn_summary
from .cli_setup import (
    CHARACTERS_DIR,
    MONSTERS_DIR,
    build_attack_scenarios,
    build_character_presets,
    build_custom_attack_scenarios,
    build_save_scenarios,
    build_turn_plans,
    list_character_files,
    list_monster_files,
    load_target_profile,
    print_monster_profile_notes,
    prompt_custom_build,
    prompt_monster_profile,
    run_interactive_menu,
)
from .cli_workflows import (
    format_damage_profile,
    load_duel_monsters,
    main,
    print_initiative_order,
    run_all_summaries,
    run_attack_summary,
    run_default_summary,
    run_duel_summary,
    run_single_combat_summary,
)
from .models import (
    AttackProfile,
    AttackScenario,
    DamageDice,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
    TargetProfile,
    TurnPlan,
)
from .monster_profiles import load_monster_profile
from .simulation import compare_attack_scenarios_by_ac


__all__ = tuple(
    name for name in globals() if not name.startswith("_") and name != "annotations"
)
