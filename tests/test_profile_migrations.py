"""Frozen historical inputs must remain readable without silent data loss."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.monster_profiles import load_monster_profile, save_monster_profile
from dnd5ecombat.profile_schema import (
    CURRENT_PROFILE_SCHEMA_VERSION, ProfileValidationError, validate_profile,
)
from dnd5ecombat.scenario_persistence import load_scenario, save_scenario


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/compatibility"
LOADERS = {
    "native-character": load_custom_build,
    "monster": load_monster_profile,
    "scenario": load_scenario,
}
WRITERS = {
    "native-character": save_custom_build,
    "monster": save_monster_profile,
    "scenario": save_scenario,
}


class ProfileMigrationTests(unittest.TestCase):
    def test_every_schema_version_has_frozen_native_inputs(self):
        versions = {path.name for path in (ROOT / "src/dnd5ecombat/schemas").glob("v*")
                    if path.is_dir()}
        self.assertEqual(versions, {path.name for path in FIXTURES.glob("v*") if path.is_dir()})
        for version in versions:
            for kind in LOADERS:
                self.assertTrue((FIXTURES / version / f"{kind}.json").is_file())

    def test_historical_and_versionless_profiles_upgrade_without_changing_sources(self):
        for fixture in sorted(FIXTURES.glob("v*/*.json")):
            kind = fixture.stem
            original = fixture.read_bytes()
            expected = LOADERS[kind](fixture)
            for versionless in (False, True):
                with self.subTest(fixture=fixture.name, versionless=versionless), TemporaryDirectory() as directory:
                    source = Path(directory) / "input.json"
                    output = Path(directory) / "output.json"
                    data = json.loads(original)
                    if versionless:
                        data.pop("schema_version")
                    source.write_text(json.dumps(data), encoding="utf-8")
                    before = source.read_bytes()
                    loaded = LOADERS[kind](source)
                    self.assertEqual(loaded, expected)
                    WRITERS[kind](loaded, output)
                    serialized = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(serialized["schema_version"], CURRENT_PROFILE_SCHEMA_VERSION)
                    self.assertEqual(LOADERS[kind](output), expected)
                    self.assertEqual(source.read_bytes(), before)
            self.assertEqual(fixture.read_bytes(), original)

    def test_old_character_keeps_mechanics_and_defaults_new_spell_fields(self):
        build = load_custom_build(FIXTURES / "v1/native-character.json")
        self.assertEqual((build.armor_class, build.max_hp, build.attacks_per_action), (15, 31, 2))
        self.assertEqual(build.attack_profile.name, "Bow")
        self.assertEqual(len(build.attack_profiles), 1)
        self.assertEqual(build.attack_profile.normal_range_feet, 80)
        self.assertEqual(build.damage_resistances, ("fire",))
        self.assertEqual(build.spell_slots, ((1, 1),))
        self.assertEqual(build.spell_slot_capacity, ((1, 3),))
        self.assertEqual(build.pact_slots, ((2, 1),))
        self.assertEqual(build.pact_slot_capacity, ((2, 2),))
        spell, = build.saving_throw_profiles
        self.assertEqual((spell.difficulty_class, spell.spell_slot_pool), (13, "any"))
        self.assertTrue(spell.allow_upcast)
        self.assertEqual([(d.number, d.sides) for d in spell.upcast_damage_dice], [(1, 6)])
        self.assertEqual(spell.reaction_trigger, "")
        self.assertFalse(spell.next_attack_disadvantage)
        self.assertFalse(spell.next_save_penalty)
        self.assertFalse(spell.flee_on_failed_save)
        self.assertEqual(build.support_spells, ())
        plan, = build.turn_plans
        self.assertEqual([s.attack.name for s in plan.attacks], ["Bow", "Bow"])
        self.assertEqual(plan.first_hit_bonus_damage.eligible_attack_indices, (0, 1))
        self.assertTrue(plan.first_hit_bonus_damage.requires_advantage)
        self.assertTrue(plan.first_hit_bonus_damage.allows_nearby_ally)

    def test_old_monster_keeps_condition_timing_and_immunity(self):
        monster = load_monster_profile(FIXTURES / "v1/monster.json")
        self.assertEqual((monster.name, monster.armor_class, monster.max_hp), ("Ghoul", 12, 22))
        self.assertEqual([a.name for a in monster.attack_profiles], ["Bite", "Claws"])
        effect = monster.attack_profiles[1].condition_effect
        self.assertEqual((effect.condition.value, effect.duration_turns), ("paralyzed", 10))
        self.assertTrue(effect.repeat_save_at_end_of_turn)
        self.assertEqual(set(effect.immune_creature_tags), {"elf", "undead"})
        self.assertEqual(monster.damage_immunities, ("poison",))
        self.assertEqual(monster.support_spells, ())

    def test_old_scenario_keeps_encounter_assumptions(self):
        settings = load_scenario(FIXTURES / "v1/scenario.json")
        self.assertEqual((settings.trials, settings.seed, settings.workers), (10000, 42, 1))
        self.assertEqual(settings.starting_distance_feet, 60)
        self.assertEqual((settings.character_speed_feet, settings.monster_speed_feet), (30, 30))
        self.assertEqual(settings.rest_before_duel, "long")
        self.assertFalse(settings.character_can_hide)
        self.assertFalse(settings.monster_ally_near_target)

    def test_unknown_or_malformed_versions_fail_before_loading_and_leave_file_intact(self):
        for kind, loader in LOADERS.items():
            for version in (0, CURRENT_PROFILE_SCHEMA_VERSION + 1, True, "1", None):
                with self.subTest(kind=kind, version=version), TemporaryDirectory() as directory:
                    data = json.loads((FIXTURES / "v1" / f"{kind}.json").read_text(encoding="utf-8"))
                    data["schema_version"] = version
                    source = Path(directory) / f"{kind}.json"
                    source.write_text(json.dumps(data), encoding="utf-8")
                    before = source.read_bytes()
                    with self.assertRaises(ProfileValidationError) as caught:
                        loader(source)
                    self.assertIn(str(source), str(caught.exception))
                    self.assertIn("$.schema_version", str(caught.exception))
                    self.assertEqual(source.read_bytes(), before)

    def test_roll20_envelope_version_is_not_a_native_schema_version(self):
        for export_version in (1, 2):
            data = {"name": "Envelope example", "stats": {}, "hp_and_level": {},
                    "export_metadata": {"format": "dnd5ecombat-roll20", "version": export_version},
                    "unknown_sheet_section": {"preserved": True}}
            before = deepcopy(data)
            normalized = validate_profile(data, "roll20-character")
            self.assertEqual(normalized, before)
            self.assertEqual(data, before)
            self.assertNotIn("schema_version", normalized)
