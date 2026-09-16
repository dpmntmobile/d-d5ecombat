"""Fixed turn-plan reduction simulations."""

from .combat import resolve_attack_sequence
from .models import TargetProfile, TurnPlan
from .simulation_core import (
    TurnPlanSimulationResult,
    _check_cancellation,
    _create_random_source,
    _process_map,
    _validate_trials,
    _validate_workers,
    calculate_attack_analytics,
)


def simulate_turns_to_zero(
    trials,
    turn_plan,
    target,
    max_turns_per_trial=10_000,
    seed=None,
    rng=None,
    cancellation_check=None,
):
    """Execute a fixed ordered attack plan each turn until HP reaches 0."""
    _validate_trials(trials)
    if not isinstance(turn_plan, TurnPlan):
        raise TypeError("turn_plan must be a TurnPlan")
    if not isinstance(target, TargetProfile):
        raise TypeError("target must be a TargetProfile")
    if not isinstance(max_turns_per_trial, int) or isinstance(
        max_turns_per_trial, bool
    ):
        raise TypeError("max_turns_per_trial must be an integer")
    if max_turns_per_trial < 1:
        raise ValueError("max_turns_per_trial must be at least 1")

    random_source = _create_random_source(seed, rng)
    if all(
        calculate_attack_analytics(
            attack_scenario.attack,
            target.armor_class,
            bonus_damage_dice=attack_scenario.bonus_damage_dice,
            advantage=attack_scenario.advantage,
            disadvantage=attack_scenario.disadvantage,
            damage_resistances=target.damage_resistances,
            damage_vulnerabilities=target.damage_vulnerabilities,
            damage_immunities=target.damage_immunities,
        ).expected_damage_per_attack
        == 0
        for attack_scenario in turn_plan.attacks
    ):
        return TurnPlanSimulationResult(
            trials, 0, 0, 0, 0, 0, 0, impossible=True
        )
    total_turns = 0
    total_attacks = 0
    minimum_turns = None
    maximum_turns = 0
    total_rolled_damage = 0
    total_hp_removed = 0

    for trial_number in range(1, trials + 1):
        _check_cancellation(cancellation_check)
        current_hp = target.max_hp
        trial_turns = 0

        while current_hp > 0:
            _check_cancellation(cancellation_check)
            if trial_turns >= max_turns_per_trial:
                raise RuntimeError(
                    f"trial {trial_number} exceeded "
                    f"max_turns_per_trial={max_turns_per_trial}"
                )

            trial_turns += 1
            total_turns += 1
            first_hit_bonus_available = turn_plan.first_hit_bonus_damage is not None
            for attack_index, attack_scenario in enumerate(turn_plan.attacks):
                conditional_bonus_dice = ()
                bonus_policy = turn_plan.first_hit_bonus_damage
                if (
                    first_hit_bonus_available
                    and attack_index in bonus_policy.eligible_attack_indices
                    and (not bonus_policy.requires_advantage or (
                        attack_scenario.advantage and not attack_scenario.disadvantage
                    ))
                ):
                    conditional_bonus_dice = bonus_policy.damage_dice

                previous_hp = current_hp
                result = resolve_attack_sequence(
                    attack_scenario.attack,
                    target.armor_class,
                    current_hp,
                    bonus_damage_dice=(
                        attack_scenario.bonus_damage_dice + conditional_bonus_dice
                    ),
                    advantage=attack_scenario.advantage,
                    disadvantage=attack_scenario.disadvantage,
                    damage_resistances=target.damage_resistances,
                    damage_vulnerabilities=target.damage_vulnerabilities,
                    damage_immunities=target.damage_immunities,
                    undead_fortitude=target.undead_fortitude,
                    constitution_save_bonus=target.get_saving_throw_bonus("con"),
                    rng=random_source,
                )
                if conditional_bonus_dice and result.attack.hit:
                    first_hit_bonus_available = False
                current_hp = result.remaining_hp
                total_attacks += 1
                total_rolled_damage += result.damage
                total_hp_removed += previous_hp - current_hp

                if current_hp == 0:
                    break

        if minimum_turns is None or trial_turns < minimum_turns:
            minimum_turns = trial_turns
        maximum_turns = max(maximum_turns, trial_turns)

    return TurnPlanSimulationResult(
        trials=trials,
        total_turns=total_turns,
        total_attacks=total_attacks,
        minimum_turns=minimum_turns,
        maximum_turns=maximum_turns,
        total_rolled_damage=total_rolled_damage,
        total_hp_removed=total_hp_removed,
    )


def _simulate_turn_plan_job(job):
    turn_plan, target, trials, max_turns_per_trial, seed = job
    return simulate_turns_to_zero(
        trials=trials,
        turn_plan=turn_plan,
        target=target,
        max_turns_per_trial=max_turns_per_trial,
        seed=seed,
    )


def simulate_turn_plan_batch(
    turn_plans,
    target,
    trials,
    seed=None,
    max_turns_per_trial=10_000,
    workers=1,
    cancellation_check=None,
):
    """Simulate independent turn plans, optionally in worker processes."""
    try:
        turn_plans = tuple(turn_plans)
    except TypeError as error:
        raise TypeError("turn_plans must be an iterable of TurnPlan") from error
    if not all(isinstance(plan, TurnPlan) for plan in turn_plans):
        raise TypeError("every turn plan must be a TurnPlan")
    if not isinstance(target, TargetProfile):
        raise TypeError("target must be a TargetProfile")
    _validate_trials(trials)
    _validate_workers(workers)
    if workers == 1 and cancellation_check is not None:
        return tuple(
            simulate_turns_to_zero(
                trials,
                plan,
                target,
                max_turns_per_trial=max_turns_per_trial,
                seed=seed,
                cancellation_check=cancellation_check,
            )
            for plan in turn_plans
        )
    jobs = (
        (plan, target, trials, max_turns_per_trial, seed) for plan in turn_plans
    )
    return _process_map(_simulate_turn_plan_job, jobs, workers)
