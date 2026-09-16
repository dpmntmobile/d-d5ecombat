# ruff: noqa: F401
"""Public simulation API assembled from focused simulation modules."""

from .attack_simulation import (
    compare_attack_scenarios,
    compare_attack_scenarios_by_ac,
    simulate_attacks,
    simulate_attacks_to_zero,
    simulate_saving_throw_scenario_batch,
    simulate_saving_throw_uses_to_zero,
    simulate_turn_plan_batch,
    simulate_turns_to_zero,
)
from .duel_simulation import (
    select_attack_sequence,
    select_best_attack,
    select_best_monster_duel_policy,
    simulate_duel,
    simulate_duel_batch,
)
from .simulation_core import (
    AnalyticalAttackResult,
    ArmorClassScenarioComparison,
    ArmorClassSweepResult,
    AttackScenarioComparison,
    AttackSimulationResult,
    DuelSimulationResult,
    SavingThrowSimulationResult,
    SimulationCancelledError,
    TargetReductionSimulationResult,
    TurnPlanSimulationResult,
    calculate_attack_analytics,
)


__all__ = tuple(name for name in globals() if not name.startswith("_"))
