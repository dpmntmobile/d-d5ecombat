"""Protect documented compatibility paths during internal module refactors."""

import importlib
import unittest
from pathlib import Path

from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.cli_arguments import parse_args
from dnd5ecombat.models import AttackProfile, DamageDice
from dnd5ecombat.monster_profiles import load_monster_profile
from dnd5ecombat.roll20_reader import import_from_roll20


class ApiCompatibilityTests(unittest.TestCase):
    def test_console_compatibility_paths_keep_public_models_and_loaders(self):
        exports = {
            "CharacterBuild": CharacterBuild, "AttackProfile": AttackProfile,
            "DamageDice": DamageDice, "load_custom_build": load_custom_build,
            "save_custom_build": save_custom_build,
            "import_from_roll20": import_from_roll20,
            "load_monster_profile": load_monster_profile, "parse_args": parse_args,
        }
        for name in ("main", "cli", "legacy_cli"):
            module = importlib.import_module(f"dnd5ecombat.{name}")
            for symbol, canonical in exports.items():
                with self.subTest(module=name, symbol=symbol):
                    self.assertIs(getattr(module, symbol), canonical)

    def test_target_aliases_select_the_same_file_and_model(self):
        path = Path(__file__).resolve().parent / "fixtures/compatibility/v1/monster.json"
        current = parse_args(["--monster-file", str(path)])
        legacy = parse_args(["--target-file", str(path)])
        self.assertEqual(vars(current), vars(legacy))
        expected = load_monster_profile(path)
        for name in ("main", "cli", "legacy_cli"):
            with self.subTest(module=name):
                module = importlib.import_module(f"dnd5ecombat.{name}")
                self.assertEqual(module.load_target_profile(path), expected)
