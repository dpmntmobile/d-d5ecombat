"""Regressions for the remaining Felicity and Tobias duel spell effects."""

import random
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.combat import resolve_saving_throw_damage
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.duel_simulation import simulate_duel
from dnd5ecombat.duel_spells import DuelSpellState
from dnd5ecombat.duel_turn_policy import attack_flags, copy_resources
from dnd5ecombat.models import (
    AttackProfile, AttackScenario, Condition, DamageDice, DuelCombatant,
    DuelMatchup, SavingThrowConditionEffect, SavingThrowDamageProfile,
    SaveSuccessDamage,
)
from dnd5ecombat.support_spells import SupportSpell


class SpellCompletionTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Sword", 5, (DamageDice(1, 6),),
                                    attack_mode="melee", reach_feet=5)
        self.bless = SupportSpell("Bless", "bless", free_casts=1)
        self.teleport = SupportSpell("Misty Step", "misty_step", spell_slot_level=2,
                                     action_type="bonus_action", free_casts=1)
        self.sliver = SavingThrowDamageProfile(
            "Mind Sliver", 100, (DamageDice(1, 6),), save_ability="int",
            spell_slot_level=0, range_feet=60, next_save_penalty=True)
        self.whispers = replace(self.sliver, name="Dissonant Whispers",
                                next_save_penalty=False, flee_on_failed_save=True,
                                damage_on_success=SaveSuccessDamage.HALF_DAMAGE)
        self.hero = DuelCombatant("Hero", 15, 100, 100, self.attack,
                                   support_spells=(self.bless, self.teleport),
                                   spell_slots=((1, 1), (2, 1)))
        self.enemy = DuelCombatant("Enemy", 15, 100, -100, self.attack)

    def state(self):
        actors = {"hero": self.hero, "enemy": self.enemy}
        return DuelSpellState(
            actors, {k: a.max_hp for k, a in actors.items()},
            {k: ConditionState() for k in actors},
            {k: AttackResources(a.support_spells + a.attack_sequence,
                                a.spell_slots) for k, a in actors.items()},
            dict.fromkeys(actors, False), random.Random(7))

    def test_free_cast_precedes_slots_without_upcast_and_recovers_on_long_rest(self):
        resource = AttackResources((self.bless,), ((2, 1),))
        clone = copy_resources(resource)
        self.assertEqual(resource.prepare(self.bless).spell_slot_level, 1)
        self.assertEqual(resource.free_casts[self.bless], 1)
        clone.spend(self.bless)
        self.assertEqual(resource.free_casts[self.bless], 1)
        resource.spend(self.bless)
        self.assertEqual(resource.spell_slots[2], 1)
        self.assertEqual(resource.prepare(self.bless).spell_slot_level, 2)
        resource.spend(self.bless)
        self.assertFalse(resource.available(self.bless))
        resource.rest("short")
        self.assertFalse(resource.available(self.bless))
        resource.rest("long")
        self.assertEqual(resource.free_casts[self.bless], 1)

    def test_bless_and_sliver_modify_one_save_and_sliver_is_consumed(self):
        condition = ConditionState()
        condition.blessed = condition.next_save_penalty = True
        rng = Mock()
        rng.randint.side_effect = [4, 2, 10, 3, 10]
        first = condition.resolve_save(1, 13, rng=rng)
        self.assertEqual(first.total, 13)
        self.assertTrue(first.success)
        self.assertFalse(condition.next_save_penalty)
        self.assertEqual(condition.resolve_save(1, 13, rng=rng).total, 14)

    def test_sliver_expires_at_end_of_casters_next_turn(self):
        state = self.state()
        state.start_turn("hero")
        state.apply_save_riders(self.sliver, "hero", "enemy", False, 30, 30)
        state.end_turn("hero")
        state.start_turn("enemy")
        state.end_turn("enemy")
        self.assertTrue(state.conditions["enemy"].next_save_penalty)
        state.start_turn("hero")
        self.assertTrue(state.conditions["enemy"].next_save_penalty)
        state.end_turn("hero")
        self.assertFalse(state.conditions["enemy"].next_save_penalty)

    def test_sliver_success_does_not_apply_rider_and_repeat_does_not_stack(self):
        state = self.state()
        state.apply_save_riders(self.sliver, "hero", "enemy", True, 30, 30)
        self.assertFalse(state.conditions["enemy"].next_save_penalty)
        for _ in range(2):
            state.apply_save_riders(self.sliver, "hero", "enemy", False, 30, 30)
        rng = Mock()
        rng.randint.return_value = 3
        self.assertEqual(state.conditions["enemy"].save_bonus(5, rng), 2)
        rng.randint.assert_called_once_with(1, 4)

    def test_sliver_affects_concentration_and_bless_ends_after_failed_save(self):
        state = self.state()
        state.cast_support("hero", "enemy", self.bless)
        state.apply_save_riders(self.sliver, "enemy", "hero", False, 30, 30)
        state.rng = Mock()
        state.rng.randint.side_effect = [1, 4, 1]
        state.damaged("hero", "enemy", 10, 30)
        self.assertFalse(state.conditions["hero"].next_save_penalty)
        self.assertFalse(state.conditions["hero"].blessed)

    def test_concentration_replacement_removes_bless(self):
        state = self.state()
        state.cast_support("hero", "enemy", self.bless)
        self.assertTrue(state.conditions["hero"].blessed)
        fire = SupportSpell("Faerie Fire", "faerie_fire", difficulty_class=100)
        state.cast_support("hero", "enemy", fire)
        self.assertFalse(state.conditions["hero"].blessed)
        self.assertTrue(state.conditions["enemy"].illuminated)

    def test_whispers_consumes_reaction_moves_and_provokes_only_one_attack(self):
        state = self.state()
        with patch("dnd5ecombat.duel_spells.resolve_attack_sequence",
                   return_value=SimpleNamespace(remaining_hp=90, damage=10)) as attack:
            distance = state.apply_save_riders(self.whispers, "hero", "enemy", False, 5, 30)
        self.assertEqual(distance, 35)
        self.assertFalse(state.reactions["hero"])
        self.assertFalse(state.reactions["enemy"])
        attack.assert_called_once()
        self.assertEqual(state.apply_save_riders(self.whispers, "hero", "enemy", False, 35, 30), 35)

    def test_whispers_no_move_when_save_passes_or_restrained_or_no_reaction(self):
        for reason in ("save", "restrained", "reaction"):
            state = self.state()
            if reason == "restrained":
                state.conditions["enemy"].apply(SavingThrowConditionEffect(
                    10, "str", Condition.RESTRAINED), "net")
            if reason == "reaction":
                state.reactions["enemy"] = False
            self.assertEqual(state.apply_save_riders(
                self.whispers, "hero", "enemy", reason == "save", 5, 30), 5)

    def test_automatic_success_and_failure_do_not_consume_next_save_penalty(self):
        state = self.state()
        condition = state.conditions["enemy"]
        condition.next_save_penalty = True
        for options in ({"automatic_success": True}, {"automatic_failure": True}):
            resolve_saving_throw_damage(self.whispers, 0, 100, rng=state.rng,
                                       saving_throw_resolver=condition.resolve_save, **options)
            self.assertTrue(condition.next_save_penalty)

    def test_faerie_fire_suppresses_invisibility_until_concentration_ends(self):
        state = self.state()
        state.conditions["enemy"].apply(SavingThrowConditionEffect(
            10, "dex", Condition.INVISIBLE), "invisibility")
        scenario = AttackScenario("Sword", self.attack)
        self.assertFalse(state.visible("enemy"))
        self.assertTrue(attack_flags(scenario, state.conditions["hero"], state.conditions["enemy"], 5)[2])
        state.cast_support("hero", "enemy", SupportSpell("Faerie Fire", "faerie_fire", difficulty_class=100))
        self.assertTrue(state.visible("enemy"))
        flags = attack_flags(scenario, state.conditions["hero"], state.conditions["enemy"], 5)
        self.assertEqual(flags[1:3], (True, False))
        state.clear_concentration("hero")
        self.assertFalse(state.visible("enemy"))

    def test_misty_step_respects_bonus_action_and_leveled_spell_restrictions(self):
        state = self.state()
        entries = ((0, AttackScenario("Sword", self.attack)),)
        self.assertEqual(state.choose_teleport("hero", entries, 60, 30), (self.teleport, 30))
        self.assertIsNone(state.choose_teleport("hero", entries, None, 30))
        for attack in (replace(self.attack, spell_slot_level=1),
                       replace(self.attack, action_type="bonus_action")):
            self.assertIsNone(state.choose_teleport("hero", ((0, AttackScenario(attack.name, attack)),), 60, 30))

    def test_misty_step_avoids_close_range_disadvantage_in_actual_duel(self):
        bow = replace(self.attack, name="Bow", attack_mode="ranged",
                      normal_range_feet=80, long_range_feet=320, reach_feet=None)
        hero = replace(self.hero, attack_profile=bow, attack_sequence=(bow,),
                       support_spells=(self.teleport,), spell_slots=())
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                   return_value=SimpleNamespace(remaining_hp=0, damage=100,
                                                attack=SimpleNamespace(hit=True))) as attack:
            simulate_duel(1, DuelMatchup(hero, self.enemy, starting_distance_feet=5), seed=7)
        attack.assert_called_once()
        self.assertFalse(attack.call_args.kwargs["disadvantage"])

    def test_bless_modifies_attack_roll_in_actual_duel(self):
        hero = replace(self.hero, support_spells=(self.bless,))
        enemy = replace(self.enemy, armor_class=23, max_hp=1000)
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append((ac, profile.attack_bonus))
            return SimpleNamespace(remaining_hp=0 if ac == 23 else hp,
                                   damage=0, attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack):
            simulate_duel(1, DuelMatchup(hero, enemy), seed=7)
        self.assertEqual([ac for ac, _ in calls], [15, 23])
        self.assertIn(calls[1][1], range(6, 10))


if __name__ == "__main__":
    unittest.main()
