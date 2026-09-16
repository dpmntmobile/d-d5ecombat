"""Condition lifetimes, rule combinations, and persistence regressions."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.models import (
    AttackProfile,
    Condition,
    DamageDice,
    DuelCombatant,
    DuelMatchup,
    SavingThrowConditionEffect,
    TargetProfile,
)
from dnd5ecombat.monster_profiles import monster_from_dict, monster_to_dict
from dnd5ecombat.profile_schema import ProfileValidationError, validate_profile
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch


class ConditionTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile(
            "Sword", 5, (DamageDice(1, 6),), attack_mode="melee"
        )
        self.hero = DuelCombatant("Hero", 12, 20, 100, self.attack)
        self.enemy = replace(self.hero, name="Enemy", initiative_bonus=-100)
        self.effect = SavingThrowConditionEffect(12, "con", Condition.POISONED)
        self.state = ConditionState()
        self.save = Mock(return_value=SimpleNamespace(success=False))

    def test_duration_validation(self):
        for value, error in (
            (True, TypeError),
            (1.5, TypeError),
            ("1", TypeError),
            (0, ValueError),
            (-1, ValueError),
        ):
            with self.subTest(value=value), self.assertRaises(error):
                replace(self.effect, duration_turns=value)

    def test_duration_counts_affected_turn_ends(self):
        self.state.apply(replace(self.effect, duration_turns=2), "venom")
        self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.POISONED, self.state)
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.POISONED, self.state)
        self.save.assert_not_called()

    def test_legacy_effect_has_no_implicit_timeout(self):
        self.state.apply(self.effect, "venom")
        for _ in range(12):
            self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.POISONED, self.state)

    def test_repeat_save_can_end_effect_early(self):
        self.state.apply(
            replace(self.effect, duration_turns=10, repeat_save_at_end_of_turn=True),
            "venom",
        )
        self.save.return_value.success = True
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.POISONED, self.state)
        self.assertEqual(self.save.call_count, 1)

    def test_expiration_ends_effect_without_unnecessary_save(self):
        self.state.apply(
            replace(self.effect, duration_turns=1, repeat_save_at_end_of_turn=True),
            "venom",
        )
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.POISONED, self.state)
        self.save.assert_not_called()

    def test_different_sources_keep_independent_durations(self):
        self.state.apply(replace(self.effect, duration_turns=1), "bite")
        self.state.apply(replace(self.effect, duration_turns=2), "sting")
        self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.POISONED, self.state)
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.POISONED, self.state)

    def test_successful_save_removes_only_its_source(self):
        self.state.apply(replace(self.effect, repeat_save_at_end_of_turn=True), "bite")
        self.state.apply(self.effect, "sting")
        self.save.return_value.success = True
        self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.POISONED, self.state)

    def test_reapplication_refreshes_same_source(self):
        effect = replace(self.effect, duration_turns=2)
        self.state.apply(effect, "bite")
        self.state.end_turn(self.hero, self.save, None)
        self.state.apply(effect, "bite")
        self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.POISONED, self.state)
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.POISONED, self.state)

    def test_standing_removes_all_prone_sources_only(self):
        for source in ("bite", "trip"):
            self.state.apply(replace(self.effect, condition=Condition.PRONE), source)
        self.state.apply(self.effect, "venom")
        self.assertTrue(self.state.remove(Condition.PRONE))
        self.assertNotIn(Condition.PRONE, self.state)
        self.assertIn(Condition.POISONED, self.state)

    def test_paralysis_and_stun_automatically_fail_strength_dexterity_saves(self):
        for condition in (Condition.PARALYZED, Condition.STUNNED):
            self.state.apply(replace(self.effect, condition=condition), "rider")
            for ability in ("str", "dex"):
                self.assertFalse(
                    self.state.save_succeeds(
                        replace(self.effect, save_ability=ability),
                        self.hero,
                        self.save,
                        None,
                    )
                )
        self.save.assert_not_called()

    def test_restrained_dex_saves_have_disadvantage_but_con_saves_do_not(self):
        self.state.apply(replace(self.effect, condition=Condition.RESTRAINED), "net")
        for ability in ("dex", "con"):
            self.state.save_succeeds(
                replace(self.effect, save_ability=ability), self.hero, self.save, None
            )
            self.assertEqual(
                self.save.call_args.kwargs["disadvantage"], ability == "dex"
            )

    def test_stunned_physical_repeat_save_fails_until_duration_expires(self):
        effect = replace(
            self.effect,
            condition=Condition.STUNNED,
            save_ability="str",
            duration_turns=2,
            repeat_save_at_end_of_turn=True,
        )
        self.state.apply(effect, "stun")
        self.state.end_turn(self.hero, self.save, None)
        self.assertIn(Condition.STUNNED, self.state)
        self.state.end_turn(self.hero, self.save, None)
        self.assertNotIn(Condition.STUNNED, self.state)
        self.save.assert_not_called()

    def _run_rider_duel(self, condition, immune=False, success=False, duration=1):
        rider = replace(
            self.attack,
            name="Rider",
            condition_effect=replace(
                self.effect,
                condition=condition,
                duration_turns=duration,
            ),
        )
        hero = replace(self.hero, attack_sequence=(rider,))
        enemy = replace(
            self.enemy, condition_immunities=(condition.value,) if immune else ()
        )
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append((profile.name, kwargs))
            return SimpleNamespace(
                remaining_hp=0 if len(calls) == 3 else hp,
                attack=SimpleNamespace(hit=True),
            )

        with (
            patch(
                "dnd5ecombat.duel_simulation.resolve_attack_sequence",
                side_effect=attack,
            ),
            patch(
                "dnd5ecombat.duel_simulation.resolve_saving_throw",
                return_value=SimpleNamespace(success=success),
            ) as save,
        ):
            result = simulate_duel(1, DuelMatchup(hero, enemy, 5), seed=1)
        return calls, result, save

    def test_poisoned_and_restrained_attacks_have_disadvantage(self):
        for condition in (Condition.POISONED, Condition.RESTRAINED):
            calls, _, _ = self._run_rider_duel(condition)
            self.assertEqual(calls[1][0], "Sword")
            self.assertTrue(calls[1][1]["disadvantage"])

    def test_stun_and_incapacitation_skip_actions_and_expire(self):
        for condition in (Condition.STUNNED, Condition.INCAPACITATED):
            calls, _, _ = self._run_rider_duel(condition)
            self.assertEqual([name for name, _ in calls], ["Rider"] * 3)
            # Duration 1 expires on the skipped turn before the next attack.
            self.assertFalse(calls[1][1]["advantage"])

    def test_condition_immunity_prevents_effect_and_save(self):
        for condition in Condition:
            calls, _, save = self._run_rider_duel(condition, immune=True)
            self.assertEqual(calls[1][0], "Sword")
            self.assertFalse(calls[1][1]["disadvantage"])
            save.assert_not_called()

    def test_successful_initial_save_prevents_condition(self):
        calls, _, save = self._run_rider_duel(Condition.STUNNED, success=True)
        self.assertEqual(calls[1][0], "Sword")
        self.assertEqual(save.call_count, 1)

    def test_stun_grants_advantage_without_paralysis_criticals(self):
        calls, _, _ = self._run_rider_duel(Condition.STUNNED, duration=2)
        self.assertTrue(calls[1][1]["advantage"])
        self.assertFalse(calls[1][1]["critical_on_hit"])

    def test_incapacitated_moves_without_dashing_and_restrained_stunned_cannot_move(
        self,
    ):
        for condition, expected_distance in (
            (Condition.INCAPACITATED, 70),
            (Condition.RESTRAINED, 100),
            (Condition.STUNNED, 100),
        ):
            with self.subTest(condition=condition):
                rider = replace(
                    self.attack,
                    attack_mode="ranged",
                    normal_range_feet=120,
                    condition_effect=replace(self.effect, condition=condition),
                )
                hero = replace(self.hero, attack_sequence=(rider,))
                distances = []
                from dnd5ecombat.duel_positioning import attack_position

                def position(attack, distance):
                    distances.append(distance)
                    return attack_position(attack, distance)

                with (
                    patch(
                        "dnd5ecombat.duel_simulation.resolve_attack_sequence",
                        side_effect=[
                            SimpleNamespace(
                                remaining_hp=20, attack=SimpleNamespace(hit=True)
                            ),
                            SimpleNamespace(remaining_hp=0),
                        ],
                    ),
                    patch(
                        "dnd5ecombat.duel_simulation.resolve_saving_throw",
                        return_value=SimpleNamespace(success=False),
                    ),
                    patch(
                        "dnd5ecombat.duel_turn_policy.attack_position",
                        side_effect=position,
                    ),
                ):
                    simulate_duel(1, DuelMatchup(hero, self.enemy, 100, 0, 30), seed=1)
                self.assertEqual(distances, [100, expected_distance])

    def test_incapacitated_target_does_not_impose_close_ranged_disadvantage(self):
        rider = replace(
            self.attack,
            attack_mode="ranged",
            normal_range_feet=30,
            condition_effect=replace(self.effect, condition=Condition.INCAPACITATED),
        )
        hero = replace(self.hero, attack_sequence=(rider, rider))
        with (
            patch(
                "dnd5ecombat.duel_simulation.resolve_attack_sequence",
                side_effect=[
                    SimpleNamespace(remaining_hp=20, attack=SimpleNamespace(hit=True)),
                    SimpleNamespace(remaining_hp=0),
                ],
            ) as attack,
            patch(
                "dnd5ecombat.duel_simulation.resolve_saving_throw",
                return_value=SimpleNamespace(success=False),
            ),
        ):
            simulate_duel(1, DuelMatchup(hero, self.enemy, 5), seed=1)
        self.assertTrue(attack.call_args_list[0].kwargs["disadvantage"])
        self.assertFalse(attack.call_args_list[1].kwargs["disadvantage"])
        self.assertFalse(attack.call_args_list[1].kwargs["advantage"])

    def test_restrained_target_advantage_and_poisoned_attacker_disadvantage_combine(
        self,
    ):
        poison = replace(self.attack, name="Poison", condition_effect=self.effect)
        restrain = replace(
            self.attack,
            name="Restrain",
            condition_effect=replace(
                self.effect,
                condition=Condition.RESTRAINED,
            ),
        )
        hero = replace(self.hero, attack_sequence=(poison,))
        enemy = replace(self.enemy, attack_sequence=(restrain, restrain))
        with (
            patch(
                "dnd5ecombat.duel_simulation.resolve_attack_sequence",
                side_effect=[
                    SimpleNamespace(remaining_hp=20, attack=SimpleNamespace(hit=True)),
                    SimpleNamespace(remaining_hp=20, attack=SimpleNamespace(hit=True)),
                    SimpleNamespace(remaining_hp=0),
                ],
            ) as attack,
            patch(
                "dnd5ecombat.duel_simulation.resolve_saving_throw",
                return_value=SimpleNamespace(success=False),
            ),
        ):
            simulate_duel(1, DuelMatchup(hero, enemy, 5), seed=1)
        self.assertTrue(attack.call_args.kwargs["advantage"])
        self.assertTrue(attack.call_args.kwargs["disadvantage"])

    def test_all_conditions_round_trip_through_monster_and_character_profiles(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "character.json"
            for condition in Condition:
                effect = replace(
                    self.effect,
                    condition=condition,
                    duration_turns=3,
                    repeat_save_at_end_of_turn=True,
                )
                attack = replace(self.attack, condition_effect=effect)
                monster = TargetProfile("Monster", 12, 20, attack_profiles=(attack,))
                self.assertEqual(monster_from_dict(monster_to_dict(monster)), monster)
                build = CharacterBuild("Hero", attack)
                save_custom_build(build, path)
                self.assertEqual(
                    load_custom_build(path).attack_profile.condition_effect, effect
                )
                # Legacy native files can store only the primary attack at top level.
                data = json.loads(path.read_text(encoding="utf-8"))
                del data["attack_profiles"]
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertEqual(
                    load_custom_build(path).attack_profile.condition_effect, effect
                )

    def test_schema_rejects_invalid_duration_at_field_path(self):
        monster = TargetProfile(
            "Monster",
            12,
            20,
            attack_profiles=(replace(self.attack, condition_effect=self.effect),),
        )
        for value in (0, -1, True, "2"):
            data = monster_to_dict(monster)
            data["attacks"][0]["condition_effect"]["duration_turns"] = value
            with self.assertRaisesRegex(ProfileValidationError, "duration_turns"):
                validate_profile(data, "monster")

    def test_timed_conditions_reproduce_across_workers(self):
        attack = replace(
            self.attack,
            condition_effect=replace(
                self.effect,
                condition=Condition.STUNNED,
                duration_turns=2,
                repeat_save_at_end_of_turn=True,
            ),
        )
        matchup = DuelMatchup(replace(self.hero, attack_sequence=(attack,)), self.enemy)
        self.assertEqual(
            simulate_duel_batch((matchup,), 20, seed=5),
            simulate_duel_batch((matchup,), 20, seed=5, workers=2),
        )
