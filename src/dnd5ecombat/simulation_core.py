"""Shared simulation result types, validation, analytics, and execution helpers."""

from .process_execution import process_map as _process_map  # noqa: F401 - shared batch API
from dataclasses import dataclass
from functools import lru_cache
import math
import random

from .models import (
    AttackProfile,
    AttackScenario,
    DamageDice,
)


class SimulationCancelledError(RuntimeError):
    """Raised when a caller requests cancellation during a simulation."""


def _check_cancellation(cancellation_check):
    if cancellation_check is not None and cancellation_check():
        raise SimulationCancelledError("Simulation cancelled")


@dataclass(frozen=True)
class AttackSimulationResult:
    attempts: int
    hits: int
    critical_hits: int
    total_damage: int

    @property
    def misses(self):
        return self.attempts - self.hits

    @property
    def hit_rate(self):
        return self.hits / self.attempts

    @property
    def critical_hit_rate(self):
        return self.critical_hits / self.attempts

    @property
    def average_damage_per_attack(self):
        return self.total_damage / self.attempts

    @property
    def average_damage_per_hit(self):
        if self.hits == 0:
            return 0.0
        return self.total_damage / self.hits


@dataclass(frozen=True)
class TargetReductionSimulationResult:
    trials: int
    total_attacks: int
    minimum_attacks: int
    maximum_attacks: int
    total_rolled_damage: int
    total_hp_removed: int
    sum_squared_attacks: int
    impossible: bool = False

    @property
    def average_attacks_to_zero(self):
        return math.inf if self.impossible else self.total_attacks / self.trials

    @property
    def average_rolled_damage_per_attack(self):
        if self.total_attacks == 0:
            return 0.0
        return self.total_rolled_damage / self.total_attacks

    @property
    def attacks_to_zero_95_margin(self):
        return _confidence_interval_margin(
            self.total_attacks,
            self.sum_squared_attacks,
            self.trials,
        )

    @property
    def total_overkill(self):
        return self.total_rolled_damage - self.total_hp_removed

    @property
    def average_overkill_per_trial(self):
        return self.total_overkill / self.trials


@dataclass(frozen=True)
class AttackScenarioComparison:
    scenario: AttackScenario
    result: TargetReductionSimulationResult


@dataclass(frozen=True)
class ArmorClassScenarioComparison:
    scenario: AttackScenario
    results: tuple


@dataclass(frozen=True)
class ArmorClassSweepResult:
    target_name: str
    target_max_hp: int
    armor_classes: tuple
    scenario_comparisons: tuple
    damage_resistances: tuple = ()
    damage_vulnerabilities: tuple = ()
    damage_immunities: tuple = ()


@dataclass(frozen=True)
class AnalyticalAttackResult:
    target_ac: int
    hit_probability: float
    critical_probability: float
    expected_damage_per_attack: float
    expected_damage_per_hit: float


@dataclass(frozen=True)
class TurnPlanSimulationResult:
    trials: int
    total_turns: int
    total_attacks: int
    minimum_turns: int
    maximum_turns: int
    total_rolled_damage: int
    total_hp_removed: int
    impossible: bool = False

    @property
    def average_turns_to_zero(self):
        return math.inf if self.impossible else self.total_turns / self.trials

    @property
    def average_attacks_used(self):
        return self.total_attacks / self.trials

    @property
    def total_overkill(self):
        return self.total_rolled_damage - self.total_hp_removed

    @property
    def average_overkill_per_trial(self):
        return self.total_overkill / self.trials


@dataclass(frozen=True)
class SavingThrowSimulationResult:
    trials: int
    total_uses: int
    successful_saves: int
    failed_saves: int
    minimum_uses: int
    maximum_uses: int
    total_rolled_damage: int
    total_applied_damage: int
    total_hp_removed: int
    impossible: bool = False

    @property
    def average_uses_to_zero(self):
        return math.inf if self.impossible else self.total_uses / self.trials

    @property
    def save_success_rate(self):
        if self.total_uses == 0:
            return 0.0
        return self.successful_saves / self.total_uses

    @property
    def average_applied_damage_per_use(self):
        if self.total_uses == 0:
            return 0.0
        return self.total_applied_damage / self.total_uses

    @property
    def total_overkill(self):
        return self.total_applied_damage - self.total_hp_removed

    @property
    def average_overkill_per_trial(self):
        return self.total_overkill / self.trials


@dataclass(frozen=True)
class DuelSimulationResult:
    trials: int
    character_wins: int
    monster_wins: int
    character_initiative_wins: int
    total_rounds: int
    total_character_remaining_hp: int
    total_monster_remaining_hp: int

    @property
    def character_win_rate(self):
        return self.character_wins / self.trials

    @property
    def character_win_95_margin(self):
        probability = self.character_win_rate
        return 1.96 * math.sqrt(
            probability * (1.0 - probability) / self.trials
        )

    @property
    def character_initiative_win_rate(self):
        return self.character_initiative_wins / self.trials

    @property
    def average_rounds(self):
        return self.total_rounds / self.trials

    @property
    def average_character_hp_on_win(self):
        if self.character_wins == 0:
            return 0.0
        return self.total_character_remaining_hp / self.character_wins

    @property
    def average_monster_hp_on_loss(self):
        if self.monster_wins == 0:
            return 0.0
        return self.total_monster_remaining_hp / self.monster_wins


def _validate_trials(trials):
    if not isinstance(trials, int) or isinstance(trials, bool):
        raise TypeError("trials must be an integer")
    if trials < 1:
        raise ValueError("trials must be at least 1")


def _validate_workers(workers):
    if not isinstance(workers, int) or isinstance(workers, bool):
        raise TypeError("workers must be an integer")
    if workers < 1:
        raise ValueError("workers must be at least 1")


def _confidence_interval_margin(total, sum_squares, count):
    if count < 2:
        return 0.0
    sample_variance = max(
        0.0,
        (sum_squares - (total * total) / count) / (count - 1),
    )
    return 1.96 * math.sqrt(sample_variance / count)


@lru_cache(maxsize=None)
def _damage_roll_distribution(
    damage_dice,
    modifier,
    dice_multiplier,
    adjustment="normal",
    reroll_at_or_below=0,
):
    totals = {0: 1}
    for pool in damage_dice:
        for _ in range(pool.number * dice_multiplier):
            next_totals = {}
            for current_total, ways in totals.items():
                for face in range(1, pool.sides + 1):
                    new_total = current_total + face
                    if reroll_at_or_below:
                        face_weight = (
                            reroll_at_or_below
                            if face <= reroll_at_or_below
                            else pool.sides + reroll_at_or_below
                        )
                    else:
                        face_weight = 1
                    next_totals[new_total] = (
                        next_totals.get(new_total, 0) + ways * face_weight
                    )
            totals = next_totals
    outcome_count = sum(totals.values())
    def adjust(value):
        value = max(0, value)
        if adjustment == "immune":
            return 0
        if adjustment == "resistant":
            return value // 2
        if adjustment == "vulnerable":
            return value * 2
        if adjustment == "resistant_vulnerable":
            return (value // 2) * 2
        return value

    probabilities = {}
    for total, ways in totals.items():
        damage = adjust(total + modifier)
        probabilities[damage] = probabilities.get(damage, 0.0) + ways / outcome_count
    return tuple(sorted(probabilities.items()))


@lru_cache(maxsize=None)
def _expected_damage_roll(
    damage_dice, modifier, dice_multiplier, adjustment="normal", reroll_at_or_below=0,
):
    return sum(
        damage * probability
        for damage, probability in _damage_roll_distribution(
            damage_dice, modifier, dice_multiplier, adjustment, reroll_at_or_below
        )
    )


def calculate_attack_analytics(
    attack,
    target_ac,
    bonus_damage_dice=(),
    advantage=False,
    disadvantage=False,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
    critical_on_hit=False,
):
    """Calculate exact hit, critical, and expected-damage values for an attack."""
    if not isinstance(attack, AttackProfile):
        raise TypeError("attack must be an AttackProfile")
    if not isinstance(target_ac, int) or isinstance(target_ac, bool):
        raise TypeError("target_ac must be an integer")
    if not isinstance(advantage, bool) or not isinstance(disadvantage, bool):
        raise TypeError("advantage and disadvantage must be booleans")
    if not isinstance(critical_on_hit, bool):
        raise TypeError("critical_on_hit must be a boolean")
    bonus_pools = _validate_bonus_damage_dice(bonus_damage_dice)

    selected_rolls = []
    if advantage != disadvantage:
        for first in range(1, 21):
            for second in range(1, 21):
                selected_rolls.append(
                    max(first, second) if advantage else min(first, second)
                )
    else:
        selected_rolls.extend(range(1, 21))

    hits = 0
    critical_hits = 0
    for natural_roll in selected_rolls:
        if natural_roll == 1:
            continue
        if natural_roll == 20:
            hits += 1
            critical_hits += 1
        elif natural_roll + attack.attack_bonus >= target_ac:
            hits += 1

    outcome_count = len(selected_rolls)
    if critical_on_hit:
        critical_hits = hits
    hit_probability = hits / outcome_count
    critical_probability = critical_hits / outcome_count
    damage_dice = attack.damage_dice + bonus_pools
    damage_type = attack.damage_type.strip().lower()
    resistant = damage_type in {value.lower() for value in damage_resistances}
    vulnerable = damage_type in {value.lower() for value in damage_vulnerabilities}
    immune = damage_type in {value.lower() for value in damage_immunities}
    if damage_type and immune:
        adjustment = "immune"
    elif damage_type and resistant and vulnerable:
        adjustment = "resistant_vulnerable"
    elif damage_type and (resistant or vulnerable):
        adjustment = "resistant" if resistant else "vulnerable"
    else:
        adjustment = "normal"
    normal_damage = _expected_damage_roll(
        damage_dice,
        attack.damage_modifier,
        1,
        adjustment,
        attack.reroll_damage_at_or_below,
    )
    critical_damage = _expected_damage_roll(
        damage_dice,
        attack.damage_modifier,
        2,
        adjustment,
        attack.reroll_damage_at_or_below,
    )
    expected_damage = (
        (hit_probability - critical_probability) * normal_damage
        + critical_probability * critical_damage
    )
    expected_damage_per_hit = (
        expected_damage / hit_probability if hit_probability else 0.0
    )
    return AnalyticalAttackResult(
        target_ac=target_ac,
        hit_probability=hit_probability,
        critical_probability=critical_probability,
        expected_damage_per_attack=expected_damage,
        expected_damage_per_hit=expected_damage_per_hit,
    )

def _validate_bonus_damage_dice(bonus_damage_dice):
    try:
        bonus_pools = tuple(bonus_damage_dice)
    except TypeError as error:
        raise TypeError(
            "bonus_damage_dice must be an iterable of DamageDice"
        ) from error
    if not all(isinstance(pool, DamageDice) for pool in bonus_pools):
        raise TypeError("every bonus damage pool must be DamageDice")
    return bonus_pools


def _create_random_source(seed, rng):
    if seed is not None and rng is not None:
        raise ValueError("provide either seed or rng, not both")
    return rng if rng is not None else random.Random(seed)
