"""Desktop party selection and cancellable background simulations."""

import json
from threading import Event
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from .party_combat import (
    MonsterGroup,
    PartyBattle,
    battle_report,
    load_battle,
    save_battle,
    save_battle_results,
    simulate_party_battle,
)
from .profile_catalog import discover_character_catalog, discover_monster_catalog


class BattleWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, battle, trials, seed, rounds, parent=None):
        super().__init__(parent)
        self.battle, self.trials, self.seed, self.rounds = battle, trials, seed, rounds
        self.cancelled = Event()

    def run(self):
        try:
            result = simulate_party_battle(
                self.battle, self.trials, self.seed, self.rounds, self.cancelled.is_set
            )
            self.completed.emit(battle_report(self.battle, result, self.seed, self.rounds))
        except Exception as error:
            self.failed.emit(str(error))


class PartyBattleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Party versus encounter")
        self.resize(700, 700)
        self.worker = None
        self.loaded_battle = None
        self.loaded_references = None
        self.result_report = None
        self.characters = discover_character_catalog().items
        self.monsters = discover_monster_catalog().items
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Set counts for party members and monster types.\n"
                "Shared initiative, abstract positioning; attacks retarget the first living opponent."
            )
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        self.character_counts, self.monster_counts = [], []
        for title, items, counts in (
            ("Party", self.characters, self.character_counts),
            ("Encounter", self.monsters, self.monster_counts),
        ):
            form.addRow(QLabel(title))
            for item in items:
                spin = QSpinBox()
                spin.setRange(0, 100)
                spin.setAccessibleName(f"{title}: {item.label} count")
                spin.valueChanged.connect(self.selection_changed)
                counts.append(spin)
                form.addRow(item.label, spin)
        self.trials, self.seed, self.rounds = QSpinBox(), QSpinBox(), QSpinBox()
        for title, spin, low, high, value in (
            ("Trials", self.trials, 1, 1000000, 1000),
            ("Seed", self.seed, -2147483647, 2147483647, 42),
            ("Round limit (draw)", self.rounds, 1, 10000, 100),
        ):
            spin.setRange(low, high)
            spin.setValue(value)
            form.addRow(title, spin)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.composition = QLabel()
        self.composition.setWordWrap(True)
        layout.addWidget(self.composition)
        row = QHBoxLayout()
        self.run_button = QPushButton("Simulate battle")
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save battle...")
        self.load_button = QPushButton("Load battle...")
        self.export_button = QPushButton("Export results...")
        self.export_button.setEnabled(False)
        for button, callback in (
            (self.run_button, self.start_battle),
            (self.cancel_button, self.cancel),
            (self.save_button, self.save),
            (self.load_button, self.load),
            (self.export_button, self.export_results),
        ):
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.set_running(False)
        self.update_composition()

    def selection_changed(self):
        self.loaded_battle = None
        self.loaded_references = None
        self.save_button.setEnabled(not (self.worker and self.worker.isRunning()))
        self.update_composition()

    def update_composition(self):
        if self.loaded_battle:
            party = [member.name for member in self.loaded_battle.party]
            encounter = [f"{g.count} x {g.profile.name}" for g in self.loaded_battle.encounter]
            source = "Loaded battle (change counts to use catalog)"
        else:
            chars, groups = self.selection()
            party = [item.label for item in chars]
            encounter = [f"{count} x {item.label}" for item, count in groups]
            source = "Catalog selection"
        self.composition.setText(
            f"Next run: {source}\nParty: {', '.join(party) or 'none'}"
            f"\nEncounter: {', '.join(encounter) or 'none'}"
        )

    def selection(self):
        chars = [
            item
            for item, count in zip(self.characters, self.character_counts)
            for _ in range(count.value())
        ]
        groups = [
            (item, count.value())
            for item, count in zip(self.monsters, self.monster_counts)
            if count.value()
        ]
        return chars, groups

    def start_battle(self):
        try:
            chars, groups = self.selection()
            battle = self.loaded_battle or PartyBattle(
                tuple(i.value for i in chars),
                tuple(MonsterGroup(i.value, count) for i, count in groups),
            )
            self.worker = BattleWorker(
                battle,
                self.trials.value(),
                self.seed.value(),
                self.rounds.value(),
                self,
            )
            self.worker.completed.connect(self.show_results)
            self.worker.failed.connect(self.output.setPlainText)
            self.worker.finished.connect(lambda: self.set_running(False))
            self.result_report = None
            self.set_running(True)
            self.output.setPlainText("Simulating...")
            self.worker.start()
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, "Invalid battle", str(error))

    def set_running(self, running):
        for button in (self.run_button, self.load_button, self.save_button):
            button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.export_button.setEnabled(not running and self.result_report is not None)
        for spin in (*self.character_counts, *self.monster_counts,
                     self.trials, self.seed, self.rounds):
            spin.setEnabled(not running)

    def show_results(self, report):
        self.result_report = report
        party = ", ".join(member["name"] for member in report["composition"]["party"])
        encounter = ", ".join(
            f"{group['count']} x {group['profile']['name']}"
            for group in report["composition"]["encounter"]
        )
        self.output.setPlainText(
            f"Completed {report['trials']:,} trials · Seed {report['seed']} · "
            f"Round limit {report['max_rounds_per_trial']}\n"
            f"Party: {party}\nEncounter: {encounter}\n\n"
            f"Party wins: {report['party_win_rate']:.1%}\n"
            f"Encounter wins: {report['encounter_win_rate']:.1%}\n"
            f"Draws: {report['draw_rate']:.1%}\n"
            f"Average rounds: {report['average_rounds']:.2f}\n\n"
            f"Party — average HP: {report['average_party_hp']:.2f}; "
            f"survivors: {report['average_party_survivors']:.2f}\n"
            f"Encounter — average HP: {report['average_encounter_hp']:.2f}; "
            f"survivors: {report['average_encounter_survivors']:.2f}\n"
            "Averages include all trials."
        )

    def export_results(self):
        if self.result_report is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export battle results", "battle-results.json", "JSON (*.json)"
        )
        if path:
            try:
                save_battle_results(self.result_report, path)
            except (OSError, TypeError, ValueError) as error:
                QMessageBox.warning(self, "Could not export results", str(error))

    def cancel(self):
        if self.worker:
            self.worker.cancelled.set()

    def save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save battle", "party-battle.json", "JSON (*.json)"
        )
        if path:
            try:
                chars, groups = self.selection()
                references = self.loaded_references or (
                    [i.source for i in chars],
                    [(i.source, n) for i, n in groups],
                )
                save_battle(path, *references)
            except (OSError, TypeError, ValueError) as error:
                QMessageBox.warning(self, "Could not save battle", str(error))

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load battle", "", "JSON (*.json)")
        if path:
            try:
                battle = load_battle(path)
                self.loaded_battle = battle
                from pathlib import Path

                source = Path(path)
                data = json.loads(source.read_text(encoding="utf-8"))
                self.loaded_references = (
                    [source.parent / p for p in data["party"]],
                    [
                        (source.parent / g["monster"], g["count"])
                        for g in data["encounter"]
                    ],
                )
                self.update_composition()
                self.output.setPlainText(
                    "Loaded battle (change counts to return to catalog selection):\n"
                    + "Party: "
                    + ", ".join(c.name for c in battle.party)
                    + "\nEncounter: "
                    + ", ".join(
                        f"{g.count} x {g.profile.name}" for g in battle.encounter
                    )
                )
            except (OSError, TypeError, ValueError) as error:
                QMessageBox.warning(self, "Could not load battle", str(error))

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel()
            event.ignore()
        else:
            super().closeEvent(event)
