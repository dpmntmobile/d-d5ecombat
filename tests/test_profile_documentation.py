"""Keep published profile examples usable by real readers and loaders."""

import json
import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.monster_profiles import load_monster_profile, monster_to_dict


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ProfileDocumentationTests(unittest.TestCase):
    def test_generated_examples_and_reference_are_current(self):
        generator = runpy.run_path(str(PROJECT_DIR / "scripts/generate_profile_docs.py"))
        for relative, expected in generator["generated_files"]().items():
            with self.subTest(path=relative):
                self.assertEqual(
                    (PROJECT_DIR / relative).read_text(encoding="utf-8"), expected
                )

    def test_native_example_loads_all_actions_and_round_trips(self):
        path = PROJECT_DIR / "docs/examples/native-character.json"
        source = json.loads(path.read_text(encoding="utf-8"))
        build = load_custom_build(path)
        # Native loading can skip invalid optional profiles; verify none vanished.
        for field in ("attack_profiles", "saving_throw_profiles", "support_spells", "turn_plans"):
            self.assertEqual(len(getattr(build, field)), len(source[field]), field)
        with TemporaryDirectory() as directory:
            saved = Path(directory) / "character.json"
            save_custom_build(build, saved)
            self.assertEqual(load_custom_build(saved), build)

    def test_monster_example_loads_and_round_trips(self):
        monster = load_monster_profile(PROJECT_DIR / "docs/examples/monster.json")
        self.assertEqual(len(monster.attack_profiles), 1)
        self.assertEqual(len(monster.saving_throw_profiles), 1)
        self.assertEqual(len(monster.support_spells), 1)
        with TemporaryDirectory() as directory:
            saved = Path(directory) / "monster.json"
            saved.write_text(json.dumps(monster_to_dict(monster)), encoding="utf-8")
            self.assertEqual(load_monster_profile(saved), monster)
