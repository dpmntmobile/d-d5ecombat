"""Deterministic scoring of repeated attacks against survival traits."""

from math import inf

from .combat import apply_damage_defenses
from .simulation_core import _damage_roll_distribution, calculate_attack_analytics


def expected_attacks_to_defeat(attack, target):
    """Expected attacks from full HP, holding attack and roll mode constant.

    Solve HP states from 1 upward. Misses and zero damage leave HP unchanged;
    Fortitude success sends lethal hits to 1 HP, including a self-loop at 1.
    Critical hits and radiant damage bypass Fortitude. No random draws are used.
    """
    analytics = calculate_attack_analytics(attack, target.armor_class)
    outcomes = []
    for critical, hit_probability in (
        (False, analytics.hit_probability - analytics.critical_probability),
        (True, analytics.critical_probability),
    ):
        if not hit_probability:
            continue
        for rolled_damage, probability in _damage_roll_distribution(
            attack.damage_dice, attack.damage_modifier, 2 if critical else 1,
            reroll_at_or_below=attack.reroll_damage_at_or_below,
        ):
            damage = apply_damage_defenses(
                rolled_damage, attack.damage_type,
                resistances=target.damage_resistances,
                vulnerabilities=target.damage_vulnerabilities,
                immunities=target.damage_immunities,
            )
            if damage == 0:
                continue
            survival = 0.0
            if (
                target.undead_fortitude and not critical
                and attack.damage_type.strip().lower() != "radiant"
            ):
                required_roll = 5 + damage - target.get_saving_throw_bonus("con")
                survival = max(0, min(20, 21 - required_roll)) / 20
            outcomes.append((damage, hit_probability * probability, survival))

    expectations = [0.0]
    for hp in range(1, target.max_hp + 1):
        progress_probability = 0.0
        future_attacks = 0.0
        for damage, probability, survival in outcomes:
            if damage < hp:
                progress_probability += probability
                future_attacks += probability * expectations[hp - damage]
            elif hp == 1:
                progress_probability += probability * (1 - survival)
            else:
                progress_probability += probability
                if survival:
                    future_attacks += probability * survival * expectations[1]
        expectations.append(
            (1 + future_attacks) / progress_probability
            if progress_probability else inf
        )
    return expectations[-1]
