import ast
import unittest
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "dnd5ecombat"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_application_modules_do_not_import_cli_compatibility_layers(self):
        application_modules = (
            "application_service.py",
            "attack_simulation.py",
            "character_models.py",
            "character_persistence.py",
            "character_profiles.py",
            "duel_simulation.py",
            "profile_catalog.py",
            "roll20_import.py",
            "scenario_factory.py",
            "simulation_core.py",
            "storage_paths.py",
            "gui_service.py",
        )
        for filename in application_modules:
            with self.subTest(filename=filename):
                tree = ast.parse(
                    (PACKAGE_DIR / filename).read_text(encoding="utf-8")
                )
                imported_modules = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imported_modules.update(
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module
                )
                self.assertTrue(
                    {"cli", "legacy_cli"}.isdisjoint(imported_modules),
                    f"{filename} depends on a CLI compatibility layer",
                )

    def test_current_cli_does_not_route_through_legacy_module(self):
        tree = ast.parse((PACKAGE_DIR / "cli.py").read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("legacy_cli", imported_modules)


if __name__ == "__main__":
    unittest.main()
