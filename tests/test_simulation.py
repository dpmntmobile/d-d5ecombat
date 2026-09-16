import random
import math
import unittest

from dnd5ecombat.combat import roll_initiative
from dnd5ecombat.models import (
    AttackProfile,
    AttackScenario,
    Condition,
    DamageDice,
    DuelCombatant,
    DuelMatchup,
    FirstHitBonusDamage,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
    SavingThrowScenario,
    SavingThrowConditionEffect,
    TargetProfile,
    TurnPlan,
)
from dnd5ecombat.simulation import (
    AttackSimulationResult,
    ArmorClassSweepResult,
    DuelSimulationResult,
    SimulationCancelledError,
    TargetReductionSimulationResult,
    SavingThrowSimulationResult,
    TurnPlanSimulationResult,
    calculate_attack_analytics,
    compare_attack_scenarios,
    compare_attack_scenarios_by_ac,
    simulate_attacks,
    simulate_attacks_to_zero,
    select_best_attack,
    select_attack_sequence,
    select_best_monster_duel_policy,
    simulate_duel,
    simulate_duel_batch,
    simulate_saving_throw_uses_to_zero,
    simulate_saving_throw_scenario_batch,
    simulate_turn_plan_batch,
    simulate_turns_to_zero,
)


class SequenceRng:
    def __init__(self, results):
        self.results = iter(results)

    def randint(self, minimum, maximum):
        result = next(self.results)
        if not minimum <= result <= maximum:
            raise ValueError("sequence result is outside the requested range")
        return result


class DuelSimulationTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Attack", 0, (DamageDice(1, 2),))
        self.character = DuelCombatant("Hero", 10, 1, 0, self.attack)
        self.monster = DuelCombatant("Monster", 10, 1, 0, self.attack)

    def test_best_monster_policy_minimizes_character_wins(self):
        weaker = DuelMatchup(self.character, self.monster)
        stronger_attack = AttackProfile(
            "Stronger", 1, (DamageDice(1, 4),)
        )
        stronger_monster = DuelCombatant(
            "Monster", 10, 2, 0, stronger_attack
        )
        stronger = DuelMatchup(self.character, stronger_monster)
        weaker_result = DuelSimulationResult(100, 70, 30, 50, 200, 100, 60)
        stronger_result = DuelSimulationResult(100, 40, 60, 50, 300, 80, 180)

        matchup, result, index = select_best_monster_duel_policy(
            (weaker, stronger), (weaker_result, stronger_result)
        )

        self.assertIs(matchup, stronger)
        self.assertIs(result, stronger_result)
        self.assertEqual(index, 1)

    def test_best_monster_policy_uses_remaining_hp_as_tiebreaker(self):
        first = DuelMatchup(self.character, self.monster)
        second = DuelMatchup(self.character, self.monster)
        first_result = DuelSimulationResult(10, 4, 6, 5, 20, 5, 12)
        second_result = DuelSimulationResult(10, 4, 6, 5, 30, 5, 18)

        _, result, index = select_best_monster_duel_policy(
            (first, second), (first_result, second_result)
        )

        self.assertIs(result, second_result)
        self.assertEqual(index, 1)

    def test_initiative_order_determines_which_lethal_attack_happens_first(self):
        character_first = simulate_duel(
            1,
            DuelMatchup(self.character, self.monster),
            rng=SequenceRng([20, 1, 10, 1]),
        )
        monster_first = simulate_duel(
            1,
            DuelMatchup(self.character, self.monster),
            rng=SequenceRng([1, 20, 10, 1]),
        )

        self.assertEqual(character_first.character_wins, 1)
        self.assertEqual(character_first.average_rounds, 1.0)
        self.assertEqual(character_first.average_character_hp_on_win, 1.0)
        self.assertEqual(monster_first.monster_wins, 1)
        self.assertEqual(monster_first.average_monster_hp_on_loss, 1.0)

    def test_attacks_per_turn_are_used(self):
        two_attack_character = DuelCombatant(
            "Hero", 10, 1, 0, self.attack, attacks_per_turn=2
        )
        result = simulate_duel(
            1,
            DuelMatchup(two_attack_character, self.monster),
            rng=SequenceRng([20, 1, 1, 10, 1]),
        )

        self.assertEqual(result.character_wins, 1)

    def test_explicit_multiattack_sequence_is_used(self):
        two_attack_monster = DuelCombatant(
            "Monster",
            10,
            1,
            0,
            self.attack,
            attack_sequence=(self.attack, self.attack),
        )
        hero = DuelCombatant("Hero", 10, 2, 0, self.attack)

        result = simulate_duel(
            1,
            DuelMatchup(hero, two_attack_monster),
            rng=SequenceRng([1, 20, 10, 1, 10, 1]),
        )

        self.assertEqual(result.monster_wins, 1)

    def test_paralysis_skips_turn_and_melee_hits_are_critical(self):
        paralyzing_attack = AttackProfile(
            "Claws",
            0,
            (DamageDice(1, 2),),
            attack_mode="melee",
            condition_effect=SavingThrowConditionEffect(
                10,
                "con",
                Condition.PARALYZED,
                repeat_save_at_end_of_turn=True,
            ),
        )
        hero = DuelCombatant(
            "Hero", 10, 3, 0, self.attack, saving_throw_bonuses={"con": 0}
        )
        monster = DuelCombatant("Monster", 10, 10, 0, paralyzing_attack)

        result = simulate_duel(
            1,
            DuelMatchup(hero, monster),
            rng=SequenceRng([1, 20, 10, 1, 1, 1, 10, 10, 1, 1]),
        )

        self.assertEqual(result.monster_wins, 1)

    def test_best_attack_uses_exact_expected_damage_and_preserves_ties(self):
        weaker = AttackProfile("Weaker", 5, (DamageDice(1, 4),), 1)
        stronger = AttackProfile("Stronger", 5, (DamageDice(1, 8),), 2)

        self.assertIs(select_best_attack((weaker, stronger), 15), stronger)
        self.assertIs(select_best_attack((weaker, weaker), 15), weaker)

    def test_attack_selection_honors_damage_immunity_and_multiattack(self):
        fire = AttackProfile(
            "Fire", 5, (DamageDice(2, 8),), damage_type="fire"
        )
        cold = AttackProfile(
            "Cold", 5, (DamageDice(1, 4),), damage_type="cold"
        )

        self.assertIs(
            select_best_attack((fire, cold), 15, damage_immunities=("fire",)),
            cold,
        )
        self.assertEqual(
            select_attack_sequence((fire, cold), ("cold", "fire"), 15),
            (cold, fire),
        )

    def test_parallel_duels_match_sequential_results(self):
        matchups = (
            DuelMatchup(self.character, self.monster),
            DuelMatchup(self.character, self.monster),
        )

        sequential = simulate_duel_batch(
            matchups, trials=50, seed=42, workers=1
        )
        parallel = simulate_duel_batch(
            matchups, trials=50, seed=42, workers=2
        )

        self.assertEqual(parallel, sequential)

    def test_duel_rejects_a_damage_immunity_stalemate(self):
        poison = AttackProfile(
            "Poison", 5, (DamageDice(1, 6),), damage_type="poison"
        )
        first = DuelCombatant(
            "First", 10, 10, 0, poison, damage_immunities=("poison",)
        )
        second = DuelCombatant(
            "Second", 10, 10, 0, poison, damage_immunities=("poison",)
        )

        with self.assertRaisesRegex(ValueError, "neither combatant"):
            simulate_duel(1, DuelMatchup(first, second))


class SimulateAttacksTests(unittest.TestCase):
    def test_simulation_aggregates_attack_results(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        result = simulate_attacks(
            3,
            attack=attack,
            target_ac=15,
            rng=SequenceRng([5, 10, 4, 20, 2, 3]),
        )

        self.assertEqual(result, AttackSimulationResult(3, 2, 1, 15))
        self.assertEqual(result.misses, 1)
        self.assertEqual(result.hit_rate, 2 / 3)
        self.assertEqual(result.critical_hit_rate, 1 / 3)
        self.assertEqual(result.average_damage_per_attack, 5.0)
        self.assertEqual(result.average_damage_per_hit, 7.5)

    def test_misses_do_not_roll_or_deal_damage(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 8)])
        result = simulate_attacks(
            2,
            attack=attack,
            target_ac=20,
            rng=SequenceRng([1, 2]),
        )

        self.assertEqual(result.hits, 0)
        self.assertEqual(result.total_damage, 0)
        self.assertEqual(result.average_damage_per_hit, 0.0)

    def test_simulation_passes_through_advantage(self):
        attack = AttackProfile("Test attack", 3, [DamageDice(1, 8)], 2)
        result = simulate_attacks(
            1,
            attack=attack,
            target_ac=15,
            advantage=True,
            rng=SequenceRng([5, 14, 4]),
        )

        self.assertEqual(result.hits, 1)
        self.assertEqual(result.total_damage, 6)

    def test_fixed_seed_is_reproducible(self):
        attack = AttackProfile(
            "Test attack",
            5,
            [DamageDice(1, 8), DamageDice(1, 6)],
            3,
        )
        arguments = {
            "trials": 100,
            "attack": attack,
            "target_ac": 15,
            "seed": 42,
        }

        self.assertEqual(simulate_attacks(**arguments), simulate_attacks(**arguments))

    def test_no_seed_uses_an_independent_random_source(self):
        original_state = random.getstate()
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)])

        simulate_attacks(
            1,
            attack=attack,
            target_ac=10,
        )

        self.assertEqual(random.getstate(), original_state)

    def test_trials_must_be_a_positive_integer(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)])
        for trials, error_type in [(0, ValueError), (-1, ValueError), (1.5, TypeError)]:
            with self.subTest(trials=trials):
                with self.assertRaises(error_type):
                    simulate_attacks(
                        trials,
                        attack=attack,
                        target_ac=10,
                    )

    def test_seed_and_rng_cannot_both_be_provided(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)])
        with self.assertRaises(ValueError):
            simulate_attacks(
                1,
                attack=attack,
                target_ac=10,
                seed=42,
                rng=SequenceRng([10, 2]),
            )

    def test_bonus_damage_pools_are_validated_before_trials_begin(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)])
        with self.assertRaises(TypeError):
            simulate_attacks(
                1,
                attack=attack,
                target_ac=100,
                bonus_damage_dice=[(1, 6)],
                rng=SequenceRng([2]),
            )

    def test_conditional_bonus_damage_is_explicit(self):
        attack = AttackProfile("Rapier", 5, [DamageDice(1, 8)], 3)
        result = simulate_attacks(
            1,
            attack=attack,
            target_ac=15,
            bonus_damage_dice=[DamageDice(2, 6)],
            rng=SequenceRng([10, 4, 2, 5]),
        )

        self.assertEqual(result.total_damage, 14)


class CalculateAttackAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Rapier", 5, [DamageDice(1, 8)], 3)

    def test_normal_attack_probabilities_and_damage_are_exact(self):
        result = calculate_attack_analytics(self.attack, target_ac=15)

        self.assertAlmostEqual(result.hit_probability, 0.55)
        self.assertAlmostEqual(result.critical_probability, 0.05)
        self.assertAlmostEqual(result.expected_damage_per_attack, 4.35)
        self.assertAlmostEqual(result.expected_damage_per_hit, 4.35 / 0.55)

    def test_damage_rerolls_are_included_in_exact_damage(self):
        greatsword = AttackProfile(
            "Greatsword",
            5,
            [DamageDice(2, 6)],
            4,
            reroll_damage_at_or_below=2,
        )

        result = calculate_attack_analytics(greatsword, target_ac=15)

        self.assertAlmostEqual(result.expected_damage_per_attack, 7.2)

    def test_advantage_and_disadvantage_use_exact_d20_distributions(self):
        advantage = calculate_attack_analytics(
            self.attack, target_ac=15, advantage=True
        )
        disadvantage = calculate_attack_analytics(
            self.attack, target_ac=15, disadvantage=True
        )

        self.assertAlmostEqual(advantage.hit_probability, 0.7975)
        self.assertAlmostEqual(advantage.critical_probability, 0.0975)
        self.assertAlmostEqual(advantage.expected_damage_per_attack, 6.42)
        self.assertAlmostEqual(disadvantage.hit_probability, 0.3025)
        self.assertAlmostEqual(disadvantage.critical_probability, 0.0025)

    def test_bonus_dice_are_included_and_doubled_on_a_critical(self):
        result = calculate_attack_analytics(
            AttackProfile("Attack", -100, [DamageDice(1, 4)]),
            target_ac=100,
            bonus_damage_dice=(DamageDice(1, 6),),
        )

        self.assertAlmostEqual(result.hit_probability, 0.05)
        self.assertAlmostEqual(result.critical_probability, 0.05)
        self.assertAlmostEqual(result.expected_damage_per_attack, 0.6)

    def test_advantage_and_disadvantage_cancel(self):
        normal = calculate_attack_analytics(self.attack, target_ac=15)
        cancelled = calculate_attack_analytics(
            self.attack, target_ac=15, advantage=True, disadvantage=True
        )

        self.assertEqual(cancelled, normal)

    def test_seeded_monte_carlo_converges_to_exact_values(self):
        analytical = calculate_attack_analytics(self.attack, target_ac=15)
        simulated = simulate_attacks(
            50_000, self.attack, target_ac=15, seed=42
        )

        self.assertAlmostEqual(
            simulated.hit_rate, analytical.hit_probability, delta=0.01
        )
        self.assertAlmostEqual(
            simulated.critical_hit_rate,
            analytical.critical_probability,
            delta=0.005,
        )
        self.assertAlmostEqual(
            simulated.average_damage_per_attack,
            analytical.expected_damage_per_attack,
            delta=0.05,
        )


class SimulateAttacksToZeroTests(unittest.TestCase):
    def test_fully_immune_target_reports_that_reduction_is_impossible(self):
        attack = AttackProfile(
            "Poison", 5, (DamageDice(1, 6),), damage_type="poison"
        )
        target = TargetProfile(
            "Immune target", 10, 10, damage_immunities=("poison",)
        )

        result = simulate_attacks_to_zero(5, attack, target, seed=1)

        self.assertTrue(result.impossible)
        self.assertTrue(math.isinf(result.average_attacks_to_zero))
        self.assertEqual(result.average_rolled_damage_per_attack, 0.0)

    def test_cancellation_is_checked_inside_trial_loop(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        target = TargetProfile("Generic target", 15, 10)
        checks = 0

        def cancel_after_first_check():
            nonlocal checks
            checks += 1
            return checks > 1

        with self.assertRaises(SimulationCancelledError):
            simulate_attacks_to_zero(
                10_000,
                attack,
                target,
                seed=1,
                cancellation_check=cancel_after_first_check,
            )

        self.assertEqual(checks, 2)

    def test_attacks_to_zero_confidence_margin_uses_trial_variance(self):
        result = TargetReductionSimulationResult(
            trials=2,
            total_attacks=4,
            minimum_attacks=1,
            maximum_attacks=3,
            total_rolled_damage=10,
            total_hp_removed=10,
            sum_squared_attacks=10,
        )

        self.assertEqual(result.average_attacks_to_zero, 2.0)
        self.assertAlmostEqual(result.attacks_to_zero_95_margin, 1.96)

    def test_persistent_hp_is_reduced_until_zero(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        target = TargetProfile("Generic target", 15, 10)

        result = simulate_attacks_to_zero(
            1,
            attack,
            target,
            rng=SequenceRng([5, 10, 4, 10, 4]),
        )

        self.assertEqual(
            result,
            TargetReductionSimulationResult(
                trials=1,
                total_attacks=3,
                minimum_attacks=3,
                maximum_attacks=3,
                total_rolled_damage=14,
                total_hp_removed=10,
                sum_squared_attacks=9,
            ),
        )
        self.assertEqual(result.average_attacks_to_zero, 3.0)
        self.assertEqual(result.average_rolled_damage_per_attack, 14 / 3)
        self.assertEqual(result.total_overkill, 4)
        self.assertEqual(result.average_overkill_per_trial, 4.0)

    def test_each_trial_resets_target_hp(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)], 1)
        target = TargetProfile("Generic target", 10, 5)

        result = simulate_attacks_to_zero(
            2,
            attack,
            target,
            rng=SequenceRng([10, 4, 10, 4]),
        )

        self.assertEqual(result.total_attacks, 2)
        self.assertEqual(result.minimum_attacks, 1)
        self.assertEqual(result.maximum_attacks, 1)
        self.assertEqual(result.total_hp_removed, 10)

    def test_overkill_is_not_counted_as_hp_removed(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 8)])
        target = TargetProfile("Generic target", 10, 3)

        result = simulate_attacks_to_zero(
            1,
            attack,
            target,
            rng=SequenceRng([10, 8]),
        )

        self.assertEqual(result.total_rolled_damage, 8)
        self.assertEqual(result.total_hp_removed, 3)

    def test_conditional_damage_is_applied_to_every_attempt(self):
        attack = AttackProfile("Rapier", 0, [DamageDice(1, 8)], 3)
        target = TargetProfile("Generic target", 10, 10)

        result = simulate_attacks_to_zero(
            1,
            attack,
            target,
            bonus_damage_dice=[DamageDice(1, 6)],
            rng=SequenceRng([10, 2, 5]),
        )

        self.assertEqual(result.total_rolled_damage, 10)
        self.assertEqual(result.total_attacks, 1)

    def test_fixed_seed_is_reproducible(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        target = TargetProfile("Generic target", 15, 20)

        first = simulate_attacks_to_zero(20, attack, target, seed=42)
        second = simulate_attacks_to_zero(20, attack, target, seed=42)

        self.assertEqual(first, second)

    def test_attack_limit_prevents_an_infinite_simulation(self):
        attack = AttackProfile("Inaccurate attack", 0, [DamageDice(1, 2)])
        target = TargetProfile("Generic target", 10, 1)

        with self.assertRaises(RuntimeError):
            simulate_attacks_to_zero(
                1,
                attack,
                target,
                max_attacks_per_trial=1,
                rng=SequenceRng([2]),
            )

    def test_attack_limit_must_be_a_positive_integer(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 4)])
        target = TargetProfile("Generic target", 10, 5)

        with self.assertRaises(ValueError):
            simulate_attacks_to_zero(
                1, attack, target, max_attacks_per_trial=0
            )

    def test_roll_initiative_uses_d20_plus_modifier(self):
        rng = random.Random(0)
        result = roll_initiative(3, rng=rng)

        self.assertGreaterEqual(result, 4)
        self.assertLessEqual(result, 23)

class CompareAttackScenariosTests(unittest.TestCase):
    def setUp(self):
        self.target = TargetProfile("Generic target", 15, 20)
        self.light_attack = AttackProfile(
            "Light attack", 5, [DamageDice(1, 6)], 3
        )
        self.heavy_attack = AttackProfile(
            "Heavy attack", 5, [DamageDice(2, 6)], 3
        )
        self.scenarios = (
            AttackScenario("Light", self.light_attack),
            AttackScenario("Heavy", self.heavy_attack),
        )

    def test_comparison_preserves_scenario_order(self):
        comparisons = compare_attack_scenarios(
            self.scenarios, self.target, trials=100, seed=42
        )

        self.assertEqual(
            tuple(comparison.scenario for comparison in comparisons),
            self.scenarios,
        )
        self.assertTrue(
            all(comparison.result.trials == 100 for comparison in comparisons)
        )

    def test_comparison_with_fixed_seed_is_reproducible(self):
        first = compare_attack_scenarios(
            self.scenarios, self.target, trials=100, seed=42
        )
        second = compare_attack_scenarios(
            self.scenarios, self.target, trials=100, seed=42
        )

        self.assertEqual(first, second)

    def test_scenario_tactical_assumptions_are_applied(self):
        scenarios = (
            AttackScenario("Normal", self.light_attack),
            AttackScenario("Advantage", self.light_attack, advantage=True),
        )

        comparisons = compare_attack_scenarios(
            scenarios, self.target, trials=1_000, seed=42
        )

        self.assertLess(
            comparisons[1].result.average_attacks_to_zero,
            comparisons[0].result.average_attacks_to_zero,
        )

    def test_comparison_requires_at_least_one_valid_scenario(self):
        with self.assertRaises(ValueError):
            compare_attack_scenarios([], self.target, trials=10, seed=42)

        with self.assertRaises(TypeError):
            compare_attack_scenarios(
                ["scenario"], self.target, trials=10, seed=42
            )


class CompareAttackScenariosByArmorClassTests(unittest.TestCase):
    def setUp(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        self.scenarios = (
            AttackScenario("Normal", attack),
            AttackScenario("Advantage", attack, advantage=True),
        )

    def test_sweep_preserves_ac_and_scenario_order(self):
        result = compare_attack_scenarios_by_ac(
            self.scenarios,
            armor_classes=(12, 16, 20),
            target_max_hp=20,
            trials=100,
            seed=42,
        )

        self.assertIsInstance(result, ArmorClassSweepResult)
        self.assertEqual(result.armor_classes, (12, 16, 20))
        self.assertEqual(
            tuple(row.scenario for row in result.scenario_comparisons),
            self.scenarios,
        )
        self.assertTrue(
            all(len(row.results) == 3 for row in result.scenario_comparisons)
        )

    def test_sweep_uses_fixed_target_hp_for_every_ac(self):
        result = compare_attack_scenarios_by_ac(
            self.scenarios,
            armor_classes=(12, 20),
            target_max_hp=17,
            trials=10,
            seed=42,
        )

        self.assertEqual(result.target_max_hp, 17)
        for row in result.scenario_comparisons:
            for simulation_result in row.results:
                self.assertEqual(simulation_result.total_hp_removed, 170)

    def test_fixed_seed_is_reproducible(self):
        arguments = {
            "scenarios": self.scenarios,
            "armor_classes": (12, 16, 20),
            "target_max_hp": 20,
            "trials": 100,
            "seed": 42,
        }

        self.assertEqual(
            compare_attack_scenarios_by_ac(**arguments),
            compare_attack_scenarios_by_ac(**arguments),
        )

    def test_parallel_sweep_matches_single_process_results(self):
        arguments = {
            "scenarios": self.scenarios,
            "armor_classes": (12, 16, 20),
            "target_max_hp": 20,
            "trials": 100,
            "seed": 42,
        }

        sequential = compare_attack_scenarios_by_ac(**arguments, workers=1)
        parallel = compare_attack_scenarios_by_ac(**arguments, workers=2)

        self.assertEqual(parallel, sequential)

    def test_worker_count_must_be_positive(self):
        with self.assertRaises(ValueError):
            compare_attack_scenarios_by_ac(
                self.scenarios,
                armor_classes=(15,),
                target_max_hp=20,
                trials=10,
                workers=0,
            )

    def test_armor_classes_cannot_be_empty_or_duplicated(self):
        with self.assertRaises(ValueError):
            compare_attack_scenarios_by_ac(
                self.scenarios, [], target_max_hp=20, trials=10
            )

        with self.assertRaises(ValueError):
            compare_attack_scenarios_by_ac(
                self.scenarios, [15, 15], target_max_hp=20, trials=10
            )

    def test_every_armor_class_must_be_an_integer(self):
        with self.assertRaises(TypeError):
            compare_attack_scenarios_by_ac(
                self.scenarios, [15, 16.5], target_max_hp=20, trials=10
            )


class SimulateTurnsToZeroTests(unittest.TestCase):
    def setUp(self):
        attack = AttackProfile("Weapon attack", 0, [DamageDice(1, 4)])
        self.attack_scenario = AttackScenario("Weapon attack", attack)

    def test_attacks_execute_in_order_across_turns(self):
        turn_plan = TurnPlan(
            "Two attacks", (self.attack_scenario, self.attack_scenario)
        )
        target = TargetProfile("Generic target", 10, 8)

        result = simulate_turns_to_zero(
            1,
            turn_plan,
            target,
            rng=SequenceRng([10, 2, 10, 2, 10, 4]),
        )

        self.assertEqual(
            result,
            TurnPlanSimulationResult(
                trials=1,
                total_turns=2,
                total_attacks=3,
                minimum_turns=2,
                maximum_turns=2,
                total_rolled_damage=8,
                total_hp_removed=8,
            ),
        )
        self.assertEqual(result.average_turns_to_zero, 2.0)
        self.assertEqual(result.average_attacks_used, 3.0)

    def test_unused_attacks_are_skipped_after_target_reaches_zero(self):
        turn_plan = TurnPlan(
            "Two attacks", (self.attack_scenario, self.attack_scenario)
        )
        target = TargetProfile("Generic target", 10, 3)

        result = simulate_turns_to_zero(
            1, turn_plan, target, rng=SequenceRng([10, 4])
        )

        self.assertEqual(result.total_turns, 1)
        self.assertEqual(result.total_attacks, 1)
        self.assertEqual(result.total_rolled_damage, 4)
        self.assertEqual(result.total_hp_removed, 3)
        self.assertEqual(result.total_overkill, 1)
        self.assertEqual(result.average_overkill_per_trial, 1.0)

    def test_attack_scenario_assumptions_are_used(self):
        advantaged = AttackScenario(
            "Advantaged attack", self.attack_scenario.attack, advantage=True
        )
        turn_plan = TurnPlan("Advantaged attack", [advantaged])
        target = TargetProfile("Generic target", 15, 4)

        result = simulate_turns_to_zero(
            1, turn_plan, target, rng=SequenceRng([5, 15, 4])
        )

        self.assertEqual(result.total_turns, 1)
        self.assertEqual(result.total_attacks, 1)

    def test_fixed_seed_is_reproducible(self):
        turn_plan = TurnPlan("One attack", [self.attack_scenario])
        target = TargetProfile("Generic target", 10, 10)

        first = simulate_turns_to_zero(100, turn_plan, target, seed=42)
        second = simulate_turns_to_zero(100, turn_plan, target, seed=42)

        self.assertEqual(first, second)

    def test_parallel_turn_plan_batch_matches_sequential_results(self):
        plans = (
            TurnPlan("One attack", [self.attack_scenario]),
            TurnPlan("Two attacks", [self.attack_scenario, self.attack_scenario]),
        )
        target = TargetProfile("Generic target", 10, 10)

        sequential = simulate_turn_plan_batch(
            plans, target, trials=100, seed=42, workers=1
        )
        parallel = simulate_turn_plan_batch(
            plans, target, trials=100, seed=42, workers=2
        )

        self.assertEqual(parallel, sequential)

    def test_turn_limit_prevents_an_infinite_simulation(self):
        harmless_attack = AttackProfile(
            "Inaccurate attack", 0, [DamageDice(1, 2)]
        )
        turn_plan = TurnPlan(
            "Harmless turn", [AttackScenario("Harmless attack", harmless_attack)]
        )
        target = TargetProfile("Generic target", 10, 1)

        with self.assertRaises(RuntimeError):
            simulate_turns_to_zero(
                1,
                turn_plan,
                target,
                max_turns_per_trial=1,
                rng=SequenceRng([2]),
            )

    def test_turn_limit_must_be_a_positive_integer(self):
        turn_plan = TurnPlan("One attack", [self.attack_scenario])
        target = TargetProfile("Generic target", 10, 1)

        with self.assertRaises(ValueError):
            simulate_turns_to_zero(
                1, turn_plan, target, max_turns_per_trial=0
            )

    def test_first_hit_bonus_moves_to_a_later_attack_after_a_miss(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [0, 1]
        )
        turn_plan = TurnPlan(
            "Two attacks", [self.attack_scenario, self.attack_scenario], bonus
        )
        target = TargetProfile("Generic target", 10, 7)

        result = simulate_turns_to_zero(
            1,
            turn_plan,
            target,
            rng=SequenceRng([5, 10, 2, 5]),
        )

        self.assertEqual(result.total_turns, 1)
        self.assertEqual(result.total_attacks, 2)
        self.assertEqual(result.total_rolled_damage, 7)

    def test_first_hit_bonus_is_used_only_once_per_turn(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [0, 1]
        )
        turn_plan = TurnPlan(
            "Two attacks", [self.attack_scenario, self.attack_scenario], bonus
        )
        target = TargetProfile("Generic target", 10, 7)

        result = simulate_turns_to_zero(
            1,
            turn_plan,
            target,
            rng=SequenceRng([10, 2, 3, 10, 2]),
        )

        self.assertEqual(result.total_attacks, 2)
        self.assertEqual(result.total_rolled_damage, 7)

    def test_first_hit_bonus_dice_are_doubled_on_a_critical_hit(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [0]
        )
        turn_plan = TurnPlan("One attack", [self.attack_scenario], bonus)
        target = TargetProfile("Generic target", 30, 10)

        result = simulate_turns_to_zero(
            1,
            turn_plan,
            target,
            rng=SequenceRng([20, 1, 2, 3, 4]),
        )

        self.assertEqual(result.total_turns, 1)
        self.assertEqual(result.total_rolled_damage, 10)

    def test_first_hit_bonus_resets_at_the_start_of_each_turn(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [0]
        )
        turn_plan = TurnPlan("One attack", [self.attack_scenario], bonus)
        target = TargetProfile("Generic target", 10, 10)

        result = simulate_turns_to_zero(
            1,
            turn_plan,
            target,
            rng=SequenceRng([10, 2, 3, 10, 2, 3]),
        )

        self.assertEqual(result.total_turns, 2)
        self.assertEqual(result.total_rolled_damage, 10)

    def test_first_hit_bonus_is_not_rolled_when_no_eligible_attack_hits(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [0, 1]
        )
        turn_plan = TurnPlan(
            "Two attacks", [self.attack_scenario, self.attack_scenario], bonus
        )
        target = TargetProfile("Generic target", 20, 1)

        with self.assertRaises(RuntimeError):
            simulate_turns_to_zero(
                1,
                turn_plan,
                target,
                max_turns_per_trial=1,
                rng=SequenceRng([5, 5]),
            )


class SimulateSavingThrowUsesToZeroTests(unittest.TestCase):
    def test_damage_immunity_reports_that_reduction_is_impossible(self):
        effect = SavingThrowDamageProfile(
            "Poison effect",
            10,
            [DamageDice(1, 8)],
            damage_type="poison",
        )
        scenario = SavingThrowScenario("Poison", effect, 0)
        target = TargetProfile(
            "Immune target", 10, 8, damage_immunities=("poison",)
        )

        result = simulate_saving_throw_uses_to_zero(2, scenario, target)

        self.assertTrue(result.impossible)
        self.assertTrue(math.isinf(result.average_uses_to_zero))

    def test_successful_and_failed_saves_are_aggregated(self):
        effect = SavingThrowDamageProfile(
            "Generic effect",
            10,
            [DamageDice(1, 8)],
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 0)
        target = TargetProfile("Generic target", 10, 8)

        result = simulate_saving_throw_uses_to_zero(
            1,
            scenario,
            target,
            rng=SequenceRng([15, 5, 5, 6]),
        )

        self.assertEqual(
            result,
            SavingThrowSimulationResult(
                trials=1,
                total_uses=2,
                successful_saves=1,
                failed_saves=1,
                minimum_uses=2,
                maximum_uses=2,
                total_rolled_damage=11,
                total_applied_damage=8,
                total_hp_removed=8,
            ),
        )
        self.assertEqual(result.average_uses_to_zero, 2.0)
        self.assertEqual(result.save_success_rate, 0.5)
        self.assertEqual(result.average_applied_damage_per_use, 4.0)

    def test_successful_no_damage_save_does_not_add_rolled_damage(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 0)
        target = TargetProfile("Generic target", 10, 4)

        result = simulate_saving_throw_uses_to_zero(
            1,
            scenario,
            target,
            rng=SequenceRng([15, 5, 4]),
        )

        self.assertEqual(result.total_uses, 2)
        self.assertEqual(result.successful_saves, 1)
        self.assertEqual(result.failed_saves, 1)
        self.assertEqual(result.total_rolled_damage, 4)
        self.assertEqual(result.total_applied_damage, 4)

    def test_each_trial_resets_target_hp(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 4)]
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 0)
        target = TargetProfile("Generic target", 10, 4)

        result = simulate_saving_throw_uses_to_zero(
            2,
            scenario,
            target,
            rng=SequenceRng([5, 4, 5, 4]),
        )

        self.assertEqual(result.total_uses, 2)
        self.assertEqual(result.total_hp_removed, 8)

    def test_overkill_uses_applied_damage(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 0)
        target = TargetProfile("Generic target", 10, 3)

        result = simulate_saving_throw_uses_to_zero(
            1,
            scenario,
            target,
            rng=SequenceRng([5, 8]),
        )

        self.assertEqual(result.total_applied_damage, 8)
        self.assertEqual(result.total_hp_removed, 3)
        self.assertEqual(result.total_overkill, 5)
        self.assertEqual(result.average_overkill_per_trial, 5.0)

    def test_save_advantage_is_an_explicit_scenario_assumption(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 4)]
        )
        scenario = SavingThrowScenario(
            "Advantaged save", effect, 0, save_advantage=True
        )
        target = TargetProfile("Generic target", 10, 4)

        result = simulate_saving_throw_uses_to_zero(
            1,
            scenario,
            target,
            rng=SequenceRng([5, 15, 5, 5, 4]),
        )

        self.assertEqual(result.total_uses, 2)
        self.assertEqual(result.successful_saves, 1)
        self.assertEqual(result.failed_saves, 1)

    def test_fixed_seed_is_reproducible(self):
        effect = SavingThrowDamageProfile(
            "Generic effect",
            13,
            [DamageDice(2, 6)],
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 2)
        target = TargetProfile("Generic target", 10, 20)

        first = simulate_saving_throw_uses_to_zero(
            100, scenario, target, seed=42
        )
        second = simulate_saving_throw_uses_to_zero(
            100, scenario, target, seed=42
        )

        self.assertEqual(first, second)

    def test_parallel_save_batch_matches_sequential_results(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 13, [DamageDice(2, 6)]
        )
        scenarios = (
            SavingThrowScenario("Normal", effect, 2),
            SavingThrowScenario("Advantage", effect, 2, save_advantage=True),
        )
        target = TargetProfile("Generic target", 10, 20)

        sequential = simulate_saving_throw_scenario_batch(
            scenarios, target, trials=100, seed=42, workers=1
        )
        parallel = simulate_saving_throw_scenario_batch(
            scenarios, target, trials=100, seed=42, workers=2
        )

        self.assertEqual(parallel, sequential)

    def test_use_limit_prevents_an_infinite_simulation(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 4)]
        )
        scenario = SavingThrowScenario("Always succeeds", effect, 100)
        target = TargetProfile("Generic target", 10, 1)

        with self.assertRaises(RuntimeError):
            simulate_saving_throw_uses_to_zero(
                1,
                scenario,
                target,
                max_uses_per_trial=1,
                rng=SequenceRng([1]),
            )

    def test_use_limit_must_be_a_positive_integer(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 4)]
        )
        scenario = SavingThrowScenario("Generic scenario", effect, 0)
        target = TargetProfile("Generic target", 10, 1)

        with self.assertRaises(ValueError):
            simulate_saving_throw_uses_to_zero(
                1, scenario, target, max_uses_per_trial=0
            )


if __name__ == "__main__":
    unittest.main()
