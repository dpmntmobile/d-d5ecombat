"""Pure construction and formatting helpers shared by user interfaces."""

from .models import AttackScenario, DuelCombatant, DuelMatchup, SavingThrowScenario
from .simulation import select_attack_sequence, select_best_attack
from .resource_models import duel_save_actions


def build_custom_attack_scenarios(
    selected_build=None,
    include_advantage=False,
    include_disadvantage=False,
):
    if selected_build is None:
        raise ValueError("selected_build is required")
    profiles = tuple(selected_build.attack_profiles)
    if not profiles:
        raise ValueError("selected_build must contain at least one attack profile")

    scenarios = []
    for profile in profiles:
        scenarios.append(AttackScenario(profile.name, profile))
        if include_advantage:
            scenarios.append(
                AttackScenario(
                    f"{profile.name} with advantage",
                    profile,
                    advantage=True,
                )
            )
        if include_disadvantage:
            scenarios.append(
                AttackScenario(
                    f"{profile.name} with disadvantage",
                    profile,
                    disadvantage=True,
                )
            )
    return tuple(scenarios)


def build_save_scenarios(selected_build, target_save_bonus=2, target_profile=None):
    if selected_build is None:
        return ()
    return tuple(
        SavingThrowScenario(
            profile.name,
            profile,
            target_profile.get_saving_throw_bonus(
                profile.save_ability, target_save_bonus
            )
            if target_profile is not None
            else target_save_bonus,
        )
        for profile in selected_build.saving_throw_profiles
    )


def format_damage_profile(attack, bonus_damage_dice=()):
    damage_dice = attack.damage_dice + tuple(bonus_damage_dice)
    dice_text = "+".join(
        f"{pool.number}d{pool.sides}" for pool in damage_dice
    )
    if attack.damage_modifier:
        dice_text += f"{attack.damage_modifier:+d}"
    if attack.reroll_damage_at_or_below:
        dice_text += f" (reroll 1-{attack.reroll_damage_at_or_below} once)"
    return dice_text


def build_duel_policy_matchups(
    build,
    monster,
    character_initiative_bonus=None,
    monster_initiative_bonus=None,
    starting_distance_feet=None,
    character_speed_feet=30,
    monster_speed_feet=30,
    character_ally_near_target=False,
    monster_ally_near_target=False,
    character_can_hide=False,
    monster_can_hide=False,
    rest_before_duel="none",
):
    """Build one matchup for every legal monster attack action."""
    monster_saves = duel_save_actions(monster.saving_throw_profiles)
    if not monster.attack_profiles and not monster_saves:
        return ()
    legal_character_attacks = tuple(
        attack
        for attack in build.attack_profiles
        if attack.action_type == "action"
    ) or build.attack_profiles
    character_attack = select_best_attack(
        legal_character_attacks,
        monster.armor_class,
        monster.damage_resistances,
        monster.damage_vulnerabilities,
        monster.damage_immunities,
        undead_fortitude=monster.undead_fortitude,
        target_hp=monster.max_hp,
        constitution_save_bonus=monster.get_saving_throw_bonus("con"),
        attacks_per_action=build.attacks_per_action,
    )
    if monster.multiattack:
        monster_sequences = (
            select_attack_sequence(
                monster.attack_profiles,
                monster.multiattack,
                build.armor_class,
                build.damage_resistances,
                build.damage_vulnerabilities,
                build.damage_immunities,
            ),
        )
    else:
        monster_sequences = tuple(
            (attack,) for attack in monster.attack_profiles if attack.action_type == "action"
        ) or ((),)

    character_initiative = (
        build.initiative_bonus
        if character_initiative_bonus is None
        else character_initiative_bonus
    )
    monster_initiative = (
        monster.initiative_bonus
        if monster_initiative_bonus is None
        else monster_initiative_bonus
    )
    matchups = []
    for monster_sequence in monster_sequences:
        matchups.append(
            DuelMatchup(
                DuelCombatant(
                    build.name,
                    build.armor_class,
                    build.max_hp,
                    character_initiative,
                    character_attack,
                    attacks_per_turn=build.attacks_per_action,
                    saving_throw_bonuses=build.saving_throw_bonuses,
                    damage_resistances=build.damage_resistances,
                    damage_vulnerabilities=build.damage_vulnerabilities,
                    damage_immunities=build.damage_immunities,
                    condition_immunities=build.condition_immunities,
                    creature_tags=build.creature_tags,
                    spell_slots=getattr(build, "spell_slots", ()),
                    pact_slots=getattr(build, "pact_slots", ()),
                    spell_slot_capacity=getattr(build, "spell_slot_capacity", ()),
                    pact_slot_capacity=getattr(build, "pact_slot_capacity", ()),

                    pack_tactics=getattr(build, "pack_tactics", False),
                    aggressive=getattr(build, "aggressive", False),
                    nimble_escape=getattr(build, "nimble_escape", False),
                    stealth_bonus=getattr(build, "stealth_bonus", 0),
                    passive_perception=getattr(build, "passive_perception", 10),

                    bonus_attacks=tuple(a for a in build.attack_profiles if a.action_type == "bonus_action" and a.spell_slot_level is not None),
                    saving_throw_profiles=duel_save_actions(getattr(build, "saving_throw_profiles", ())),
                    fallback_attacks=tuple(a for a in legal_character_attacks if a.action_type == "action"),
                    turn_plans=getattr(build, "turn_plans", ()),
                ),
                DuelCombatant(
                    monster.name,
                    monster.armor_class,
                    monster.max_hp,
                    monster_initiative,
                    monster_sequence[0] if monster_sequence else None,
                    attack_sequence=monster_sequence,
                    saving_throw_bonuses=monster.saving_throw_bonuses,
                    damage_resistances=monster.damage_resistances,
                    damage_vulnerabilities=monster.damage_vulnerabilities,
                    damage_immunities=monster.damage_immunities,
                    condition_immunities=monster.condition_immunities,
                    creature_tags=monster.creature_tags,
                    undead_fortitude=monster.undead_fortitude,
                    spell_slots=monster.spell_slots,
                    pact_slots=monster.pact_slots,
                    spell_slot_capacity=getattr(monster, "spell_slot_capacity", ()),
                    pact_slot_capacity=getattr(monster, "pact_slot_capacity", ()),

                    turn_plans=monster.turn_plans,
                    pack_tactics=monster.pack_tactics,
                    aggressive=monster.aggressive,
                    nimble_escape=monster.nimble_escape,
                    stealth_bonus=monster.stealth_bonus,
                    passive_perception=monster.passive_perception,

                    bonus_attacks=tuple(a for a in monster.attack_profiles if a.action_type == "bonus_action"),
                    saving_throw_profiles=monster_saves,
                    fallback_attacks=tuple(a for a in monster.attack_profiles if a.action_type == "action"),
                ),
                starting_distance_feet=starting_distance_feet,
                character_speed_feet=character_speed_feet,
                monster_speed_feet=monster_speed_feet,
                character_ally_near_target=character_ally_near_target,
                monster_ally_near_target=monster_ally_near_target,
                character_can_hide=character_can_hide,
                monster_can_hide=monster_can_hide,
                rest_before_duel=rest_before_duel,

            )
        )
    return tuple(matchups)
