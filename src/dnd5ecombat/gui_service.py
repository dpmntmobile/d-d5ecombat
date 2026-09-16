"""Application services used by the desktop GUI.

This module deliberately has no Qt dependency.  It turns the existing combat
models and simulation results into structured tables that can be presented by
any user interface.
"""

from dataclasses import dataclass

from .resource_models import duel_save_actions

from .application_service import (
    SimulationSettings,
    evaluate_attacks,
    evaluate_duel_policies,
    evaluate_saving_throws,
    evaluate_turns,
)
from .scenario_factory import (
    build_custom_attack_scenarios,
    format_damage_profile,
)
from .simulation import (
    SimulationCancelledError,
    calculate_attack_analytics,
)


@dataclass(frozen=True)
class TableColumn:
    title: str
    kind: str = "text"
    tooltip: str = ""
    best: str = ""
    chart: bool = False


@dataclass(frozen=True)
class TableData:
    columns: tuple
    rows: tuple
    note: str = ""


@dataclass(frozen=True)
class SimulationTables:
    attacks: TableData = None
    turns: TableData = None
    saving_throws: TableData = None
    duels: TableData = None


SimulationCancelled = SimulationCancelledError


SIMULATION_SECTIONS = ("attacks", "turns", "saving_throws", "duels")


def _monster_notes(monster):
    notes = list(monster.unmodeled_traits)
    for attack in monster.attack_profiles + monster.saving_throw_profiles:
        notes.extend(
            f"{attack.name}: {effect}" for effect in attack.unmodeled_effects
        )
    if not notes:
        return ""
    return "Not modeled: " + "; ".join(notes)


def _attack_table(build, monster, settings, scenarios, cancellation_check=None):
    evaluation = evaluate_attacks(
        scenarios, monster, settings, cancellation_check=cancellation_check
    )
    sweep = evaluation.sweep
    rows = []
    for comparison in sweep.scenario_comparisons:
        scenario = comparison.scenario
        result = comparison.results[0]
        analytics = calculate_attack_analytics(
            scenario.attack,
            monster.armor_class,
            bonus_damage_dice=scenario.bonus_damage_dice,
            advantage=scenario.advantage,
            disadvantage=scenario.disadvantage,
            damage_resistances=monster.damage_resistances,
            damage_vulnerabilities=monster.damage_vulnerabilities,
            damage_immunities=monster.damage_immunities,
        )
        rows.append(
            (
                scenario.name,
                scenario.attack.attack_bonus,
                format_damage_profile(
                    scenario.attack, scenario.bonus_damage_dice
                ),
                analytics.hit_probability,
                analytics.critical_probability,
                analytics.expected_damage_per_attack,
                result.average_attacks_to_zero,
                result.attacks_to_zero_95_margin,
                result.minimum_attacks,
                result.maximum_attacks,
            )
        )
    return TableData(
        columns=(
            TableColumn("Scenario", tooltip="Attack profile and roll mode."),
            TableColumn("To hit", "signed", "Attack-roll modifier."),
            TableColumn("Damage", tooltip="Damage dice and fixed modifier."),
            TableColumn("Hit chance", "percent", "Exact probability of a hit."),
            TableColumn("Critical", "percent", "Exact critical-hit probability."),
            TableColumn(
                "Expected damage",
                "float",
                "Exact expected damage per attack.",
                chart=True,
            ),
            TableColumn(
                "Avg attacks",
                "float",
                "Simulated attacks required to reduce the target to 0 HP.",
                best="min",
            ),
            TableColumn("95% margin", "float", "Approximate confidence margin."),
            TableColumn("Minimum", "integer", "Fewest attacks observed."),
            TableColumn("Maximum", "integer", "Most attacks observed."),
        ),
        rows=tuple(rows),
        note=(
            f"{build.name} attacking {monster.name} (AC {monster.armor_class}, "
            f"{monster.max_hp} HP); {settings.trials:,} trials per scenario."
            " Attack uses and recharge are tracked only in duels."
        ),
    )


def _turn_table(build, monster, settings, scenarios, cancellation_check=None):
    evaluation = evaluate_turns(
        scenarios,
        build.attacks_per_action,
        monster,
        settings,
        cancellation_check=cancellation_check,
        additional_plans=getattr(build, "turn_plans", ()),
    )
    plans = evaluation.plans
    results = evaluation.results
    rows = tuple(
        (
            plan.name,
            len(plan.attacks),
            result.average_turns_to_zero,
            result.average_attacks_used,
            result.minimum_turns,
            result.maximum_turns,
            result.average_overkill_per_trial,
        )
        for plan, result in zip(plans, results)
    )
    return TableData(
        columns=(
            TableColumn("Turn plan", tooltip="Attack sequence repeated each turn."),
            TableColumn("Attacks/turn", "integer", "Configured attacks per action."),
            TableColumn(
                "Avg turns",
                "float",
                "Average turns required to reduce the target to 0 HP.",
                best="min",
                chart=True,
            ),
            TableColumn("Avg attacks", "float", "Average attacks actually used."),
            TableColumn("Minimum", "integer", "Fewest turns observed."),
            TableColumn("Maximum", "integer", "Most turns observed."),
            TableColumn("Avg overkill", "float", "Damage beyond remaining HP."),
        ),
        rows=rows,
        note=f"Repeated turns against {monster.name} until it reaches 0 HP. "
        "Attack uses and recharge are tracked only in duels.",
    )


def _saving_throw_table(build, monster, settings, cancellation_check=None):
    evaluation = evaluate_saving_throws(
        build, monster, settings, cancellation_check=cancellation_check
    )
    scenarios = evaluation.scenarios
    columns = (
        TableColumn("Effect", tooltip="Imported save-based damage effect."),
        TableColumn("Action type", tooltip="Action economy used by the effect."),
        TableColumn("Save", tooltip="Saving throw ability."),
        TableColumn("DC", "integer", "Difficulty class."),
        TableColumn("Monster bonus", "signed", "Target saving throw modifier."),
        TableColumn("On success", tooltip="Damage applied on a successful save."),
        TableColumn(
            "Avg uses",
            "float",
            "Average uses required to reduce the target to 0 HP.",
            best="min",
        ),
        TableColumn("Save success", "percent", "Observed successful-save rate."),
        TableColumn(
            "Avg damage/use",
            "float",
            "Average applied damage per use.",
            chart=True,
        ),
        TableColumn("Minimum", "integer", "Fewest uses observed."),
        TableColumn("Maximum", "integer", "Most uses observed."),
    )
    if not scenarios:
        return TableData(
            columns=columns,
            rows=(),
            note=f"{build.name} has no imported damaging save effects.",
        )

    results = evaluation.results
    rows = tuple(
        (
            scenario.name,
            scenario.effect.action_type.replace("_", " "),
            scenario.effect.save_ability.upper() or "—",
            scenario.effect.difficulty_class,
            scenario.target_save_bonus,
            scenario.effect.damage_on_success.value.replace("_", " "),
            result.average_uses_to_zero,
            result.save_success_rate,
            result.average_applied_damage_per_use,
            result.minimum_uses,
            result.maximum_uses,
        )
        for scenario, result in zip(scenarios, results)
    )
    limitations = tuple(
        f"{scenario.name}: {effect}"
        for scenario in scenarios
        for effect in scenario.effect.unmodeled_effects
    )
    note = f"Save-based damage against {monster.name}; {settings.trials:,} trials. "
    note += "Uses, recharge, and spell slots are tracked only in duels."
    if limitations:
        note += " Not modeled: " + "; ".join(limitations)
    return TableData(
        columns=columns,
        rows=rows,
        note=note,
    )


def _duel_table(build, monster, settings, cancellation_check=None):
    columns = (
        TableColumn("Monster"),
        TableColumn("Character attack", tooltip="Preferred attack; an available fallback is used when spent."),
        TableColumn(
            "Monster attack",
            tooltip="Action policy with the best simulated duel result.",
        ),
        TableColumn(
            "Character win",
            "percent",
            "Observed character win rate.",
            best="max",
            chart=True,
        ),
        TableColumn("95% margin", "percent", "Approximate confidence margin."),
        TableColumn("Avg rounds", "float", "Average combat duration."),
        TableColumn("Character HP/win", "float", "Remaining HP on character wins."),
        TableColumn("Monster HP/loss", "float", "Enemy HP on character losses."),
        TableColumn("Initiative first", "percent", "Character initiative win rate."),
    )
    if not monster.attack_profiles and not duel_save_actions(monster.saving_throw_profiles):
        return TableData(
            columns=columns,
            rows=(),
            note=f"{monster.name} has no attack profile and cannot duel.",
        )

    evaluation = evaluate_duel_policies(
        build,
        monster,
        settings,
        cancellation_check=cancellation_check,
    )
    policy_matchups = evaluation.matchups
    policy_results = evaluation.results
    matchup = evaluation.selected_matchup
    result = evaluation.selected_result
    character_attack = matchup.character.attack_profile
    monster_sequence = matchup.monster.attack_sequence
    policy_summaries = "; ".join(
        f"{' + '.join(attack.name for attack in candidate.monster.attack_sequence) or 'Save actions'} "
        f"({candidate_result.character_win_rate:.1%} character win)"
        for candidate, candidate_result in zip(policy_matchups, policy_results)
    )
    return TableData(
        columns=columns,
        rows=((
            monster.name,
            character_attack.name,
            " + ".join(attack.name for attack in monster_sequence) or "Save actions",
            result.character_win_rate,
            result.character_win_95_margin,
            result.average_rounds,
            result.average_character_hp_on_win,
            result.average_monster_hp_on_loss,
            result.character_initiative_win_rate,
        ),),
        note=(
            "Attacks shown are preferred choices. Spent attacks use available fallbacks; "
            "recharge is checked at the start of each turn. Eligible save actions compete "
            "with the attack plan by expected damage. Attack and save spells share slots; "
            "action spells replace the Attack action. Eligible attack turn plans compete "
            "with one bonus action and one first-hit rider per turn. Imported Sneak Attack "
            "requires advantage without disadvantage; nearby allies are not assumed. "
            f"Character turn plans: {', '.join(p.name for p in getattr(build, 'turn_plans', ())) or 'preferred action only'}. "
            "The monster "
            f"evaluated {len(policy_matchups)} legal action policy/policies with "
            f"{settings.trials:,} full duels each and selected "
            f"{' + '.join(attack.name for attack in monster_sequence) or 'Save actions'}. "
            f"Evaluated: {policy_summaries}. "
            f"{settings.duel_positioning_note} "
            + (_monster_notes(monster) or "No recorded exclusions for this monster.")
        ),
    )


def run_simulations(
    build,
    monster,
    settings,
    sections=SIMULATION_SECTIONS,
    progress_callback=None,
    is_cancelled=None,
):
    required_build_fields = (
        "attack_profiles",
        "saving_throw_profiles",
        "attacks_per_action",
        "armor_class",
        "max_hp",
    )
    if any(not hasattr(build, field) for field in required_build_fields):
        raise TypeError("build must be a character build")
    if not isinstance(settings, SimulationSettings):
        raise TypeError("settings must be SimulationSettings")

    sections = tuple(dict.fromkeys(sections))
    unsupported = set(sections) - set(SIMULATION_SECTIONS)
    if unsupported:
        raise ValueError(
            "unsupported simulation section(s): " + ", ".join(sorted(unsupported))
        )
    if not sections:
        raise ValueError("sections must contain at least one simulation section")

    scenarios = None
    values = {}
    for completed, section in enumerate(sections):
        if is_cancelled is not None and is_cancelled():
            raise SimulationCancelled("Simulation cancelled")
        if progress_callback is not None:
            progress_callback(completed, len(sections), section)

        if section in {"attacks", "turns"} and scenarios is None:
            scenarios = build_custom_attack_scenarios(
                build,
                include_advantage=settings.include_advantage,
                include_disadvantage=settings.include_disadvantage,
            )
        if section == "attacks":
            values[section] = _attack_table(
                build, monster, settings, scenarios, is_cancelled
            )
        elif section == "turns":
            values[section] = _turn_table(
                build, monster, settings, scenarios, is_cancelled
            )
        elif section == "saving_throws":
            values[section] = _saving_throw_table(
                build, monster, settings, is_cancelled
            )
        else:
            values[section] = _duel_table(
                build, monster, settings, is_cancelled
            )

        if is_cancelled is not None and is_cancelled():
            raise SimulationCancelled("Simulation cancelled")

    if progress_callback is not None:
        progress_callback(len(sections), len(sections), "complete")
    return SimulationTables(**values)
