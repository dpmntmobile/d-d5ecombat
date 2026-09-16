"""Action budgets, bonus attacks, and first-hit riders in complete duels."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.duel_turn_policy import first_hit_dice, reserve_plan, score_plan
from dnd5ecombat.models import (
    AttackProfile, AttackScenario, Condition, DamageDice, DuelCombatant, DuelMatchup,
    FirstHitBonusDamage, SavingThrowConditionEffect, SavingThrowDamageProfile,
    TargetProfile, TurnPlan,
)
from dnd5ecombat.profile_catalog import load_character_build
from dnd5ecombat.profile_schema import ProfileValidationError, validate_profile
from dnd5ecombat.roll20_build import build_from_roll20_with_attack
from dnd5ecombat.roll20_reader import import_from_roll20
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch, simulate_turns_to_zero
from dnd5ecombat.simulation_core import calculate_attack_analytics


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)
    def randint(self, low, high):
        value = next(self.values)
        assert low <= value <= high
        return value


class DuelTurnPlanTests(unittest.TestCase):
    def setUp(self):
        self.main = AttackProfile("Main", 0, (DamageDice(1, 2),), attack_mode="melee")
        self.off = replace(self.main, name="Off", action_type="bonus_action")
        self.bonus = FirstHitBonusDamage("First hit", (DamageDice(1, 6),), (0, 1))
        self.plan = TurnPlan("Two weapons", (
            AttackScenario("Main", self.main), AttackScenario("Off", self.off)), self.bonus)
        self.hero = DuelCombatant("Hero", 11, 100, 100, self.main, turn_plans=(self.plan,))
        self.enemy = DuelCombatant("Enemy", 11, 100, -100, replace(self.main, name="Claw"))

    def scripted(self, hero=None, enemy=None, hits=(False, True, True, True, True), trials=1, distance=None):
        calls = []
        def resolve(attack, ac, hp, **kwargs):
            index = len(calls) % len(hits)
            calls.append((attack.name, kwargs))
            return SimpleNamespace(remaining_hp=0 if index == len(hits) - 1 else hp,
                                   attack=SimpleNamespace(hit=hits[index]))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve):
            result = simulate_duel(trials, DuelMatchup(hero or self.hero, enemy or self.enemy,
                starting_distance_feet=distance, monster_speed_feet=0), seed=7)
        return result, calls

    def test_miss_preserves_first_hit_for_bonus_attack_and_new_turn_resets(self):
        result, calls = self.scripted()
        self.assertEqual([name for name, _ in calls], ["Main", "Off", "Claw", "Main", "Off"])
        self.assertEqual([bool(options["bonus_damage_dice"]) for _, options in calls],
                         [True, True, False, True, False])
        self.assertEqual(result.total_rounds, 2)

    def test_bonus_resets_between_trials(self):
        _, calls = self.scripted(hits=(True,), trials=3)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(options["bonus_damage_dice"] == self.bonus.damage_dice for _, options in calls))

    def test_extra_attack_does_not_multiply_bonus_action(self):
        plan = TurnPlan("Extra Attack", (self.plan.attacks[0], self.plan.attacks[0], self.plan.attacks[1]),
                        replace(self.bonus, eligible_attack_indices=(0, 1, 2)))
        hero = replace(self.hero, attacks_per_turn=2, attack_sequence=(self.main,) * 2, turn_plans=(plan,))
        _, calls = self.scripted(hero, hits=(True, True, True))
        self.assertEqual([name for name, _ in calls], ["Main", "Main", "Off"])
        self.assertEqual([bool(k["bonus_damage_dice"]) for _, k in calls], [True, False, False])

    def test_depleted_bonus_attack_is_skipped_and_does_not_borrow_action(self):
        off = replace(self.off, limited_uses=1)
        plan = replace(self.plan, attacks=(self.plan.attacks[0], AttackScenario("Off", off)))
        hero = replace(self.hero, turn_plans=(plan,))
        _, calls = self.scripted(hero, hits=(True, True, True, True, True, True))
        self.assertEqual([n for n, _ in calls], ["Main", "Off", "Claw", "Main", "Claw", "Main"])

    def test_reservation_preserves_original_bonus_indices_and_shared_uses(self):
        scarce = replace(self.main, limited_uses=1)
        plan = TurnPlan("Repeated", (AttackScenario("One", scarce), AttackScenario("Two", scarce),
                                    self.plan.attacks[1]), replace(self.bonus, eligible_attack_indices=(2,)))
        state = AttackResources((scarce, self.off))
        entries = reserve_plan(plan, state)
        self.assertEqual([index for index, _ in entries], [0, 2])
        self.assertTrue(state.available(scarce))
        state.spend(scarce)
        self.assertEqual(reserve_plan(plan, state), ())

    def test_first_hit_score_accounts_for_probability_that_prior_attacks_miss(self):
        score = score_plan(tuple(enumerate(self.plan.attacks)), self.bonus, self.enemy,
                           ConditionState(), ConditionState())
        self.assertAlmostEqual(score, 4.5375)

    def test_scoring_includes_automatic_critical_hits_from_paralysis(self):
        state = ConditionState()
        state.apply(SavingThrowConditionEffect(30, "con", Condition.PARALYZED), "paralysis")
        score = score_plan(tuple(enumerate(self.plan.attacks)), self.bonus, self.enemy, ConditionState(), state)
        # Advantage hits 75%; all hits crit. Two d2 weapon pools average 3;
        # first-hit doubled d6 averages 7, applied with 1 - .25**2 probability.
        self.assertAlmostEqual(score, 2 * .75 * 3 + (1 - .25**2) * 7)
        analytics = calculate_attack_analytics(self.main, 11, critical_on_hit=True)
        self.assertEqual(analytics.critical_probability, analytics.hit_probability)
        with self.assertRaises(TypeError):
            calculate_attack_analytics(self.main, 11, critical_on_hit=1)

    def test_sneak_eligibility_requires_advantage_without_disadvantage(self):
        bonus = replace(self.bonus, requires_advantage=True)
        for advantage, disadvantage, expected in ((False, False, ()), (True, True, ()),
                                                  (False, True, ()), (True, False, bonus.damage_dice)):
            self.assertEqual(first_hit_dice(bonus, 0, True, advantage, disadvantage), expected)
        self.assertEqual(first_hit_dice(bonus, 0, False, True, False), ())
        self.assertEqual(first_hit_dice(bonus, 2, True, True, False), ())

    def test_runtime_conditions_can_enable_bonus_after_the_first_attack(self):
        rider = SavingThrowConditionEffect(30, "con", Condition.PRONE)
        main = replace(self.main, condition_effect=rider)
        plan = replace(self.plan, attacks=(AttackScenario("Trip", main), self.plan.attacks[1]),
                       first_hit_bonus_damage=replace(self.bonus, requires_advantage=True))
        hero = replace(self.hero, attack_profile=main, attack_sequence=(main,), turn_plans=(plan,))
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw", return_value=SimpleNamespace(success=False)):
            _, calls = self.scripted(hero, hits=(True, True))
        self.assertEqual(calls[0][1]["bonus_damage_dice"], ())
        self.assertEqual(calls[1][1]["bonus_damage_dice"], self.bonus.damage_dice)
        self.assertTrue(calls[1][1]["advantage"])

    def test_critical_hit_doubles_first_hit_dice_in_actual_damage(self):
        enemy = replace(self.enemy, max_hp=9)
        # Initiative; natural 20; doubled d2 weapon dice; doubled d6 rider dice.
        result = simulate_duel(1, DuelMatchup(self.hero, enemy), rng=Rolls(10, 10, 20, 1, 1, 3, 4))
        self.assertEqual((result.character_wins, result.total_rounds), (1, 1))

    def test_damage_resistance_applies_after_combining_weapon_and_bonus(self):
        main = replace(self.main, damage_type="fire")
        plan = TurnPlan("Fire", (AttackScenario("Fire", main),),
                        FirstHitBonusDamage("Bonus", (DamageDice(1, 2),), (0,)))
        hero = replace(self.hero, attack_profile=main, attack_sequence=(main,), turn_plans=(plan,))
        enemy = replace(self.enemy, armor_class=10, max_hp=2, damage_resistances=("fire",))
        result = simulate_duel(1, DuelMatchup(hero, enemy), rng=Rolls(10, 10, 10, 2, 2))
        self.assertEqual(result.character_wins, 1)

    def test_save_action_competes_against_entire_turn_including_bonus(self):
        save = SavingThrowDamageProfile("Save", 30, (DamageDice(1, 2),), damage_modifier=1,
                                       save_ability="dex", spell_slot_level=0)
        hero = replace(self.hero, saving_throw_profiles=(save,))
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage") as cast:
            _, calls = self.scripted(hero, hits=(True, True))
        cast.assert_not_called()
        self.assertEqual([n for n, _ in calls], ["Main", "Off"])
        with patch("dnd5ecombat.duel_simulation.resolve_saving_throw_damage",
                   return_value=SimpleNamespace(remaining_hp=0)) as cast:
            simulate_duel(1, DuelMatchup(replace(hero, saving_throw_profiles=(replace(save, damage_modifier=100),)),
                                       self.enemy), seed=7)
        cast.assert_called_once()

    def test_incapacitation_prevents_both_actions_without_spending_bonus_use(self):
        off = replace(self.off, limited_uses=1)
        hero = replace(self.hero, turn_plans=(replace(self.plan,
            attacks=(self.plan.attacks[0], AttackScenario("Off", off))),))
        original = ConditionState.has_rule
        turns = 0
        def rule(state, name):
            nonlocal turns
            if name == "prevents_actions":
                turns += 1
                return turns == 1
            return original(state, name)
        with patch.object(ConditionState, "has_rule", rule):
            _, calls = self.scripted(hero, hits=(True, True, True))
        self.assertEqual([n for n, _ in calls], ["Claw", "Main", "Off"])

    def test_bonus_weapon_requires_an_in_range_weapon_action(self):
        off = replace(self.off, attack_mode="ranged", normal_range_feet=120)
        hero = replace(self.hero, turn_plans=(replace(self.plan,
            attacks=(self.plan.attacks[0], AttackScenario("Off", off))),))
        # After movement the off-hand weapon can reach but Main cannot; it cannot attack alone.
        _, calls = self.scripted(hero, hits=(True, True, True), distance=60)
        self.assertEqual([name for name, _ in calls], ["Claw", "Main", "Off"])

    def test_bonus_spell_cost_and_2014_casting_budget(self):
        cantrip = replace(self.main, spell_slot_level=0)
        quick = replace(self.off, spell_slot_level=1, damage_modifier=10)
        plan = TurnPlan("Two casts", (AttackScenario("Cantrip", cantrip), AttackScenario("Quick", quick)))
        hero = replace(self.hero, attack_profile=cantrip, attack_sequence=(cantrip,),
                       turn_plans=(plan,), spell_slots={1: 1})
        _, calls = self.scripted(hero, hits=(True, True, True, True))
        self.assertEqual([n for n, _ in calls], ["Main", "Off", "Claw", "Main"])

    def test_bonus_spell_can_follow_dash_and_spends_only_when_cast(self):
        quick = replace(self.off, spell_slot_level=1, attack_mode="ranged", normal_range_feet=30)
        plan = TurnPlan("Dash and cast", (self.plan.attacks[0], AttackScenario("Quick", quick)))
        hero = replace(self.hero, turn_plans=(plan,), spell_slots={1: 1})
        result, calls = self.scripted(hero, hits=(True,), distance=80)
        self.assertEqual((result.total_rounds, calls[0][0]), (1, "Off"))

    def test_invalid_action_budgets_are_rejected(self):
        spell = AttackScenario("Spell", replace(self.main, spell_slot_level=1))
        bonus_spell = AttackScenario("Quick", replace(self.off, spell_slot_level=0))
        reaction = AttackScenario("Reaction", replace(self.off, action_type="reaction"))
        for attacks in ((self.plan.attacks[1],), self.plan.attacks + (self.plan.attacks[1],),
                        (self.plan.attacks[0],) * 2, tuple(reversed(self.plan.attacks)),
                        (spell, self.plan.attacks[0]), (spell, self.plan.attacks[1]),
                        (spell, bonus_spell), (self.plan.attacks[0], reaction)):
            with self.subTest(attacks=attacks), self.assertRaises(ValueError):
                replace(self.hero, turn_plans=(TurnPlan("Invalid", attacks),))
        with self.assertRaises(TypeError):
            replace(self.hero, turn_plans=("invalid",))
        with self.assertRaises(TypeError):
            replace(self.bonus, requires_advantage=1)
        with self.assertRaises(ValueError):
            replace(self.hero, attack_sequence=(self.off,))

    def test_explicit_main_sequence_defines_available_action_attack_count(self):
        plan = TurnPlan("Two main attacks", (self.plan.attacks[0],) * 2)
        hero = DuelCombatant("Hero", 10, 20, 0, self.main,
                             attack_sequence=(self.main,) * 2, turn_plans=(plan,))
        self.assertEqual(hero.attacks_per_turn, 2)

    def test_seeded_parallel_results_match_with_turn_plans(self):
        matchups = (DuelMatchup(self.hero, self.enemy),) * 2
        self.assertEqual(simulate_duel_batch(matchups, 10, seed=31, workers=1),
                         simulate_duel_batch(matchups, 10, seed=31, workers=2))

    def test_one_sided_turns_also_honor_explicit_advantage_requirement(self):
        bonus = replace(self.bonus, eligible_attack_indices=(0,), requires_advantage=True)
        plan = TurnPlan("Conditional", (self.plan.attacks[0],), bonus)
        target = TargetProfile("Target", 10, 2)
        result = simulate_turns_to_zero(1, plan, target, rng=Rolls(10, 2))
        self.assertEqual(result.total_rolled_damage, 2)


class ImportedDuelPlanTests(unittest.TestCase):
    def test_gui_services_expose_duel_plans_and_advantage_comparison_variants(self):
        from dnd5ecombat.gui_service import run_simulations, SimulationSettings
        path = Path(__file__).resolve().parents[1] / "characters/blackleaf.json"
        build = load_character_build(path)
        monster = TargetProfile("Target", 10, 20, attack_profiles=(build.attack_profile,))
        tables = run_simulations(build, monster,
            SimulationSettings(trials=5, seed=7, include_advantage=True, include_disadvantage=True),
            sections=("turns", "duels"))
        plan_name = build.turn_plans[0].name
        names = {row[0] for row in tables.turns.rows}
        self.assertTrue({plan_name, plan_name + " with advantage", plan_name + " with disadvantage"} <= names)
        self.assertIn(plan_name, tables.duels.note)
        self.assertIn("requires advantage without disadvantage", tables.duels.note)
        self.assertEqual(len(tables.duels.rows), 1)

    def test_blackleaf_plans_enter_duels_and_eligibility_survives_persistence(self):
        path = Path(__file__).resolve().parents[1] / "characters/blackleaf.json"
        build = load_character_build(path)
        monster = TargetProfile("Target", 10, 20, attack_profiles=(build.attack_profile,))
        matchup = build_duel_policy_matchups(build, monster)[0]
        self.assertEqual(matchup.character.turn_plans, build.turn_plans)
        self.assertTrue(all(p.first_hit_bonus_damage.requires_advantage
                            for p in build.turn_plans if p.first_hit_bonus_damage))
        with TemporaryDirectory() as directory:
            saved = Path(directory) / "native.json"
            save_custom_build(build, saved)
            self.assertEqual(load_custom_build(saved).turn_plans, build.turn_plans)
            data = json.loads(saved.read_text())
            data["turn_plans"][0]["first_hit_bonus_damage"]["requires_advantage"] = "true"
            with self.assertRaises(ProfileValidationError):
                validate_profile(data, "native-character")

    def test_roll20_bonus_attack_spells_generate_only_legal_casting_pairs(self):
        data = {"name": "Caster", "stats": {}, "hp_and_level": {},
                "attacks_and_spellcasting": {}, "other_repeating_attributes": {}}
        for name, level, time in (("Cantrip", 0, "1 action"), ("Spell", 1, "1 action"),
                                  ("Quick", 1, "1 bonus action"), ("Weapon", None, "")):
            fields = {"atkname": name, "atkbonus": "+5", "dmgbase": "1d6", "atkrange": "60"}
            if level is not None:
                fields["spelllevel"] = level
                for field, value in {"spellattackid": name, "spellcastingtime": time}.items():
                    data["other_repeating_attributes"][f"repeating_spell-1_{name}_{field}"] = {"current": value}
            for field, value in fields.items():
                data["attacks_and_spellcasting"][f"repeating_attack_{name}_{field}"] = {"current": value}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "caster.json"
            path.write_text(json.dumps(data))
            build = load_character_build(path)
        self.assertEqual({plan.name for plan in build.turn_plans}, {"Cantrip + Quick", "Weapon + Quick"})

    def test_roll20_extra_attack_expands_main_attacks_and_eligible_indices_only(self):
        path = Path(__file__).resolve().parents[1] / "characters/blackleaf.json"
        data = import_from_roll20(path)
        data["attacks_per_action"] = 2
        attack = next(a for a in data["attacks"] if a["name"] == "Shortsword")
        build = build_from_roll20_with_attack(data, attack["bonus"], attack["damage_dice"],
                                            attack["damage_modifier"], selected_attack_name=attack["name"])
        plan = next(p for p in build.turn_plans if p.name.startswith("Shortsword + Dagger Off Hand"))
        self.assertEqual([s.attack.action_type for s in plan.attacks], ["action", "action", "bonus_action"])
        self.assertEqual(plan.first_hit_bonus_damage.eligible_attack_indices, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
