"""Console formatting for simulation results."""

from .scenario_factory import format_damage_profile as format_scenario_damage
from .simulation import (
    calculate_attack_analytics,
    simulate_saving_throw_scenario_batch,
    simulate_turn_plan_batch,
)


def print_attack_summary(sweep, trials, seed, workers=1):
    print("Attack uses and recharge are tracked only in duels.")
    print(f"Target: {sweep.target_name} ({sweep.target_max_hp} HP)")
    print(
        f"Trials per scenario and AC: {trials:,} "
        f"(seed {seed}, workers {workers})"
    )
    print()

    ranked = sorted(
        sweep.scenario_comparisons,
        key=lambda comparison: (
            sum(result.average_attacks_to_zero for result in comparison.results)
            / len(comparison.results),
            comparison.scenario.name.lower(),
        ),
    )
    best_by_ac = tuple(
        min(
            comparison.results[index].average_attacks_to_zero
            for comparison in ranked
        )
        for index in range(len(sweep.armor_classes))
    )

    name_width = max(
        len("Scenario"),
        max(len(comparison.scenario.name) for comparison in ranked),
    ) + 2
    atk_width = 8
    damage_width = max(
        len("Damage"),
        max(
            len(
                format_scenario_damage(
                    comparison.scenario.attack,
                    comparison.scenario.bonus_damage_dice,
                )
            )
            for comparison in ranked
        ),
    ) + 2
    ac_width = 16
    header = (
        f"{'Scenario':<{name_width}}"
        f"{'Atk':<{atk_width}}"
        f"{'Damage':<{damage_width}}"
        + "".join(f"{'AC ' + str(armor_class):>{ac_width}}" for armor_class in sweep.armor_classes)
    )
    print("Average attacks to reduce target to 0 HP")
    print(header)
    print("-" * len(header))
    for comparison in ranked:
        attack_bonus = comparison.scenario.attack.attack_bonus
        attack_bonus_text = f"{attack_bonus:+d}"
        damage_text = format_scenario_damage(
            comparison.scenario.attack,
            comparison.scenario.bonus_damage_dice,
        )
        average_cells = []
        for index, result in enumerate(comparison.results):
            cell = (
                f"{result.average_attacks_to_zero:.3f}"
                f"±{result.attacks_to_zero_95_margin:.3f}"
            )
            if result.average_attacks_to_zero == best_by_ac[index]:
                cell += "*"
            average_cells.append(f"{cell:>{ac_width}}")
        averages = "".join(average_cells)
        print(
            f"{comparison.scenario.name:<{name_width}}"
            f"{attack_bonus_text:<{atk_width}}"
            f"{damage_text:<{damage_width}}"
            f"{averages}"
        )

    print()
    print("* Best for that AC: lowest average attacks-to-zero; ties are all marked.")
    print("± is the approximate 95% confidence-interval margin for the simulated mean.")
    print("Overlapping intervals indicate that a small numerical lead may be simulation noise.")

    representative_index = len(sweep.armor_classes) // 2
    representative_ac = sweep.armor_classes[representative_index]
    analytics_name_width = name_width
    print()
    print(f"Analytical attack check at AC {representative_ac}")
    print(
        f"{'Scenario':<{analytics_name_width}}"
        f"{'Hit':>8} {'Crit':>8} {'Exact dmg/atk':>15} "
        f"{'Pooled sim dmg/atk':>20}"
    )
    print("-" * (analytics_name_width + 57))
    for comparison in ranked:
        scenario = comparison.scenario
        analytical = calculate_attack_analytics(
            scenario.attack,
            representative_ac,
            bonus_damage_dice=scenario.bonus_damage_dice,
            advantage=scenario.advantage,
            disadvantage=scenario.disadvantage,
            damage_resistances=getattr(sweep, "damage_resistances", ()),
            damage_vulnerabilities=getattr(sweep, "damage_vulnerabilities", ()),
            damage_immunities=getattr(sweep, "damage_immunities", ()),
        )
        simulated = comparison.results[representative_index]
        simulated_damage = f"{simulated.average_rolled_damage_per_attack:.3f}"
        print(
            f"{scenario.name:<{analytics_name_width}}"
            f"{analytical.hit_probability:>7.1%} "
            f"{analytical.critical_probability:>7.1%} "
            f"{analytical.expected_damage_per_attack:>15.3f} "
            f"{simulated_damage:>20}"
        )
    print(
        "Exact values are calculated from the complete d20 and damage-dice "
        "distributions; pooled simulation values should converge toward them."
    )


def print_turn_summary(
    turn_plans, target, trials, seed, workers=1, results=None
):
    turn_plans = tuple(turn_plans)
    plan_width = max(30, *(len(plan.name) for plan in turn_plans))
    print()
    print(
        f"Fixed turn-plan assumptions against {target.name} "
        f"(AC {target.armor_class}, {target.max_hp} HP)"
    )
    print(f"Trials per turn plan: {trials:,} (seed {seed}, workers {workers})")
    print(
        f"{'Turn plan':<{plan_width}} "
        f"{'Avg turns':>12} {'Avg attacks used':>18}"
    )
    print("-" * (plan_width + 32))
    if results is None:
        results = simulate_turn_plan_batch(
            turn_plans,
            target,
            trials,
            seed=seed,
            workers=workers,
        )
    for turn_plan, result in zip(turn_plans, results):
        print(
            f"{turn_plan.name:<{plan_width}} "
            f"{result.average_turns_to_zero:>12.3f} "
            f"{result.average_attacks_used:>18.3f}"
        )


def print_save_summary(
    save_scenarios, target, trials, seed, workers=1, results=None
):
    print("Uses, recharge, and spell slots are tracked only in duels.")
    print()
    print(
        f"Save-effect uses against {target.name} "
        f"({target.max_hp} HP)"
    )
    print(f"Trials per scenario: {trials:,} (seed {seed}, workers {workers})")
    print(
        f"{'Save scenario':<25} {'Ability':>8} {'Bonus':>7} {'DC':>5} {'Avg uses':>10} "
        f"{'Save success':>14} {'Avg dmg/use':>13}"
    )
    print("-" * 88)
    if results is None:
        results = simulate_saving_throw_scenario_batch(
            save_scenarios,
            target,
            trials,
            seed=seed,
            workers=workers,
        )
    for save_scenario, result in zip(save_scenarios, results):
        print(
            f"{save_scenario.name:<25} "
            f"{(save_scenario.effect.save_ability or '-').upper():>8} "
            f"{save_scenario.target_save_bonus:>+7d} "
            f"{save_scenario.effect.difficulty_class:>5d} "
            f"{result.average_uses_to_zero:>10.3f} "
            f"{result.save_success_rate:>13.1%} "
            f"{result.average_applied_damage_per_use:>13.3f}"
        )
        for limitation in save_scenario.effect.unmodeled_effects:
            print(f"  Note - {save_scenario.name}: {limitation}")
