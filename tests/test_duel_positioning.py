"""Range boundaries, movement decisions, and positioned duel integration."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.application_service import SimulationSettings, evaluate_duel_policies
from dnd5ecombat.cli_arguments import parse_args
from dnd5ecombat.cli_workflows import _simulation_settings
from dnd5ecombat.duel_positioning import approach, attack_position
from dnd5ecombat.models import (
    AttackProfile, Condition, DamageDice, DuelCombatant, DuelMatchup,
    SavingThrowConditionEffect,
)
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch
from dnd5ecombat.profile_catalog import discover_characters, discover_monsters


class DuelPositioningTests(unittest.TestCase):
    def setUp(self):
        self.sword = AttackProfile("Sword", 5, (DamageDice(1, 6),), attack_mode="melee")
        self.bow = replace(self.sword, name="Bow", attack_mode="ranged",
                           normal_range_feet=30, long_range_feet=120)
        self.hero = DuelCombatant("Hero", 12, 10, 100, self.sword)
        self.enemy = DuelCombatant("Enemy", 12, 10, -100, self.sword)

    def test_range_boundaries(self):
        for distance, expected in ((5, (True, False, False)),
                                   (6, (False, False, False))):
            self.assertEqual(attack_position(self.sword, distance), expected)
        for distance, expected in ((30, (True, True, False)),
                                   (31, (True, True, True)),
                                   (120, (True, True, True)),
                                   (121, (False, True, True))):
            self.assertEqual(attack_position(self.bow, distance), expected)
        single_range = replace(self.bow, long_range_feet=None)
        self.assertFalse(attack_position(single_range, 31)[0])

    def test_thrown_weapon_switches_mode_at_reach(self):
        thrown = replace(self.bow, attack_mode="melee_or_ranged", reach_feet=10)
        self.assertEqual(attack_position(thrown, 10), (True, False, False))
        self.assertEqual(attack_position(thrown, 11), (True, True, False))

    def test_missing_ranged_metadata_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Bow.*normal_range_feet"):
            simulate_duel(1, DuelMatchup(
                replace(self.hero, attack_sequence=(replace(self.bow, normal_range_feet=None),)),
                self.enemy, 30,
            ))

    def test_movement_and_dash_decisions(self):
        self.assertEqual(approach((self.sword,), 35, 30, 30), (5, True))
        self.assertEqual(approach((self.sword,), 65, 30, 30), (5, False))
        self.assertEqual(approach((self.bow,), 100, 30, 30), (70, True))
        self.assertEqual(approach((self.bow,), 200, 30, 30), (140, False))
        self.assertEqual(approach((self.bow,), 5, 30, 30), (5, True))
        self.assertEqual(approach((self.sword,), 50, 0, 0), (50, False))

    def test_validation(self):
        for field in ("starting_distance_feet", "character_speed_feet", "monster_speed_feet"):
            for value, error in ((-1, ValueError), (True, TypeError), (2.5, TypeError)):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(error):
                        SimulationSettings(**{field: value})
                    with self.assertRaises(error):
                        DuelMatchup(self.hero, self.enemy, **{field: value})

    def _attack_flags(self, attack, distance, effect=None):
        hero = replace(self.hero, attack_sequence=(attack,))
        enemy_attack = replace(self.sword, condition_effect=effect)
        enemy = replace(self.enemy, initiative_bonus=200,
                        attack_sequence=(enemy_attack,))
        calls = []

        def resolve(profile, ac, hp, **kwargs):
            calls.append((profile, kwargs))
            # Enemy applies a rider, then hero ends the duel.
            return SimpleNamespace(remaining_hp=hp if profile is enemy_attack else 0,
                                   attack=SimpleNamespace(hit=True))

        with patch('dnd5ecombat.duel_simulation.resolve_attack_sequence', side_effect=resolve), \
             patch('dnd5ecombat.duel_simulation.resolve_saving_throw',
                   return_value=SimpleNamespace(success=False)):
            simulate_duel(1, DuelMatchup(hero, enemy, distance, 0, 0), seed=1)
        return calls[-1][1]

    def test_long_range_and_close_ranged_disadvantage(self):
        self.assertTrue(self._attack_flags(self.bow, 31)['disadvantage'])
        self.assertFalse(self._attack_flags(self.bow, 30)['disadvantage'])
        self.assertTrue(self._attack_flags(self.bow, 5)['disadvantage'])

    def test_prone_attacker_with_zero_speed_cannot_stand(self):
        effect = SavingThrowConditionEffect(20, "str", Condition.PRONE)
        self.assertTrue(self._attack_flags(self.sword, 5, effect)['disadvantage'])

    def test_dash_consumes_attack_action(self):
        matchup = DuelMatchup(self.hero, self.enemy, 65, 30, 0)
        with patch('dnd5ecombat.duel_simulation.resolve_attack_sequence',
                   return_value=SimpleNamespace(remaining_hp=0)) as attack:
            result = simulate_duel(1, matchup, seed=1)
        # Hero Dashes; stationary enemy can then attack at the new distance.
        self.assertEqual(result.monster_wins, 1)
        self.assertIs(attack.call_args.args[0], self.enemy.attack_profile)

    def test_condition_benefits_use_distance_instead_of_weapon_mode(self):
        for condition in (Condition.PRONE, Condition.PARALYZED):
            for distance in (5, 10):
                with self.subTest(condition=condition, distance=distance):
                    rider = replace(self.bow, condition_effect=SavingThrowConditionEffect(
                        20, "str", condition,
                    ))
                    hero = replace(self.hero, attack_sequence=(rider, self.bow))
                    with patch('dnd5ecombat.duel_simulation.resolve_attack_sequence',
                               side_effect=[
                                   SimpleNamespace(remaining_hp=10, attack=SimpleNamespace(hit=True)),
                                   SimpleNamespace(remaining_hp=0),
                               ]) as attack, patch(
                                   'dnd5ecombat.duel_simulation.resolve_saving_throw',
                                   return_value=SimpleNamespace(success=False)):
                        simulate_duel(1, DuelMatchup(hero, self.enemy, distance, 0, 0), seed=1)
                    flags = attack.call_args.kwargs
                    self.assertEqual(flags['critical_on_hit'],
                                     condition == Condition.PARALYZED and distance == 5)
                    self.assertEqual(flags['advantage'],
                                     condition == Condition.PARALYZED or distance == 5)
                    self.assertEqual(flags['disadvantage'], condition == Condition.PRONE)

    def test_standing_uses_half_movement_before_approaching(self):
        rider = replace(self.bow, condition_effect=SavingThrowConditionEffect(
            20, "str", Condition.PRONE,
        ))
        enemy = replace(self.enemy, initiative_bonus=200, attack_sequence=(rider,))
        calls = []

        def resolve(profile, ac, hp, **kwargs):
            calls.append(profile)
            return SimpleNamespace(remaining_hp=0 if len(calls) == 2 else hp,
                                   attack=SimpleNamespace(hit=True))

        with patch('dnd5ecombat.duel_simulation.resolve_attack_sequence', side_effect=resolve), \
             patch('dnd5ecombat.duel_simulation.resolve_saving_throw',
                   return_value=SimpleNamespace(success=False)):
            result = simulate_duel(1, DuelMatchup(self.hero, enemy, 30, 30, 0), seed=1)
        # At 30 ft, standing leaves 15 ft: hero must Dash and loses its action.
        self.assertEqual(calls, [rider, rider])
        self.assertEqual(result.total_rounds, 2)

    def test_unreachable_attacks_are_skipped_in_multiattack(self):
        hero = replace(self.hero, attack_sequence=(self.sword, self.bow))
        with patch('dnd5ecombat.duel_simulation.resolve_attack_sequence',
                   return_value=SimpleNamespace(remaining_hp=0)) as attack:
            simulate_duel(1, DuelMatchup(hero, self.enemy, 30, 0, 0), seed=1)
        self.assertEqual(attack.call_count, 1)
        self.assertIs(attack.call_args.args[0], self.bow)

    def test_round_limit_handles_immobile_out_of_range_duel(self):
        with self.assertRaisesRegex(RuntimeError, "max_rounds_per_trial=2"):
            simulate_duel(1, DuelMatchup(self.hero, self.enemy, 100, 0, 0),
                          max_rounds_per_trial=2, seed=1)

    def test_positioned_parallel_results_are_reproducible(self):
        matchups = (DuelMatchup(self.hero, self.enemy, 100),)
        self.assertEqual(simulate_duel_batch(matchups, 20, seed=7),
                         simulate_duel_batch(matchups, 20, seed=7, workers=2))

    def test_cli_settings_reach_policy_matchups(self):
        settings = _simulation_settings(parse_args([
            '--starting-distance-feet', '90', '--character-speed-feet', '25',
            '--monster-speed-feet', '20', '--trials', '2',
        ]))
        build = discover_characters()[0].value
        monster = discover_monsters()[0].value
        evaluation = evaluate_duel_policies(build, monster, settings)
        for matchup in evaluation.matchups:
            self.assertEqual(matchup.starting_distance_feet, 90)
            self.assertEqual(matchup.character_speed_feet, 25)
            self.assertEqual(matchup.monster_speed_feet, 20)
        self.assertIn('90 ft', settings.duel_positioning_note)


if __name__ == '__main__':
    unittest.main()
