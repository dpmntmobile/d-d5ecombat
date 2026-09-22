import csv
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None

if PYSIDE_AVAILABLE:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication

    from dnd5ecombat.desktop_gui import (
        CombatSimulatorWindow,
        ResultsPage,
        ResultsTableModel,
        SimulationWorker,
    )
    from dnd5ecombat.gui_service import SimulationSettings, TableColumn, TableData
    from dnd5ecombat.monster_editor import MonsterEditorDialog
    from dnd5ecombat.profile_catalog import discover_characters, discover_monsters


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 is not installed")
class DesktopGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_scenario_buttons_round_trip_settings_and_keep_profile_selection(self):
        from dnd5ecombat.scenario_persistence import load_scenario

        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = CombatSimulatorWindow(settings=settings)
            self.addCleanup(window.close)
            expected = SimulationSettings(
                trials=13, seed=5, workers=2, include_advantage=True,
                starting_distance_feet=90, character_speed_feet=20,
                monster_speed_feet=45, character_can_hide=True,
                monster_ally_near_target=True, rest_before_duel="short",
            )
            window._apply_scenario_settings(expected)
            path = str(Path(directory) / "scenario.json")
            with patch("dnd5ecombat.desktop_gui.QFileDialog.getSaveFileName", return_value=(path, "")):
                window._save_scenario()
            self.assertEqual(load_scenario(path), expected)
            sources = (window._catalog_source(window.character_combo), window._catalog_source(window.monster_combo))
            window._apply_scenario_settings(SimulationSettings())
            with patch("dnd5ecombat.desktop_gui.QFileDialog.getOpenFileName", return_value=(path, "")):
                window._load_scenario()
            self.assertEqual(window._simulation_settings(), expected)
            self.assertEqual(sources, (window._catalog_source(window.character_combo), window._catalog_source(window.monster_combo)))
            window._set_controls_enabled(False)
            self.assertFalse(window.load_scenario_button.isEnabled())
            self.assertFalse(window.save_scenario_button.isEnabled())
            self.assertFalse(window.rest_combo.isEnabled())

    def test_loaded_settings_above_initial_gui_limits_survive_restart(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = CombatSimulatorWindow(settings=settings)
            expected = SimulationSettings(trials=10_000_001, workers=256, starting_distance_feet=100_001)
            window._apply_scenario_settings(expected)
            window.close()
            restored = CombatSimulatorWindow(settings=settings)
            self.assertEqual(restored._simulation_settings(), expected)
            restored.close()

    def test_invalid_scenario_leaves_gui_settings_unchanged(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = CombatSimulatorWindow(settings=settings)
            self.addCleanup(window.close)
            before = window._simulation_settings()
            path = Path(directory) / "bad.json"
            path.write_text('{"settings": {"trials": 0}}', encoding="utf-8")
            with patch("dnd5ecombat.desktop_gui.QFileDialog.getOpenFileName", return_value=(str(path), "")), patch("dnd5ecombat.desktop_gui.QMessageBox.critical") as error:
                window._load_scenario()
            error.assert_called_once()
            self.assertEqual(window._simulation_settings(), before)
            with self.assertRaisesRegex(ValueError, "seed"):
                window._apply_scenario_settings(SimulationSettings(trials=5, seed=2**40))
            self.assertEqual(window._simulation_settings(), before)

    def test_monster_editor_preserves_and_can_disable_undead_fortitude(self):
        from dnd5ecombat.monster_profiles import load_monster_profile

        zombie = load_monster_profile(Path(__file__).parents[1] / "monsters/zombie.json")
        dialog = MonsterEditorDialog(zombie)
        self.assertTrue(dialog.undead_fortitude_check.isChecked())
        self.assertEqual(dialog.monster(), zombie)
        dialog.undead_fortitude_check.setChecked(False)
        self.assertFalse(dialog.monster().undead_fortitude)
        dialog.close()

    def test_monster_editor_preserves_and_edits_attack_resources(self):
        from dataclasses import replace
        from dnd5ecombat.models import TargetProfile, AttackProfile, DamageDice
        from PySide6.QtWidgets import QTableWidgetItem

        attack = AttackProfile("Burst", 4, (DamageDice(1, 6),), limited_uses=2)
        monster = TargetProfile("Monster", 12, 20, attack_profiles=(attack,))
        dialog = MonsterEditorDialog(monster)
        self.assertEqual(dialog.monster().attack_profiles, monster.attack_profiles)
        dialog.attacks.setItem(0, 16, QTableWidgetItem(""))
        dialog.attacks.setItem(0, 17, QTableWidgetItem("5"))
        self.assertEqual(
            dialog.monster().attack_profiles,
            (replace(attack, limited_uses=None, recharge_min_roll=5),),
        )
        dialog.close()

    def test_duel_positioning_settings_are_restored_and_disabled_during_runs(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = CombatSimulatorWindow(settings=settings)
            window.positioning_check.setChecked(True)
            window.starting_distance_feet_spin.setValue(90)
            window.character_speed_feet_spin.setValue(25)
            window.monster_speed_feet_spin.setValue(40)
            window._save_settings()
            window._set_controls_enabled(False)
            self.assertFalse(window.starting_distance_feet_spin.isEnabled())
            self.assertFalse(window.positioning_check.isEnabled())
            window.close()
            restored = CombatSimulatorWindow(settings=settings)
            self.assertTrue(restored.positioning_check.isChecked())
            self.assertEqual(restored.starting_distance_feet_spin.value(), 90)
            self.assertEqual(restored.character_speed_feet_spin.value(), 25)
            self.assertEqual(restored.monster_speed_feet_spin.value(), 40)
            restored.close()

    def test_best_result_is_highlighted(self):
        table = TableData(
            (TableColumn("Name"), TableColumn("Score", "float", best="min")),
            (("slower", 2.0), ("faster", 1.0)),
        )
        model = ResultsTableModel(table)

        normal = model.index(0, 1)
        best = model.index(1, 1)

        self.assertIsNone(model.data(normal, Qt.ItemDataRole.BackgroundRole))
        self.assertIsNotNone(model.data(best, Qt.ItemDataRole.BackgroundRole))

    def test_csv_export_writes_headers_and_raw_values(self):
        table = TableData(
            (TableColumn("Name"), TableColumn("Rate", "percent")),
            (("Tobias", 0.75),),
        )
        page = ResultsPage("results")
        page.set_table_data(table)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "results.csv"
            with patch.object(
                __import__(
                    "dnd5ecombat.desktop_gui", fromlist=["QFileDialog"]
                ).QFileDialog,
                "getSaveFileName",
                return_value=(str(destination), "CSV files (*.csv)"),
            ):
                page.export_csv()
            self.assertTrue(destination.with_suffix(".csv.json").is_file())
            with open(destination, "r", encoding="utf-8-sig", newline="") as source:
                rows = tuple(csv.reader(source))

        self.assertEqual(
            tuple(tuple(row) for row in rows),
            (("Name", "Rate"), ("Tobias", "0.75")),
        )

    def test_settings_are_restored(self):
        with TemporaryDirectory() as directory:
            filename = str(Path(directory) / "settings.ini")
            first = CombatSimulatorWindow(
                QSettings(filename, QSettings.Format.IniFormat)
            )
            first.trials_spin.setValue(123)
            first.seed_spin.setValue(99)
            first._save_settings()
            first.deleteLater()

            second = CombatSimulatorWindow(
                QSettings(filename, QSettings.Format.IniFormat)
            )
            self.assertEqual(second.trials_spin.value(), 123)
            self.assertEqual(second.seed_spin.value(), 99)
            second.deleteLater()

    def test_worker_honors_cancellation_before_start(self):
        worker = SimulationWorker(
            discover_characters()[0].value,
            discover_monsters()[0].value,
            SimulationSettings(trials=2),
            ("attacks",),
        )
        events = []
        worker.cancelled.connect(lambda: events.append("cancelled"))
        worker.request_cancel()

        worker.run()

        self.assertEqual(events, ["cancelled"])

    def test_roster_dialog_requires_both_sides_and_returns_checked_profiles(self):
        from dnd5ecombat.roster_dialog import RosterDialog
        from PySide6.QtWidgets import QDialogButtonBox

        characters, monsters = discover_characters()[:2], discover_monsters()[:2]
        dialog = RosterDialog(characters, monsters)
        button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(button.isEnabled())
        for widget in (dialog.character_list, dialog.monster_list):
            for index in range(widget.count()):
                widget.item(index).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(button.isEnabled())
        self.assertEqual(dialog.selection(), (characters, monsters))
        self.assertIn("4 comparisons", dialog.summary.text())
        dialog.close()

    def test_roster_worker_returns_combined_tables_and_honors_cancel(self):
        worker = SimulationWorker(
            discover_characters()[:2], discover_monsters()[:2],
            SimulationSettings(trials=1), ("attacks",), roster=True,
        )
        results, cancelled = [], []
        worker.succeeded.connect(results.append)
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.run()
        self.assertEqual(len(results), 1)
        self.assertEqual(len({row[:2] for row in results[0].attacks.rows}), 4)
        worker.request_cancel()
        worker.run()
        self.assertEqual(cancelled, [True])
        self.assertEqual(len(results), 1)

    def test_compare_multiple_button_dispatches_selected_roster(self):
        from PySide6.QtWidgets import QDialog

        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            window = CombatSimulatorWindow(settings=settings)
            roster = (window._character_items[:2], window._monster_items[:2])
            with patch("dnd5ecombat.desktop_gui.RosterDialog") as dialog, patch.object(window, "_run_simulation") as run:
                dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
                dialog.return_value.selection.return_value = roster
                window.roster_button.click()
                run.assert_called_once_with(roster=roster)
                run.reset_mock()
                window.run_button.click()
                run.assert_called_once_with()
            window._set_controls_enabled(False)
            self.assertFalse(window.roster_button.isEnabled())
            window.close()

    def test_monster_editor_preserves_new_conditions_and_duration(self):
        from dataclasses import replace
        from PySide6.QtWidgets import QTableWidgetItem
        from dnd5ecombat.models import Condition, SavingThrowConditionEffect

        original = discover_monsters()[0].value
        for condition in Condition:
            effect = SavingThrowConditionEffect(
                13, "con", condition, repeat_save_at_end_of_turn=True, duration_turns=3,
            )
            monster = replace(original, attack_profiles=(
                replace(original.attack_profiles[0], condition_effect=effect),
            ), multiattack=())
            dialog = MonsterEditorDialog(monster)
            self.assertEqual(dialog.monster(), monster)
            dialog.attacks.setItem(0, 15, QTableWidgetItem("2"))
            self.assertEqual(dialog.monster().attack_profiles[0].condition_effect.duration_turns, 2)
            dialog.attacks.setItem(0, 15, QTableWidgetItem(""))
            self.assertIsNone(dialog.monster().attack_profiles[0].condition_effect.duration_turns)
            dialog.attacks.setItem(0, 15, QTableWidgetItem("0"))
            with self.assertRaises(ValueError):
                dialog.monster()
            dialog.deleteLater()

    def test_monster_editor_round_trips_existing_profile(self):
        original = discover_monsters()[0].value
        dialog = MonsterEditorDialog(original)

        edited = dialog.monster()

        self.assertEqual(edited, original)
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
