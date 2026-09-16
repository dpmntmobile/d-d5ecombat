import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.models import AttackProfile, DamageDice
from dnd5ecombat.monster_profiles import load_monster_profile, monster_to_dict
from dnd5ecombat.profile_schema import (
    CURRENT_PROFILE_SCHEMA_VERSION,
    ProfileValidationError,
    load_profile_schema,
    validate_profile,
)
from dnd5ecombat.profile_catalog import (
    discover_character_catalog,
    discover_monster_catalog,
)
from dnd5ecombat.roll20_import import import_from_roll20


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ProfileSchemaTests(unittest.TestCase):
    def test_every_version_one_schema_is_bundled_and_valid(self):
        for profile_kind in ("native-character", "monster", "roll20-character"):
            with self.subTest(profile_kind=profile_kind):
                schema = load_profile_schema(profile_kind)

                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )

    def test_bundled_monsters_satisfy_the_current_schema(self):
        for path in sorted((PROJECT_DIR / "monsters").glob("*.json")):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))

                validate_profile(data, "monster", source=path)

    def test_bundled_monster_audit_records_every_unmodeled_trait(self):
        expected_traits = {
            "ghoul.json": (),
            "goblin.json": (),
            "orc.json": (),
            "skeleton.json": (),
            "wolf.json": ("Keen Hearing and Smell",),
            "zombie.json": (),
        }

        for filename, expected in expected_traits.items():
            with self.subTest(filename=filename):
                monster = load_monster_profile(PROJECT_DIR / "monsters" / filename)

                self.assertEqual(monster.unmodeled_traits, expected)

    def test_ghoul_paralysis_has_ten_turn_duration_and_repeat_save(self):
        monster = load_monster_profile(PROJECT_DIR / "monsters" / "ghoul.json")
        effect = monster.attack_profiles[1].condition_effect
        self.assertEqual(effect.duration_turns, 10)
        self.assertTrue(effect.repeat_save_at_end_of_turn)

    def test_versionless_monster_remains_compatible_with_version_one(self):
        data = {"name": "Legacy target", "armor_class": 12, "max_hp": 9}

        normalized = validate_profile(data, "monster")

        self.assertEqual(normalized["schema_version"], 1)
        self.assertNotIn("schema_version", data)

    def test_unsupported_schema_version_has_a_field_path(self):
        data = {
            "schema_version": 99,
            "name": "Future target",
            "armor_class": 12,
            "max_hp": 9,
        }

        with self.assertRaisesRegex(
            ProfileValidationError,
            r"\$\.schema_version: unsupported monster schema version 99",
        ):
            validate_profile(data, "monster")

    def test_nested_validation_error_identifies_the_field(self):
        data = {
            "schema_version": 1,
            "name": "Broken target",
            "armor_class": 12,
            "max_hp": 9,
            "attacks": [
                {"name": "Bite", "attack_bonus": "four", "damage_dice": "1d6"}
            ],
        }

        with self.assertRaisesRegex(
            ProfileValidationError,
            r"\$\.attacks\[0\]\.attack_bonus",
        ):
            validate_profile(data, "monster")

    def test_loaded_file_error_includes_source_and_field_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Broken target",
                        "armor_class": "twelve",
                        "max_hp": 9,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ProfileValidationError) as context:
                load_monster_profile(path)

        self.assertIn("broken.json", str(context.exception))
        self.assertIn("$.armor_class", str(context.exception))

    def test_new_monster_serialization_declares_schema_version(self):
        monster = load_monster_profile(PROJECT_DIR / "monsters" / "goblin.json")

        data = monster_to_dict(monster)

        self.assertEqual(data["schema_version"], CURRENT_PROFILE_SCHEMA_VERSION)

    def test_native_character_round_trip_declares_schema_version(self):
        attack = AttackProfile("Sword", 5, (DamageDice(1, 8),), 3)
        build = CharacterBuild("Schema hero", attack)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "hero.json"
            save_custom_build(build, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_custom_build(path)

        self.assertEqual(data["schema_version"], CURRENT_PROFILE_SCHEMA_VERSION)
        self.assertEqual(loaded.name, build.name)
        self.assertEqual(loaded.attack_profile, build.attack_profile)

    def test_roll20_schema_reports_missing_required_section(self):
        data = {"name": "Incomplete export", "hp_and_level": {}}

        with self.assertRaisesRegex(ProfileValidationError, "stats"):
            validate_profile(data, "roll20-character")

    def test_monster_catalog_reports_schema_field_path(self):
        with TemporaryDirectory() as directory:
            profile_directory = Path(directory) / "monsters"
            profile_directory.mkdir()
            (profile_directory / "broken.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Broken target",
                        "armor_class": "twelve",
                        "max_hp": 9,
                    }
                ),
                encoding="utf-8",
            )

            catalog = discover_monster_catalog(directory)

        self.assertEqual(catalog.items, ())
        self.assertIn("$.armor_class", catalog.issues[0].message)

    def test_character_catalog_reports_roll20_schema_field_path(self):
        with TemporaryDirectory() as directory:
            profile_directory = Path(directory) / "characters"
            profile_directory.mkdir()
            (profile_directory / "broken.json").write_text(
                json.dumps({"name": "Incomplete export", "hp_and_level": {}}),
                encoding="utf-8",
            )

            catalog = discover_character_catalog(directory)

        self.assertEqual(catalog.items, ())
        self.assertIn("stats", catalog.issues[0].message)

    def test_native_character_load_reports_schema_field_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Broken hero",
                        "armor_class": "sixteen",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ProfileValidationError) as context:
                load_custom_build(path)

        self.assertIn("$.armor_class", str(context.exception))

    def test_malformed_roll20_json_keeps_compatibility_none_result(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("not json", encoding="utf-8")

            result = import_from_roll20(path)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
