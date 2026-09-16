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
