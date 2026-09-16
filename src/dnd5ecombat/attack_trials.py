"""Attack, turn-plan, and saving-throw reduction simulations."""

from .combat import (
    resolve_attack,
    resolve_attack_sequence,
    resolve_damage,
)
from .models import AttackProfile, AttackScenario, TargetProfile
from .simulation_core import (
    ArmorClassScenarioComparison,
    ArmorClassSweepResult,
    AttackScenarioComparison,
    AttackSimulationResult,
    TargetReductionSimulationResult,
    _check_cancellation,
    _create_random_source,
    _process_map,
    _validate_bonus_damage_dice,
    _validate_trials,
    _validate_workers,
    calculate_attack_analytics,
)


def _normalize_attack_scenarios(scenarios):
    try:
        scenarios = tuple(scenarios)
    except TypeError as error:
        raise TypeError("scenarios must be an iterable of AttackScenario") from error
    if not scenarios:
        raise ValueError("scenarios must contain at least one AttackScenario")
    if not all(isinstance(scenario, AttackScenario) for scenario in scenarios):
        raise TypeError("every scenario must be an AttackScenario")
    return scenarios


def simulate_attacks(
    trials,
    attack,
    target_ac,
    bonus_damage_dice=(),
    advantage=False,
    disadvantage=False,
    seed=None,
    rng=None,
    cancellation_check=None,
):
    """Simulate independent uses of one attack and aggregate the results."""
    _validate_trials(trials)
    if not isinstance(attack, AttackProfile):
        raise TypeError("attack must be an AttackProfile")
    bonus_pools = _validate_bonus_damage_dice(bonus_damage_dice)
    damage_pools = attack.damage_dice + bonus_pools

    random_source = _create_random_source(seed, rng)

    hits = 0
    critical_hits = 0
    total_damage = 0

    for _ in range(trials):
        _check_cancellation(cancellation_check)
        attack_result = resolve_attack(
            attack.attack_bonus,
            target_ac,
            advantage=advantage,
            disadvantage=disadvantage,
            rng=random_source,
        )
        if not attack_result.hit:
            continue

        hits += 1
        if attack_result.critical:
            critical_hits += 1
        total_damage += resolve_damage(
            damage_pools,
            attack.damage_modifier,
            critical=attack_result.critical,
            reroll_at_or_below=attack.reroll_damage_at_or_below,
            rng=random_source,
        )

    return AttackSimulationResult(
        attempts=trials,
        hits=hits,
        critical_hits=critical_hits,
        total_damage=total_damage,
    )


def simulate_attacks_to_zero(
    trials,
    attack,
    target,
    bonus_damage_dice=(),
    advantage=False,
    disadvantage=False,
    max_attacks_per_trial=10_000,
    seed=None,
    rng=None,
    cancellation_check=None,
):
    """Simulate attacks against persistent HP until the target reaches 0 HP."""
    _validate_trials(trials)
    if not isinstance(attack, AttackProfile):
        raise TypeError("attack must be an AttackProfile")
    if not isinstance(target, TargetProfile):
        raise TypeError("target must be a TargetProfile")
    if not isinstance(max_attacks_per_trial, int) or isinstance(
        max_attacks_per_trial, bool
    ):
        raise TypeError("max_attacks_per_trial must be an integer")
    if max_attacks_per_trial < 1:
        raise ValueError("max_attacks_per_trial must be at least 1")
    bonus_pools = _validate_bonus_damage_dice(bonus_damage_dice)
    random_source = _create_random_source(seed, rng)
    analytics = calculate_attack_analytics(
        attack,
        target.armor_class,
        bonus_damage_dice=bonus_pools,
        advantage=advantage,
        disadvantage=disadvantage,
        damage_resistances=target.damage_resistances,
        damage_vulnerabilities=target.damage_vulnerabilities,
        damage_immunities=target.damage_immunities,
    )
    if analytics.expected_damage_per_attack == 0:
        return TargetReductionSimulationResult(
            trials, 0, 0, 0, 0, 0, 0, impossible=True
        )

    total_attacks = 0
    minimum_attacks = None
    maximum_attacks = 0
    total_rolled_damage = 0
    total_hp_removed = 0
    sum_squared_attacks = 0

    for trial_number in range(1, trials + 1):
        _check_cancellation(cancellation_check)
        current_hp = target.max_hp
        trial_attacks = 0

        while current_hp > 0:
            _check_cancellation(cancellation_check)
            if trial_attacks >= max_attacks_per_trial:
                raise RuntimeError(
                    f"trial {trial_number} exceeded "
                    f"max_attacks_per_trial={max_attacks_per_trial}"
                )

            previous_hp = current_hp
            result = resolve_attack_sequence(
                attack,
                target.armor_class,
                current_hp,
                bonus_damage_dice=bonus_pools,
                advantage=advantage,
                disadvantage=disadvantage,
                damage_resistances=target.damage_resistances,
                damage_vulnerabilities=target.damage_vulnerabilities,
                damage_immunities=target.damage_immunities,
                undead_fortitude=target.undead_fortitude,
                constitution_save_bonus=target.get_saving_throw_bonus("con"),
                rng=random_source,
            )
            current_hp = result.remaining_hp
            trial_attacks += 1
            total_attacks += 1
            total_rolled_damage += result.damage
            total_hp_removed += previous_hp - current_hp

        if minimum_attacks is None or trial_attacks < minimum_attacks:
            minimum_attacks = trial_attacks
        maximum_attacks = max(maximum_attacks, trial_attacks)
        sum_squared_attacks += trial_attacks * trial_attacks

    return TargetReductionSimulationResult(
        trials=trials,
        total_attacks=total_attacks,
        minimum_attacks=minimum_attacks,
        maximum_attacks=maximum_attacks,
        total_rolled_damage=total_rolled_damage,
        total_hp_removed=total_hp_removed,
        sum_squared_attacks=sum_squared_attacks,
    )


def compare_attack_scenarios(
    scenarios,
    target,
    trials,
    seed=None,
    max_attacks_per_trial=10_000,
    cancellation_check=None,
):
    """Run named attack scenarios against the same target assumptions."""
    scenarios = _normalize_attack_scenarios(scenarios)

    comparisons = []
    for scenario in scenarios:
        result = simulate_attacks_to_zero(
            trials=trials,
            attack=scenario.attack,
            target=target,
            bonus_damage_dice=scenario.bonus_damage_dice,
            advantage=scenario.advantage,
            disadvantage=scenario.disadvantage,
            max_attacks_per_trial=max_attacks_per_trial,
            seed=seed,
            cancellation_check=cancellation_check,
        )
        comparisons.append(AttackScenarioComparison(scenario, result))

    return tuple(comparisons)


def _simulate_attack_scenario_job(job):
    scenario, target, trials, max_attacks_per_trial, seed = job
    return simulate_attacks_to_zero(
        trials=trials,
        attack=scenario.attack,
        target=target,
        bonus_damage_dice=scenario.bonus_damage_dice,
        advantage=scenario.advantage,
        disadvantage=scenario.disadvantage,
        max_attacks_per_trial=max_attacks_per_trial,
        seed=seed,
    )


def compare_attack_scenarios_by_ac(
    scenarios,
    armor_classes,
    target_max_hp,
    trials,
    target_name="Generic target",
    seed=None,
    max_attacks_per_trial=10_000,
    workers=1,
    cancellation_check=None,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
    undead_fortitude=False,
    saving_throw_bonuses=(),
):
    """Compare attack scenarios across generic targets with different ACs."""
    scenarios = _normalize_attack_scenarios(scenarios)
    _validate_trials(trials)
    _validate_workers(workers)
    try:
        armor_classes = tuple(armor_classes)
    except TypeError as error:
        raise TypeError("armor_classes must be an iterable of integers") from error
    if not armor_classes:
        raise ValueError("armor_classes must contain at least one value")
    if not all(
        isinstance(armor_class, int) and not isinstance(armor_class, bool)
        for armor_class in armor_classes
    ):
        raise TypeError("every armor class must be an integer")
    if len(set(armor_classes)) != len(armor_classes):
        raise ValueError("armor_classes cannot contain duplicates")

    targets = tuple(
        TargetProfile(
            target_name,
            armor_class,
            target_max_hp,
            damage_resistances=damage_resistances,
            damage_vulnerabilities=damage_vulnerabilities,
            damage_immunities=damage_immunities,
            undead_fortitude=undead_fortitude,
            saving_throw_bonuses=saving_throw_bonuses,
        )
        for armor_class in armor_classes
    )
    if workers == 1 and cancellation_check is not None:
        flat_results = tuple(
            simulate_attacks_to_zero(
                trials=trials,
                attack=scenario.attack,
                target=target,
                bonus_damage_dice=scenario.bonus_damage_dice,
                advantage=scenario.advantage,
                disadvantage=scenario.disadvantage,
                max_attacks_per_trial=max_attacks_per_trial,
                seed=seed,
                cancellation_check=cancellation_check,
            )
            for scenario in scenarios
            for target in targets
        )
    else:
        jobs = (
            (
                scenario,
                target,
                trials,
                max_attacks_per_trial,
                seed,
            )
            for scenario in scenarios
            for target in targets
        )
        flat_results = _process_map(_simulate_attack_scenario_job, jobs, workers)
    ac_count = len(armor_classes)
    results_by_scenario = tuple(
        flat_results[index * ac_count : (index + 1) * ac_count]
        for index in range(len(scenarios))
    )

    scenario_comparisons = tuple(
        ArmorClassScenarioComparison(scenario, tuple(results))
        for scenario, results in zip(scenarios, results_by_scenario)
    )
    return ArmorClassSweepResult(
        target_name=target_name,
        target_max_hp=target_max_hp,
        armor_classes=armor_classes,
        scenario_comparisons=scenario_comparisons,
        damage_resistances=tuple(damage_resistances),
        damage_vulnerabilities=tuple(damage_vulnerabilities),
        damage_immunities=tuple(damage_immunities),
    )
