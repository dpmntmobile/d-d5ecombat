"""Group-state regressions exercised through complete initiative rounds."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.combat import resolve_attack_sequence
from dnd5ecombat.duel_spells import DuelSpellState
from dnd5ecombat.models import (
    AttackProfile, Condition, DamageDice, SavingThrowConditionEffect,
    SavingThrowDamageProfile, TargetProfile,
)
from dnd5ecombat.party_combat import MonsterGroup, PartyBattle, simulate_party_battle
from dnd5ecombat.support_spells import SupportSpell


class PartyStateTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Sword", 100, (DamageDice(1, 2),), 10)
        self.harmless = replace(self.attack, name="Harmless", damage_modifier=-100)
        self.hero = CharacterBuild("Hero", self.harmless, max_hp=100,
                                   initiative_bonus=-100)
        self.monster = TargetProfile("Monster", 10, 100,
                                     attack_profiles=(self.attack,))

    def test_pack_tactics_excludes_dead_or_incapacitated_allies(self):
        for status in ("active", "dead", "incapacitated"):
            with self.subTest(status=status):
                ally = replace(self.hero, max_hp=1 if status == "dead" else 100,
                               initiative_bonus=200)
                wolf = replace(self.hero, name="Wolf", pack_tactics=True)
                attack = self.attack
                if status == "incapacitated":
                    attack = replace(attack, condition_effect=SavingThrowConditionEffect(
                        100, "con", Condition.INCAPACITATED, duration_turns=2,
                    ))
                monster = replace(self.monster, attack_profiles=(attack,), initiative_bonus=100)
                battle = PartyBattle((ally, wolf), (MonsterGroup(monster),))
                with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                           wraps=resolve_attack_sequence) as resolve:
                    simulate_party_battle(battle, 1, seed=42, max_rounds_per_trial=1)
                wolf_attack = resolve.call_args_list[-1]
                self.assertEqual(wolf_attack.args[0].name, "Harmless")
                self.assertEqual(wolf_attack.kwargs["advantage"], status == "active")

    def test_condition_on_first_target_does_not_leak_to_retargeted_opponent(self):
        poison = replace(self.attack, name="Poison", condition_effect=
                         SavingThrowConditionEffect(100, "con", Condition.POISONED,
                                                   duration_turns=2))
        monster = replace(self.monster, initiative_bonus=100,
                          attack_profiles=(poison, self.attack),
                          multiattack=("Poison", "Sword", "Sword"))
        first = replace(self.hero, max_hp=15)
        second = replace(self.hero, name="Second")
        battle = PartyBattle((first, second), (MonsterGroup(monster),))
        states = []

        def capture(*args):
            state = DuelSpellState(*args)
            states.append(state)
            return state

        with patch("dnd5ecombat.duel_simulation.DuelSpellState", side_effect=capture):
            result = simulate_party_battle(battle, 1, seed=42, max_rounds_per_trial=1)
        self.assertEqual(result.party_survivors, 1)
        self.assertIn(Condition.POISONED, states[0].conditions["character:0"])
        self.assertNotIn(Condition.POISONED, states[0].conditions["character:1"])

    def test_sneak_attack_ally_route_excludes_dead_or_incapacitated_allies(self):
        from dnd5ecombat.models import AttackScenario, FirstHitBonusDamage, TurnPlan

        rider = FirstHitBonusDamage("Sneak Attack", (DamageDice(1, 6),), (0,),
                                   requires_advantage=True, allows_nearby_ally=True)
        plan = TurnPlan("Sneak", (AttackScenario("Sword", self.attack),), rider)
        rogue = replace(self.hero, attack_profile=self.attack,
                        attack_profiles=(self.attack,), turn_plans=(plan,))
        for status in ("active", "dead", "incapacitated"):
            with self.subTest(status=status):
                ally = replace(self.hero, max_hp=1 if status == "dead" else 100,
                               initiative_bonus=200)
                attack = self.attack
                if status == "incapacitated":
                    attack = replace(attack, condition_effect=SavingThrowConditionEffect(
                        100, "con", Condition.INCAPACITATED, duration_turns=2,
                    ))
                monster = replace(self.monster, initiative_bonus=100, attack_profiles=(attack,))
                battle = PartyBattle((ally, rogue), (MonsterGroup(monster),))
                with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                           wraps=resolve_attack_sequence) as resolve:
                    simulate_party_battle(battle, 1, seed=42, max_rounds_per_trial=1)
                self.assertEqual(bool(resolve.call_args_list[-1].kwargs["bonus_damage_dice"]),
                                 status == "active")

    def test_concentration_cleans_up_after_death_incapacitation_or_failed_save(self):
        for cause in ("death", "incapacitation", "damage"):
            with self.subTest(cause=cause):
                spell = SupportSpell("Faerie Fire", "faerie_fire", difficulty_class=100)
                caster = replace(self.hero, max_hp=1 if cause == "death" else 100,
                                 spell_slots={1: 1}, support_spells=(spell,),
                                 saving_throw_bonuses={"con": -100})
                attack = self.attack
                if cause == "incapacitation":
                    attack = replace(attack, condition_effect=SavingThrowConditionEffect(
                        100, "con", Condition.STUNNED, duration_turns=2,
                    ))
                monster = replace(self.monster, initiative_bonus=100, attack_profiles=(attack,))
                battle = PartyBattle((caster, self.hero), (MonsterGroup(monster, 2),))
                states = []

                def capture(*args):
                    state = DuelSpellState(*args)
                    state.cast_support("character:0", "monster:0:1", spell)
                    self.assertTrue(state.conditions["monster:0:1"].illuminated)
                    states.append(state)
                    return state

                with patch("dnd5ecombat.duel_simulation.DuelSpellState", side_effect=capture):
                    simulate_party_battle(battle, 2, seed=42, max_rounds_per_trial=1)
                for state in states:
                    self.assertFalse(state.concentration)
                    self.assertFalse(state.conditions["monster:0:1"].illuminated)

    def test_reaction_budget_is_shared_across_opponents_and_resets_next_turn(self):
        rebuke = SavingThrowDamageProfile(
            "Rebuke", 100, (DamageDice(1, 2),), save_ability="dex",
            damage_type="fire", action_type="reaction", spell_slot_level=1,
            range_feet=60, reaction_trigger="damaged_by_visible_creature",
        )
        hero = replace(self.hero, max_hp=1000, spell_slots={1: 10},
                       saving_throw_profiles=(rebuke,))
        battle = PartyBattle((hero,), (MonsterGroup(self.monster, 2),))
        from dnd5ecombat.combat import resolve_saving_throw_damage

        with patch("dnd5ecombat.duel_spells.resolve_saving_throw_damage",
                   wraps=resolve_saving_throw_damage) as react:
            result = simulate_party_battle(battle, 2, seed=42, max_rounds_per_trial=3)
        self.assertEqual(result.draws, 2)
        self.assertEqual(react.call_count, 6)


if __name__ == "__main__":
    unittest.main()
