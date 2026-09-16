"""Compatibility API for focused attack, turn, and save simulations."""

from .attack_trials import (
    compare_attack_scenarios,
    compare_attack_scenarios_by_ac,
    simulate_attacks,
    simulate_attacks_to_zero,
)
from .saving_throw_simulation import (
    simulate_saving_throw_scenario_batch,
    simulate_saving_throw_uses_to_zero,
)
from .turn_simulation import simulate_turn_plan_batch, simulate_turns_to_zero


__all__ = (
    "compare_attack_scenarios",
    "compare_attack_scenarios_by_ac",
    "simulate_attacks",
    "simulate_attacks_to_zero",
    "simulate_saving_throw_scenario_batch",
    "simulate_saving_throw_uses_to_zero",
    "simulate_turn_plan_batch",
    "simulate_turns_to_zero",
)
