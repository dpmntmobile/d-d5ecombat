import json
import random
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.combat import resolve_saving_throw_damage
from dnd5ecombat.duel_simulation import simulate_duel, simulate_duel_batch
from dnd5ecombat.duel_spells import DuelSpellState
from dnd5ecombat.models import (
    AttackProfile, Condition, DamageDice, DuelCombatant, DuelMatchup,
    SaveSuccessDamage, SavingThrowConditionEffect, SavingThrowDamageProfile,
)
from dnd5ecombat.monster_profiles import monster_from_dict, monster_to_dict
from dnd5ecombat.profile_catalog import load_character_build
from dnd5ecombat.profile_schema import ProfileValidationError, validate_profile
from dnd5ecombat.resource_models import duel_save_actions
from dnd5ecombat.roll20_support_spells import map_support_spells
from dnd5ecombat.support_spells import SupportSpell


ROOT = Path(__file__).resolve().parents[1]


class DuelSpellTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Sword", 5, (DamageDice(1, 6),), attack_mode="melee")
        self.rebuke = SavingThrowDamageProfile(
            "Rebuke", 100, (DamageDice(2, 10),), damage_modifier=30,
            save_ability="dex", damage_type="fire", action_type="reaction",
            spell_slot_level=1, range_feet=60, reaction_trigger="damaged_by_visible_creature",
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
            allow_upcast=True, upcast_damage_dice=(DamageDice(1, 10),),
        )
        self.heal = SupportSpell("Cure Wounds", "healing", (DamageDice(1, 8),), 3,
                                 upcast_damage_dice=(DamageDice(1, 8),))
        self.fire = SupportSpell("Faerie Fire", "faerie_fire", difficulty_class=100)
        self.hero = DuelCombatant("Hero", 15, 20, 100, self.attack,
                                  spell_slots=((1, 2),), saving_throw_profiles=(self.rebuke,),
                                  support_spells=(self.heal, self.fire))
        self.enemy = DuelCombatant("Enemy", 15, 20, -100, replace(self.attack, name="Claw"))

    def state(self, hero=None, enemy=None):
        combatants = {"hero": hero or self.hero, "enemy": enemy or self.enemy}
        hp = {k: c.max_hp for k, c in combatants.items()}
        conditions = {k: ConditionState() for k in combatants}
        resources = {k: AttackResources(c.saving_throw_profiles + c.support_spells,
                                       c.spell_slots, c.pact_slots,
                                       c.spell_slot_capacity, c.pact_slot_capacity)
                     for k, c in combatants.items()}
        return DuelSpellState(combatants, hp, conditions, resources,
                              dict.fromkeys(combatants, False), random.Random(7))

    def test_reaction_interrupts_multiattack_and_resets_each_trial(self):
        hero = replace(self.hero, initiative_bonus=-100, support_spells=())
        enemy = replace(self.enemy, initiative_bonus=100, attacks_per_turn=3,
                        attack_sequence=(self.enemy.attack_profile,) * 3)
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append(profile.name)
            return SimpleNamespace(remaining_hp=hp - 1, damage=1, attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack):
            result = simulate_duel(3, DuelMatchup(hero, enemy), seed=7)
        self.assertEqual(result.character_wins, 3)
        self.assertEqual(calls, ["Claw"] * 3)

    def test_reaction_requires_damage_living_actor_visibility_range_and_resources(self):
        for reason in ("zero", "dead", "hidden", "range", "slots", "incapacitated", "bonus_spell"):
            with self.subTest(reason=reason):
                state = self.state()
                damage, distance = 1, 60
                if reason == "zero":
                    damage = 0
                elif reason == "dead":
                    state.hp["hero"] = 0
                elif reason == "hidden":
                    state.hidden["enemy"] = True
                elif reason == "range":
                    distance = 61
                elif reason == "slots":
                    state.resources["hero"].spell_slots = {}
                elif reason == "bonus_spell":
                    state.bonus_spell_turn = "hero"
                else:
                    state.conditions["hero"].apply(SavingThrowConditionEffect(10, "con", Condition.STUNNED), "stun")
                state.damaged("hero", "enemy", damage, distance)
                self.assertEqual(state.hp["enemy"], 20)

    def test_one_reaction_until_start_of_next_turn(self):
        state = self.state(enemy=replace(self.enemy, max_hp=1000))
        state.damaged("hero", "enemy", 1, None)
        hp = state.hp["enemy"]
        state.damaged("hero", "enemy", 1, None)
        self.assertEqual(state.hp["enemy"], hp)
        self.assertEqual(state.resources["hero"].spell_slots[1], 1)
        state.start_turn("hero")
        state.damaged("hero", "enemy", 1, None)
        self.assertLess(state.hp["enemy"], hp)
        self.assertEqual(state.resources["hero"].spell_slots[1], 0)

    def test_reaction_uses_upcast_and_damage_defenses(self):
        hero = replace(self.hero, spell_slots=((2, 1),), spell_slot_capacity=((2, 1),))
        state = self.state(hero, replace(self.enemy, damage_immunities=("fire",)))
        state.damaged("hero", "enemy", 1, None)
        self.assertEqual(state.hp["enemy"], 20)
        self.assertEqual(state.resources["hero"].spell_slots[2], 1)
        state = self.state(hero)
        with patch("dnd5ecombat.duel_spells.resolve_saving_throw_damage", wraps=resolve_saving_throw_damage) as cast:
            state.damaged("hero", "enemy", 1, 60)
        self.assertEqual(sum(d.number for d in cast.call_args.args[0].damage_dice), 3)
        self.assertEqual(state.resources["hero"].spell_slots[2], 0)

    def test_mockery_expires_at_end_of_targets_next_turn(self):
        state = self.state()
        state.apply_mockery("enemy")
        state.start_turn("enemy")
        self.assertTrue(state.conditions["enemy"].has_rule("attack_disadvantage"))
        state.end_turn("enemy")
        self.assertFalse(state.conditions["enemy"].has_rule("attack_disadvantage"))

    def test_mockery_only_affects_first_attack_even_when_advantage_cancels(self):
        mockery = SavingThrowDamageProfile("Mockery", 100, (DamageDice(1, 4),),
                                          save_ability="wis", spell_slot_level=0,
                                          next_attack_disadvantage=True)
        hero = replace(self.hero, saving_throw_profiles=(mockery,), support_spells=())
        enemy = replace(self.enemy, attacks_per_turn=2, pack_tactics=True,
                        attack_sequence=(self.enemy.attack_profile,) * 2)
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(remaining_hp=0 if len(calls) == 2 else hp,
                                   damage=0, attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.choose_turn_plan", return_value=(
            ((0, SimpleNamespace(attack=mockery)),), None, 10)), patch(
            "dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack):
            simulate_duel(1, DuelMatchup(hero, enemy, monster_ally_near_target=True), seed=7)
        self.assertEqual([c["disadvantage"] for c in calls], [True, False])
        self.assertTrue(all(c["advantage"] for c in calls))

    def test_heal_caps_hp_spends_slot_and_upcasts(self):
        state = self.state(replace(self.hero, spell_slots=((2, 1),), spell_slot_capacity=((2, 1),)))
        state.hp["hero"] = 19
        state.cast_support("hero", "enemy", self.heal)
        self.assertEqual(state.hp["hero"], 20)
        self.assertEqual(state.resources["hero"].spell_slots[2], 0)
        self.assertFalse(state.resources["hero"].available(self.heal))

    def test_healing_replaces_attack_action_in_actual_duel(self):
        hero = replace(self.hero, support_spells=(self.heal,), saving_throw_profiles=(),
                       initiative_bonus=-100)
        enemy = replace(self.enemy, initiative_bonus=100)
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append((profile.name, hp))
            damage = 16 if len(calls) == 1 else 100
            return SimpleNamespace(remaining_hp=max(0, hp - damage), damage=damage,
                                   attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack):
            simulate_duel(1, DuelMatchup(hero, enemy), seed=7)
        self.assertEqual([name for name, _ in calls], ["Claw", "Claw"])
        self.assertGreater(calls[1][1], 4)

    def test_faerie_fire_policy_and_attack_advantage_in_actual_duel(self):
        hero = replace(self.hero, support_spells=(self.fire,), saving_throw_profiles=())
        enemy = replace(self.enemy, armor_class=30, max_hp=100)
        state = self.state(hero, enemy)
        self.assertEqual(state.choose_support("hero", "enemy", 60, 0.35), self.fire)
        self.assertIsNone(state.choose_support("hero", "enemy", 61, 0.35))
        calls = []

        def attack(profile, ac, hp, **kwargs):
            calls.append((profile.name, kwargs))
            return SimpleNamespace(remaining_hp=0 if profile.name == "Sword" else hp,
                                   damage=0, attack=SimpleNamespace(hit=True))

        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=attack):
            simulate_duel(1, DuelMatchup(hero, enemy), seed=7)
        self.assertEqual([name for name, _ in calls], ["Claw", "Sword"])
        self.assertTrue(calls[1][1]["advantage"])

    def test_support_policy_does_not_heal_full_hp_or_undead_or_easy_kill(self):
        state = self.state()
        self.assertIsNone(state.choose_support("hero", "enemy", None, 100))
        state.hp["hero"] = 5
        self.assertEqual(state.choose_support("hero", "enemy", None, 1), self.heal)
        state.hp["enemy"] = 1
        self.assertIsNone(state.choose_support("hero", "enemy", None, 1))
        state = self.state(replace(self.hero, creature_tags=("undead",)))
        state.hp["hero"] = 5
        self.assertIsNone(state.choose_support("hero", "enemy", None, 5))

    def test_faerie_fire_failed_save_advantage_success_no_effect(self):
        state = self.state()
        state.start_turn("hero")
        state.cast_support("hero", "enemy", self.fire)
        self.assertTrue(state.conditions["enemy"].has_rule("grants_attack_advantage"))
        state.cast_support("hero", "enemy", replace(self.fire, difficulty_class=1))
        self.assertFalse(state.conditions["enemy"].illuminated)
        self.assertEqual(state.resources["hero"].spell_slots[1], 0)

    def test_concentration_damage_dc_duration_and_incapacitation(self):
        state = self.state()
        state.start_turn("hero")
        state.cast_support("hero", "enemy", self.fire)
        with patch("dnd5ecombat.duel_spells.resolve_saving_throw", return_value=SimpleNamespace(success=True)) as save:
            state.damaged("hero", "enemy", 26, None)
        self.assertEqual(save.call_args.args[1], 13)
        self.assertTrue(state.conditions["enemy"].illuminated)
        for _ in range(9):
            state.start_turn("hero")
        self.assertTrue(state.conditions["enemy"].illuminated)
        state.start_turn("hero")
        self.assertFalse(state.conditions["enemy"].illuminated)
        state = self.state()
        state.cast_support("hero", "enemy", self.fire)
        state.conditions["hero"].apply(SavingThrowConditionEffect(10, "con", Condition.PARALYZED), "paralysis")
        state.check_incapacitated()
        self.assertFalse(state.conditions["enemy"].illuminated)

    def test_failed_concentration_and_zero_damage(self):
        state = self.state()
        state.cast_support("hero", "enemy", self.fire)
        with patch("dnd5ecombat.duel_spells.resolve_saving_throw", return_value=SimpleNamespace(success=False)) as save:
            state.damaged("hero", "enemy", 0, None)
            save.assert_not_called()
            state.damaged("hero", "enemy", 1, None)
        self.assertFalse(state.conditions["enemy"].illuminated)

    def test_concentration_uses_damage_after_resistance_in_actual_duel(self):
        hero = replace(self.hero, max_hp=100, damage_resistances=("fire",),
                       support_spells=(self.fire,), saving_throw_profiles=(),
                       spell_slots=((1, 1),))
        attack = replace(self.enemy.attack_profile, attack_bonus=100,
                         damage_dice=(DamageDice(1, 2),), damage_modifier=38,
                         damage_type="fire")
        enemy = replace(self.enemy, armor_class=30, max_hp=100,
                        attack_profile=attack, attack_sequence=(attack,))
        with patch("dnd5ecombat.duel_spells.resolve_saving_throw",
                   return_value=SimpleNamespace(success=False)) as save:
            simulate_duel(1, DuelMatchup(hero, enemy), seed=7)
        # Resistance reduces the hit enough to use DC 10. Losing concentration
        # removes the effect, so later hits do not prompt additional saves.
        self.assertEqual([call.args[1] for call in save.call_args_list], [100, 10])

    def test_mutual_reactions_each_spend_one_reaction_and_slot(self):
        hero = replace(self.hero, max_hp=100)
        enemy = replace(self.enemy, max_hp=100, spell_slots=((1, 2),),
                        saving_throw_profiles=(self.rebuke,))
        state = self.state(hero, enemy)
        state.damaged("hero", "enemy", 1, None)
        self.assertLess(state.hp["hero"], 100)
        self.assertLess(state.hp["enemy"], 100)
        self.assertFalse(any(state.reactions.values()))
        self.assertEqual(state.resources["hero"].spell_slots[1], 1)
        self.assertEqual(state.resources["enemy"].spell_slots[1], 1)

    def test_seeded_parallel_results_match(self):
        matchup = DuelMatchup(self.hero, self.enemy)
        self.assertEqual(simulate_duel_batch((matchup, matchup), 20, seed=7, workers=1),
                         simulate_duel_batch((matchup, matchup), 20, seed=7, workers=2))


class SpellImportTests(unittest.TestCase):
    def test_real_characters_and_native_round_trip(self):
        tobias = load_character_build(ROOT / "characters/tobias_wren.json")
        self.assertEqual({s.name for s in tobias.support_spells}, {"Cure Wounds", "Faerie Fire", "Bless", "Misty Step"})
        spells = {s.name: s for s in tobias.support_spells}
        heal, fire = spells["Cure Wounds"], spells["Faerie Fire"]
        self.assertEqual(spells["Bless"].free_casts, 1)
        self.assertEqual(spells["Misty Step"].free_casts, 1)
        self.assertEqual(heal.damage_modifier, 3)
        self.assertEqual(fire.difficulty_class, 13)
        felicity = load_character_build(ROOT / "characters/felicity.json")
        saves = {s.name: s for s in duel_save_actions(felicity.saving_throw_profiles)}
        self.assertEqual(saves["Hellish Rebuke"].reaction_trigger, "damaged_by_visible_creature")
        self.assertTrue(saves["Vicious Mockery"].next_attack_disadvantage)
        self.assertFalse(saves["Vicious Mockery"].unmodeled_effects)
        with TemporaryDirectory() as directory:
            for build in (tobias, felicity):
                path = Path(directory) / "build.json"
                save_custom_build(build, path)
                loaded = load_custom_build(path)
                self.assertEqual(loaded.support_spells, build.support_spells)
                self.assertEqual(loaded.saving_throw_profiles, build.saving_throw_profiles)

    def test_unprepared_support_spell_is_not_imported(self):
        data = {"other_repeating_attributes": {
            "repeating_spell-1_row_spellname": {"current": "Faerie Fire"},
            "repeating_spell-1_row_spellprepared": {"current": "0"},
        }}
        self.assertEqual(map_support_spells(data, {"pb": 2}), [])

    def test_monster_round_trip_and_schema_reject_invalid_effects(self):
        data = json.loads((ROOT / "monsters/goblin.json").read_text())
        data["support_spells"] = [{"name": "Faerie Fire", "effect": "faerie_fire"}]
        monster = monster_from_dict(data)
        self.assertEqual(monster_from_dict(monster_to_dict(monster)), monster)
        data["support_spells"][0]["effect"] = "unknown"
        with self.assertRaises(ProfileValidationError):
            validate_profile(data, "monster")


if __name__ == "__main__":
    unittest.main()
