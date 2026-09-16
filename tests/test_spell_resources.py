"""Shared slots and single-action save effects in complete duels."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import save_custom_build, load_custom_build
from dnd5ecombat.combat import resolve_saving_throw_damage
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.models import (
    AttackProfile, DamageDice, DuelCombatant, DuelMatchup, TargetProfile,
    SavingThrowDamageProfile, SaveSuccessDamage, Condition, SavingThrowConditionEffect,
)
from dnd5ecombat.monster_profiles import save_monster_profile, load_monster_profile, monster_to_dict
from dnd5ecombat.profile_schema import validate_profile, ProfileValidationError
from dnd5ecombat.resource_models import normalize_spell_slots, duel_save_actions
from dnd5ecombat.save_action_policy import expected_save_damage, save_flags
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)
    def randint(self, low, high):
        value = next(self.values)
        assert low <= value <= high
        return value


class SpellResourceTests(unittest.TestCase):
    def setUp(self):
        self.weapon = AttackProfile("Sword", 5, (DamageDice(1, 2),))
        self.enemy_weapon = replace(self.weapon, name="Claw")
        self.spell = SavingThrowDamageProfile(
            "Flame", 30, (DamageDice(1, 2),), 10, save_ability="dex",
            damage_type="fire", spell_slot_level=1, range_feet=30,
        )
        self.hero = DuelCombatant("Hero", 10, 100, 100, self.weapon,
            saving_throw_profiles=(self.spell,), spell_slots={"1": 1})
        self.enemy = DuelCombatant("Enemy", 10, 14, -100, self.enemy_weapon)

    def test_distinct_spells_share_pool_and_levels_stay_separate(self):
        second = replace(self.spell, name="Frost")
        high = replace(self.spell, name="Greater flame", spell_slot_level=2)
        state = AttackResources((self.spell, second, high), ((1, 1), (2, 1)))
        state.spend(self.spell)
        self.assertFalse(state.available(second))
        self.assertTrue(state.available(high))
        with self.assertRaises(ValueError):
            state.spend(second)
        self.assertEqual(state.spell_slots, {1: 0, 2: 1})

    def test_no_slots_does_not_imply_unlimited_and_cantrips_cost_nothing(self):
        cantrip = replace(self.spell, spell_slot_level=0)
        state = AttackResources((self.spell, cantrip), ())
        self.assertFalse(state.available(self.spell))
        for _ in range(4):
            state.spend(cantrip)
        self.assertTrue(state.available(cantrip))

    def test_per_action_uses_and_slots_are_both_required(self):
        spell = replace(self.spell, limited_uses=1)
        state = AttackResources((spell,), ((1, 2),))
        state.spend(spell)
        self.assertFalse(state.available(spell))
        self.assertEqual(state.spell_slots[1], 1)

    def test_exhausted_slot_falls_back_to_weapon(self):
        result = simulate_duel(1, DuelMatchup(self.hero, self.enemy),
            rng=Rolls(10, 10, 10, 1, 1, 10, 2, 1, 10, 1))
        self.assertEqual(result.character_wins, 1)
        self.assertEqual(result.total_rounds, 3)

    def test_save_action_replaces_entire_multiattack(self):
        hero = replace(self.hero, attack_sequence=(self.weapon,) * 2)
        calls = []
        def save(effect, bonus, hp, **kwargs):
            calls.append(effect)
            return SimpleNamespace(remaining_hp=0)
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage", side_effect=save), patch(
            "dnd5ecombat.duel_simulation.resolve_attack_sequence"
        ) as attacks:
            simulate_duel(1, DuelMatchup(hero, self.enemy), rng=Rolls(10, 10))
        self.assertEqual(calls, [self.spell])
        attacks.assert_not_called()

    def test_successful_save_still_spends_shared_slot(self):
        calls = []
        def save(effect, bonus, hp, **kwargs):
            calls.append("spell")
            return SimpleNamespace(remaining_hp=hp)
        def attack(profile, ac, hp, **kwargs):
            calls.append(profile.name)
            return SimpleNamespace(remaining_hp=0 if profile == self.weapon else hp,
                                   attack=SimpleNamespace(hit=True))
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage", side_effect=save), patch(
            "dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack
        ):
            simulate_duel(1, DuelMatchup(self.hero, self.enemy), rng=Rolls(10, 10))
        self.assertEqual(calls, ["spell", "Claw", "Sword"])

    def test_immune_target_prefers_weapon_and_save_failure_flags(self):
        target = replace(self.enemy, damage_immunities=("fire",))
        self.assertEqual(expected_save_damage(self.spell, target, ConditionState()), 0)
        state = ConditionState()
        state.apply(SavingThrowConditionEffect(10, "con", Condition.STUNNED), "stun")
        self.assertEqual(save_flags(self.spell, state), (True, False))
        result = resolve_saving_throw_damage(self.spell, 100, 100,
            automatic_failure=True, rng=Rolls(1))
        self.assertFalse(result.saving_throw.success)
        self.assertEqual(result.applied_damage, 11)

    def test_half_damage_rounding_then_resistance_and_restrained_saves(self):
        spell = replace(self.spell, difficulty_class=11,
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE)
        target = replace(self.enemy, damage_resistances=("fire",))
        # d2+10: fail damage 5 or 6; success damage 2 or 3 after resistance.
        state = ConditionState()
        self.assertAlmostEqual(expected_save_damage(spell, target, state), 4)
        state.apply(SavingThrowConditionEffect(10, "con", Condition.RESTRAINED), "net")
        self.assertAlmostEqual(expected_save_damage(spell, target, state), 4.75)

    def test_range_is_required_and_dashing_does_not_cast(self):
        hero = replace(self.hero, saving_throw_profiles=(replace(self.spell, range_feet=None),))
        with self.assertRaisesRegex(ValueError, "range_feet"):
            simulate_duel(1, DuelMatchup(hero, self.enemy, starting_distance_feet=70))
        matchup = DuelMatchup(self.hero, self.enemy, 100, 30, 0)
        casts = []
        def save(effect, bonus, hp, **kwargs):
            casts.append(effect)
            return SimpleNamespace(remaining_hp=0)
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage", side_effect=save):
            result = simulate_duel(1, matchup, rng=Rolls(10, 10))
        self.assertEqual(result.total_rounds, 2)
        self.assertEqual(casts, [self.spell])

    def test_save_only_monster_factory_and_seeded_workers(self):
        monster = TargetProfile("Caster", 10, 14, saving_throw_profiles=(self.spell,),
                                spell_slots={"1": 1})
        build = CharacterBuild("Hero", self.weapon)
        matchups = build_duel_policy_matchups(build, monster)
        self.assertIsNone(matchups[0].monster.attack_profile)
        self.assertEqual(matchups[0].monster.saving_throw_profiles, (self.spell,))
        self.assertEqual(simulate_duel_batch(matchups * 2, 10, seed=89, workers=1),
                         simulate_duel_batch(matchups * 2, 10, seed=89, workers=2))

    def test_legacy_unmapped_spells_excluded_and_bonus_actions_enabled(self):
        legacy = replace(self.spell, spell_slot_level=None)
        bonus = replace(self.spell, action_type="bonus_action")
        self.assertEqual(duel_save_actions((legacy, bonus, self.spell)), (bonus, self.spell))

    def test_profile_round_trips_and_schema_validation(self):
        monster = TargetProfile("Caster", 10, 14, saving_throw_profiles=(self.spell,), spell_slots={1: 2})
        hero = CharacterBuild("Hero", self.weapon, saving_throw_profiles=(self.spell,), spell_slots={1: 2})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "monster.json"
            save_monster_profile(monster, path)
            self.assertEqual(load_monster_profile(path), monster)
            path = Path(directory) / "hero.json"
            save_custom_build(hero, path)
            loaded = load_custom_build(path)
            self.assertEqual(loaded.saving_throw_profiles, hero.saving_throw_profiles)
            self.assertEqual(loaded.spell_slots, hero.spell_slots)
        data = monster_to_dict(monster)
        data["spell_slots"] = {"0": 1}
        with self.assertRaises(ProfileValidationError):
            validate_profile(data, "monster")

    def test_slots_reset_each_trial_and_cantrip_remains_available(self):
        calls = []
        def save(effect, bonus, hp, **kwargs):
            calls.append(effect)
            return SimpleNamespace(remaining_hp=0)
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage", side_effect=save):
            simulate_duel(3, DuelMatchup(self.hero, self.enemy), rng=Rolls(10, 10, 10, 10, 10, 10))
        self.assertEqual(calls, [self.spell] * 3)

    def test_recharge_save_action_returns_after_failed_recharge(self):
        spell = replace(self.spell, spell_slot_level=None, recharge_min_roll=5)
        hero = replace(self.hero, saving_throw_profiles=(spell,))
        calls = []
        def save(effect, bonus, hp, **kwargs):
            calls.append("spell")
            return SimpleNamespace(remaining_hp=0 if calls.count("spell") == 2 else hp)
        def attack(profile, ac, hp, **kwargs):
            calls.append(profile.name)
            return SimpleNamespace(remaining_hp=hp, attack=SimpleNamespace(hit=False))
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage", side_effect=save), patch(
            "dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack
        ):
            simulate_duel(1, DuelMatchup(hero, self.enemy), rng=Rolls(10, 10, 4, 5))
        self.assertEqual(calls, ["spell", "Claw", "Sword", "Claw", "spell"])

    def test_invalid_slots_and_save_resources_are_rejected(self):
        for values in ({0: 1}, {10: 1}, {1: -1}, {True: 1}, {1: True}, ((1, 1), ("1", 2))):
            with self.assertRaises(ValueError):
                normalize_spell_slots(values)
        for field, values in (("spell_slot_level", (-1, 10, True)),
                              ("limited_uses", (0, True)), ("recharge_min_roll", (1, 7)),
                              ("range_feet", (0, False))):
            for value in values:
                with self.assertRaises((ValueError, TypeError)):
                    replace(self.spell, **{field: value})


if __name__ == "__main__":
    unittest.main()
