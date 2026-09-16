"""Interface-neutral orchestration for combat simulation use cases."""

from dataclasses import dataclass, replace

from .models import TurnPlan
from .tactical_rules import ASSUMPTIONS, validate_assumptions
from .duel_positioning import validate_distance
from .scenario_factory import build_duel_policy_matchups, build_save_scenarios
from .simulation import (
    compare_attack_scenarios_by_ac,
    select_best_monster_duel_policy,
    simulate_duel_batch,
    simulate_saving_throw_scenario_batch,
    simulate_turn_plan_batch,
)


@dataclass(frozen=True)
class SimulationSettings:
    trials: int = 10_000
    seed: int = 42
    workers: int = 1
    include_advantage: bool = False
    include_disadvantage: bool = False
    starting_distance_feet: int = None
    character_speed_feet: int = 30
    monster_speed_feet: int = 30
    character_ally_near_target: bool = False
    monster_ally_near_target: bool = False
    character_can_hide: bool = False
    monster_can_hide: bool = False
    rest_before_duel: str = "none"


    def __post_init__(self):
        validate_assumptions(self)
        if self.rest_before_duel not in {"none", "short", "long"}:
            raise ValueError("rest_before_duel must be none, short, or long")
        for field_name in ("trials", "seed", "workers"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer")
        validate_distance(self.starting_distance_feet, "starting_distance_feet", optional=True)
        validate_distance(self.character_speed_feet, "character_speed_feet")
        validate_distance(self.monster_speed_feet, "monster_speed_feet")
        if self.trials < 1:
            raise ValueError("trials must be at least 1")
        if self.workers < 1:
            raise ValueError("workers must be at least 1")


    @property
    def duel_positioning_note(self):
        assumptions = "; ".join(name.replace("_", " ") for name in ASSUMPTIONS if getattr(self, name))
        suffix = f" Assumptions: {assumptions}." if assumptions else ""
        if self.rest_before_duel != "none":
            suffix += f" {self.rest_before_duel.title()} rest before duel."
        if self.starting_distance_feet is None:
            return "Positioning: abstract (movement and ranges disabled)." + suffix
        return (
            f"Positioning: start {self.starting_distance_feet} ft; "
            f"character speed {self.character_speed_feet} ft; "
            f"monster speed {self.monster_speed_feet} ft. "
            "Approach normal range/reach; Dash if unable to attack." + suffix
        )


@dataclass(frozen=True)
class AttackEvaluation:
    scenarios: tuple
    sweep: object


@dataclass(frozen=True)
class TurnEvaluation:
    plans: tuple
    results: tuple


@dataclass(frozen=True)
class SavingThrowEvaluation:
    scenarios: tuple
    results: tuple


@dataclass(frozen=True)
class DuelPolicyEvaluation:
    matchups: tuple
    results: tuple
    selected_matchup: object
    selected_result: object
    selected_index: int


def evaluate_attacks(
    scenarios,
    target,
    settings,
    armor_classes=None,
    cancellation_check=None,
):
    """Run an attack comparison without applying presentation concerns."""
    scenarios = tuple(scenarios)
    armor_classes = tuple(armor_classes or (target.armor_class,))
    sweep = compare_attack_scenarios_by_ac(
        scenarios=scenarios,
        armor_classes=armor_classes,
        target_max_hp=target.max_hp,
        trials=settings.trials,
        target_name=target.name,
        seed=settings.seed,
        workers=settings.workers,
        cancellation_check=cancellation_check,
        damage_resistances=target.damage_resistances,
        damage_vulnerabilities=target.damage_vulnerabilities,
        damage_immunities=target.damage_immunities,
        undead_fortitude=target.undead_fortitude,
        saving_throw_bonuses=target.saving_throw_bonuses,
    )
    return AttackEvaluation(scenarios, sweep)


def evaluate_turns(
    scenarios,
    attacks_per_action,
    target,
    settings,
    cancellation_check=None,
    additional_plans=(),
):
    """Run one repeated turn plan for each supplied attack scenario."""
    plans = tuple(
        TurnPlan(
            f"{scenario.name} × {attacks_per_action}",
            (scenario,) * attacks_per_action,
        )
        for scenario in scenarios
        if scenario.attack.action_type == "action"
    )
    for plan in additional_plans:
        plans += (plan,)
        for flag, enabled in (("advantage", settings.include_advantage),
                              ("disadvantage", settings.include_disadvantage)):
            if enabled:
                plans += (replace(plan, name=f"{plan.name} with {flag}", attacks=tuple(
                    replace(scenario, **{flag: True}) for scenario in plan.attacks
                )),)
    results = simulate_turn_plan_batch(
        plans,
        target,
        settings.trials,
        seed=settings.seed,
        workers=settings.workers,
        cancellation_check=cancellation_check,
    )
    return TurnEvaluation(plans, results)


def evaluate_saving_throws(
    build,
    target,
    settings,
    target_save_bonus=2,
    cancellation_check=None,
):
    """Run every imported save-based damage effect for a character."""
    scenarios = build_save_scenarios(build, target_save_bonus, target)
    results = (
        simulate_saving_throw_scenario_batch(
            scenarios,
            target,
            settings.trials,
            seed=settings.seed,
            workers=settings.workers,
            cancellation_check=cancellation_check,
        )
        if scenarios
        else ()
    )
    return SavingThrowEvaluation(scenarios, results)


def evaluate_duel_policies(
    build,
    monster,
    settings,
    character_initiative_bonus=None,
    monster_initiative_bonus=None,
    cancellation_check=None,
):
    """Evaluate and select the monster action policy for one duel matchup."""
    evaluations = evaluate_duel_roster(
        build,
        (monster,),
        settings,
        character_initiative_bonus=character_initiative_bonus,
        monster_initiative_bonus=monster_initiative_bonus,
        cancellation_check=cancellation_check,
    )
    return evaluations[0]


def evaluate_duel_roster(
    build,
    monsters,
    settings,
    character_initiative_bonus=None,
    monster_initiative_bonus=None,
    cancellation_check=None,
):
    """Evaluate duel policies for multiple monsters in one reproducible batch."""
    groups = tuple(
        build_duel_policy_matchups(
            build,
            monster,
            character_initiative_bonus=character_initiative_bonus,
            monster_initiative_bonus=monster_initiative_bonus,
            starting_distance_feet=settings.starting_distance_feet,
            character_speed_feet=settings.character_speed_feet,
            monster_speed_feet=settings.monster_speed_feet,
            character_ally_near_target=settings.character_ally_near_target,
            monster_ally_near_target=settings.monster_ally_near_target,
            character_can_hide=settings.character_can_hide,
            monster_can_hide=settings.monster_can_hide,
            rest_before_duel=settings.rest_before_duel,

        )
        for monster in monsters
    )
    all_matchups = tuple(matchup for group in groups for matchup in group)
    if not all_matchups:
        return tuple(
            DuelPolicyEvaluation((), (), None, None, -1) for _ in groups
        )
    all_results = simulate_duel_batch(
        all_matchups,
        settings.trials,
        seed=settings.seed,
        workers=settings.workers,
        cancellation_check=cancellation_check,
    )
    evaluations = []
    offset = 0
    for group in groups:
        if not group:
            evaluations.append(DuelPolicyEvaluation((), (), None, None, -1))
            continue
        results = all_results[offset : offset + len(group)]
        matchup, result, index = select_best_monster_duel_policy(group, results)
        evaluations.append(
            DuelPolicyEvaluation(group, results, matchup, result, index)
        )
        offset += len(group)
    return tuple(evaluations)
