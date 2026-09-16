"""Character presets, prompts, and scenario construction for the CLI."""

from .character_models import CharacterBuild
from .character_profiles import get_build_file_path, parse_damage_dice, save_custom_build
from .models import AttackProfile, AttackScenario, DamageDice, TurnPlan
from .scenario_factory import (
    build_custom_attack_scenarios as create_attack_scenarios,
    build_save_scenarios as create_save_scenarios,
)


def build_character_presets():
    tobias = CharacterBuild(
        name="Tobias",
        attack_profile=AttackProfile(
            name="Tobias rapier",
            attack_bonus=5,
            damage_dice=(DamageDice(1, 8),),
            damage_modifier=3,
        ),
        armor_class=16,
        max_hp=20,
        save_bonus=2,
        description="A precise rapier fighter with reliable bonus damage.",
        equipment=("Rapier", "Leather armor", "Hand crossbow"),
    )
    brute = CharacterBuild(
        name="Brute",
        attack_profile=AttackProfile(
            name="Brute greatsword",
            attack_bonus=3,
            damage_dice=(DamageDice(2, 6),),
            damage_modifier=3,
        ),
        armor_class=15,
        max_hp=24,
        save_bonus=1,
        description="A heavy-hitting melee build that trades accuracy for damage.",
        equipment=("Greatsword", "Scale mail", "Shield"),
    )
    scout = CharacterBuild(
        name="Scout",
        attack_profile=AttackProfile(
            name="Scout shortbow",
            attack_bonus=5,
            damage_dice=(DamageDice(1, 8),),
            damage_modifier=2,
        ),
        armor_class=14,
        max_hp=18,
        save_bonus=3,
        description="A ranged striker that prefers mobility and precision.",
        equipment=("Shortbow", "Studded leather", "Dagger"),
    )
    return (tobias, brute, scout)



def prompt_custom_build(input_func=input, output_func=print, save_after=False):
    output_func("Create a custom character build:")
    name = input_func("Character name [Custom fighter]: ").strip() or "Custom fighter"
    attack_bonus = int((input_func("Attack bonus [5]: ").strip() or "5"))
    damage_text = input_func("Damage dice [1d8]: ").strip() or "1d8"
    damage_dice = parse_damage_dice(damage_text)
    damage_modifier = int((input_func("Damage modifier [0]: ").strip() or "0"))
    armor_class = int((input_func("Armor class [16]: ").strip() or "16"))
    max_hp = int((input_func("Max HP [20]: ").strip() or "20"))
    save_bonus = int((input_func("Save bonus [2]: ").strip() or "2"))

    equipment_value = input_func("Equipment (comma-separated) [none]: ").strip()
    equipment = tuple(
        item.strip() for item in equipment_value.split(",") if item.strip()
    ) if equipment_value else ()

    try:
        initiative_bonus = int((input_func("Initiative bonus [0]: ").strip() or "0"))
    except (StopIteration, ValueError):
        initiative_bonus = 0

    build = CharacterBuild(
        name=name,
        attack_profile=AttackProfile(
            name=f"{name} attack",
            attack_bonus=attack_bonus,
            damage_dice=damage_dice,
            damage_modifier=damage_modifier,
        ),
        armor_class=armor_class,
        max_hp=max_hp,
        save_bonus=save_bonus,
        initiative_bonus=initiative_bonus,
        description=f"Custom build for {name}.",
        equipment=equipment,
    )

    if save_after:
        save_custom_build(build)
        output_func(f"Saved {name} to {get_build_file_path(name)}.")

    return build



def build_attack_scenarios(
    include_advantage=False,
    include_disadvantage=False,
):
    one_handed_attack = AttackProfile(
        name="Generic 1d8+3 attack",
        attack_bonus=5,
        damage_dice=(DamageDice(1, 8),),
        damage_modifier=3,
    )
    two_handed_attack = AttackProfile(
        name="Generic 2d6+3 attack",
        attack_bonus=5,
        damage_dice=(DamageDice(2, 6),),
        damage_modifier=3,
    )
    scenarios = []
    for label, profile in (
        ("1d8+3", one_handed_attack),
        ("2d6+3", two_handed_attack),
    ):
        scenarios.append(AttackScenario(f"{label}, normal", profile))
        if include_advantage:
            scenarios.append(
                AttackScenario(f"{label}, advantage", profile, advantage=True)
            )
        if include_disadvantage:
            scenarios.append(
                AttackScenario(
                    f"{label}, disadvantage", profile, disadvantage=True
                )
            )
    return tuple(scenarios)


def build_turn_plans(scenarios, attacks_per_action=1):
    if not isinstance(attacks_per_action, int) or isinstance(
        attacks_per_action, bool
    ):
        raise TypeError("attacks_per_action must be an integer")
    if attacks_per_action < 1:
        raise ValueError("attacks_per_action must be at least 1")
    attacks = (scenarios[0],) * attacks_per_action
    attack_label = "attack" if attacks_per_action == 1 else "attacks"
    return (
        TurnPlan(
            f"{attacks_per_action} {attack_label} per Attack action",
            attacks,
        ),
    )


def build_save_scenarios(
    selected_build,
    target_save_bonus=2,
    target_profile=None,
):
    return create_save_scenarios(
        selected_build,
        target_save_bonus=target_save_bonus,
        target_profile=target_profile,
    )




def build_custom_attack_scenarios(
    selected_build=None,
    include_advantage=False,
    include_disadvantage=False,
):
    if selected_build is None:
        return build_attack_scenarios(
            include_advantage=include_advantage,
            include_disadvantage=include_disadvantage,
        )

    if not getattr(selected_build, "attack_profiles", ()):
        return build_attack_scenarios(
            include_advantage=include_advantage,
            include_disadvantage=include_disadvantage,
        )
    return create_attack_scenarios(
        selected_build,
        include_advantage=include_advantage,
        include_disadvantage=include_disadvantage,
    )
