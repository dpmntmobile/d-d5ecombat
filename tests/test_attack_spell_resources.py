"""Spell costs across import, persistence, action selection, and full duels."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dnd5ecombat.action_resources import AttackResources
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.models import (
    AttackProfile, DamageDice, DuelCombatant, DuelMatchup,
    SavingThrowDamageProfile, TargetProfile,
)
from dnd5ecombat.monster_profiles import load_monster_profile, save_monster_profile, monster_to_dict
from dnd5ecombat.profile_catalog import load_character_build
from dnd5ecombat.profile_schema import ProfileValidationError, validate_profile
from dnd5ecombat.roll20_reader import import_from_roll20
from dnd5ecombat.roll20_spell_resources import spell_level, spell_range, spell_slots
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import simulate_duel, simulate_duel_batch, select_best_attack


class AttackSpellResourcesTests(unittest.TestCase):
    def setUp(self):
        self.weapon = AttackProfile("Sword", 5, (DamageDice(1, 6),), attack_mode="melee")
        self.spell = replace(self.weapon, name="Ray", damage_modifier=10,
                             spell_slot_level=1, attack_mode="ranged", normal_range_feet=30)
        self.save = SavingThrowDamageProfile("Burst", 12, (DamageDice(1, 6),),
                                            spell_slot_level=1, save_ability="dex")

    def test_attack_and_save_share_slots_and_planning_does_not_spend(self):
        state = AttackResources((self.spell, self.save, self.weapon), {1: 1})
        self.assertEqual(state.plan((self.spell,) * 2, (self.weapon,), lambda a: a[0]),
                         (self.spell,))
        self.assertEqual(state.spell_slots, {1: 1})
        state.spend(self.save)
        self.assertFalse(state.available(self.spell))
        self.assertEqual(state.plan((self.spell,) * 2, (self.weapon,), lambda a: a[0]),
                         (self.weapon, self.weapon))
        with self.assertRaisesRegex(ValueError, "no uses"):
            state.spend(self.spell)
        state = AttackResources((self.spell, self.save), {1: 1})
        state.spend(self.spell)
        self.assertFalse(state.available(self.save))

    def test_cantrip_is_one_cast_and_does_not_consume_slots(self):
        cantrip = replace(self.spell, spell_slot_level=0)
        state = AttackResources((cantrip,), {1: 2})
        for _ in range(3):
            self.assertEqual(state.plan((cantrip,) * 3, (), None), (cantrip,))
            state.spend(cantrip)
        self.assertEqual(state.spell_slots, {1: 2})

    def test_no_higher_slot_substitution_or_cast_after_weapon_attack(self):
        state = AttackResources((self.spell, self.weapon), {2: 2})
        self.assertEqual(state.plan((self.spell,), (), None), ())
        state = AttackResources((self.spell, self.weapon), {1: 2})
        self.assertEqual(state.plan((self.weapon, self.spell), (self.weapon,), lambda a: a[0]),
                         (self.weapon, self.weapon))

    def test_slot_and_limited_use_are_both_required(self):
        spell = replace(self.spell, limited_uses=1)
        state = AttackResources((spell,), {1: 2})
        state.spend(spell)
        self.assertEqual(state.spell_slots, {1: 1})
        self.assertEqual(state.plan((spell,), (), None), ())

    def test_factory_scores_entire_weapon_action_against_one_cast(self):
        spell = replace(self.spell, damage_modifier=2)
        build = CharacterBuild("Hero", spell, attack_profiles=(spell, self.weapon),
                               attacks_per_action=2, spell_slots={1: 2})
        monster = TargetProfile("Enemy", 10, 20, attack_profiles=(self.weapon,))
        matchup = build_duel_policy_matchups(build, monster)[0]
        self.assertEqual(matchup.character.attack_profile, self.weapon)
        self.assertEqual(matchup.character.spell_slots, ((1, 2),))
        self.assertEqual(select_best_attack((spell, self.weapon), 10), spell)
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises((TypeError, ValueError)):
                select_best_attack((spell,), 10, attacks_per_action=invalid)

    def matchup(self, distance=None):
        return DuelMatchup(
            DuelCombatant("Hero", 10, 100, 100, self.spell, attacks_per_turn=2,
                          fallback_attacks=(self.weapon,), spell_slots={1: 1}),
            DuelCombatant("Enemy", 10, 100, -100, replace(self.weapon, name="Claw")),
            starting_distance_feet=distance, monster_speed_feet=0,
        )

    def test_missed_cast_spends_slot_then_full_weapon_action_and_trial_reset(self):
        calls = []
        def resolve(attack, ac, hp, **kwargs):
            calls.append(attack.name)
            return SimpleNamespace(remaining_hp=0 if calls.count("Sword") % 2 == 0
                                   and attack.name == "Sword" else hp,
                                   attack=SimpleNamespace(hit=False))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve):
            result = simulate_duel(2, self.matchup(), seed=7)
        self.assertEqual(result.character_wins, 2)
        self.assertEqual(calls, ["Ray", "Claw", "Sword", "Sword"] * 2)

    def test_dash_preserves_slot_until_in_range(self):
        calls = []
        def resolve(attack, ac, hp, **kwargs):
            calls.append(attack.name)
            return SimpleNamespace(remaining_hp=0, attack=SimpleNamespace(hit=True))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence", side_effect=resolve):
            result = simulate_duel(1, self.matchup(distance=100), seed=7)
        self.assertEqual(result.total_rounds, 2)
        self.assertEqual(calls, ["Ray"])

    def test_seeded_worker_results_match_for_attack_spell_duels(self):
        matchups = (self.matchup(), self.matchup())
        self.assertEqual(simulate_duel_batch(matchups, 8, seed=37, workers=1),
                         simulate_duel_batch(matchups, 8, seed=37, workers=2))

    def test_native_and_monster_round_trip_spell_level_including_zero(self):
        for level in (None, 0, 1, 9):
            spell = replace(self.spell, spell_slot_level=level)
            build = CharacterBuild("Hero", spell, spell_slots={1: 2})
            monster = TargetProfile("Caster", 10, 20, attack_profiles=(spell,), spell_slots={1: 2})
            with TemporaryDirectory() as directory:
                path = Path(directory) / "hero.json"
                save_custom_build(build, path)
                loaded = load_custom_build(path)
                self.assertEqual(loaded.attack_profile, spell)
                self.assertEqual(loaded.attack_profiles, build.attack_profiles)
                # The legacy top-level attack fields must also preserve costs.
                data = json.loads(path.read_text())
                del data["attack_profiles"]
                path.write_text(json.dumps(data))
                self.assertEqual(load_custom_build(path).attack_profile.spell_slot_level, level)
                path = Path(directory) / "monster.json"
                save_monster_profile(monster, path)
                self.assertEqual(load_monster_profile(path), monster)

    def test_invalid_attack_spell_level_rejected_by_model_and_schema(self):
        data = monster_to_dict(TargetProfile("Caster", 10, 20, attack_profiles=(self.spell,)))
        for invalid in (-1, 10, True, "1", 1.5):
            with self.assertRaises((TypeError, ValueError)):
                replace(self.spell, spell_slot_level=invalid)
            data["attacks"][0]["spell_slot_level"] = invalid
            with self.assertRaises(ProfileValidationError):
                validate_profile(data, "monster")


class Roll20SpellResourcesTests(unittest.TestCase):
    def export(self):
        def attributes(prefix, fields):
            return {prefix + key: {"current": value} for key, value in fields.items()}
        return {
            "name": "Caster", "stats": {}, "hp_and_level": {},
            "other_attributes": attributes("", {"lvl1_slots_total": 4, "lvl1_slots_expended": 1}),
            "attacks_and_spellcasting": {
                **attributes("repeating_attack_ray_", {"atkname": "Ray", "atkbonus": "+5", "dmgbase": "2d6"}),
                **attributes("repeating_attack_save_", {"atkname": "Burst", "dmgbase": "2d6", "saveflag": "{{save=1}}", "savedc": "12", "saveattr": "dex"}),
            },
            "other_repeating_attributes": {
                **attributes("repeating_spell-1_row_with_underscores_", {"spellattackid": "ray", "spellrange": "60 feet", "spellcastingtime": "1 action"}),
                **attributes("repeating_spell-1_second_", {"spellattackid": "save", "spelllevel": "1", "spellrange": "30 feet"}),
            },
        }

    def load(self, data):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "roll20.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_character_build(path)

    def test_linked_rows_supply_levels_ranges_and_shared_starting_pool(self):
        build = self.load(self.export())
        self.assertEqual(build.spell_slots, ((1, 1),))
        self.assertEqual(build.attack_profile.spell_slot_level, 1)
        self.assertEqual(build.attack_profile.normal_range_feet, 60)
        self.assertEqual(build.attack_profile.attack_mode, "ranged")
        self.assertEqual(build.saving_throw_profiles[0].range_feet, 30)
        self.assertEqual(build.saving_throw_profiles[0].spell_slot_level, 1)
        self.assertEqual(build.saving_throw_profiles[0].unmodeled_effects, ())
        state = AttackResources((build.attack_profile, *build.saving_throw_profiles), build.spell_slots)
        state.spend(build.attack_profile)
        self.assertFalse(state.available(build.saving_throw_profiles[0]))

    def test_attack_level_and_range_override_linked_row_and_touch_is_melee(self):
        data = self.export()
        data["attacks_and_spellcasting"].update({
            "repeating_attack_ray_spelllevel": {"current": 0},
            "repeating_attack_ray_atkrange": {"current": "Touch"},
        })
        spell = self.load(data).attack_profile
        self.assertEqual((spell.spell_slot_level, spell.attack_mode, spell.reach_feet), (0, "melee", 5))

    def test_attack_ids_with_underscores_link_to_spell_rows(self):
        data = self.export()
        data["attacks_and_spellcasting"] = {
            key.replace("attack_ray_", "attack_ray_with_underscores_"): value
            for key, value in data["attacks_and_spellcasting"].items()
        }
        data["other_repeating_attributes"][
            "repeating_spell-1_row_with_underscores_spellattackid"
        ]["current"] = "ray_with_underscores"
        spell = self.load(data).attack_profile
        self.assertEqual((spell.name, spell.spell_slot_level, spell.normal_range_feet), ("Ray", 1, 60))

    def test_remaining_zero_is_not_replaced_by_total_and_missing_pools_are_empty(self):
        data = self.export()
        data["other_attributes"]["lvl1_slots_expended"]["current"] = 0
        self.assertEqual(self.load(data).spell_slots, ((1, 0),))
        del data["other_attributes"]["lvl1_slots_expended"]
        self.assertEqual(self.load(data).spell_slots, ((1, 4),))
        data["other_attributes"] = {}
        build = self.load(data)
        self.assertEqual(build.spell_slots, ())
        self.assertFalse(AttackResources((build.attack_profile,)).available(build.attack_profile))

    def test_cantrip_section_numeric_zero_and_invalid_metadata(self):
        self.assertEqual(spell_level(None, "repeating_spell-cantrip_row_"), 0)
        self.assertEqual(spell_level(0), 0)
        self.assertIsNone(spell_level(""))
        for value in (-1, 10, True, "unknown"):
            with self.assertRaises(ValueError):
                spell_level(value)
        for value in (-1, True, 1.5, "unknown"):
            with self.assertRaisesRegex(ValueError, "lvl1_slots_expended"):
                spell_slots({"lvl1_slots_expended": {"current": value}})
        for value in ("Self (15-foot cone)", "1 mile", "", "0", "unknown"):
            self.assertIsNone(spell_range(value))
        self.assertEqual(spell_range("120 ft."), 120)

    def test_bundled_felicity_maps_cantrips_and_preserves_unmodeled_riders(self):
        path = Path(__file__).resolve().parents[1] / "characters/felicity.json"
        data = import_from_roll20(path)
        build = load_character_build(path)
        self.assertEqual(build.attack_profile.spell_slot_level, 0)
        self.assertEqual(build.spell_slots, tuple(sorted(data["spell_slots"].items())))
        whisper = next(p for p in build.saving_throw_profiles if p.name == "Dissonant Whispers")
        self.assertEqual(whisper.spell_slot_level, 1)
        self.assertEqual(whisper.range_feet, 60)
        self.assertIn("Forced movement is not modeled.", whisper.unmodeled_effects)


if __name__ == "__main__":
    unittest.main()
