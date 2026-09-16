"""Validation and JSON persistence for monster profiles."""

import json
import os
from pathlib import Path

from .dice_parser import extract_damage_dice
from .turn_plan_persistence import plan_from_dict, plan_to_dict
from .models import (
    AttackProfile,
    Condition,
    SavingThrowConditionEffect,
    SavingThrowDamageProfile,
    SaveSuccessDamage,
    TargetProfile,
)
from .profile_schema import CURRENT_PROFILE_SCHEMA_VERSION, validate_profile


def parse_damage_dice(text):
    if not isinstance(text, str):
        raise TypeError("damage_dice must be a string")
    try:
        return extract_damage_dice(text)
    except ValueError:
        raise ValueError("damage_dice must use a format such as 1d8 or 2d6")


def _load_attack(data, attack_index):
    if not isinstance(data, dict):
        raise TypeError(f"monster attack {attack_index} must be a JSON object")
    supported = {
        "name",
        "attack_bonus",
        "damage_dice",
        "damage_modifier",
        "damage_type",
        "attack_mode",
        "reach_feet",
        "normal_range_feet",
        "long_range_feet",
        "unmodeled_effects",
        "condition_effect",
        "limited_uses",
        "recharge_min_roll",
        "spell_slot_level",
        "spell_slot_pool", "allow_upcast", "upcast_damage_dice", "action_type",
    }
    unsupported = sorted(set(data) - supported)
    if unsupported:
        raise ValueError(
            f"unsupported field(s) in monster attack {attack_index}: "
            + ", ".join(unsupported)
        )
    missing = sorted({"name", "attack_bonus", "damage_dice"} - set(data))
    if missing:
        raise ValueError(
            f"missing required field(s) in monster attack {attack_index}: "
            + ", ".join(missing)
        )
    effect_data = data.get("condition_effect")
    condition_effect = None
    if effect_data is not None:
        if not isinstance(effect_data, dict):
            raise TypeError(
                f"condition_effect in monster attack {attack_index} must be an object"
            )
        effect_fields = {
            "difficulty_class",
            "save_ability",
            "condition",
            "repeat_save_at_end_of_turn",
            "duration_turns",
            "immune_creature_tags",
        }
        unsupported_effect_fields = sorted(set(effect_data) - effect_fields)
        if unsupported_effect_fields:
            raise ValueError(
                f"unsupported condition_effect field(s) in monster attack "
                f"{attack_index}: " + ", ".join(unsupported_effect_fields)
            )
        missing_effect_fields = sorted(
            {"difficulty_class", "save_ability", "condition"} - set(effect_data)
        )
        if missing_effect_fields:
            raise ValueError(
                f"missing condition_effect field(s) in monster attack "
                f"{attack_index}: " + ", ".join(missing_effect_fields)
            )
        condition_effect = SavingThrowConditionEffect(
            difficulty_class=effect_data["difficulty_class"],
            save_ability=effect_data["save_ability"],
            condition=Condition(effect_data["condition"]),
            duration_turns=effect_data.get("duration_turns"),
            repeat_save_at_end_of_turn=effect_data.get(
                "repeat_save_at_end_of_turn", False
            ),
            immune_creature_tags=effect_data.get("immune_creature_tags", ()),
        )

    return AttackProfile(
        name=data["name"],
        attack_bonus=data["attack_bonus"],
        damage_dice=parse_damage_dice(data["damage_dice"]),
        damage_modifier=data.get("damage_modifier", 0),
        damage_type=data.get("damage_type", ""),
        attack_mode=data.get("attack_mode", ""),
        reach_feet=data.get("reach_feet"),
        normal_range_feet=data.get("normal_range_feet"),
        long_range_feet=data.get("long_range_feet"),
        unmodeled_effects=data.get("unmodeled_effects", ()),
        condition_effect=condition_effect,
        limited_uses=data.get("limited_uses"),
        recharge_min_roll=data.get("recharge_min_roll"),
        spell_slot_level=data.get("spell_slot_level"),
        spell_slot_pool=data.get("spell_slot_pool", "spellcasting"),
        allow_upcast=data.get("allow_upcast", False),
        upcast_damage_dice=parse_damage_dice(data["upcast_damage_dice"]) if data.get("upcast_damage_dice") else (),
        action_type=data.get("action_type", "action"),
    )


def monster_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("monster file must contain a JSON object")
    supported = {
        "schema_version",
        "name",
        "armor_class",
        "max_hp",
        "initiative_bonus",
        "saving_throw_bonuses",
        "ruleset",
        "source_url",
        "unmodeled_traits",
        "attacks",
        "damage_resistances",
        "damage_vulnerabilities",
        "damage_immunities",
        "condition_immunities",
        "creature_tags",
        "multiattack", "turn_plans",
        "spell_slots", "pact_slots", "spell_slot_capacity", "pact_slot_capacity",
        "pack_tactics", "aggressive", "nimble_escape", "stealth_bonus", "passive_perception",
        "saving_throw_profiles",
        "undead_fortitude",
    }
    unsupported = sorted(set(data) - supported)
    if unsupported:
        raise ValueError("unsupported monster field(s): " + ", ".join(unsupported))
    missing = sorted({"name", "armor_class", "max_hp"} - set(data))
    if missing:
        raise ValueError("missing required monster field(s): " + ", ".join(missing))
    attacks = data.get("attacks", ())
    if not isinstance(attacks, (list, tuple)):
        raise TypeError("monster attacks must be a JSON array")
    profiles = tuple(_load_attack(attack, index) for index, attack in enumerate(attacks, start=1))
    try:
        plans = tuple(plan_from_dict(plan, profiles) for plan in data.get("turn_plans", ()))
    except KeyError as error:
        raise ValueError(f"turn plan references missing attack or field: {error.args[0]}") from error
    return TargetProfile(
        name=data["name"],
        armor_class=data["armor_class"],
        max_hp=data["max_hp"],
        initiative_bonus=data.get("initiative_bonus", 0),
        saving_throw_bonuses=data.get("saving_throw_bonuses", ()),
        ruleset=data.get("ruleset", ""),
        source_url=data.get("source_url", ""),
        unmodeled_traits=data.get("unmodeled_traits", ()),
        attack_profiles=profiles,
        damage_resistances=data.get("damage_resistances", ()),
        damage_vulnerabilities=data.get("damage_vulnerabilities", ()),
        damage_immunities=data.get("damage_immunities", ()),
        condition_immunities=data.get("condition_immunities", ()),
        creature_tags=data.get("creature_tags", ()),
        multiattack=data.get("multiattack", ()),
        turn_plans=plans,
        spell_slots=data.get("spell_slots", ()),
        pact_slots=data.get("pact_slots", ()),
        spell_slot_capacity=data.get("spell_slot_capacity", ()),
        pact_slot_capacity=data.get("pact_slot_capacity", ()),
        pack_tactics=data.get("pack_tactics", False),
        aggressive=data.get("aggressive", False),
        nimble_escape=data.get("nimble_escape", False),
        stealth_bonus=data.get("stealth_bonus", 0),
        passive_perception=data.get("passive_perception", 10),

        saving_throw_profiles=tuple(save_action_from_dict(effect) for effect in data.get("saving_throw_profiles", ())),
        undead_fortitude=data.get("undead_fortitude", False),
    )


def load_monster_profile(filename):
    with open(filename, "r", encoding="utf-8") as source:
        data = json.load(source)
    data = validate_profile(data, "monster", source=filename)
    return monster_from_dict(data)


def _dice_text(attack):
    return "+".join(
        f"{pool.number}d{pool.sides}" for pool in attack.damage_dice
    )


def monster_to_dict(monster):
    data = {
        "schema_version": CURRENT_PROFILE_SCHEMA_VERSION,
        "name": monster.name,
        "armor_class": monster.armor_class,
        "max_hp": monster.max_hp,
        "initiative_bonus": monster.initiative_bonus,
        "saving_throw_bonuses": dict(monster.saving_throw_bonuses),
        "ruleset": monster.ruleset,
        "source_url": monster.source_url,
        "unmodeled_traits": list(monster.unmodeled_traits),
        "damage_resistances": list(monster.damage_resistances),
        "damage_vulnerabilities": list(monster.damage_vulnerabilities),
        "damage_immunities": list(monster.damage_immunities),
        "condition_immunities": list(monster.condition_immunities),
        "creature_tags": list(monster.creature_tags),
        "multiattack": list(monster.multiattack),
        "turn_plans": [plan_to_dict(plan) for plan in monster.turn_plans],
        "spell_slots": {str(level): count for level, count in monster.spell_slots},
        "pact_slots": {str(level): count for level, count in monster.pact_slots},
        "spell_slot_capacity": {str(level): count for level, count in monster.spell_slot_capacity},
        "pact_slot_capacity": {str(level): count for level, count in monster.pact_slot_capacity},
        "pack_tactics": monster.pack_tactics,
        "aggressive": monster.aggressive,
        "nimble_escape": monster.nimble_escape,
        "stealth_bonus": monster.stealth_bonus,
        "passive_perception": monster.passive_perception,

        "saving_throw_profiles": [save_action_to_dict(effect) for effect in monster.saving_throw_profiles],
        "undead_fortitude": monster.undead_fortitude,
        "attacks": [
            {
                "name": attack.name,
                "limited_uses": attack.limited_uses,
                "recharge_min_roll": attack.recharge_min_roll,
                "spell_slot_level": attack.spell_slot_level,
                **casting_to_dict(attack),
                "action_type": attack.action_type,
                "attack_bonus": attack.attack_bonus,
                "damage_dice": _dice_text(attack),
                "damage_modifier": attack.damage_modifier,
                "damage_type": attack.damage_type,
                "attack_mode": attack.attack_mode,
                "reach_feet": attack.reach_feet,
                "normal_range_feet": attack.normal_range_feet,
                "long_range_feet": attack.long_range_feet,
                "unmodeled_effects": list(attack.unmodeled_effects),
                "condition_effect": (
                    {
                        "difficulty_class": attack.condition_effect.difficulty_class,
                        "save_ability": attack.condition_effect.save_ability,
                        "condition": attack.condition_effect.condition.value,
                        "duration_turns": attack.condition_effect.duration_turns,
                        "repeat_save_at_end_of_turn": (
                            attack.condition_effect.repeat_save_at_end_of_turn
                        ),
                        "immune_creature_tags": list(
                            attack.condition_effect.immune_creature_tags
                        ),
                    }
                    if attack.condition_effect is not None
                    else None
                ),
            }
            for attack in monster.attack_profiles
        ],
    }
    return validate_profile(data, "monster")


def save_monster_profile(monster, filename):
    destination = Path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as output:
            json.dump(monster_to_dict(monster), output, indent=2)
            output.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def save_action_from_dict(data):
    return SavingThrowDamageProfile(
        name=data["name"], difficulty_class=data["difficulty_class"],
        damage_dice=parse_damage_dice(data["damage_dice"]),
        damage_modifier=data.get("damage_modifier", 0),
        damage_on_success=SaveSuccessDamage(data.get("damage_on_success", "no_damage")),
        save_ability=data["save_ability"], damage_type=data.get("damage_type", ""),
        action_type=data.get("action_type", "action"),
        limited_uses=data.get("limited_uses"), recharge_min_roll=data.get("recharge_min_roll"),
        spell_slot_level=data.get("spell_slot_level"), range_feet=data.get("range_feet"),
        spell_slot_pool=data.get("spell_slot_pool", "spellcasting"),
        allow_upcast=data.get("allow_upcast", False),
        upcast_damage_dice=parse_damage_dice(data["upcast_damage_dice"]) if data.get("upcast_damage_dice") else (),
        unmodeled_effects=data.get("unmodeled_effects", ()),
    )


def save_action_to_dict(effect):
    return dict(name=effect.name, difficulty_class=effect.difficulty_class,
                damage_dice=_dice_text(effect), damage_modifier=effect.damage_modifier,
                damage_on_success=effect.damage_on_success.value,
                save_ability=effect.save_ability, damage_type=effect.damage_type,
                action_type=effect.action_type, limited_uses=effect.limited_uses,
                recharge_min_roll=effect.recharge_min_roll,
                spell_slot_level=effect.spell_slot_level, range_feet=effect.range_feet,
                unmodeled_effects=list(effect.unmodeled_effects), **casting_to_dict(effect))


def casting_to_dict(effect):
    return dict(spell_slot_pool=effect.spell_slot_pool, allow_upcast=effect.allow_upcast,
                upcast_damage_dice="+".join(f"{d.number}d{d.sides}" for d in effect.upcast_damage_dice))
