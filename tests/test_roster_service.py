import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

from dnd5ecombat.cli_arguments import parse_args
from dnd5ecombat.cli_workflows import main
from dnd5ecombat.gui_service import (
    SimulationCancelled,
    SimulationSettings,
    run_simulations,
)
from dnd5ecombat.profile_catalog import CatalogItem, load_character_build
from dnd5ecombat.monster_profiles import load_monster_profile
from dnd5ecombat.roster_service import run_roster_simulations


ROOT = Path(__file__).resolve().parents[1]


class RosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.characters = tuple(
            CatalogItem(name, load_character_build(ROOT / "characters" / name))
            for name in ("tobias_wren.json", "amara_summerfield.json")
        )
        cls.monsters = tuple(
            CatalogItem(name, load_monster_profile(ROOT / "monsters" / name))
            for name in ("goblin.json", "wolf.json")
        )

    def test_every_pair_matches_independent_run_in_order(self):
        settings = SimulationSettings(trials=2, seed=19)
        progress = []
        combined = run_roster_simulations(
            self.characters,
            self.monsters,
            settings,
            progress_callback=lambda *args: progress.append(args),
        )
        for section in ("attacks", "turns", "saving_throws", "duels"):
            expected = []
            for character in self.characters:
                for monster in self.monsters:
                    single = run_simulations(
                        character.value, monster.value, settings, (section,)
                    )
                    expected.extend(
                        (character.label, monster.label, *row)
                        for row in getattr(single, section).rows
                    )
            self.assertEqual(getattr(combined, section).rows, tuple(expected))
        self.assertEqual(progress[-1], (16, 16, "complete"))
        self.assertEqual([item[0] for item in progress], list(range(17)))
        self.assertFalse(any(column.best for column in combined.attacks.columns))

    def test_cancellation_between_pairs_stops_roster(self):
        cancelled = False

        def progress(completed, total, section):
            nonlocal cancelled
            if completed == 1:
                cancelled = True

        with self.assertRaises(SimulationCancelled):
            run_roster_simulations(
                self.characters,
                self.monsters,
                SimulationSettings(trials=2),
                ("attacks",),
                progress,
                lambda: cancelled,
            )

    def test_empty_tables_keep_pair_notes(self):
        harmless = replace(
            self.monsters[0].value,
            attack_profiles=(),
            multiattack=(),
            saving_throw_profiles=(),
        )
        tables = run_roster_simulations(
            self.characters,
            (CatalogItem("Harmless", harmless),),
            SimulationSettings(trials=1),
            ("duels",),
        )
        self.assertEqual(tables.duels.rows, ())
        self.assertIn("cannot duel", tables.duels.details)
        self.assertIn(self.characters[1].label, tables.duels.details)
        self.assertIsNone(tables.attacks)

    def test_empty_rosters_and_invalid_sections_are_rejected(self):
        for characters, monsters, sections in (
            ((), self.monsters, ("attacks",)),
            (self.characters, (), ("attacks",)),
            (self.characters, self.monsters, ()),
            (self.characters, self.monsters, ("unknown",)),
        ):
            with self.assertRaises(ValueError):
                run_roster_simulations(
                    characters, monsters, SimulationSettings(), sections
                )

    def test_cli_runs_real_roster_and_deduplicates_paths(self):
        character = str(ROOT / "characters/tobias_wren.json")
        with redirect_stdout(io.StringIO()) as output:
            result = main(
                [
                    "--character-files",
                    character,
                    character,
                    "--monster-files",
                    str(ROOT / "monsters/goblin.json"),
                    str(ROOT / "monsters/wolf.json"),
                    "--duels",
                    "--trials",
                    "2",
                    "--scenario",
                    str(ROOT / "scenarios/ranged-duel.json"),
                ]
            )
        self.assertEqual(result, 0)
        self.assertIn("1 characters × 2 monsters", output.getvalue())
        self.assertIn("Character profile\tMonster profile", output.getvalue())
        self.assertIn("Wolf", output.getvalue())
        self.assertIn("Goblin", output.getvalue())

    def test_cli_rejects_conflicting_or_incomplete_selection(self):
        for options in (
            ["--character-files", "a.json"],
            [
                "--character-files",
                "a.json",
                "--character-file",
                "b.json",
                "--monster-file",
                "c.json",
            ],
            [
                "--character-files",
                "a.json",
                "--monster-files",
                "b.json",
                "--interactive",
            ],
        ):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(options)

    def test_cli_bad_profile_reports_error_before_simulating(self):
        with redirect_stderr(io.StringIO()) as error, redirect_stdout(io.StringIO()):
            result = main(
                [
                    "--character-files",
                    str(ROOT / "missing.json"),
                    "--monster-file",
                    str(ROOT / "monsters/goblin.json"),
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("missing.json", error.getvalue())
