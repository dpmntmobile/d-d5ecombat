"""Read and map Roll20 JSON exports into simulator-neutral data."""

import json
import os
import re

from .profile_schema import validate_profile
from .roll20_feature_rules import map_traits, map_sneak_attack, map_turn_plans
from .roll20_spell_resources import (
    spell_level as parse_spell_level,
    spell_range,
    casting_pools,
    casting_capacities,
    upcast_dice,
    upcast_warnings,
)
from .roll20_fields import (
    _group_repeating_rows,
    _normalize_save_ability,
    _preferred_attack_name,
    _resolve_roll20_formula,
    _resolve_roll20_modifier,
    _roll20_action_type,
    _roll20_flag_enabled,
    parse_damage_dice,
)


def import_from_roll20(roll20_json_file):
    """Import character data from a Roll20 character sheet JSON export."""
    if not os.path.exists(roll20_json_file):
        return None

    try:
        with open(roll20_json_file, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            decoded_content = content.encode("utf-8").decode("unicode-escape")
            data = json.loads(decoded_content)
    except (json.JSONDecodeError, IOError, UnicodeDecodeError, AttributeError):
        return None

    data = validate_profile(data, "roll20-character", source=roll20_json_file)

    name = data.get("name", "Roll20 Import")
    hp_level = data.get("hp_and_level", {})
    max_hp = hp_level.get("hp", {}).get("max", 20)
    armor_class = hp_level.get("ac", {}).get("current", 16)
    proficiency_bonus = int(hp_level.get("pb", {}).get("current", "2") or "2")

    stats = data.get("stats", {})
    strength_mod = stats.get("strength_mod", {}).get("current", 0)
    dexterity_mod = stats.get("dexterity_mod", {}).get("current", 0)
    wisdom_mod = stats.get("wisdom_mod", {}).get("current", 0)

    char_class = hp_level.get("class", {}).get("current", "Fighter")
    race = hp_level.get("race", {}).get("current", "Human")
    level = hp_level.get("level", {}).get("current", 1)

    other_attrs = data.get("other_attributes", {})
    ordinary_slots, pact_slots = casting_pools(data)
    ordinary_capacity, pact_capacity = casting_capacities(data)
    wisdom_save = other_attrs.get("wisdom_save_bonus", {}).get("current", wisdom_mod)
    save_bonus = int(wisdom_save) if wisdom_save else wisdom_mod
    initiative_bonus = int(hp_level.get("initiative_bonus", {}).get("current", 0) or 0)
    attacks_per_action_value = data.get("attacks_per_action")
    if attacks_per_action_value is None:
        attacks_per_action_value = other_attrs.get("attacks_per_action", {}).get(
            "current", 1
        )
    try:
        attacks_per_action = int(attacks_per_action_value or 1)
    except (TypeError, ValueError):
        attacks_per_action = 1
    if attacks_per_action < 1:
        attacks_per_action = 1

    stat_lookup = {
        "strength_mod": int(strength_mod) if strength_mod else 0,
        "dexterity_mod": int(dexterity_mod) if dexterity_mod else 0,
        "wisdom_mod": int(wisdom_mod) if wisdom_mod else 0,
        "constitution_mod": int(
            stats.get("constitution_mod", {}).get("current", 0) or 0
        ),
        "intelligence_mod": int(
            stats.get("intelligence_mod", {}).get("current", 0) or 0
        ),
        "charisma_mod": int(stats.get("charisma_mod", {}).get("current", 0) or 0),
        "pb": proficiency_bonus,
        "level": int(level) if level else 1,
        "spell_dc_mod": int(other_attrs.get("spell_dc_mod", {}).get("current", 0) or 0),
    }
    ability_names = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    saving_throw_bonuses = {}
    for short_name, long_name in ability_names.items():
        fallback = stat_lookup[f"{long_name}_mod"]
        raw_bonus = other_attrs.get(
            f"{long_name}_save_bonus", {"current": fallback}
        ).get("current", fallback)
        try:
            saving_throw_bonuses[short_name] = int(raw_bonus)
        except (TypeError, ValueError):
            saving_throw_bonuses[short_name] = fallback

    creature_type = str(other_attrs.get("creaturetype", {}).get("current", "")).strip()
    creature_tag_values = [
        value.strip().lower() for value in (str(race), creature_type) if value.strip()
    ]
    if any(re.search(r"\belf\b", value) for value in creature_tag_values):
        creature_tag_values.append("elf")
    if "drow" in creature_tag_values:
        creature_tag_values.append("elf")
    creature_tags = tuple(dict.fromkeys(creature_tag_values))

    attacks = []
    saving_throw_attacks = []
    attacks_section = data.get("attacks_and_spellcasting", {})
    traits_section = data.get("traits_and_features", {})
    inventory_section = data.get("inventory", {})
    other_repeating_section = data.get("other_repeating_attributes", {})

    spell_groups = _group_repeating_rows(other_repeating_section, "spellattackid")
    for prefix, fields in spell_groups.items():
        fields["mapped_spell_level"] = parse_spell_level(
            fields.get("spelllevel"), prefix
        )
    spells_by_attack_id = {
        str(fields.get("spellattackid", "")): fields
        for fields in spell_groups.values()
        if str(fields.get("spellattackid", ""))
    }

    trait_groups = _group_repeating_rows(traits_section, "name")

    traits = tuple(
        {
            "name": str(fields.get("name", "")).strip(),
            "description": str(fields.get("description", "")).strip(),
            "source": str(fields.get("source", "")).strip(),
            "source_type": str(fields.get("source_type", "")).strip(),
        }
        for _, fields in sorted(trait_groups.items())
        if str(fields.get("name", "")).strip()
    )
    inferred_resistances, inferred_condition_immunities, has_great_weapon_fighting = (
        map_traits(traits)
    )

    inventory_groups = {}
    for key, value in inventory_section.items():
        if not key.startswith("repeating_inventory_"):
            continue
        suffix = key[len("repeating_inventory_") :]
        if "_" not in suffix:
            continue
        item_id, field = suffix.split("_", 1)
        inventory_groups.setdefault(item_id, {})[field] = value.get("current", "")

    sneak_attack_dice = map_sneak_attack(traits, other_attrs)

    attack_groups = {
        prefix[len("repeating_attack_") :]: fields
        for prefix, fields in _group_repeating_rows(attacks_section, "atkname").items()
        if prefix.startswith("repeating_attack_")
    }

    for attack_id, fields in sorted(attack_groups.items()):
        spell_fields = spells_by_attack_id.get(attack_id, {})
        name_val = fields.get("atkname", "").strip()
        bonus_val = str(fields.get("atkbonus", "")).strip()
        dmg_base_val = str(fields.get("dmgbase", "")).strip()
        computed_damage_val = str(fields.get("atkdmgtype", "")).strip()
        dmg_type_val = str(fields.get("dmgtype", "")).strip()
        save_flag = str(fields.get("saveflag", "")).strip()
        spell_level = parse_spell_level(fields.get("spelllevel"))
        if spell_level is None:
            spell_level = spell_fields.get("mapped_spell_level")
        scaling_warnings = upcast_warnings(fields, spell_fields) if spell_level else ()
        spell_description = str(spell_fields.get("spelldescription", "")).strip()
        action_type = _roll20_action_type(
            spell_fields.get("spellcastingtime", ""), name_val
        )
        damage_attr = fields.get("dmgattr", "")
        raw_damage_mod = _resolve_roll20_modifier(damage_attr, stat_lookup)
        range_text = str(
            fields.get("atkrange", "") or spell_fields.get("spellrange", "")
        ).strip()
        mapped_spell_range = spell_range(range_text)
        item_properties = str(
            inventory_groups.get(str(fields.get("itemid", "")), {}).get(
                "itemproperties", ""
            )
        )
        range_match = re.search(r"(\d+)\s*/\s*(\d+)", range_text)
        single_range_match = re.search(r"(\d+)", range_text)
        normal_range_feet = None
        long_range_feet = None
        if range_match:
            normal_range_feet = int(range_match.group(1))
            long_range_feet = int(range_match.group(2))
        elif single_range_match:
            normal_range_feet = int(single_range_match.group(1))

        thrown = "thrown" in item_properties.lower()
        properties_lower = item_properties.lower()
        two_handed = "two-handed" in properties_lower or (
            "versatile" in properties_lower and "two-handed" in name_val.lower()
        )
        if range_text.lower() == "touch" or not range_text:
            attack_mode = "melee"
        elif thrown:
            attack_mode = "melee_or_ranged"
        else:
            attack_mode = "ranged"
        if spell_level is not None:
            normal_range_feet = mapped_spell_range
            long_range_feet = None
            attack_mode = (
                "melee"
                if (
                    range_text.lower() == "touch"
                    or str(spell_fields.get("spellattack", "")).lower() == "melee"
                )
                else "ranged"
            )

        if not name_val or not dmg_base_val:
            continue

        damage_text = dmg_base_val.lower()
        if "healing" in dmg_type_val.lower():
            continue
        if any(token in damage_text for token in ("healing", "temp_hp", "hp")):
            continue

        damage_dice_text = dmg_base_val
        if computed_damage_val:
            try:
                computed_pools = parse_damage_dice(computed_damage_val)
                damage_dice_text = "+".join(
                    f"{pool.number}d{pool.sides}" for pool in computed_pools
                )
            except ValueError:
                pass

        if _roll20_flag_enabled(save_flag, "save") and spell_level is not None:
            fallback_dc = int(
                other_attrs.get("spell_save_dc", {}).get("current", 0) or 0
            )
            save_dc = _resolve_roll20_formula(
                fields.get("savedc", ""), stat_lookup, default=fallback_dc
            )
            if save_dc < 1:
                continue
            save_effect = (
                str(fields.get("saveeffect", "")) + " " + spell_description
            ).lower()
            unmodeled_effects = list(scaling_warnings)
            if "move as far as" in spell_description.lower():
                unmodeled_effects.append("Forced movement is not modeled.")
            if "disadvantage on the next attack roll" in spell_description.lower():
                unmodeled_effects.append(
                    "Disadvantage on the target's next attack is not modeled."
                )
            if "subtract 1d4 from the next saving throw" in spell_description.lower():
                unmodeled_effects.append(
                    "The target's next-saving-throw penalty is not modeled."
                )
            if "automatically succeeds on the save" in spell_description.lower():
                unmodeled_effects.append(
                    "Automatic save success for specially immune targets is not modeled."
                )
            saving_throw_attacks.append(
                {
                    "name": name_val,
                    "save_dc": save_dc,
                    "save_ability": _normalize_save_ability(
                        fields.get("saveattr", "") or spell_fields.get("spellsave", "")
                    ),
                    "damage_dice": damage_dice_text,
                    "damage_type": dmg_type_val,
                    "damage_modifier": raw_damage_mod,
                    "damage_on_success": (
                        "half_damage" if "half" in save_effect else "no_damage"
                    ),
                    "action_type": action_type,
                    "spell_slot_level": spell_level,
                    "spell_slot_pool": "any" if spell_level else "spellcasting",
                    "allow_upcast": bool(spell_level) and not scaling_warnings,
                    "upcast_damage_dice": upcast_dice(fields, spell_fields)
                    if spell_level
                    else "",
                    "range_feet": mapped_spell_range,
                    "unmodeled_effects": tuple(unmodeled_effects),
                }
            )
            continue

        bonus_match = re.search(r"[-+]?\d+", bonus_val)
        if not bonus_match:
            if not bonus_val or bonus_val in {"-", "--"}:
                continue

        try:
            bonus_int = int(bonus_match.group(0)) if bonus_match else 0
        except ValueError:
            continue

        attacks.append(
            {
                "name": name_val,
                "bonus": bonus_int,
                "damage_dice": damage_dice_text,
                "damage_type": dmg_type_val,
                "damage_modifier": raw_damage_mod,
                "attack_mode": attack_mode,
                "normal_range_feet": normal_range_feet,
                "long_range_feet": long_range_feet,
                "action_type": action_type,
                "spell_slot_level": spell_level,
                "spell_slot_pool": "any" if spell_level else "spellcasting",
                "allow_upcast": bool(spell_level) and not scaling_warnings,
                "upcast_damage_dice": upcast_dice(fields, spell_fields)
                if spell_level
                else "",
                "reach_feet": mapped_spell_range
                if spell_level is not None and attack_mode == "melee"
                else None,
                "unmodeled_effects": scaling_warnings,
                "sneak_attack_eligible": (
                    spell_level is None
                    and ("finesse" in properties_lower or attack_mode == "ranged")
                ),
                "two_weapon_eligible": (
                    spell_level is None
                    and action_type == "action"
                    and attack_mode == "melee"
                    and "light" in properties_lower
                ),
                "reroll_damage_at_or_below": (
                    2
                    if has_great_weapon_fighting
                    and attack_mode == "melee"
                    and two_handed
                    else 0
                ),
            }
        )

    turn_plan_specs = map_turn_plans(attacks, sneak_attack_dice)

    primary_attack_name = _preferred_attack_name(attacks)

    return {
        "name": name,
        "class": char_class,
        "race": race,
        "level": level,
        "max_hp": int(max_hp) if max_hp else 20,
        "armor_class": int(armor_class) if armor_class else 16,
        "proficiency_bonus": proficiency_bonus,
        "strength_mod": int(strength_mod) if strength_mod else 0,
        "dexterity_mod": int(dexterity_mod) if dexterity_mod else 0,
        "wisdom_mod": int(wisdom_mod) if wisdom_mod else 0,
        "save_bonus": int(save_bonus) if save_bonus else 0,
        "initiative_bonus": initiative_bonus,
        "attacks_per_action": attacks_per_action,
        "attacks": attacks,
        "primary_attack_name": primary_attack_name,
        "saving_throw_attacks": saving_throw_attacks,
        "spell_slots": ordinary_slots,
        "pact_slots": pact_slots,
        "spell_slot_capacity": ordinary_capacity,
        "pact_slot_capacity": pact_capacity,
        "stealth_bonus": int(
            other_attrs.get("stealth_bonus", {}).get("current", dexterity_mod) or 0
        ),
        "passive_perception": int(
            other_attrs.get("passive_wisdom", {}).get(
                "current", 10 + int(wisdom_mod or 0)
            )
            or 10
        ),
        "turn_plan_specs": turn_plan_specs,
        "saving_throw_bonuses": saving_throw_bonuses,
        "damage_resistances": tuple(
            dict.fromkeys(
                tuple(data.get("damage_resistances", ())) + tuple(inferred_resistances)
            )
        ),
        "damage_vulnerabilities": data.get("damage_vulnerabilities", ()),
        "damage_immunities": data.get("damage_immunities", ()),
        "condition_immunities": tuple(
            dict.fromkeys(
                tuple(data.get("condition_immunities", ()))
                + tuple(inferred_condition_immunities)
            )
        ),
        "creature_tags": data.get("creature_tags", creature_tags),
        "traits": traits,
    }
