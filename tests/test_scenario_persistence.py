import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dnd5ecombat.application_service import SimulationSettings
from dnd5ecombat.cli_arguments import parse_args
from dnd5ecombat.cli_workflows import main
from dnd5ecombat.scenario_persistence import (
    load_scenario, save_scenario, settings_from_arguments,
)


class ScenarioPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "encounter.json"

    def test_round_trip_preserves_all_settings(self):
        settings = SimulationSettings(
            trials=21, seed=-7, workers=2, include_advantage=True,
            include_disadvantage=True, starting_distance_feet=80,
            character_speed_feet=25, monster_speed_feet=40,
            character_ally_near_target=True, monster_ally_near_target=True,
            character_can_hide=True, monster_can_hide=True, rest_before_duel="short",
        )
        save_scenario(settings, self.path)
        self.assertEqual(load_scenario(self.path), settings)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"schema_version": 1, "settings": asdict(settings)})

    def test_bundled_scenario_is_valid(self):
        settings = load_scenario(Path(__file__).resolve().parents[1] / "scenarios/ranged-duel.json")
        self.assertEqual(settings.starting_distance_feet, 60)
        self.assertEqual(settings.rest_before_duel, "long")

    def test_partial_settings_and_versionless_file_use_defaults(self):
        self.path.write_text('{"settings": {"seed": 9}}', encoding="utf-8-sig")
        self.assertEqual(load_scenario(self.path), SimulationSettings(seed=9))

    def test_invalid_settings_report_source_and_field(self):
        cases = (
            ({"trials": 0}, "$.settings.trials"),
            ({"workers": True}, "$.settings.workers"),
            ({"starting_distance_feet": -1}, "$.settings.starting_distance_feet"),
            ({"character_can_hide": "yes"}, "$.settings.character_can_hide"),
            ({"rest_before_duel": "full"}, "$.settings.rest_before_duel"),
            ({"typo": 1}, "$.settings"),
        )
        for settings, location in cases:
            with self.subTest(settings=settings):
                self.path.write_text(json.dumps({"settings": settings}), encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    load_scenario(self.path)
                self.assertIn(str(self.path), str(caught.exception))
                self.assertIn(location, str(caught.exception))

    def test_invalid_documents_and_future_versions_are_rejected(self):
        for document in ("{", "[]", "{}", '{"schema_version": 2, "settings": {}}'):
            with self.subTest(document=document):
                self.path.write_text(document, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_scenario(self.path)

    def test_cli_explicit_options_override_file_in_either_order(self):
        save_scenario(SimulationSettings(
            trials=20, seed=8, include_advantage=True,
            character_can_hide=True, starting_distance_feet=60,
            rest_before_duel="long",
        ), self.path)
        overrides = ["--trials", "3", "--no-include-advantage",
                     "--no-character-can-hide", "--abstract-positioning"]
        for options in (
            ["--scenario", str(self.path), *overrides],
            [*overrides, "--scenario", str(self.path)],
        ):
            self.assertEqual(settings_from_arguments(parse_args(options)), SimulationSettings(
                trials=3, seed=8, rest_before_duel="long",
            ))

    def test_cli_reports_bad_file_without_traceback(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as caught:
            parse_args(["--scenario", str(self.path)])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("encounter.json", output.getvalue())

    def test_cli_save_exits_without_starting_simulation(self):
        with patch("dnd5ecombat.cli_workflows.run_default_summary") as simulate:
            with redirect_stdout(io.StringIO()):
                result = main(["--save-scenario", str(self.path), "--trials", "4"])
        self.assertEqual(result, 0)
        simulate.assert_not_called()
        self.assertEqual(load_scenario(self.path).trials, 4)

    def test_cli_save_failure_is_reported(self):
        with redirect_stderr(io.StringIO()) as output:
            result = main(["--save-scenario", str(self.path / "missing.json")])
        self.assertEqual(result, 2)
        self.assertIn("Could not save scenario", output.getvalue())

    def test_cli_scenario_does_not_enter_interactive_menu(self):
        save_scenario(SimulationSettings(trials=2), self.path)
        with patch("sys.argv", ["dnd5ecombat"]), patch(
            "dnd5ecombat.cli_workflows.run_interactive_menu"
        ) as menu, patch("dnd5ecombat.cli_workflows.run_default_summary"):
            self.assertEqual(main(["--scenario", str(self.path)]), 0)
        menu.assert_not_called()

    def test_cli_profile_run_matches_explicit_settings(self):
        save_scenario(SimulationSettings(trials=2, seed=17), self.path)
        common = [sys.executable, "-m", "dnd5ecombat",
                  "--character-file", "characters/tobias_wren.json",
                  "--monster-file", "monsters/goblin.json"]
        outputs = []
        for options in (["--scenario", str(self.path)], ["--trials", "2", "--seed", "17"]):
            result = subprocess.run(
                common + options, cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(*outputs)

    def test_scenario_options_cannot_be_silently_ignored_by_other_modes(self):
        for mode in ("--gui", "--interactive"):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args([mode, "--save-scenario", str(self.path)])
