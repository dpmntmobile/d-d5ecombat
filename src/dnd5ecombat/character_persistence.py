"""Persistence for native character-build JSON files."""

import json
import os

from .character_models import CharacterBuild
from .condition_rules import condition_effect_from_dict, condition_effect_to_dict
from .models import (
    AttackProfile,
    AttackScenario,
    DamageDice,
    FirstHitBonusDamage,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
    TurnPlan,
)
from .profile_schema import CURRENT_PROFILE_SCHEMA_VERSION, validate_profile


def get_build_file_path(name):
    """Return the JSON file path for a character build."""
    safe_name = name.lower().replace(" ", "_")
    return f"{safe_name}_build.json"


def save_custom_build(build, filename=None):
    """Save a character build to JSON file."""
    if filename is None:
        filename = get_build_file_path(build.name)

    data = {
        "schema_version": CURRENT_PROFILE_SCHEMA_VERSION,
        "name": build.name,
        "primary_attack_name": build.attack_profile.name,
        "attack_bonus": build.attack_profile.attack_bonus,
        "damage_dice": [
            {"number": dice.number, "sides": dice.sides}
            for dice in build.attack_profile.damage_dice
        ],
        "damage_modifier": build.attack_profile.damage_modifier,
        "damage_type": build.attack_profile.damage_type,
        "attack_mode": build.attack_profile.attack_mode,
        "condition_effect": condition_effect_to_dict(build.attack_profile.condition_effect),
        "reach_feet": build.attack_profile.reach_feet,
        "normal_range_feet": build.attack_profile.normal_range_feet,
        "long_range_feet": build.attack_profile.long_range_feet,
        "unmodeled_effects": list(build.attack_profile.unmodeled_effects),
        "reroll_damage_at_or_below": (
            build.attack_profile.reroll_damage_at_or_below
        ),
        "action_type": build.attack_profile.action_type,
        "limited_uses": build.attack_profile.limited_uses,
        "recharge_min_roll": build.attack_profile.recharge_min_roll,
        "spell_slot_level": build.attack_profile.spell_slot_level,
        "spell_slot_pool": build.attack_profile.spell_slot_pool,
        "allow_upcast": build.attack_profile.allow_upcast,
        "upcast_damage_dice": [dict(number=d.number, sides=d.sides) for d in build.attack_profile.upcast_damage_dice],
        "armor_class": build.armor_class,
        "max_hp": build.max_hp,
        "save_bonus": build.save_bonus,
        "initiative_bonus": build.initiative_bonus,
        "attacks_per_action": build.attacks_per_action,
        "description": build.description,
        "equipment": list(build.equipment) if build.equipment else [],
        "attack_profiles": [
            {
                "name": profile.name,
                "attack_bonus": profile.attack_bonus,
                "damage_dice": [
                    {"number": dice.number, "sides": dice.sides}
                    for dice in profile.damage_dice
                ],
                "damage_modifier": profile.damage_modifier,
                "damage_type": profile.damage_type,
                "attack_mode": profile.attack_mode,
                "condition_effect": condition_effect_to_dict(profile.condition_effect),
                "reach_feet": profile.reach_feet,
                "normal_range_feet": profile.normal_range_feet,
                "long_range_feet": profile.long_range_feet,
                "unmodeled_effects": list(profile.unmodeled_effects),
                "reroll_damage_at_or_below": profile.reroll_damage_at_or_below,
                "action_type": profile.action_type,
                "limited_uses": profile.limited_uses,
                "recharge_min_roll": profile.recharge_min_roll,
                "spell_slot_level": profile.spell_slot_level,
                "spell_slot_pool": profile.spell_slot_pool,
                "allow_upcast": profile.allow_upcast,
                "upcast_damage_dice": [dict(number=d.number, sides=d.sides) for d in profile.upcast_damage_dice],
            }
            for profile in build.attack_profiles
        ],
        "spell_slots": {str(level): count for level, count in build.spell_slots},
        "pact_slots": {str(level): count for level, count in build.pact_slots},
        "spell_slot_capacity": {str(level): count for level, count in build.spell_slot_capacity},
        "pact_slot_capacity": {str(level): count for level, count in build.pact_slot_capacity},
        "pack_tactics": build.pack_tactics,
        "aggressive": build.aggressive,
        "nimble_escape": build.nimble_escape,
        "stealth_bonus": build.stealth_bonus,
        "passive_perception": build.passive_perception,

        "saving_throw_profiles": [
            {
                "name": profile.name,
                "difficulty_class": profile.difficulty_class,
                "damage_dice": [
                    {"number": dice.number, "sides": dice.sides}
                    for dice in profile.damage_dice
                ],
                "damage_modifier": profile.damage_modifier,
                "damage_on_success": profile.damage_on_success.value,
                "save_ability": profile.save_ability,
                "damage_type": profile.damage_type,
                "action_type": profile.action_type,
                "limited_uses": profile.limited_uses,
                "recharge_min_roll": profile.recharge_min_roll,
                "spell_slot_level": profile.spell_slot_level,
                "spell_slot_pool": profile.spell_slot_pool,
                "allow_upcast": profile.allow_upcast,
                "upcast_damage_dice": [dict(number=d.number, sides=d.sides) for d in profile.upcast_damage_dice],
                "range_feet": profile.range_feet,
                "unmodeled_effects": list(profile.unmodeled_effects),
            }
            for profile in build.saving_throw_profiles
        ],
        "turn_plans": [
            {
                "name": plan.name,
                "attacks": [
                    {
                        "name": scenario.name,
                        "attack_name": scenario.attack.name,
                        "bonus_damage_dice": [
                            {"number": dice.number, "sides": dice.sides}
                            for dice in scenario.bonus_damage_dice
                        ],
                        "advantage": scenario.advantage,
                        "disadvantage": scenario.disadvantage,
                    }
                    for scenario in plan.attacks
                ],
                "first_hit_bonus_damage": (
                    {
                        "name": plan.first_hit_bonus_damage.name,
                        "requires_advantage": plan.first_hit_bonus_damage.requires_advantage,
                    "allows_nearby_ally": plan.first_hit_bonus_damage.allows_nearby_ally,
                        "damage_dice": [
                            {"number": dice.number, "sides": dice.sides}
                            for dice in plan.first_hit_bonus_damage.damage_dice
                        ],
                        "eligible_attack_indices": list(
                            plan.first_hit_bonus_damage.eligible_attack_indices
                        ),
                    }
                    if plan.first_hit_bonus_damage is not None
                    else None
                ),
            }
            for plan in build.turn_plans
        ],
        "saving_throw_bonuses": dict(build.saving_throw_bonuses),
        "damage_resistances": list(build.damage_resistances),
        "damage_vulnerabilities": list(build.damage_vulnerabilities),
        "damage_immunities": list(build.damage_immunities),
        "condition_immunities": list(build.condition_immunities),
        "creature_tags": list(build.creature_tags),
    }
    data = validate_profile(data, "native-character")

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_custom_build(filename):
    """Load a character build from JSON file."""
    if not os.path.exists(filename):
        return None

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    data = validate_profile(data, "native-character", source=filename)

    damage_dice = tuple(
        DamageDice(dice["number"], dice["sides"]) for dice in data.get("damage_dice", [])
    ) or (DamageDice(1, 8),)

    primary_profile = AttackProfile(
        name=data.get(
            "primary_attack_name", f"{data.get('name', 'Loaded build')} attack"
        ),
        attack_bonus=data.get("attack_bonus", 5),
        damage_dice=damage_dice,
        damage_modifier=data.get("damage_modifier", 0),
        damage_type=data.get("damage_type", ""),
        attack_mode=data.get("attack_mode", ""),
        condition_effect=condition_effect_from_dict(data.get("condition_effect")),
        reach_feet=data.get("reach_feet"),
        normal_range_feet=data.get("normal_range_feet"),
        long_range_feet=data.get("long_range_feet"),
        unmodeled_effects=data.get("unmodeled_effects", ()),
        reroll_damage_at_or_below=data.get("reroll_damage_at_or_below", 0),
        action_type=data.get("action_type", "action"),
        limited_uses=data.get("limited_uses"),
        recharge_min_roll=data.get("recharge_min_roll"),
        spell_slot_level=data.get("spell_slot_level"),
        spell_slot_pool=data.get("spell_slot_pool", "spellcasting"),
        allow_upcast=data.get("allow_upcast", False),
        upcast_damage_dice=tuple(DamageDice(**d) for d in data.get("upcast_damage_dice", ())),
    )
    loaded_profiles = []
    for profile_data in data.get("attack_profiles", []):
        try:
            profile_dice = tuple(
                DamageDice(dice["number"], dice["sides"])
                for dice in profile_data["damage_dice"]
            )
            loaded_profiles.append(
                AttackProfile(
                    name=profile_data["name"],
                    attack_bonus=profile_data["attack_bonus"],
                    damage_dice=profile_dice,
                    damage_modifier=profile_data.get("damage_modifier", 0),
                    damage_type=profile_data.get("damage_type", ""),
                    attack_mode=profile_data.get("attack_mode", ""),
                    condition_effect=condition_effect_from_dict(profile_data.get("condition_effect")),
                    reach_feet=profile_data.get("reach_feet"),
                    normal_range_feet=profile_data.get("normal_range_feet"),
                    long_range_feet=profile_data.get("long_range_feet"),
                    unmodeled_effects=profile_data.get(
                        "unmodeled_effects", ()
                    ),
                    reroll_damage_at_or_below=profile_data.get(
                        "reroll_damage_at_or_below", 0
                    ),
                    action_type=profile_data.get("action_type", "action"),
                    limited_uses=profile_data.get("limited_uses"),
                    recharge_min_roll=profile_data.get("recharge_min_roll"),
                    spell_slot_level=profile_data.get("spell_slot_level"),
                    spell_slot_pool=profile_data.get("spell_slot_pool", "spellcasting"),
                    allow_upcast=profile_data.get("allow_upcast", False),
                    upcast_damage_dice=tuple(DamageDice(**d) for d in profile_data.get("upcast_damage_dice", ())),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if loaded_profiles:
        matching_primary = next(
            (
                profile
                for profile in loaded_profiles
                if profile.name == primary_profile.name
            ),
            None,
        )
        primary_profile = matching_primary or loaded_profiles[0]

    loaded_save_profiles = []
    for profile_data in data.get("saving_throw_profiles", []):
        try:
            loaded_save_profiles.append(
                SavingThrowDamageProfile(
                    name=profile_data["name"],
                    difficulty_class=profile_data["difficulty_class"],
                    damage_dice=tuple(
                        DamageDice(dice["number"], dice["sides"])
                        for dice in profile_data["damage_dice"]
                    ),
                    damage_modifier=profile_data.get("damage_modifier", 0),
                    damage_on_success=SaveSuccessDamage(
                        profile_data.get("damage_on_success", "no_damage")
                    ),
                    save_ability=profile_data.get("save_ability", ""),
                    damage_type=profile_data.get("damage_type", ""),
                    action_type=profile_data.get("action_type", "action"),
                    limited_uses=profile_data.get("limited_uses"),
                    recharge_min_roll=profile_data.get("recharge_min_roll"),
                    spell_slot_level=profile_data.get("spell_slot_level"),
                    spell_slot_pool=profile_data.get("spell_slot_pool", "spellcasting"),
                    allow_upcast=profile_data.get("allow_upcast", False),
                    upcast_damage_dice=tuple(DamageDice(**d) for d in profile_data.get("upcast_damage_dice", ())),
                    range_feet=profile_data.get("range_feet"),
                    unmodeled_effects=profile_data.get("unmodeled_effects", ()),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    profiles_by_name = {profile.name: profile for profile in loaded_profiles}
    loaded_turn_plans = []
    for plan_data in data.get("turn_plans", []):
        try:
            scenarios = tuple(
                AttackScenario(
                    scenario_data["name"],
                    profiles_by_name[scenario_data["attack_name"]],
                    tuple(
                        DamageDice(dice["number"], dice["sides"])
                        for dice in scenario_data.get("bonus_damage_dice", [])
                    ),
                    advantage=scenario_data.get("advantage", False),
                    disadvantage=scenario_data.get("disadvantage", False),
                )
                for scenario_data in plan_data["attacks"]
            )
            bonus_data = plan_data.get("first_hit_bonus_damage")
            first_hit_bonus = None
            if bonus_data is not None:
                first_hit_bonus = FirstHitBonusDamage(
                    bonus_data["name"],
                    tuple(
                        DamageDice(dice["number"], dice["sides"])
                        for dice in bonus_data["damage_dice"]
                    ),
                    tuple(bonus_data["eligible_attack_indices"]),
                    requires_advantage=bonus_data.get("requires_advantage", False),
                    allows_nearby_ally=bonus_data.get("allows_nearby_ally", False),
                )
            loaded_turn_plans.append(
                TurnPlan(plan_data["name"], scenarios, first_hit_bonus)
            )
        except (KeyError, TypeError, ValueError):
            continue

    return CharacterBuild(
        name=data.get("name", "Loaded build"),
        attack_profile=primary_profile,
        armor_class=data.get("armor_class", 16),
        max_hp=data.get("max_hp", 20),
        save_bonus=data.get("save_bonus", 2),
        initiative_bonus=int(data.get("initiative_bonus", 0) or 0),
        attacks_per_action=int(data.get("attacks_per_action", 1) or 1),
        description=data.get("description", ""),
        equipment=tuple(data.get("equipment", [])),
        attack_profiles=tuple(loaded_profiles) if loaded_profiles else (primary_profile,),
        saving_throw_profiles=tuple(loaded_save_profiles),
        spell_slots=data.get("spell_slots", ()),
        pact_slots=data.get("pact_slots", ()),
        spell_slot_capacity=data.get("spell_slot_capacity", ()),
        pact_slot_capacity=data.get("pact_slot_capacity", ()),
        pack_tactics=data.get("pack_tactics", False),
        aggressive=data.get("aggressive", False),
        nimble_escape=data.get("nimble_escape", False),
        stealth_bonus=data.get("stealth_bonus", 0),
        passive_perception=data.get("passive_perception", 10),

        saving_throw_bonuses=data.get("saving_throw_bonuses", ()),
        damage_resistances=data.get("damage_resistances", ()),
        damage_vulnerabilities=data.get("damage_vulnerabilities", ()),
        damage_immunities=data.get("damage_immunities", ()),
        condition_immunities=data.get("condition_immunities", ()),
        creature_tags=data.get("creature_tags", ()),
        turn_plans=tuple(loaded_turn_plans),
    )
