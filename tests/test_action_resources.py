"""Availability, fallback policies, and persistence for limited attacks."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import save_custom_build, load_custom_build
from dnd5ecombat.models import (
    AttackProfile, Condition, DamageDice, DuelCombatant, DuelMatchup,
    SavingThrowConditionEffect, TargetProfile,
)
from dnd5ecombat.monster_profiles import monster_to_dict, monster_from_dict, save_monster_profile, load_monster_profile
from dnd5ecombat.profile_schema import validate_profile, ProfileValidationError
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, low, high):
        value = next(self.values)
        assert low <= value <= high
        return value


class ActionResourceTests(unittest.TestCase):
    def setUp(self):
        self.sword = AttackProfile("Sword", 5, (DamageDice(1, 6),), attack_mode="melee")
        self.burst = replace(self.sword, name="Burst", limited_uses=1)
        self.recharge = replace(self.sword, name="Recharge", recharge_min_roll=5)

    def test_initial_availability_and_repeated_references_share_uses(self):
        state = AttackResources((self.burst, self.burst))
        plan = state.plan((self.burst,) * 3, (self.sword,), lambda attacks: attacks[0])
        self.assertEqual(plan, (self.burst, self.sword, self.sword))
        self.assertEqual(state.remaining[self.burst], 1)
        state.spend(self.burst)
        with self.assertRaisesRegex(ValueError, "no uses"):
            state.spend(self.burst)

    def test_recharge_rolls_only_while_expended_and_at_threshold(self):
        state = AttackResources((self.recharge, self.burst))
        state.start_turn(Rolls())
        state.spend(self.recharge)
        state.spend(self.burst)
        state.start_turn(Rolls(4))
        self.assertEqual(state.remaining[self.recharge], 0)
        state.start_turn(Rolls(5))
        self.assertEqual(state.remaining[self.recharge], 1)
        self.assertEqual(state.remaining[self.burst], 0)
        state.start_turn(Rolls())

    def test_multiple_uses_and_no_fallback(self):
        attack = replace(self.burst, limited_uses=2)
        state = AttackResources((attack,))
        state.spend(attack)
        self.assertEqual(state.plan((attack, attack), (), None), (attack,))
        state.spend(attack)
        self.assertEqual(state.plan((attack,), (), None), ())

    def matchup(self, attack, fallbacks=()):
        return DuelMatchup(
            DuelCombatant("Hero", 10, 100, 100, attack, fallback_attacks=fallbacks),
            DuelCombatant("Monster", 10, 100, -100, self.sword),
        )

    def scripted_duel(self, matchup, rng, turns=3, trials=1):
        calls = []
        hero_turns = 0

        def resolve(attack, ac, hp, **kwargs):
            nonlocal hero_turns
            calls.append(attack)
            # Tests use unique hero profiles and a sword-wielding opponent.
            if attack is not self.sword:
                hero_turns += 1
            return SimpleNamespace(
                remaining_hp=0 if hero_turns == turns else hp,
                attack=SimpleNamespace(hit=False),
            )

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve):
            simulate_duel(trials, matchup, rng=rng, max_rounds_per_trial=10)
        return calls

    def test_missed_attack_spends_use_and_fallback_is_used_next_turn(self):
        fallback = replace(self.sword, name="Fallback")
        calls = self.scripted_duel(self.matchup(self.burst, (fallback,)), Rolls(10, 10))
        self.assertEqual(calls, [self.burst, self.sword, fallback, self.sword, fallback])

    def test_recharge_failure_uses_fallback_and_success_restores_preference(self):
        fallback = replace(self.sword, name="Fallback")
        calls = self.scripted_duel(
            self.matchup(self.recharge, (fallback,)), Rolls(10, 10, 4, 5)
        )
        self.assertEqual(calls, [self.recharge, self.sword, fallback, self.sword, self.recharge])

    def test_resource_is_reset_for_every_trial(self):
        calls = []

        def resolve(attack, ac, hp, **kwargs):
            calls.append(attack)
            return SimpleNamespace(remaining_hp=0, attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve):
            simulate_duel(3, self.matchup(self.burst), rng=Rolls(10, 10, 10, 10, 10, 10))
        self.assertEqual(calls, [self.burst] * 3)

    def test_out_of_range_does_not_spend_or_roll_recharge(self):
        matchup = replace(
            self.matchup(self.recharge), starting_distance_feet=70,
            character_speed_feet=0, monster_speed_feet=0,
        )
        with self.assertRaisesRegex(RuntimeError, "max_rounds"):
            simulate_duel(1, matchup, rng=Rolls(10, 10), max_rounds_per_trial=3)

    def test_exhaustion_without_fallback_can_wait_for_recharge(self):
        # Hero fires in turns 1 and 3; opponent attacks during the empty turn 2.
        calls = self.scripted_duel(
            self.matchup(self.recharge), Rolls(10, 10, 4, 5), turns=2
        )
        self.assertEqual(calls, [self.recharge, self.sword, self.sword, self.recharge])

    def test_recharge_during_incapacitation_does_not_spend_restored_use(self):
        effect = SavingThrowConditionEffect(
            15, "con", Condition.INCAPACITATED, duration_turns=1
        )
        enemy_attack = replace(self.sword, condition_effect=effect)
        matchup = self.matchup(self.recharge)
        matchup = replace(matchup, monster=replace(
            matchup.monster, attack_profile=enemy_attack, attack_sequence=(enemy_attack,)
        ))
        calls = []

        def resolve(attack, ac, hp, **kwargs):
            calls.append(attack)
            return SimpleNamespace(
                remaining_hp=0 if calls.count(self.recharge) == 2 else hp,
                attack=SimpleNamespace(hit=len(calls) == 2),
            )

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve), patch(
            "dnd5ecombat.duel_simulation.resolve_saving_throw",
            return_value=SimpleNamespace(success=False),
        ):
            result = simulate_duel(1, matchup, rng=Rolls(10, 10, 5), max_rounds_per_trial=3)
        self.assertEqual(calls, [self.recharge, enemy_attack, enemy_attack, self.recharge])
        self.assertEqual(result.total_rounds, 3)

    def test_factory_supplies_legal_fallbacks_and_batch_is_deterministic(self):
        monster = TargetProfile("Monster", 10, 10, attack_profiles=(self.recharge, self.sword))
        bonus = replace(self.sword, name="Bonus", action_type="bonus_action")
        build = CharacterBuild("Hero", self.burst, attack_profiles=(self.burst, self.sword, bonus))
        matchups = build_duel_policy_matchups(build, monster)
        self.assertEqual(matchups[0].character.fallback_attacks, (self.burst, self.sword))
        self.assertEqual(matchups[0].monster.fallback_attacks, monster.attack_profiles)
        self.assertEqual(
            simulate_duel_batch(matchups, 20, seed=92, workers=1),
            simulate_duel_batch(matchups, 20, seed=92, workers=2),
        )

    def test_monster_and_native_character_round_trips(self):
        monster = TargetProfile("Monster", 10, 10, attack_profiles=(self.burst, self.recharge))
        build = CharacterBuild("Hero", self.burst, attack_profiles=(self.burst, self.recharge))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "monster.json"
            save_monster_profile(monster, path)
            self.assertEqual(load_monster_profile(path), monster)
            path = Path(directory) / "hero.json"
            save_custom_build(build, path)
            loaded = load_custom_build(path)
            self.assertEqual(loaded.attack_profiles, build.attack_profiles)
            self.assertEqual(loaded.attack_profile, build.attack_profile)

    def test_validation_and_legacy_defaults(self):
        self.assertIsNone(self.sword.limited_uses)
        self.assertIsNone(self.sword.recharge_min_roll)
        for field, values in (("limited_uses", (0, -1, True, "1")),
                              ("recharge_min_roll", (1, 7, True, "5"))):
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        replace(self.sword, **{field: value})
                    data = monster_to_dict(TargetProfile("M", 10, 1, attack_profiles=(self.sword,)))
                    data["attacks"][0][field] = value
                    with self.assertRaises(ProfileValidationError):
                        validate_profile(data, "monster")
        with self.assertRaisesRegex(ValueError, "combine"):
            replace(self.burst, recharge_min_roll=5)
        invalid = monster_to_dict(TargetProfile("M", 10, 1, attack_profiles=(self.burst,)))
        invalid["attacks"][0]["recharge_min_roll"] = 5
        with self.assertRaises(ProfileValidationError):
            validate_profile(invalid, "monster")
        data = monster_to_dict(TargetProfile("M", 10, 1, attack_profiles=(self.sword,)))
        data["attacks"][0].pop("limited_uses")
        data["attacks"][0].pop("recharge_min_roll")
        self.assertEqual(monster_from_dict(data).attack_profiles, (self.sword,))


if __name__ == "__main__":
    unittest.main()
