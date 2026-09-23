"""PySide6 desktop interface for the combat simulator."""

import os
import re
from html import escape
from pathlib import Path

from PySide6.QtCore import (
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Slot,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .gui_service import (
    SIMULATION_SECTIONS,
    SimulationSettings,
    TableData,
)
from .gui_results import ResultsBarChart, ResultsTableModel
from .gui_worker import SimulationWorker
from .monster_editor import MonsterEditorDialog
from .monster_profiles import save_monster_profile
from .profile_catalog import (
    discover_character_catalog,
    discover_monster_catalog,
    import_character_file,
    monster_profile_path,
)
from .storage_paths import PROJECT_DIR
from .scenario_persistence import load_scenario, save_scenario
from .roster_dialog import RosterDialog
from .result_export import save_table_csv
from .gui_guidance import GuidanceDialog


TAB_SECTIONS = ("attacks", "turns", "saving_throws", "duels")
SECTION_LABELS = {
    "attacks": "attacks",
    "turns": "turn plans",
    "saving_throws": "saving throws",
    "duels": "duels",
}


class ResultsPage(QWidget):
    navigate = Signal(str)

    def __init__(self, export_name, parent=None):
        super().__init__(parent)
        self.export_name = export_name
        self._table_data = TableData((), ())
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        self.note = QLabel("Run a simulation to populate this table.")
        self.note.setWordWrap(True)
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading.addWidget(self.note, 1)
        self.export_button = QPushButton("Export CSV…")
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("Save CSV and a .csv.json companion with results and run metadata.")
        self.export_button.clicked.connect(self.export_csv)
        heading.addWidget(self.export_button)
        layout.addLayout(heading)
        self.guidance = QLabel('Choose profiles and settings, then <a href="run">run a simulation</a>.')
        self.guidance.setWordWrap(True)
        self.guidance.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.guidance.linkActivated.connect(self.navigate.emit)
        layout.addWidget(self.guidance)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        splitter.addWidget(self.table)
        self.chart = ResultsBarChart()
        splitter.addWidget(self.chart)
        splitter.setSizes([430, 190])
        layout.addWidget(splitter, 1)
        self._model = None
        self._proxy = None

    def set_table_data(self, table_data):
        self._table_data = table_data
        self.note.setText(table_data.note)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setToolTip(table_data.details)
        self.export_button.setEnabled(bool(table_data.rows))
        if table_data.rows:
            self.guidance.clear()
        elif self.export_name == "saving-throw-results":
            self.guidance.setText(
                'No damaging save effects to compare. <a href="character">Choose a character</a> '
                'with a damaging save spell, or add it in Roll20, re-export, and '
                '<a href="import">import the character</a>. Check each pair\'s notes for roster results.'
            )
        elif self.export_name == "duel-results":
            self.guidance.setText(
                'No eligible duel actions. <a href="monster">Choose a monster</a> with an attack '
                'or supported save action; use Edit to add one. Check each pair\'s notes for roster results.'
            )
        else:
            self.guidance.setText('No results. <a href="character">Review the character</a> and <a href="run">run again</a>.')
        self._model = ResultsTableModel(table_data, self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self._proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table.setModel(self._proxy)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.chart.set_table_data(table_data)

    @Slot()
    def export_csv(self):
        if not self._table_data.rows:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export simulation results",
            f"{self.export_name}.csv",
            "CSV files (*.csv)",
        )
        if not filename:
            return
        try:
            save_table_csv(self._table_data, self.export_name, filename)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Export failed", str(error))


class CombatSimulatorWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("D&D 5e Combat Simulator")
        icon_path = PROJECT_DIR / "assets" / "app-icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1240, 820)
        self._thread = None
        self._worker = None
        self._settings = settings or QSettings("dnd5ecombat", "CombatSimulator")
        self._character_items = ()
        self._monster_items = ()
        self._catalog_issues = ()
        self._build_ui()
        self._refresh_catalogs(show_issues=False)
        self._restore_settings()
        self._selection_changed()

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        self.setCentralWidget(central)
        selection_group = QGroupBox("Combat setup")
        selection_layout = QVBoxLayout(selection_group)
        scenario_row = QHBoxLayout()
        self.load_scenario_button = QPushButton("Load scenario...")
        self.save_scenario_button = QPushButton("Save scenario...")
        scenario_row.addWidget(self.load_scenario_button)
        scenario_row.addWidget(self.save_scenario_button)
        scenario_row.addStretch(1)
        selection_layout.addLayout(scenario_row)
        self.load_scenario_button.clicked.connect(self._load_scenario)
        self.save_scenario_button.clicked.connect(self._save_scenario)
        selectors = QFormLayout()
        character_row = QHBoxLayout()
        self.character_combo = QComboBox()
        character_row.addWidget(self.character_combo, 1)
        self.import_button = QPushButton("Import…")
        self.refresh_button = QPushButton("Refresh")
        character_row.addWidget(self.import_button)
        character_row.addWidget(self.refresh_button)
        selectors.addRow("Character", character_row)
        monster_row = QHBoxLayout()
        self.monster_combo = QComboBox()
        monster_row.addWidget(self.monster_combo, 1)
        self.new_monster_button = QPushButton("New…")
        self.edit_monster_button = QPushButton("Edit…")
        monster_row.addWidget(self.new_monster_button)
        monster_row.addWidget(self.edit_monster_button)
        selectors.addRow("Monster", monster_row)
        selection_layout.addLayout(selectors)
        self.selection_summary = QLabel()
        self.selection_summary.setWordWrap(True)
        self.selection_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.selection_summary.linkActivated.connect(self._navigate)
        selection_layout.addWidget(self.selection_summary)
        self.catalog_warning = QLabel()
        self.catalog_warning.setStyleSheet("color: #b02a37;")
        self.catalog_warning.setWordWrap(True)
        self.catalog_warning.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.catalog_warning.linkActivated.connect(self._navigate)
        selection_layout.addWidget(self.catalog_warning)
        positioning = QHBoxLayout()
        self.positioning_check = QCheckBox("Duel positioning")
        positioning.addWidget(self.positioning_check)
        for field, label, default in (
            ("starting_distance_feet", "Starting distance", 30),
            ("character_speed_feet", "Character speed", 30),
            ("monster_speed_feet", "Monster speed", 30),
        ):
            spin = QSpinBox()
            spin.setRange(0, 100_000)
            spin.setSuffix(" ft")
            spin.setValue(default)
            setattr(self, field + "_spin", spin)
            positioning.addWidget(QLabel(label))
            positioning.addWidget(spin)
        selection_layout.addLayout(positioning)
        tactics = QHBoxLayout()
        self.tactical_checks = {}
        for field, label in (('character_ally_near_target', 'Character ally near target'), ('monster_ally_near_target', 'Monster ally near target'), ('character_can_hide', 'Character can hide'), ('monster_can_hide', 'Monster can hide')):
            check = QCheckBox(label)
            check.setToolTip("Explicit encounter assumption; ally must be within 5 feet of the target and not incapacitated. Hide needs concealment.")
            self.tactical_checks[field] = check
            tactics.addWidget(check)
        self.rest_combo = QComboBox()
        self.rest_combo.addItems(("none", "short", "long"))
        tactics.addWidget(QLabel("Rest before duel"))
        tactics.addWidget(self.rest_combo)
        selection_layout.addLayout(tactics)
        controls = QHBoxLayout()
        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(1, 10_000_000)
        self.trials_spin.setValue(10_000)
        self.trials_spin.setSingleStep(1_000)
        self.trials_spin.setGroupSeparatorShown(True)
        controls.addWidget(QLabel("Trials"))
        controls.addWidget(self.trials_spin)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-2_147_483_648, 2_147_483_647)
        self.seed_spin.setValue(42)
        controls.addWidget(QLabel("Seed"))
        controls.addWidget(self.seed_spin)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.workers_spin.setValue(1)
        controls.addWidget(QLabel("Workers"))
        controls.addWidget(self.workers_spin)
        self.advantage_check = QCheckBox("Advantage")
        self.disadvantage_check = QCheckBox("Disadvantage")
        controls.addWidget(self.advantage_check)
        controls.addWidget(self.disadvantage_check)
        controls.addStretch(1)
        self.run_scope_combo = QComboBox()
        self.run_scope_combo.addItem("All tabs", "all")
        self.run_scope_combo.addItem("Current tab", "current")
        controls.addWidget(self.run_scope_combo)
        self.run_button = QPushButton("Simulate")
        self.run_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.run_button)
        self.roster_button = QPushButton("Compare multiple...")
        self.roster_button.clicked.connect(self._choose_roster)
        controls.addWidget(self.roster_button)
        controls.addWidget(self.cancel_button)
        selection_layout.addLayout(controls)
        outer.addWidget(selection_group)
        self.tabs = QTabWidget()
        self.attack_page = ResultsPage("attack-results")
        self.turn_page = ResultsPage("turn-results")
        self.save_page = ResultsPage("saving-throw-results")
        self.duel_page = ResultsPage("duel-results")
        self.pages = {
            "attacks": self.attack_page,
            "turns": self.turn_page,
            "saving_throws": self.save_page,
            "duels": self.duel_page,
        }
        self.tabs.addTab(self.attack_page, "Attacks")
        for page in self.pages.values():
            page.navigate.connect(self._navigate)
        self.tabs.addTab(self.turn_page, "Turns")
        self.tabs.addTab(self.save_page, "Saving Throws")
        self.tabs.addTab(self.duel_page, "Duels")
        outer.addWidget(self.tabs, 1)
        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.hide()
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        status_row.addWidget(self.progress)
        outer.addLayout(status_row)
        self.character_combo.currentIndexChanged.connect(self._selection_changed)
        self.monster_combo.currentIndexChanged.connect(self._selection_changed)
        self.import_button.clicked.connect(self._import_character)
        self.new_monster_button.clicked.connect(self._new_monster)
        self.edit_monster_button.clicked.connect(self._edit_monster)
        self.refresh_button.clicked.connect(
            lambda: self._refresh_catalogs(show_issues=True)
        )
        self.run_button.clicked.connect(self._start_simulation)
        self.cancel_button.clicked.connect(self._cancel_simulation)

    def _catalog_source(self, combo):
        item = combo.currentData()
        return item.source if item is not None else ""

    def _select_source(self, combo, source):
        for index in range(combo.count()):
            item = combo.itemData(index)
            if item is not None and item.source == source:
                combo.setCurrentIndex(index)
                return True
        return False

    def _refresh_catalogs(self, show_issues=False, select_character=""):
        previous_character = select_character or self._catalog_source(self.character_combo)
        previous_monster = self._catalog_source(self.monster_combo)
        character_catalog = discover_character_catalog()
        monster_catalog = discover_monster_catalog()
        self._character_items = character_catalog.items
        self._monster_items = monster_catalog.items
        self._catalog_issues = character_catalog.issues + monster_catalog.issues
        self.character_combo.blockSignals(True)
        self.monster_combo.blockSignals(True)
        self.character_combo.clear()
        self.monster_combo.clear()
        for item in self._character_items:
            self.character_combo.addItem(item.label, item)
        for item in self._monster_items:
            self.monster_combo.addItem(item.label, item)
        self._select_source(self.character_combo, previous_character)
        self._select_source(self.monster_combo, previous_monster)
        self.character_combo.blockSignals(False)
        self.monster_combo.blockSignals(False)
        if self._catalog_issues:
            details = "\n".join(
                f"{Path(issue.path).name}: {issue.message}"
                for issue in self._catalog_issues
            )
            self.catalog_warning.setText(
                f'{len(self._catalog_issues)} invalid profile file(s). <a href="issues">Review errors and files</a>.'
            )
            self.catalog_warning.setToolTip(details)
            if show_issues:
                self._review_catalog_issues()
        else:
            self.catalog_warning.clear()
            self.catalog_warning.setToolTip("")
            if show_issues:
                self.status_label.setText("Character and monster lists refreshed")
        self._selection_changed()

    def _setting_controls(self):
        return {
            **{field: getattr(self, field + "_spin") for field in (
                "trials", "seed", "workers", "starting_distance_feet",
                "character_speed_feet", "monster_speed_feet",
            )},
            "rest_before_duel": self.rest_combo,
            "include_advantage": self.advantage_check,
            "include_disadvantage": self.disadvantage_check,
            **self.tactical_checks,
        }

    def _navigate(self, action):
        if self._thread is not None:
            return
        callbacks = {"issues": self._review_catalog_issues, "import": self._import_character,
                     "new_monster": self._new_monster}
        if action in callbacks:
            callbacks[action]()
            return
        controls = {"character": self.character_combo, "monster": self.monster_combo,
                    "run": self.run_button, **self._setting_controls()}
        control = controls.get(action)
        if control is not None:
            control.setFocus(Qt.FocusReason.OtherFocusReason)
            if isinstance(control, QSpinBox):
                control.selectAll()

    def _review_catalog_issues(self):
        if not self._catalog_issues:
            return
        GuidanceDialog(
            "Invalid profile files",
            "These files could not be loaded. Correct the reported field, then Refresh. "
            "For characters, correct the Roll20 sheet/export and import it again.\n\n" +
            "\n\n".join(f"{issue.path}\n{issue.message}" for issue in self._catalog_issues),
            files=tuple(issue.path for issue in self._catalog_issues),
            parent=self,
        ).exec()

    def _validation_error(self, title, error, files=()):
        message = str(error)
        actions = tuple(
            (field, "Review setting: " + field.replace("_", " "))
            for field in self._setting_controls()
            if re.search(r"\b" + re.escape(field) + r"\b", message)
        )
        GuidanceDialog(title, message, files=files, actions=actions,
                       navigate=self._navigate, parent=self).exec()

    @Slot()
    def _import_character(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import character", "", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            item = import_character_file(filename)
        except FileExistsError as error:
            answer = QMessageBox.question(
                self,
                "Replace character?",
                f"{error}\n\nReplace the existing file?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                item = import_character_file(filename, overwrite=True)
            except (OSError, TypeError, ValueError) as retry_error:
                self._validation_error("Import failed", retry_error, (filename,))
                return
        except (OSError, TypeError, ValueError) as error:
            self._validation_error("Import failed", error, (filename,))
            return
        self._refresh_catalogs(select_character=item.source)
        self.status_label.setText(f"Imported {item.value.name}")

    @Slot()
    def _new_monster(self):
        dialog = MonsterEditorDialog(parent=self)
        if not dialog.exec():
            return
        monster = dialog.monster()
        destination = monster_profile_path(monster.name)
        if destination.exists():
            answer = QMessageBox.question(
                self,
                "Replace monster?",
                f"{destination.name} already exists. Replace it?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            save_monster_profile(monster, destination)
        except OSError as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return
        self._refresh_catalogs()
        self._select_source(self.monster_combo, str(destination))
        self._selection_changed()
        self.status_label.setText(f"Saved {monster.name}")

    @Slot()
    def _edit_monster(self):
        item = self.monster_combo.currentData()
        if item is None:
            return
        dialog = MonsterEditorDialog(item.value, self)
        if not dialog.exec():
            return
        monster = dialog.monster()
        destination = monster_profile_path(Path(item.source).stem)
        try:
            save_monster_profile(monster, destination)
        except OSError as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return
        self._refresh_catalogs()
        self._select_source(self.monster_combo, str(destination))
        self._selection_changed()
        self.status_label.setText(f"Updated {monster.name}")

    @Slot()
    def _selection_changed(self):
        character_item = self.character_combo.currentData()
        monster_item = self.monster_combo.currentData()
        idle = self._thread is None
        self.edit_monster_button.setEnabled(idle and monster_item is not None)
        self.roster_button.setEnabled(idle and bool(self._character_items) and bool(self._monster_items))
        if character_item is None or monster_item is None:
            missing = []
            if character_item is None:
                missing.append('No valid characters. Export a character from Roll20, then <a href="import">Import character</a>.')
            if monster_item is None:
                missing.append('No valid monsters. <a href="new_monster">Create a monster</a> or add a monster JSON file and Refresh.')
            if self._catalog_issues:
                missing.append('<a href="issues">Review invalid profile files</a>.')
            self.selection_summary.setText("<br>".join(missing))
            self.run_button.setEnabled(False)
            return
        build = character_item.value
        monster = monster_item.value
        attacks = ", ".join(
            f"{attack.name} ({attack.attack_bonus:+d})"
            for attack in build.attack_profiles
        ) or "none"
        equipment = ", ".join(build.equipment) or "not specified"
        defenses = []
        if monster.damage_resistances:
            defenses.append("resists " + ", ".join(monster.damage_resistances))
        if monster.damage_vulnerabilities:
            defenses.append(
                "vulnerable to " + ", ".join(monster.damage_vulnerabilities)
            )
        if monster.undead_fortitude:
            defenses.append("Undead Fortitude")
        if monster.damage_immunities:
            defenses.append("immune to " + ", ".join(monster.damage_immunities))
        defense_text = "; ".join(defenses) or "no damage defenses"
        multiattack_text = (
            " + ".join(monster.multiattack)
            if monster.multiattack
            else "best single attack"
        )
        description = f" — {escape(build.description)}" if build.description else ""
        self.selection_summary.setText(
            f"<b>{escape(build.name)}</b>{description}<br>"
            f"AC {build.armor_class}; {build.max_hp} HP; initiative "
            f"{build.initiative_bonus:+d}; {build.attacks_per_action} attack(s)/action; "
            f"attacks: {escape(attacks)}; equipment: {escape(equipment)}.<br>"
            f"<b>{escape(monster.name)}</b>: AC {monster.armor_class}; {monster.max_hp} HP; "
            f"initiative {monster.initiative_bonus:+d}; "
            f"{len(monster.attack_profiles)} attack(s); {escape(defense_text)}; "
            f"turn sequence: {escape(multiattack_text)}."
        )
        self.run_button.setEnabled(self._thread is None)

    def _set_controls_enabled(self, enabled):
        for control in (
            self.character_combo,
            self.monster_combo,
            self.trials_spin,
            self.seed_spin,
            self.workers_spin,
            self.positioning_check,
            self.starting_distance_feet_spin,
            self.character_speed_feet_spin,
            self.monster_speed_feet_spin,
            self.advantage_check,
            self.disadvantage_check,
            self.run_scope_combo,
            self.import_button,
            self.refresh_button,
            self.new_monster_button,
            self.edit_monster_button,
            self.run_button,
            self.roster_button,
            self.load_scenario_button,
            self.save_scenario_button,
            self.rest_combo,
            *self.tactical_checks.values(),
        ):
            control.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)

    def _selected_sections(self):
        if self.run_scope_combo.currentData() == "current":
            return (TAB_SECTIONS[self.tabs.currentIndex()],)
        return SIMULATION_SECTIONS

    def _simulation_settings(self):
        return SimulationSettings(
            trials=self.trials_spin.value(),
            seed=self.seed_spin.value(),
            workers=self.workers_spin.value(),
            include_advantage=self.advantage_check.isChecked(),
            include_disadvantage=self.disadvantage_check.isChecked(),
            starting_distance_feet=(self.starting_distance_feet_spin.value()
                                    if self.positioning_check.isChecked() else None),
            character_speed_feet=self.character_speed_feet_spin.value(),
            monster_speed_feet=self.monster_speed_feet_spin.value(),
            **{field: check.isChecked() for field, check in self.tactical_checks.items()},
            rest_before_duel=self.rest_combo.currentText(),
        )

    def _apply_scenario_settings(self, settings):
        numeric = {
            field: getattr(settings, field)
            for field in ("trials", "seed", "workers", "character_speed_feet",
                          "monster_speed_feet", "starting_distance_feet")
            if getattr(settings, field) is not None
        }
        # Validate every value before changing any controls; never silently clamp.
        for field, value in numeric.items():
            if not -2_147_483_648 <= value <= 2_147_483_647:
                raise ValueError(f"{field}: value exceeds the desktop control's integer range")
        for field, value in numeric.items():
            spin = getattr(self, field + "_spin")
            spin.setRange(min(spin.minimum(), value), max(spin.maximum(), value))
            spin.setValue(value)
        self.positioning_check.setChecked(settings.starting_distance_feet is not None)
        self.advantage_check.setChecked(settings.include_advantage)
        self.disadvantage_check.setChecked(settings.include_disadvantage)
        for field, check in self.tactical_checks.items():
            check.setChecked(getattr(settings, field))
        self.rest_combo.setCurrentText(settings.rest_before_duel)

    @Slot()
    def _load_scenario(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load scenario settings", "", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            self._apply_scenario_settings(load_scenario(filename))
        except (OSError, ValueError, TypeError) as error:
            self._validation_error("Could not load scenario", error, (filename,))
            return
        self._save_settings()
        self.status_label.setText(f"Loaded scenario settings: {Path(filename).name}")

    @Slot()
    def _save_scenario(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save scenario settings", "scenario.json", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            save_scenario(self._simulation_settings(), filename)
        except (OSError, ValueError, TypeError) as error:
            self._validation_error("Could not save scenario", error)
            return
        self.status_label.setText(f"Saved scenario settings: {Path(filename).name}")

    @Slot()
    def _choose_roster(self):
        if self._thread is not None:
            return
        dialog = RosterDialog(
            self._character_items, self._monster_items,
            self.character_combo.currentData(), self.monster_combo.currentData(), self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run_simulation(roster=dialog.selection())

    @Slot()
    def _start_simulation(self):
        self._run_simulation()

    def _run_simulation(self, roster=None):
        character_item = self.character_combo.currentData()
        monster_item = self.monster_combo.currentData()
        if character_item is None or monster_item is None or self._thread is not None:
            return
        try:
            settings = self._simulation_settings()
        except (ValueError, TypeError) as error:
            self._validation_error("Check simulation settings", error)
            return
        sections = self._selected_sections()
        self._run_profile_items = (
            (character_item, monster_item) if roster is None else tuple(roster[0]) + tuple(roster[1])
        )
        self._thread = QThread(self)
        if roster is None:
            self._worker = SimulationWorker(
                character_item.value, monster_item.value, settings, sections
            )
        else:
            self._worker = SimulationWorker(*roster, settings, sections, roster=True)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._show_results)
        self._worker.cancelled.connect(self._show_cancelled)
        self._worker.failed.connect(self._show_error)
        self._worker.progress.connect(self._show_progress)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._simulation_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._save_settings()
        self._set_controls_enabled(False)
        self.progress.setRange(0, len(sections))
        self.progress.setValue(0)
        self.progress.show()
        self.status_label.setText("Starting simulations…")
        self._thread.start()

    @Slot()
    def _cancel_simulation(self):
        if self._worker is not None:
            self._worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Cancellation requested; waiting for active work to stop…"
            )

    @Slot(int, int, str)
    def _show_progress(self, completed, total, section):
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        if section != "complete":
            self.status_label.setText(
                f"Running {SECTION_LABELS.get(section, section)} "
                f"({completed + 1} of {total})…"
            )

    @Slot(object)
    def _show_results(self, tables):
        for section, page in self.pages.items():
            table_data = getattr(tables, section)
            if table_data is not None:
                page.set_table_data(table_data)
        self.status_label.setText("Simulation complete")

    @Slot()
    def _show_cancelled(self):
        self.status_label.setText("Simulation cancelled")

    @Slot(str)
    def _show_error(self, details):
        self.status_label.setText("Simulation failed")
        message = details.strip().splitlines()[-1] if details.strip() else "Unknown error"
        files = tuple(dict.fromkeys(
            item.source for item in getattr(self, "_run_profile_items", ()) if item.source
        ))
        self._validation_error(
            "Simulation failed", message + "\n\nReview the run's profiles and settings.\n\n" + details,
            files,
        )

    @Slot()
    def _simulation_finished(self):
        self._thread = None
        self._worker = None
        self.progress.hide()
        self._set_controls_enabled(True)
        self._selection_changed()

    def _setting_bool(self, key, default=False):
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes"}

    def _restore_settings(self):
        self.rest_combo.setCurrentText(self._settings.value("rest_before_duel", "none"))
        for field, check in self.tactical_checks.items():
            check.setChecked(self._setting_bool(field))
        self.positioning_check.setChecked(self._setting_bool("duel_positioning"))
        for field, default in (
            ("starting_distance_feet", 30), ("character_speed_feet", 30),
            ("monster_speed_feet", 30), ("trials", 10_000), ("seed", 42),
            ("workers", 1),
        ):
            spin = getattr(self, field + "_spin")
            value = int(self._settings.value(field, default))
            if spin.minimum() <= value <= 2_147_483_647:
                spin.setMaximum(max(spin.maximum(), value))
            spin.setValue(value)
        self.advantage_check.setChecked(self._setting_bool("advantage"))
        self.disadvantage_check.setChecked(self._setting_bool("disadvantage"))
        scope_index = self.run_scope_combo.findData(
            self._settings.value("run_scope", "all")
        )
        self.run_scope_combo.setCurrentIndex(max(0, scope_index))
        self.tabs.setCurrentIndex(int(self._settings.value("tab", 0)))
        self._select_source(
            self.character_combo, self._settings.value("character_source", "")
        )
        self._select_source(
            self.monster_combo, self._settings.value("monster_source", "")
        )
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _save_settings(self):
        self._settings.setValue("rest_before_duel", self.rest_combo.currentText())
        for field, check in self.tactical_checks.items():
            self._settings.setValue(field, check.isChecked())
        self._settings.setValue("duel_positioning", self.positioning_check.isChecked())
        for field in ("starting_distance_feet", "character_speed_feet", "monster_speed_feet"):
            self._settings.setValue(field, getattr(self, field + "_spin").value())
        self._settings.setValue("trials", self.trials_spin.value())
        self._settings.setValue("seed", self.seed_spin.value())
        self._settings.setValue("workers", self.workers_spin.value())
        self._settings.setValue("advantage", self.advantage_check.isChecked())
        self._settings.setValue(
            "disadvantage", self.disadvantage_check.isChecked()
        )
        self._settings.setValue("run_scope", self.run_scope_combo.currentData())
        self._settings.setValue("tab", self.tabs.currentIndex())
        self._settings.setValue(
            "character_source", self._catalog_source(self.character_combo)
        )
        self._settings.setValue(
            "monster_source", self._catalog_source(self.monster_combo)
        )
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.sync()

    def closeEvent(self, event: QCloseEvent):
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self,
                "Simulation running",
                "Cancel or wait for the current simulation before closing.",
            )
            event.ignore()
            return
        self._save_settings()
        super().closeEvent(event)


def launch_gui(argv=None):
    app = QApplication.instance() or QApplication(argv or [])
    app.setApplicationName("D&D 5e Combat Simulator")
    window = CombatSimulatorWindow()
    window.show()
    return app.exec()
