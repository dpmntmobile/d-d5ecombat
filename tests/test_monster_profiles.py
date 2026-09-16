import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.monster_profiles import (
    load_monster_profile,
    monster_from_dict,
    monster_to_dict,
    save_monster_profile,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]


class MonsterProfilePersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_goblin_profile(self):
        original = load_monster_profile(PROJECT_DIR / "monsters" / "goblin.json")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "goblin.json"
            save_monster_profile(original, destination)
            loaded = load_monster_profile(destination)

        self.assertEqual(loaded, original)

    def test_monster_from_dict_validates_attack_damage_dice(self):
        data = {
            "name": "Broken beast",
            "armor_class": 10,
            "max_hp": 5,
            "attacks": [
                {"name": "Bite", "attack_bonus": 2, "damage_dice": "bad"}
            ],
        }

        with self.assertRaisesRegex(ValueError, "damage_dice"):
            monster_from_dict(data)

    def test_serialized_profile_uses_json_compatible_values(self):
        monster = load_monster_profile(PROJECT_DIR / "monsters" / "wolf.json")

        data = monster_to_dict(monster)

        self.assertIsInstance(data["saving_throw_bonuses"], dict)
        self.assertIsInstance(data["attacks"], list)
        self.assertEqual(data["attacks"][0]["damage_dice"], "2d4")
        self.assertEqual(data["attacks"][0]["condition_effect"]["condition"], "prone")

    def test_multiattack_allows_repeated_named_attacks(self):
        monster = monster_from_dict(
            {
                "name": "Claw beast",
                "armor_class": 12,
                "max_hp": 20,
                "multiattack": ["Claw", "Claw"],
                "attacks": [
                    {"name": "Claw", "attack_bonus": 4, "damage_dice": "1d6"}
                ],
            }
        )

        self.assertEqual(monster.multiattack, ("Claw", "Claw"))


if __name__ == "__main__":
    unittest.main()
