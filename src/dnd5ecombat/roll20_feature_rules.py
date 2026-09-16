"""Explicit 2014 Roll20 feature mapping rules, independent of file I/O.

Exact trait names select defense/fighting-style rules. Sneak Attack prefers
exported damage rows over descriptive dice. Turn rules enforce spell timing.
Unknown features are preserved by the reader without inferred combat effects.
"""

import re
from .roll20_fields import _group_repeating_rows


def map_traits(traits):
    known_trait_resistances = {
        "celestial resistance": ("necrotic", "radiant"),
        "hellish resistance": ("fire",),
    }
    known_trait_condition_immunities = {
        "fey ancestry": ("magical sleep",),
    }
    inferred_resistances = []
    inferred_condition_immunities = []
    for trait in traits:
        inferred_resistances.extend(
            known_trait_resistances.get(trait["name"].lower(), ())
        )
        inferred_condition_immunities.extend(
            known_trait_condition_immunities.get(trait["name"].lower(), ())
        )
    has_great_weapon_fighting = any(
        trait["name"].lower()
        in {
            "great weapon fighting",
            "fighting style: great weapon fighting",
        }
        for trait in traits
    )

    return (
        tuple(inferred_resistances),
        tuple(inferred_condition_immunities),
        has_great_weapon_fighting,
    )


def map_sneak_attack(traits, other_attrs):
    damage_modifier_groups = _group_repeating_rows(other_attrs, "global_damage_name")
    sneak_attack_dice = ""
    for fields in damage_modifier_groups.values():
        if str(fields.get("global_damage_name", "")).strip().lower() == "sneak attack":
            sneak_attack_dice = str(fields.get("global_damage_damage", "")).strip()
            break
    if not sneak_attack_dice:
        sneak_attack_trait = next(
            (trait for trait in traits if trait["name"].lower() == "sneak attack"),
            None,
        )
        if sneak_attack_trait:
            dice_match = re.search(
                r"extra\s+(\d+d\d+)\s+damage",
                sneak_attack_trait["description"],
                re.IGNORECASE,
            )
            if dice_match:
                sneak_attack_dice = dice_match.group(1)

    return sneak_attack_dice


def map_turn_plans(attacks, sneak_attack_dice=""):
    turn_plan_specs = []
    action_attacks = [attack for attack in attacks if attack["action_type"] == "action"]
    off_hand_attacks = [
        attack for attack in attacks if attack["action_type"] == "bonus_action"
    ]
    if sneak_attack_dice:
        for attack in action_attacks:
            if attack["sneak_attack_eligible"]:
                turn_plan_specs.append(
                    {
                        "name": f"{attack['name']} + Sneak Attack (when eligible)",
                        "attack_names": (attack["name"],),
                        "first_hit_bonus_name": "Sneak Attack",
                        "first_hit_bonus_damage": sneak_attack_dice,
                        "first_hit_bonus_indices": (0,),
                        "first_hit_requires_advantage": True,
                        "first_hit_allows_nearby_ally": True,
                    }
                )
    for main_attack in action_attacks:
        for off_hand_attack in off_hand_attacks:
            if off_hand_attack["spell_slot_level"] is None:
                if not main_attack["two_weapon_eligible"]:
                    continue
            elif main_attack["spell_slot_level"] not in (None, 0):
                # 2014: a bonus-action spell allows only an action cantrip.
                continue
            attack_names = (main_attack["name"], off_hand_attack["name"])
            spec = {
                "name": f"{main_attack['name']} + {off_hand_attack['name']}",
                "attack_names": attack_names,
            }
            if sneak_attack_dice:
                eligible_indices = tuple(
                    index
                    for index, attack in enumerate((main_attack, off_hand_attack))
                    if attack["sneak_attack_eligible"]
                )
                if eligible_indices:
                    spec.update(
                        {
                            "name": spec["name"] + " + Sneak Attack (when eligible)",
                            "first_hit_bonus_name": "Sneak Attack",
                            "first_hit_bonus_damage": sneak_attack_dice,
                            "first_hit_bonus_indices": eligible_indices,
                            "first_hit_requires_advantage": True,
                            "first_hit_allows_nearby_ally": True,
                        }
                    )
            turn_plan_specs.append(spec)

    return turn_plan_specs
