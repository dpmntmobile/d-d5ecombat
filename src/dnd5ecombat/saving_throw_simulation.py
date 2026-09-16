"""Saving-throw damage reduction simulations."""

from .combat import apply_damage_defenses, resolve_saving_throw_damage
from .models import SavingThrowScenario, TargetProfile
from .simulation_core import (
    SavingThrowSimulationResult,
    _check_cancellation,
    _create_random_source,
    _process_map,
    _validate_trials,
    _validate_workers,
)


def simulate_saving_throw_uses_to_zero(
    trials,
    scenario,
    target,
    max_uses_per_trial=10_000,
    seed=None,
    rng=None,
    cancellation_check=None,
):
    """Repeat one save-based effect until persistent target HP reaches 0."""
    _validate_trials(trials)
    if not isinstance(scenario, SavingThrowScenario):
        raise TypeError("scenario must be a SavingThrowScenario")
    if not isinstance(target, TargetProfile):
        raise TypeError("target must be a TargetProfile")
    if not isinstance(max_uses_per_trial, int) or isinstance(
        max_uses_per_trial, bool
    ):
        raise TypeError("max_uses_per_trial must be an integer")
    if max_uses_per_trial < 1:
        raise ValueError("max_uses_per_trial must be at least 1")

    random_source = _create_random_source(seed, rng)
    maximum_damage = max(
        0,
        sum(pool.number * pool.sides for pool in scenario.effect.damage_dice)
        + scenario.effect.damage_modifier,
    )
    maximum_applied_damage = apply_damage_defenses(
        maximum_damage,
        scenario.effect.damage_type,
        resistances=target.damage_resistances,
        vulnerabilities=target.damage_vulnerabilities,
        immunities=target.damage_immunities,
    )
    if maximum_applied_damage == 0:
        return SavingThrowSimulationResult(
            trials, 0, 0, 0, 0, 0, 0, 0, 0, impossible=True
        )
    total_uses = 0
    successful_saves = 0
    failed_saves = 0
    minimum_uses = None
    maximum_uses = 0
    total_rolled_damage = 0
    total_applied_damage = 0
    total_hp_removed = 0

    for trial_number in range(1, trials + 1):
        _check_cancellation(cancellation_check)
        current_hp = target.max_hp
        trial_uses = 0

        while current_hp > 0:
            _check_cancellation(cancellation_check)
            if trial_uses >= max_uses_per_trial:
                raise RuntimeError(
                    f"trial {trial_number} exceeded "
                    f"max_uses_per_trial={max_uses_per_trial}"
                )

            previous_hp = current_hp
            result = resolve_saving_throw_damage(
                scenario.effect,
                scenario.target_save_bonus,
                current_hp,
                advantage=scenario.save_advantage,
                disadvantage=scenario.save_disadvantage,
                damage_resistances=target.damage_resistances,
                damage_vulnerabilities=target.damage_vulnerabilities,
                damage_immunities=target.damage_immunities,
                undead_fortitude=target.undead_fortitude,
                constitution_save_bonus=target.get_saving_throw_bonus("con"),
                rng=random_source,
            )
            current_hp = result.remaining_hp
            trial_uses += 1
            total_uses += 1
            if result.saving_throw.success:
                successful_saves += 1
            else:
                failed_saves += 1
            if result.rolled_damage is not None:
                total_rolled_damage += result.rolled_damage
            total_applied_damage += result.applied_damage
            total_hp_removed += previous_hp - current_hp

        if minimum_uses is None or trial_uses < minimum_uses:
            minimum_uses = trial_uses
        maximum_uses = max(maximum_uses, trial_uses)

    return SavingThrowSimulationResult(
        trials=trials,
        total_uses=total_uses,
        successful_saves=successful_saves,
        failed_saves=failed_saves,
        minimum_uses=minimum_uses,
        maximum_uses=maximum_uses,
        total_rolled_damage=total_rolled_damage,
        total_applied_damage=total_applied_damage,
        total_hp_removed=total_hp_removed,
    )


def _simulate_saving_throw_scenario_job(job):
    scenario, target, trials, max_uses_per_trial, seed = job
    return simulate_saving_throw_uses_to_zero(
        trials=trials,
        scenario=scenario,
        target=target,
        max_uses_per_trial=max_uses_per_trial,
        seed=seed,
    )


def simulate_saving_throw_scenario_batch(
    scenarios,
    target,
    trials,
    seed=None,
    max_uses_per_trial=10_000,
    workers=1,
    cancellation_check=None,
):
    """Simulate independent save-based scenarios in worker processes."""
    try:
        scenarios = tuple(scenarios)
    except TypeError as error:
        raise TypeError("scenarios must be an iterable of SavingThrowScenario") from error
    if not all(isinstance(scenario, SavingThrowScenario) for scenario in scenarios):
        raise TypeError("every scenario must be a SavingThrowScenario")
    if not isinstance(target, TargetProfile):
        raise TypeError("target must be a TargetProfile")
    _validate_trials(trials)
    _validate_workers(workers)
    if workers == 1 and cancellation_check is not None:
        return tuple(
            simulate_saving_throw_uses_to_zero(
                trials,
                scenario,
                target,
                max_uses_per_trial=max_uses_per_trial,
                seed=seed,
                cancellation_check=cancellation_check,
            )
            for scenario in scenarios
        )
    jobs = (
        (scenario, target, trials, max_uses_per_trial, seed)
        for scenario in scenarios
    )
    return _process_map(_simulate_saving_throw_scenario_job, jobs, workers)
