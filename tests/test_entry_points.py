import subprocess
import sys
import unittest
from unittest.mock import patch
from importlib.metadata import entry_points
from pathlib import Path

from dnd5ecombat.gui import main as gui_main


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ApplicationEntryPointTests(unittest.TestCase):
    def test_installed_console_scripts_target_package_modules(self):
        scripts = {
            entry.name: entry.value
            for entry in entry_points(group="console_scripts")
            if entry.name.startswith("dnd5ecombat")
        }

        self.assertEqual(scripts["dnd5ecombat"], "dnd5ecombat.main:main")
        self.assertEqual(scripts["dnd5ecombat-gui"], "dnd5ecombat.gui:main")

    def test_module_help_starts_in_a_subprocess(self):
        result = subprocess.run(
            [sys.executable, "-m", "dnd5ecombat", "--help"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--monster-file", result.stdout)

    def test_cli_runs_with_real_profiles_in_a_subprocess(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dnd5ecombat",
                "--trials",
                "2",
                "--seed",
                "7",
                "--character-file",
                "characters/tobias_wren.json",
                "--monster-file",
                "monsters/goblin.json",
            ],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Target: Goblin", result.stdout)
        self.assertIn("Trials per scenario and AC: 2", result.stdout)

    def test_gui_smoke_mode_validates_resources_without_opening_window(self):
        self.assertEqual(gui_main(["dnd5ecombat-gui", "--smoke-test"]), 0)

    def test_gui_smoke_mode_rejects_missing_version_metadata(self):
        with patch("dnd5ecombat.__version__", "0+unknown"):
            with self.assertRaisesRegex(RuntimeError, "version metadata"):
                gui_main(["dnd5ecombat-gui", "--smoke-test"])


if __name__ == "__main__":
    unittest.main()
