import csv
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dnd5ecombat import __version__
from dnd5ecombat.cli_arguments import parse_args
from dnd5ecombat.cli_workflows import main
from dnd5ecombat.gui_service import SimulationSettings, run_simulations
from dnd5ecombat.monster_profiles import load_monster_profile
from dnd5ecombat.profile_catalog import CatalogItem, load_character_build
from dnd5ecombat.result_export import save_results, save_table_csv
from dnd5ecombat.roster_service import run_roster_simulations


ROOT = Path(__file__).resolve().parents[1]


class ResultExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = load_character_build(ROOT / "characters/tobias_wren.json")
        cls.monster = load_monster_profile(ROOT / "monsters/goblin.json")
        cls.settings = SimulationSettings(trials=2, seed=91, character_can_hide=True)

    def test_csv_companion_preserves_raw_results_and_effective_inputs(self):
        tables = run_simulations(self.build, self.monster, self.settings)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "attacks.csv"
            save_table_csv(tables.attacks, "attacks", path)
            record = json.loads(path.with_suffix(".csv.json").read_text(encoding="utf-8"))
            with path.open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.reader(source))
        self.assertEqual(record["result_format_version"], 1)
        table = record["tables"]["attacks"]
        self.assertEqual(rows[0], [column.title for column in tables.attacks.columns])
        self.assertEqual(table["rows"], [list(row) for row in tables.attacks.rows])
        metadata = table["metadata"]
        self.assertEqual(metadata["application_version"], __version__)
        self.assertEqual(metadata["settings"], asdict(self.settings))
        self.assertEqual(metadata["characters"][0]["profile"]["spell_slots"],
                         [list(slot) for slot in self.build.spell_slots])
        self.assertEqual(metadata["monsters"][0]["profile"]["max_hp"], self.monster.max_hp)
        self.assertEqual(table["note"], tables.attacks.note)

    def test_roster_identifies_duplicate_names_and_keeps_empty_pair_notes(self):
        harmless = replace(self.monster, attack_profiles=(), multiattack=())
        tables = run_roster_simulations(
            (CatalogItem("first.json", self.build), CatalogItem("second.json", self.build)),
            (CatalogItem("harmless.json", harmless),), self.settings, ("duels",),
        )
        with TemporaryDirectory() as directory:
            path = save_results({"duels": tables.duels}, Path(directory) / "results.json")
            table = json.loads(path.read_text(encoding="utf-8"))["tables"]["duels"]
        self.assertEqual(table["rows"], [])
        self.assertIn("cannot duel", table["details"])
        self.assertEqual([item["label"] for item in table["metadata"]["characters"]],
                         ["first.json", "second.json"])

    def test_cli_exports_single_pair_with_scenario_and_initiative_overrides(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            with redirect_stdout(io.StringIO()):
                status = main([
                    "--character-file", str(ROOT / "characters/tobias_wren.json"),
                    "--monster-file", str(ROOT / "monsters/goblin.json"),
                    "--scenario", str(ROOT / "scenarios/ranged-duel.json"),
                    "--trials", "2", "--seed", "17", "--initiative-bonus", "8",
                    "--enemy-initiative-bonus", "-2", "--duels",
                    "--export-results", str(path),
                ])
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(set(record["tables"]), {"duels"})
        metadata = record["tables"]["duels"]["metadata"]
        self.assertEqual(metadata["settings"]["seed"], 17)
        self.assertEqual(metadata["settings"]["trials"], 2)
        self.assertEqual(metadata["characters"][0]["profile"]["initiative_bonus"], 8)
        self.assertEqual(metadata["monsters"][0]["profile"]["initiative_bonus"], -2)

    def test_failed_replace_preserves_existing_export_and_cleans_temporary_file(self):
        table = run_simulations(self.build, self.monster, self.settings, ("attacks",)).attacks
        with TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            path.write_text("previous result", encoding="utf-8")
            with patch("dnd5ecombat.result_export.os.replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    save_results({"attacks": table}, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous result")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_cli_rejects_export_without_profiles(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--export-results", "results.json"])

    def test_cli_reports_export_failure(self):
        with redirect_stderr(io.StringIO()) as error, redirect_stdout(io.StringIO()):
            with patch("dnd5ecombat.cli_workflows.save_results", side_effect=OSError("locked")):
                status = main([
                    "--character-file", str(ROOT / "characters/tobias_wren.json"),
                    "--monster-file", str(ROOT / "monsters/goblin.json"),
                    "--trials", "1", "--export-results", "results.json",
                ])
        self.assertEqual(status, 2)
        self.assertIn("locked", error.getvalue())
