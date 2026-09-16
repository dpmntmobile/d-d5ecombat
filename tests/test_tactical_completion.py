"""0.4.0 mixed actions, structured tactics, and slot recovery regressions."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.condition_rules import ConditionState
from dnd5ecombat.duel_turn_policy import choose_turn_plan, first_hit_dice, mixed_plans
from dnd5ecombat.models import (
    AttackProfile,
    AttackScenario,
    DamageDice,
    DuelCombatant,
    DuelMatchup,
    FirstHitBonusDamage,
    SavingThrowDamageProfile,
    TargetProfile,
    TurnPlan,
)
from dnd5ecombat.monster_profiles import monster_from_dict, monster_to_dict
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch


class TacticalCompletionTests(unittest.TestCase):
    def setUp(self):
        self.weapon = AttackProfile(
            "Sword", 5, (DamageDice(1, 6),), attack_mode="melee"
        )
        self.hero = DuelCombatant("Hero", 12, 100, 100, self.weapon)
        self.enemy = DuelCombatant(
            "Enemy", 12, 100, -100, replace(self.weapon, name="Claw")
        )
        self.save = SavingThrowDamageProfile(
            "Flame",
            15,
            (DamageDice(3, 6),),
            save_ability="dex",
            spell_slot_level=1,
            range_feet=30,
        )

    def select(self, sequence=None, saves=(), bonuses=(), slots=(), pact=(), plans=()):
        sequence = (self.weapon,) if sequence is None else sequence
        state = AttackResources(sequence + saves + bonuses, slots, pact)
        entries, rider, damage = choose_turn_plan(
            sequence,
            plans,
            state,
            self.enemy,
            ConditionState(),
            ConditionState(),
            saves=saves,
            bonus_attacks=bonuses,
        )
        return tuple(s.attack for _, s in entries), rider, damage, state

    def trace(self, matchup, count=3, trials=1):
        calls = []

        def resolve(attack, defense, hp, **kwargs):
            calls.append((attack, kwargs))
            return SimpleNamespace(
                remaining_hp=0 if len(calls) % count == 0 else hp,
                attack=SimpleNamespace(hit=True),
            )

        with (
            patch(
                "dnd5ecombat.duel_simulation.resolve_attack_sequence",
                side_effect=resolve,
            ),
            patch(
                "dnd5ecombat.duel_simulation.resolve_saving_throw_damage",
                side_effect=resolve,
            ),
        ):
            result = simulate_duel(trials, matchup, seed=17, max_rounds_per_trial=20)
        return result, calls

    def test_weapon_and_bonus_save_are_selected_without_spending_slots(self):
        bonus = replace(self.save, action_type="bonus_action")
        attacks, _, _, state = self.select(saves=(bonus,), slots={1: 1})
        self.assertEqual(attacks, (self.weapon, bonus))
        self.assertEqual(state.spell_slots, {1: 1})

    def test_save_cantrip_and_bonus_attack_spell_are_legal(self):
        cantrip = replace(self.save, spell_slot_level=0)
        bonus = replace(
            self.weapon, name="Ray", spell_slot_level=1, action_type="bonus_action"
        )
        attacks, _, _, _ = self.select(saves=(cantrip,), bonuses=(bonus,), slots={1: 1})
        self.assertEqual(attacks, (cantrip, bonus))

    def test_two_leveled_spells_cannot_share_action_and_bonus(self):
        bonus = replace(self.save, name="Bonus flame", action_type="bonus_action")
        attacks, _, _, _ = self.select(saves=(self.save, bonus), slots={1: 2})
        self.assertEqual(attacks, (self.weapon, bonus))

    def test_save_action_does_not_enable_offhand_weapon(self):
        offhand = replace(self.weapon, name="Dagger", action_type="bonus_action")
        attacks, _, _, _ = self.select(
            saves=(self.save,), bonuses=(offhand,), slots={1: 1}
        )
        self.assertEqual(attacks, (self.save,))

    def test_nonspell_bonus_save_can_follow_leveled_action_spell(self):
        bonus = replace(
            self.save,
            name="Breath",
            spell_slot_level=None,
            action_type="bonus_action",
            limited_uses=1,
        )
        attacks, _, _, _ = self.select(saves=(self.save, bonus), slots={1: 1})
        self.assertEqual(attacks, (self.save, bonus))

    def test_depleted_bonus_save_falls_back_to_weapon_next_turn(self):
        bonus = replace(self.save, action_type="bonus_action")
        hero = replace(self.hero, saving_throw_profiles=(bonus,), spell_slots={1: 1})
        _, calls = self.trace(DuelMatchup(hero, self.enemy), count=5)
        self.assertEqual(
            [a.name for a, _ in calls], ["Sword", "Flame", "Claw", "Sword", "Claw"]
        )

    def test_bonus_save_after_dash_and_out_of_range_costs_no_slot(self):
        bonus = replace(self.save, action_type="bonus_action", range_feet=10)
        hero = replace(self.hero, saving_throw_profiles=(bonus,), spell_slots={1: 1})
        _, calls = self.trace(
            DuelMatchup(
                hero, self.enemy, starting_distance_feet=65, monster_speed_feet=0
            ),
            count=1,
        )
        self.assertEqual(calls[0][0].name, "Flame")

    def test_independent_bonus_save_can_be_used_after_dash(self):
        bonus = replace(
            self.save,
            action_type="bonus_action",
            range_feet=10,
            spell_slot_level=None,
            limited_uses=1,
        )
        hero = replace(self.hero, saving_throw_profiles=(bonus,))
        _, calls = self.trace(
            DuelMatchup(
                hero, self.enemy, starting_distance_feet=65, monster_speed_feet=0
            ),
            count=1,
        )
        self.assertEqual(calls[0][0].name, "Flame")

    def test_replacing_bonus_action_does_not_transfer_rider_eligibility(self):
        offhand = replace(self.weapon, name="Dagger", action_type="bonus_action")
        rider = FirstHitBonusDamage("Dagger rider", (DamageDice(1, 6),), (1,))
        plan = TurnPlan(
            "Two weapons",
            (AttackScenario("Sword", self.weapon), AttackScenario("Dagger", offhand)),
            rider,
        )
        ray = replace(offhand, name="Ray", spell_slot_level=1)
        generated = mixed_plans((self.weapon,), (plan,), (), (ray,))
        for candidate in generated:
            if candidate.attacks[-1].attack == ray:
                self.assertIsNone(candidate.first_hit_bonus_damage)

    def test_any_pool_uses_lowest_slot_and_pact_on_equal_level(self):
        spell = replace(self.save, spell_slot_pool="any", allow_upcast=True)
        state = AttackResources((spell,), {1: 1, 3: 1}, {3: 1})
        self.assertEqual(state.slot_for(spell), (1, "spellcasting"))
        state.spend(spell)
        self.assertEqual(state.slot_for(spell), (3, "pact"))
        state.spend(spell)
        self.assertEqual(state.slot_for(spell), (3, "spellcasting"))

    def test_explicit_pool_restriction_and_legacy_exact_level(self):
        state = AttackResources((self.save,), {2: 1}, {1: 1})
        self.assertFalse(state.available(self.save))
        pact_spell = replace(self.save, spell_slot_pool="pact")
        self.assertTrue(state.available(pact_spell))
        state.spend(pact_spell)
        self.assertEqual(state.spell_slots, {2: 1})

    def test_upcast_dice_are_per_extra_level_and_preserve_original(self):
        spell = replace(
            self.save,
            spell_slot_pool="any",
            allow_upcast=True,
            upcast_damage_dice=(DamageDice(1, 6),),
        )
        state = AttackResources((spell,), (), {3: 1})
        prepared = state.prepare(spell)
        self.assertEqual(
            prepared.damage_dice, spell.damage_dice + (DamageDice(1, 6),) * 2
        )
        self.assertEqual(prepared.spell_slot_level, 3)
        self.assertEqual(spell.spell_slot_level, 1)
        self.assertEqual(state.pact_slots, {3: 1})

    def test_upcast_attack_and_save_spells_execute_with_scaled_dice(self):
        for spell in (
            self.save,
            replace(self.weapon, spell_slot_level=1, damage_dice=(DamageDice(8, 6),)),
        ):
            with self.subTest(kind=type(spell).__name__):
                spell = replace(
                    spell,
                    spell_slot_pool="pact",
                    allow_upcast=True,
                    upcast_damage_dice=(DamageDice(1, 6),),
                )
                hero = replace(
                    self.hero,
                    pact_slots={3: 1},
                    saving_throw_profiles=(spell,)
                    if isinstance(spell, SavingThrowDamageProfile)
                    else (),
                    attack_profile=self.weapon
                    if isinstance(spell, SavingThrowDamageProfile)
                    else spell,
                    attack_sequence=(self.weapon,)
                    if isinstance(spell, SavingThrowDamageProfile)
                    else (spell,),
                )
                _, calls = self.trace(DuelMatchup(hero, self.enemy), count=1)
                self.assertEqual(calls[0][0].spell_slot_level, 3)
                self.assertEqual(
                    calls[0][0].damage_dice, spell.damage_dice + (DamageDice(1, 6),) * 2
                )

    def test_short_rest_recovers_only_pact_and_long_rest_recovers_both(self):
        state = AttackResources((), {1: 0}, {3: 0}, {1: 4}, {3: 2})
        state.rest("short")
        self.assertEqual((state.spell_slots, state.pact_slots), ({1: 0}, {3: 2}))
        state.rest("long")
        self.assertEqual((state.spell_slots, state.pact_slots), ({1: 4}, {3: 2}))
        with self.assertRaises(ValueError):
            state.rest("nap")

    def test_rest_before_duel_uses_recorded_full_capacity_and_resets_trials(self):
        spell = replace(self.save, spell_slot_pool="pact")
        hero = replace(
            self.hero,
            pact_slots={1: 0},
            pact_slot_capacity={1: 1},
            saving_throw_profiles=(spell,),
        )
        _, calls = self.trace(
            DuelMatchup(hero, self.enemy, rest_before_duel="short"), count=1, trials=2
        )
        self.assertEqual([a.name for a, _ in calls], ["Flame", "Flame"])
        self.assertEqual(hero.pact_slots, ((1, 0),))

    def test_pack_tactics_needs_explicit_active_nearby_ally(self):
        hero = replace(self.hero, pack_tactics=True)
        for ally in (False, True):
            _, calls = self.trace(
                DuelMatchup(hero, self.enemy, character_ally_near_target=ally), count=1
            )
            self.assertEqual(calls[0][1]["advantage"], ally)

    def test_sneak_attack_ally_route_still_rejects_disadvantage(self):
        rider = FirstHitBonusDamage("Sneak", (DamageDice(1, 6),), (0,), True, True)
        self.assertEqual(
            first_hit_dice(rider, 0, True, False, False, True), rider.damage_dice
        )
        self.assertEqual(first_hit_dice(rider, 0, True, False, True, True), ())
        self.assertEqual(
            first_hit_dice(rider, 0, True, True, True, True), rider.damage_dice
        )
        self.assertEqual(first_hit_dice(rider, 0, True, False, False, False), ())

    def test_ally_rider_participates_in_scoring_and_execution(self):
        rider = FirstHitBonusDamage("Sneak", (DamageDice(2, 6),), (0,), True, True)
        plan = TurnPlan("Sneak", (AttackScenario("Sword", self.weapon),), rider)
        hero = replace(self.hero, turn_plans=(plan,))
        _, calls = self.trace(
            DuelMatchup(hero, self.enemy, character_ally_near_target=True), count=1
        )
        self.assertEqual(calls[0][1]["bonus_damage_dice"], rider.damage_dice)
        self.assertFalse(calls[0][1]["advantage"])

    def test_aggressive_reaches_target_without_spending_attack_action(self):
        hero = replace(self.hero, aggressive=True)
        result, calls = self.trace(
            DuelMatchup(
                hero, self.enemy, starting_distance_feet=60, monster_speed_feet=0
            ),
            count=1,
        )
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual(calls[0][0].name, "Sword")

    def test_nimble_disengage_removes_close_range_bow_disadvantage(self):
        bow = replace(
            self.weapon, name="Bow", attack_mode="ranged", normal_range_feet=80
        )
        for nimble in (False, True):
            hero = replace(
                self.hero,
                attack_profile=bow,
                attack_sequence=(bow,),
                nimble_escape=nimble,
            )
            _, calls = self.trace(
                DuelMatchup(hero, self.enemy, starting_distance_feet=5), count=1
            )
            self.assertEqual(calls[0][1]["disadvantage"], not nimble)

    def test_hide_requires_concealment_and_reveals_on_first_attack(self):
        hero = replace(
            self.hero,
            nimble_escape=True,
            stealth_bonus=30,
            attack_sequence=(self.weapon, self.weapon),
            attacks_per_turn=2,
        )
        for concealment in (False, True):
            _, calls = self.trace(
                DuelMatchup(hero, self.enemy, character_can_hide=concealment), count=2
            )
            self.assertEqual([kw["advantage"] for _, kw in calls], [concealment, False])

    def test_hide_does_not_add_a_second_bonus_action(self):
        bonus = replace(self.save, action_type="bonus_action")
        hero = replace(
            self.hero,
            nimble_escape=True,
            stealth_bonus=30,
            saving_throw_profiles=(bonus,),
            spell_slots={1: 1},
        )
        _, calls = self.trace(
            DuelMatchup(hero, self.enemy, character_can_hide=True), count=2
        )
        self.assertFalse(calls[0][1]["advantage"])

    def test_tactical_resources_are_deterministic_across_workers(self):
        hero = replace(
            self.hero,
            pack_tactics=True,
            saving_throw_profiles=(
                replace(
                    self.save,
                    action_type="bonus_action",
                    spell_slot_pool="any",
                    allow_upcast=True,
                ),
            ),
            pact_slots={2: 2},
        )
        matchup = DuelMatchup(hero, self.enemy, character_ally_near_target=True)
        self.assertEqual(
            simulate_duel_batch((matchup,) * 2, 5, seed=23, workers=1),
            simulate_duel_batch((matchup,) * 2, 5, seed=23, workers=2),
        )

    def test_invalid_slot_capacities_traits_and_assumptions_are_rejected(self):
        for kwargs in (
            dict(pack_tactics=1),
            dict(pact_slots={1: 1, 2: 1}),
            dict(pact_slots={6: 1}),
            dict(spell_slots={1: 2}, spell_slot_capacity={1: 1}),
        ):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises((ValueError, TypeError)),
            ):
                replace(self.hero, **kwargs)
        with self.assertRaises(TypeError):
            DuelMatchup(self.hero, self.enemy, monster_can_hide="yes")
        with self.assertRaises(ValueError):
            replace(self.save, spell_slot_pool="wizard")

    def test_native_and_monster_round_trip_new_fields_and_plans(self):
        offhand = replace(self.weapon, name="Dagger", action_type="bonus_action")
        rider = FirstHitBonusDamage("Sneak", (DamageDice(1, 6),), (0, 1), True, True)
        plan = TurnPlan(
            "Two weapons",
            (AttackScenario("Sword", self.weapon), AttackScenario("Dagger", offhand)),
            rider,
        )
        spell = replace(
            self.save,
            spell_slot_pool="any",
            allow_upcast=True,
            upcast_damage_dice=(DamageDice(1, 6),),
        )
        shared = dict(
            attack_profiles=(self.weapon, offhand),
            turn_plans=(plan,),
            saving_throw_profiles=(spell,),
            pack_tactics=True,
            nimble_escape=True,
            stealth_bonus=6,
            pact_slots={2: 0},
            pact_slot_capacity={2: 2},
        )
        monster = TargetProfile("Monster", 12, 30, **shared)
        self.assertEqual(monster_from_dict(monster_to_dict(monster)), monster)
        hero = CharacterBuild("Hero", self.weapon, **shared)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "hero.json"
            save_custom_build(hero, path)
            self.assertEqual(load_custom_build(path), hero)
        matchups = build_duel_policy_matchups(
            hero, monster, monster_ally_near_target=True
        )
        self.assertEqual(len(matchups), 1)
        self.assertEqual(matchups[0].monster.turn_plans, (plan,))
        self.assertEqual(matchups[0].monster.bonus_attacks, (offhand,))


if __name__ == "__main__":
    unittest.main()
