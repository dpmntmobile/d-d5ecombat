import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.gui_service import (
    SimulationCancelled,
    SimulationSettings,
    run_simulations,
)
from dnd5ecombat.profile_catalog import (
    PROJECT_DIR,
    discover_character_catalog,
    discover_characters,
    discover_monsters,
    import_character_file,
)


class GuiServiceTests(unittest.TestCase):
    def test_catalogs_load_project_profiles(self):
        characters = discover_characters()
        monsters = discover_monsters()

        self.assertTrue(any(item.value.name == "Tobias Wren" for item in characters))
        self.assertTrue(any(item.value.name == "Goblin" for item in monsters))

    def test_character_catalog_only_reads_characters_directory(self):
        characters = discover_characters()

        self.assertTrue(
            all(
                Path(item.source).parent == PROJECT_DIR / "characters"
                for item in characters
            )
        )
        self.assertGreaterEqual(
            {item.value.name for item in characters},
            {"Amara Summerfield", "Tobias Wren"},
        )

    def test_run_simulations_returns_all_result_tables(self):
        build = discover_characters()[0].value
        monster = next(
            item.value for item in discover_monsters() if item.value.name == "Goblin"
        )

        tables = run_simulations(
            build,
            monster,
            SimulationSettings(trials=10, seed=7),
        )

        self.assertTrue(tables.attacks.rows)
        self.assertTrue(tables.turns.rows)
        self.assertEqual(tables.saving_throws.rows, ())
        self.assertEqual(len(tables.duels.rows), 1)
        self.assertIn("evaluated 2 legal action", tables.duels.note.lower())
        self.assertIn("selected", tables.duels.note.lower())

    def test_advantage_adds_attack_and_turn_rows(self):
        build = discover_characters()[0].value
        monster = next(
            item.value for item in discover_monsters() if item.value.name == "Goblin"
        )

        normal = run_simulations(
            build,
            monster,
            SimulationSettings(trials=2, seed=1),
        )
        with_advantage = run_simulations(
            build,
            monster,
            SimulationSettings(trials=2, seed=1, include_advantage=True),
        )

        self.assertGreater(len(with_advantage.attacks.rows), len(normal.attacks.rows))
        self.assertGreater(len(with_advantage.turns.rows), len(normal.turns.rows))

    def test_selective_run_only_populates_requested_table(self):
        build = discover_characters()[0].value
        monster = discover_monsters()[0].value
        progress = []

        tables = run_simulations(
            build,
            monster,
            SimulationSettings(trials=2, seed=1),
            sections=("attacks",),
            progress_callback=lambda *values: progress.append(values),
        )

        self.assertIsNotNone(tables.attacks)
        self.assertIsNone(tables.turns)
        self.assertIsNone(tables.saving_throws)
        self.assertIsNone(tables.duels)
        self.assertEqual(progress, [(0, 1, "attacks"), (1, 1, "complete")])

    def test_cancelled_run_stops_before_work(self):
        build = discover_characters()[0].value
        monster = discover_monsters()[0].value

        with self.assertRaises(SimulationCancelled):
            run_simulations(
                build,
                monster,
                SimulationSettings(trials=2),
                is_cancelled=lambda: True,
            )

    def test_catalog_reports_invalid_character_files(self):
        with TemporaryDirectory() as directory:
            characters = Path(directory) / "characters"
            characters.mkdir()
            (characters / "broken.json").write_text("not json", encoding="utf-8")

            catalog = discover_character_catalog(directory)

        self.assertEqual(catalog.items, ())
        self.assertEqual(len(catalog.issues), 1)
        self.assertEqual(Path(catalog.issues[0].path).name, "broken.json")

    def test_import_character_copies_valid_file_into_catalog(self):
        source = PROJECT_DIR / "tests" / "fixtures" / "test_roll20.json"
        with TemporaryDirectory() as directory:
            item = import_character_file(source, project_dir=directory)
            destination = Path(item.source)
            catalog = discover_character_catalog(directory)

            self.assertTrue(destination.exists())
            self.assertEqual(destination.parent.name, "characters")
            self.assertEqual(item.value.name, "Ovehaw Ugijo")
            self.assertEqual(len(catalog.items), 1)


if __name__ == "__main__":
    unittest.main()
