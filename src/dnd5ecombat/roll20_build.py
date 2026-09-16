"""Convert mapped Roll20 data into validated character domain models."""

from typing import Optional

from .character_models import CharacterBuild
from .models import (
    AttackProfile,
    AttackScenario,
    FirstHitBonusDamage,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
    TurnPlan,
)
from .roll20_fields import parse_damage_dice


def build_from_roll20_with_attack(
    roll20_data: dict,
    attack_bonus: int,
    damage_dice_text: str,
    damage_modifier: int,
    equipment_text: str = "",
    selected_attack_name: Optional[str] = None,
) -> CharacterBuild:
    """Convert Roll20 import data to a CharacterBuild with weapon/attack details."""
    if not roll20_data:
        raise ValueError("Invalid Roll20 data.")

    damage_dice = parse_damage_dice(damage_dice_text)
    equipment = tuple(
        item.strip() for item in equipment_text.split(",") if item.strip()
    ) if equipment_text else ()

    manual_profile = AttackProfile(
        name=f"{roll20_data['name']} attack",
        attack_bonus=attack_bonus,
        damage_dice=damage_dice,
        damage_modifier=damage_modifier,
    )
    selected_profile = manual_profile

    parsed_profiles = []
    if isinstance(roll20_data.get("attacks"), list):
        for attack in roll20_data["attacks"]:
            if "name" not in attack or "damage_dice" not in attack:
                continue
            if "bonus" not in attack:
                continue
            try:
                profile_damage_modifier = int(attack.get("damage_modifier", damage_modifier))
                parsed_profiles.append(
                    AttackProfile(
                        name=attack["name"],
                        attack_bonus=int(attack["bonus"]),
                        damage_dice=parse_damage_dice(attack["damage_dice"]),
                        damage_modifier=profile_damage_modifier,
                        damage_type=str(attack.get("damage_type", "")),
                        attack_mode=str(attack.get("attack_mode", "")),
                        normal_range_feet=attack.get("normal_range_feet"),
                        long_range_feet=attack.get("long_range_feet"),
                        action_type=attack.get("action_type", "action"),
                        spell_slot_level=attack.get("spell_slot_level"),
                        spell_slot_pool=attack.get("spell_slot_pool", "spellcasting"),
                        allow_upcast=attack.get("allow_upcast", False),
                        upcast_damage_dice=parse_damage_dice(attack["upcast_damage_dice"]) if attack.get("upcast_damage_dice") else (),
                        reach_feet=attack.get("reach_feet"),
                        unmodeled_effects=attack.get("unmodeled_effects", ()),
                        reroll_damage_at_or_below=int(
                            attack.get("reroll_damage_at_or_below", 0)
                        ),
                    )
                )
            except (TypeError, ValueError):
                continue

    if parsed_profiles:
        selected_profile = parsed_profiles[0]
        named_profile = next(
            (profile for profile in parsed_profiles if profile.name == selected_attack_name),
            None,
        )
        matching_profile = next(
            (
                profile
                for profile in parsed_profiles
                if profile.attack_bonus == attack_bonus
                and profile.damage_dice == damage_dice
                and profile.damage_modifier == damage_modifier
            ),
            None,
        )
        if named_profile is not None:
            selected_profile = named_profile
        elif matching_profile is not None:
            selected_profile = matching_profile
        else:
            selected_profile = manual_profile

    available_profiles = tuple(parsed_profiles)
    if selected_profile not in available_profiles:
        available_profiles = (selected_profile,) + available_profiles

    saving_throw_profiles = []
    for save_attack in roll20_data.get("saving_throw_attacks", []):
        try:
            saving_throw_profiles.append(
                SavingThrowDamageProfile(
                    name=save_attack["name"],
                    difficulty_class=int(save_attack["save_dc"]),
                    damage_dice=parse_damage_dice(save_attack["damage_dice"]),
                    damage_modifier=int(save_attack.get("damage_modifier", 0)),
                    damage_on_success=SaveSuccessDamage(
                        save_attack.get("damage_on_success", "no_damage")
                    ),
                    save_ability=save_attack.get("save_ability", ""),
                    damage_type=save_attack.get("damage_type", ""),
                    action_type=save_attack.get("action_type", "action"),
                    unmodeled_effects=save_attack.get("unmodeled_effects", ()),
                    spell_slot_level=save_attack.get("spell_slot_level"),
                    spell_slot_pool=save_attack.get("spell_slot_pool", "spellcasting"),
                    allow_upcast=save_attack.get("allow_upcast", False),
                    upcast_damage_dice=parse_damage_dice(save_attack["upcast_damage_dice"]) if save_attack.get("upcast_damage_dice") else (),
                    range_feet=save_attack.get("range_feet"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    profiles_by_name = {profile.name: profile for profile in available_profiles}
    turn_plans = []
    for spec in roll20_data.get("turn_plan_specs", ()):
        try:
            plan_attacks = []
            eligible_indices = []
            for original_index, attack_name in enumerate(spec["attack_names"]):
                attack = profiles_by_name[attack_name]
                count = (roll20_data.get("attacks_per_action", 1)
                         if attack.action_type == "action" and attack.spell_slot_level is None else 1)
                if original_index in spec.get("first_hit_bonus_indices", ()):
                    eligible_indices.extend(range(len(plan_attacks), len(plan_attacks) + count))
                plan_attacks.extend((AttackScenario(attack_name, attack),) * count)
            first_hit_bonus = None
            if spec.get("first_hit_bonus_damage"):
                first_hit_bonus = FirstHitBonusDamage(
                    spec.get("first_hit_bonus_name", "First-hit bonus"),
                    parse_damage_dice(spec["first_hit_bonus_damage"]),
                    tuple(eligible_indices),
                    requires_advantage=spec.get("first_hit_requires_advantage", False),
                    allows_nearby_ally=spec.get("first_hit_allows_nearby_ally", False),
                )
            turn_plans.append(
                TurnPlan(spec["name"], plan_attacks, first_hit_bonus)
            )
        except (KeyError, TypeError, ValueError):
            continue

    return CharacterBuild(
        name=roll20_data["name"],
        attack_profile=selected_profile,
        armor_class=roll20_data["armor_class"],
        max_hp=roll20_data["max_hp"],
        save_bonus=roll20_data["save_bonus"],
        initiative_bonus=roll20_data.get("initiative_bonus", 0),
        attacks_per_action=roll20_data.get("attacks_per_action", 1),
        description=f"{roll20_data['class']} {roll20_data['level']} ({roll20_data['race']}) - imported from Roll20.",
        equipment=equipment,
        attack_profiles=available_profiles or (selected_profile,),
        saving_throw_profiles=tuple(saving_throw_profiles),
        saving_throw_bonuses=roll20_data.get("saving_throw_bonuses", ()),
        damage_resistances=roll20_data.get("damage_resistances", ()),
        damage_vulnerabilities=roll20_data.get("damage_vulnerabilities", ()),
        damage_immunities=roll20_data.get("damage_immunities", ()),
        condition_immunities=roll20_data.get("condition_immunities", ()),
        creature_tags=roll20_data.get("creature_tags", ()),
        turn_plans=tuple(turn_plans),
        spell_slots=roll20_data.get("spell_slots", ()),
        pact_slots=roll20_data.get("pact_slots", ()),
        spell_slot_capacity=roll20_data.get("spell_slot_capacity", ()),
        pact_slot_capacity=roll20_data.get("pact_slot_capacity", ()),
        stealth_bonus=roll20_data.get("stealth_bonus", 0),
        passive_perception=roll20_data.get("passive_perception", 10),
    )
