"""Console execution workflows and application orchestration."""

import os
import random
import sys
from pathlib import Path
from dataclasses import replace

from .resource_models import duel_save_actions

from .application_service import (
    evaluate_attacks,
    evaluate_duel_roster,
    evaluate_saving_throws,
    evaluate_turns,
)
from .character_profiles import build_from_roll20_with_attack, import_from_roll20
from .cli_arguments import parse_args
from .cli_reporting import print_attack_summary, print_save_summary, print_turn_summary
from .cli_setup import (
    MONSTERS_DIR,
    build_character_presets,
    build_custom_attack_scenarios,
    list_monster_files,
    print_monster_profile_notes,
    run_interactive_menu,
)
from .combat import InitiativeParticipant, resolve_initiative_order
from .models import TargetProfile
from .monster_profiles import load_monster_profile
from .scenario_factory import format_damage_profile as format_scenario_damage
from .simulation import simulate_attacks_to_zero
from .scenario_persistence import save_scenario, settings_from_arguments
from .profile_catalog import CatalogItem, load_character_build
from .roster_service import run_roster_simulations
from .result_export import save_results


def _build_comparison_target(arguments, target_profile=None):
    if target_profile is not None:
        return target_profile
    armor_classes = tuple(arguments.armor_classes)
    target_ac = armor_classes[len(armor_classes) // 2]
    return TargetProfile("Generic comparison target", target_ac, arguments.target_hp)


def _enemy_initiative_bonus(arguments, target_profile=None):
    override = getattr(arguments, "enemy_initiative_bonus", None)
    if override is not None:
        return override
    if target_profile is not None:
        return target_profile.initiative_bonus
    return 0


def _simulation_settings(arguments):
    return settings_from_arguments(arguments)


def print_initiative_order(
    character_name,
    character_bonus,
    enemy_name,
    enemy_bonus,
    seed,
):
    order = resolve_initiative_order(
        (
            InitiativeParticipant(character_name, character_bonus),
            InitiativeParticipant(enemy_name, enemy_bonus),
        ),
        rng=random.Random(seed),
    )
    print()
    print(f"Initiative order (seed {seed})")
    for position, result in enumerate(order, start=1):
        tie_text = ""
        if result.tie_break_rolls:
            tie_text = ", tie reroll(s) " + "/".join(
                str(roll) for roll in result.tie_break_rolls
            )
        print(
            f"{position}) {result.participant.name}: "
            f"d20 {result.natural_roll} {result.participant.modifier:+d} "
            f"= {result.total}{tie_text}"
        )
    return order


def run_attack_summary(arguments, selected_build=None, target_profile=None):
    scenarios = build_custom_attack_scenarios(
        selected_build,
        include_advantage=arguments.include_advantage,
        include_disadvantage=arguments.include_disadvantage,
    )
    initiative_bonus = getattr(selected_build, "initiative_bonus", 0) if selected_build else 0
    override_bonus = getattr(arguments, "initiative_bonus", None)
    if override_bonus is not None:
        initiative_bonus = override_bonus
    print_initiative_order(
        selected_build.name if selected_build else "Attacker",
        initiative_bonus,
        target_profile.name if target_profile else "Generic target",
        _enemy_initiative_bonus(arguments, target_profile),
        arguments.seed,
    )

    armor_classes = (
        (target_profile.armor_class,)
        if target_profile is not None
        else tuple(arguments.armor_classes)
    )
    evaluation = evaluate_attacks(
        scenarios,
        _build_comparison_target(arguments, target_profile),
        _simulation_settings(arguments),
        armor_classes=armor_classes,
    )
    print_attack_summary(
        evaluation.sweep,
        arguments.trials,
        arguments.seed,
        workers=arguments.workers,
    )
    return scenarios


def run_default_summary(arguments, selected_build=None, target_profile=None):
    scenarios = run_attack_summary(arguments, selected_build, target_profile)

    turn_target = _build_comparison_target(arguments, target_profile)
    attacks_per_action = selected_build.attacks_per_action if selected_build else 1
    evaluation = evaluate_turns(
        scenarios,
        attacks_per_action,
        turn_target,
        _simulation_settings(arguments),
        additional_plans=(selected_build.turn_plans if selected_build else ()),
    )
    print_turn_summary(
        evaluation.plans,
        turn_target,
        arguments.trials,
        arguments.seed,
        workers=arguments.workers,
        results=evaluation.results,
    )


def run_all_summaries(arguments, selected_build=None, target_profile=None):
    run_default_summary(arguments, selected_build, target_profile)
    target = _build_comparison_target(arguments, target_profile)
    evaluation = evaluate_saving_throws(
        selected_build,
        target,
        _simulation_settings(arguments),
        target_save_bonus=getattr(arguments, "target_save_bonus", 2),
    )
    if evaluation.scenarios:
        print_save_summary(
            evaluation.scenarios,
            target,
            arguments.trials,
            arguments.seed,
            workers=arguments.workers,
            results=evaluation.results,
        )
    else:
        print("\nNo imported damaging spells require a saving throw.")


def format_damage_profile(attack, bonus_damage_dice=()):
    return format_scenario_damage(attack, bonus_damage_dice)


def load_duel_monsters(selected_monster=None):
    if selected_monster is not None:
        if not selected_monster.attack_profiles and not duel_save_actions(selected_monster.saving_throw_profiles):
            raise ValueError(
                f"{selected_monster.name} has no attacks and cannot duel yet."
            )
        return (selected_monster,)

    monsters = []
    for filename in list_monster_files():
        monster = load_monster_profile(os.path.join(MONSTERS_DIR, filename))
        if monster.attack_profiles or duel_save_actions(monster.saving_throw_profiles):
            monsters.append(monster)
    if not monsters:
        raise ValueError("No monster profiles with attacks were found.")
    return tuple(monsters)



def run_duel_summary(arguments, selected_build=None, target_profile=None):
    monsters = load_duel_monsters(target_profile)
    build = selected_build or build_character_presets()[0]
    character_initiative = build.initiative_bonus
    if getattr(arguments, "initiative_bonus", None) is not None:
        character_initiative = arguments.initiative_bonus
    monster_override = getattr(arguments, "enemy_initiative_bonus", None)
    evaluations = evaluate_duel_roster(
        build,
        monsters,
        _simulation_settings(arguments),
        character_initiative_bonus=character_initiative,
        monster_initiative_bonus=monster_override,
    )
    matchups = tuple(item.selected_matchup for item in evaluations)
    results = tuple(item.selected_result for item in evaluations)
    policy_evaluations = tuple(
        tuple(zip(item.matchups, item.results)) for item in evaluations
    )

    print()
    print("Two-sided character-versus-monster duels")
    print(_simulation_settings(arguments).duel_positioning_note)
    print(
        f"Trials per monster: {arguments.trials:,} "
        f"(seed {arguments.seed}, workers {arguments.workers})"
    )
    print(
        "Assumptions: normal attack rolls; character preference uses expected damage "
        "or expected attacks to defeat a target with Undead Fortitude. "
        "Spent attacks use available fallbacks; recharge is checked at turn start. "
        "Eligible save actions compete by expected damage. Attack and save spells share slots."
    )
    print(
        "Weapon actions use attacks_per_action; an action spell replaces the Attack action. "
        "Eligible attack turn plans allow one bonus action and one first-hit rider per turn. "
        "Imported Sneak Attack requires advantage without disadvantage; nearby allies are not assumed. "
        "Each monster action is tested in "
        "full duels and the policy producing the lowest character win rate is used; "
        "a configured multiattack remains one action sequence."
    )
    if getattr(selected_build, "turn_plans", ()):
        print("Character turn plans: " + "; ".join(plan.name for plan in selected_build.turn_plans))

    monster_width = max(7, *(len(monster.name) for monster in monsters))
    character_attack_labels = tuple(
        f"{matchup.character.attack_profile.name} "
        f"({matchup.character.attack_profile.attack_bonus:+d}, "
        f"{format_damage_profile(matchup.character.attack_profile)})"
        for matchup in matchups
    )
    monster_attack_labels = tuple(
        " + ".join(attack.name for attack in matchup.monster.attack_sequence) or "Save actions"
        for matchup in matchups
    )
    character_attack_width = max(
        len("Character attack"), *(len(label) for label in character_attack_labels)
    )
    monster_attack_width = max(
        len("Monster attack"), *(len(label) for label in monster_attack_labels)
    )
    print(
        f"{'Monster':<{monster_width}}  "
        f"{'Character attack':<{character_attack_width}}  "
        f"{'Monster attack':<{monster_attack_width}}  "
        f"{'Win rate':>15} {'Avg rounds':>11} {'HP on win':>10} "
        f"{'Enemy HP/loss':>14} {'Init first':>11}"
    )
    print(
        "-" * (
            monster_width
            + character_attack_width
            + monster_attack_width
            + 69
        )
    )
    for monster, matchup, character_label, monster_label, result, evaluations in zip(
        monsters,
        matchups,
        character_attack_labels,
        monster_attack_labels,
        results,
        policy_evaluations,
    ):
        win_rate = (
            f"{result.character_win_rate:.1%}"
            f"+/-{result.character_win_95_margin:.1%}"
        )
        print(
            f"{monster.name:<{monster_width}}  "
            f"{character_label:<{character_attack_width}}  "
            f"{monster_label:<{monster_attack_width}}  "
            f"{win_rate:>15} "
            f"{result.average_rounds:>11.3f} "
            f"{result.average_character_hp_on_win:>10.3f} "
            f"{result.average_monster_hp_on_loss:>14.3f} "
            f"{result.character_initiative_win_rate:>10.1%}"
        )

        evaluation_text = "; ".join(
            f"{' + '.join(attack.name for attack in candidate.monster.attack_sequence)} "
            f"({candidate_result.character_win_rate:.1%} character win)"
            for candidate, candidate_result in evaluations
        )
        print(f"  Evaluated: {evaluation_text}; selected {monster_label}.")

        excluded = list(monster.unmodeled_traits)
        for attack in matchup.monster.attack_sequence:
            excluded.extend(attack.unmodeled_effects)
        if excluded:
            print(f"  Excluded for {monster.name}: {', '.join(excluded)}")

    return tuple(zip(matchups, results))


def run_single_combat_summary(
    arguments,
    selected_build=None,
    target_profile=None,
):
    build = selected_build or build_character_presets()[0]
    if target_profile is not None:
        enemy = target_profile
    else:
        enemy_ac = getattr(arguments, "enemy_armor_class", 15)
        enemy = TargetProfile("Bandit skirmisher", enemy_ac, arguments.target_hp)
    initiative_bonus = build.initiative_bonus
    if getattr(arguments, "initiative_bonus", None) is not None:
        initiative_bonus = arguments.initiative_bonus
    print_initiative_order(
        build.name,
        initiative_bonus,
        enemy.name,
        _enemy_initiative_bonus(arguments, target_profile),
        arguments.seed,
    )
    result = simulate_attacks_to_zero(
        trials=arguments.trials,
        attack=build.attack_profile,
        target=enemy,
        seed=arguments.seed,
    )

    print()
    print(f"Single combat drill: {build.name}")
    print(f"Equipment: {', '.join(build.equipment) if build.equipment else 'Unspecified'}")
    print(
        f"Attack: {build.attack_profile.name} "
        f"({build.attack_profile.attack_bonus:+d} to hit, "
        f"{format_damage_profile(build.attack_profile)})"
    )
    print(f"Defense: AC {build.armor_class}, HP {build.max_hp}, save +{build.save_bonus}")
    print(f"Enemy: {enemy.name} (AC {enemy.armor_class}, {enemy.max_hp} HP)")
    print(f"Trials: {arguments.trials:,} (seed {arguments.seed})")
    print(f"Average attacks to reduce enemy to 0 HP: {result.average_attacks_to_zero:.3f}")
    print(f"Average rolled damage per attack: {result.average_rolled_damage_per_attack:.3f}")
    print(f"Total overkill: {result.total_overkill}")


def main(argv=None):
    arguments = parse_args(argv)
    if arguments.character_files or arguments.monster_files or arguments.export_results:
        try:
            def load_items(paths, loader, initiative_bonus):
                items = []
                for path in dict.fromkeys(Path(path).resolve() for path in paths):
                    value = loader(path)
                    if initiative_bonus is not None:
                        value = replace(value, initiative_bonus=initiative_bonus)
                    items.append(CatalogItem(f"{value.name} — {path}", value, str(path)))
                return items

            characters = load_items(arguments.character_files or [arguments.character_file], load_character_build, arguments.initiative_bonus)
            monsters = load_items(arguments.monster_files or [arguments.target_file], load_monster_profile, arguments.enemy_initiative_bonus)
            sections = ("duels",) if arguments.duels else ("attacks", "turns")
            tables = run_roster_simulations(characters, monsters, _simulation_settings(arguments), sections)
            if arguments.export_results:
                save_results({section: getattr(tables, section) for section in sections}, arguments.export_results)
        except (OSError, TypeError, ValueError) as error:
            print(f"Could not compare roster: {error}", file=sys.stderr)
            return 2
        for section in sections:
            table = getattr(tables, section)
            print(f"\n{section.replace('_', ' ').title()}")
            print("\t".join(column.title for column in table.columns))
            for row in table.rows:
                print("\t".join(f"{value:.6g}" if isinstance(value, float) else str(value) for value in row))
            print(table.note)
            print(table.details)
        return 0
    if arguments.save_scenario:
        try:
            path = save_scenario(_simulation_settings(arguments), arguments.save_scenario)
        except (OSError, ValueError, TypeError) as error:
            print(f"Could not save scenario: {error}", file=sys.stderr)
            return 2
        print(f"Saved scenario: {path}")
        return 0
    if arguments.gui:
        from .gui import main as gui_main

        return gui_main([sys.argv[0]])

    target_profile = (
        load_monster_profile(arguments.target_file)
        if arguments.target_file
        else None
    )
    if target_profile is not None:
        print_monster_profile_notes(target_profile)

    selected_build = None
    if arguments.character_file:
        roll20_data = import_from_roll20(arguments.character_file)
        if roll20_data:
            imported_attacks = roll20_data.get("attacks", [])
            if imported_attacks:
                preferred_name = roll20_data.get("primary_attack_name")
                primary_attack = next(
                    (
                        attack
                        for attack in imported_attacks
                        if attack["name"] == preferred_name
                    ),
                    imported_attacks[0],
                )
                attack_bonus = primary_attack["bonus"]
                damage_dice_text = primary_attack["damage_dice"]
                damage_modifier = primary_attack["damage_modifier"]
                selected_attack_name = primary_attack["name"]
            else:
                attack_bonus = (
                    roll20_data["strength_mod"] + roll20_data["proficiency_bonus"]
                )
                damage_dice_text = "1d8"
                damage_modifier = roll20_data["strength_mod"]
                selected_attack_name = None
            selected_build = build_from_roll20_with_attack(
                roll20_data,
                attack_bonus=attack_bonus,
                damage_dice_text=damage_dice_text,
                damage_modifier=damage_modifier,
                equipment_text="",
                selected_attack_name=selected_attack_name,
            )

    if arguments.duels and not arguments.interactive:
        run_duel_summary(arguments, selected_build, target_profile)
        return 0

    run_default_when_no_selection = (
        not arguments.interactive
        and not arguments.character_file
        and not arguments.scenario
        and len(sys.argv[1:]) == 0
    )

    if arguments.interactive or run_default_when_no_selection:
        settings = run_interactive_menu(target_profile=target_profile)
        arguments.trials = settings["trials"]
        arguments.seed = settings["seed"]
        arguments.target_hp = settings["target_hp"]
        arguments.armor_classes = settings["armor_classes"]
        arguments.enemy_armor_class = settings["enemy_armor_class"]
        target_profile = settings["target_profile"]
        if target_profile is None:
            arguments.enemy_initiative_bonus = settings["enemy_initiative_bonus"]
        arguments.target_save_bonus = settings["target_save_bonus"]
        selected_build = settings["selected_build"]
        if settings["mode"] == "default":
            run_default_summary(arguments, selected_build, target_profile)
            return 0
        if settings["mode"] == "turns":
            scenarios = build_custom_attack_scenarios(
                selected_build,
                include_advantage=arguments.include_advantage,
                include_disadvantage=arguments.include_disadvantage,
            )
            attacks_per_action = (
                selected_build.attacks_per_action if selected_build else 1
            )
            initiative_bonus = (
                selected_build.initiative_bonus if selected_build else 0
            )
            if arguments.initiative_bonus is not None:
                initiative_bonus = arguments.initiative_bonus
            print_initiative_order(
                selected_build.name if selected_build else "Attacker",
                initiative_bonus,
                target_profile.name if target_profile else "Generic target",
                _enemy_initiative_bonus(arguments, target_profile),
                arguments.seed,
            )
            target = _build_comparison_target(arguments, target_profile)
            evaluation = evaluate_turns(
                scenarios,
                attacks_per_action,
                target,
                _simulation_settings(arguments),
                additional_plans=(
                    selected_build.turn_plans if selected_build else ()
                ),
            )
            print_turn_summary(
                evaluation.plans,
                target,
                arguments.trials,
                arguments.seed,
                workers=arguments.workers,
                results=evaluation.results,
            )
            return 0
        if settings["mode"] == "saves":
            target = _build_comparison_target(arguments, target_profile)
            evaluation = evaluate_saving_throws(
                selected_build,
                target,
                _simulation_settings(arguments),
                target_save_bonus=arguments.target_save_bonus,
            )
            if evaluation.scenarios:
                print_save_summary(
                    evaluation.scenarios,
                    target,
                    arguments.trials,
                    arguments.seed,
                    workers=arguments.workers,
                    results=evaluation.results,
                )
            else:
                print("\nNo imported damaging spells require a saving throw.")
            return 0
        if settings["mode"] == "single":
            run_single_combat_summary(arguments, selected_build, target_profile)
            return 0
        if settings["mode"] == "duels":
            run_duel_summary(arguments, selected_build, target_profile)
            return 0
        if settings["mode"] == "attacks":
            run_attack_summary(arguments, selected_build, target_profile)
            return 0
        if settings["mode"] == "all":
            run_all_summaries(arguments, selected_build, target_profile)
            return 0
        run_default_summary(arguments, selected_build, target_profile)
        return 0

    if selected_build is not None:
        run_default_summary(arguments, selected_build, target_profile)
        return 0

    run_default_summary(arguments, target_profile=target_profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
