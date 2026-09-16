"""Monster-only profile editor for the desktop interface."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .models import Condition
from .save_action_editor import SaveActionEditor
from .turn_plan_editor import TurnPlanEditor
from .monster_profiles import monster_from_dict, monster_to_dict


ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
ATTACK_COLUMNS = (
    "Name",
    "To hit",
    "Damage dice",
    "Modifier",
    "Damage type",
    "Mode",
    "Reach",
    "Normal range",
    "Long range",
    "Unmodeled effects",
    "Condition",
    "Save DC",
    "Save ability",
    "Repeat save",
    "Immune tags",
    "Duration (turns)",
    "Uses per encounter",
    "Recharge (d6 minimum)",
    "Spell slot level (0 = cantrip)",
    "Action type", "Slot pool", "Allow upcast", "Extra dice per slot level",
)


class MonsterEditorDialog(QDialog):
    def __init__(self, monster=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit monster" if monster is not None else "New monster")
        self.resize(820, 620)
        self._build_ui()
        if monster is not None:
            self._populate(monster)

    def _spin(self, minimum, maximum, value=0):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def _build_ui(self):
        layout = QVBoxLayout(self)
        basics = QFormLayout()
        self.name_edit = QLineEdit()
        self.ac_spin = self._spin(1, 40, 10)
        self.hp_spin = self._spin(1, 100_000, 10)
        self.initiative_spin = self._spin(-20, 30)
        self.ruleset_edit = QLineEdit("D&D 5e")
        self.source_edit = QLineEdit()
        basics.addRow("Name", self.name_edit)
        basics.addRow("Armor class", self.ac_spin)
        basics.addRow("Maximum HP", self.hp_spin)
        basics.addRow("Initiative bonus", self.initiative_spin)
        basics.addRow("Ruleset", self.ruleset_edit)
        basics.addRow("Source URL", self.source_edit)
        layout.addLayout(basics)

        saves_group = QGroupBox("Saving throw bonuses")
        saves_layout = QHBoxLayout(saves_group)
        self.save_spins = {}
        for ability in ABILITIES:
            column = QVBoxLayout()
            column.addWidget(QLabel(ability.upper()))
            spin = self._spin(-20, 30)
            self.save_spins[ability] = spin
            column.addWidget(spin)
            saves_layout.addLayout(column)
        layout.addWidget(saves_group)

        defenses = QFormLayout()
        self.resistances_edit = QLineEdit()
        self.vulnerabilities_edit = QLineEdit()
        self.immunities_edit = QLineEdit()
        self.condition_immunities_edit = QLineEdit()
        self.creature_tags_edit = QLineEdit()
        self.undead_fortitude_check = QCheckBox("Undead Fortitude (2014)")
        self.multiattack_edit = QLineEdit()
        self.multiattack_edit.setPlaceholderText(
            "Ordered attack names, comma-separated; duplicates allowed"
        )
        defenses.addRow("Damage resistances", self.resistances_edit)
        defenses.addRow("Damage vulnerabilities", self.vulnerabilities_edit)
        defenses.addRow("Damage immunities", self.immunities_edit)
        defenses.addRow("Condition immunities", self.condition_immunities_edit)
        defenses.addRow("Creature tags", self.creature_tags_edit)
        defenses.addRow("Multiattack sequence", self.multiattack_edit)
        defenses.addRow(self.undead_fortitude_check)
        self.structured_trait_checks = {}
        for name in ("pack_tactics", "aggressive", "nimble_escape"):
            check = QCheckBox(name.replace("_", " ").title())
            self.structured_trait_checks[name] = check
            defenses.addRow(check)
        self.stealth_spin = self._spin(-20, 40)
        self.perception_spin = self._spin(0, 50, 10)
        defenses.addRow("Stealth bonus", self.stealth_spin)
        defenses.addRow("Passive Perception", self.perception_spin)
        layout.addLayout(defenses)

        attack_buttons = QHBoxLayout()
        attack_buttons.addWidget(QLabel("Attacks"))
        attack_buttons.addStretch(1)
        add_attack = QPushButton("Add attack")
        remove_attack = QPushButton("Remove selected")
        attack_buttons.addWidget(add_attack)
        attack_buttons.addWidget(remove_attack)
        layout.addLayout(attack_buttons)
        self.attacks = QTableWidget(0, len(ATTACK_COLUMNS))
        self.attacks.setHorizontalHeaderLabels(ATTACK_COLUMNS)
        self.attacks.horizontalHeaderItem(16).setToolTip("Blank for unlimited uses; duels only.")
        self.attacks.horizontalHeaderItem(17).setToolTip("2-6; one use, recovered on this d6 roll or higher. Duels only.")
        self.attacks.horizontalHeaderItem(15).setToolTip(
            "Positive number of affected creature turns; expires at end of final turn. "
            "Leave blank for no time limit. Repeat saves may end it earlier."
        )
        self.attacks.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        tabs = QTabWidget()
        tabs.addTab(self.attacks, "Attack rolls")
        self.save_action_editor = SaveActionEditor()
        tabs.addTab(self.save_action_editor, "Saving throws and slots")
        self.turn_plan_editor = TurnPlanEditor()
        tabs.addTab(self.turn_plan_editor, "Turn plans and riders")
        layout.addWidget(tabs, 1)
        add_attack.clicked.connect(self._add_attack)
        remove_attack.clicked.connect(self._remove_attacks)

        self.traits_edit = QPlainTextEdit()
        self.traits_edit.setPlaceholderText("One unmodeled trait per line")
        self.traits_edit.setMaximumHeight(90)
        layout.addWidget(QLabel("Unmodeled traits"))
        layout.addWidget(self.traits_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_attack(self, values=None):
        values = values or (
            "Attack",
            "0",
            "1d6",
            "0",
            "",
            "melee",
            "5",
            "",
            "",
            "",
            "",
            "",
            "",
            "false",
            "",
            "",
            "",
            "",
            "",
        )
        if len(values) < len(ATTACK_COLUMNS):
            values = tuple(values) + ("action", "spellcasting", "false", "")
        row = self.attacks.rowCount()
        self.attacks.insertRow(row)
        for column, value in enumerate(values):
            if column in (19, 20, 21):
                choice = QComboBox()
                choice.addItems({19: ("action", "bonus_action", "reaction"), 20: ("spellcasting", "pact", "any"), 21: ("false", "true")}[column])
                choice.setCurrentText(str(value).lower())
                self.attacks.setCellWidget(row, column, choice)
            elif column == 5:
                mode = QComboBox()
                mode.addItems(("melee", "ranged", "melee_or_ranged", ""))
                mode.setCurrentText(str(value))
                self.attacks.setCellWidget(row, column, mode)
            elif column == 10:
                condition = QComboBox()
                condition.addItems(("", *(item.value for item in Condition)))
                condition.setCurrentText(str(value))
                self.attacks.setCellWidget(row, column, condition)
            elif column == 13:
                repeat = QComboBox()
                repeat.addItems(("false", "true"))
                repeat.setCurrentText(str(value).lower())
                self.attacks.setCellWidget(row, column, repeat)
            else:
                self.attacks.setItem(row, column, QTableWidgetItem(str(value)))

    def _remove_attacks(self):
        rows = sorted(
            {index.row() for index in self.attacks.selectedIndexes()}, reverse=True
        )
        for row in rows:
            self.attacks.removeRow(row)

    def _populate(self, monster):
        data = monster_to_dict(monster)
        for name, check in self.structured_trait_checks.items():
            check.setChecked(data[name])
        self.stealth_spin.setValue(data["stealth_bonus"])
        self.perception_spin.setValue(data["passive_perception"])
        self.save_action_editor.populate(data)
        for plan in data["turn_plans"]:
            self.turn_plan_editor.add_plan(plan)
        self.name_edit.setText(data["name"])
        self.ac_spin.setValue(data["armor_class"])
        self.hp_spin.setValue(data["max_hp"])
        self.initiative_spin.setValue(data["initiative_bonus"])
        self.ruleset_edit.setText(data["ruleset"])
        self.source_edit.setText(data["source_url"])
        for ability, spin in self.save_spins.items():
            spin.setValue(data["saving_throw_bonuses"].get(ability, 0))
        self.resistances_edit.setText(", ".join(data["damage_resistances"]))
        self.vulnerabilities_edit.setText(", ".join(data["damage_vulnerabilities"]))
        self.immunities_edit.setText(", ".join(data["damage_immunities"]))
        self.condition_immunities_edit.setText(
            ", ".join(data["condition_immunities"])
        )
        self.creature_tags_edit.setText(", ".join(data["creature_tags"]))
        self.undead_fortitude_check.setChecked(data["undead_fortitude"])
        self.multiattack_edit.setText(", ".join(data["multiattack"]))
        for attack in data["attacks"]:
            effect = attack["condition_effect"] or {}
            self._add_attack(
                (
                    attack["name"],
                    attack["attack_bonus"],
                    attack["damage_dice"],
                    attack["damage_modifier"],
                    attack["damage_type"],
                    attack["attack_mode"],
                    attack["reach_feet"] or "",
                    attack["normal_range_feet"] or "",
                    attack["long_range_feet"] or "",
                    "\n".join(attack["unmodeled_effects"]),
                    effect.get("condition", ""),
                    effect.get("difficulty_class", ""),
                    effect.get("save_ability", ""),
                    str(effect.get("repeat_save_at_end_of_turn", False)).lower(),
                    ", ".join(effect.get("immune_creature_tags", ())),
                    effect.get("duration_turns") or "",
                    attack["limited_uses"] or "",
                    attack["recharge_min_roll"] or "",
                    "" if attack["spell_slot_level"] is None else attack["spell_slot_level"],
                    attack["action_type"], attack["spell_slot_pool"], str(attack["allow_upcast"]).lower(), attack["upcast_damage_dice"],
                )
            )
        self.traits_edit.setPlainText("\n".join(data["unmodeled_traits"]))

    def _cell_text(self, row, column):
        item = self.attacks.item(row, column)
        return item.text().strip() if item is not None else ""

    def monster(self):
        def optional_int(value):
            return int(value) if value else None

        attacks = []
        for row in range(self.attacks.rowCount()):
            mode = self.attacks.cellWidget(row, 5)
            condition_widget = self.attacks.cellWidget(row, 10)
            repeat_widget = self.attacks.cellWidget(row, 13)
            condition = (
                condition_widget.currentText() if condition_widget is not None else ""
            )
            condition_effect = None
            if condition:
                condition_effect = {
                    "difficulty_class": int(self._cell_text(row, 11)),
                    "save_ability": self._cell_text(row, 12),
                    "condition": condition,
                    "duration_turns": optional_int(self._cell_text(row, 15)),
                    "repeat_save_at_end_of_turn": (
                        repeat_widget.currentText() == "true"
                        if repeat_widget is not None
                        else False
                    ),
                    "immune_creature_tags": tuple(
                        value.strip()
                        for value in self._cell_text(row, 14).split(",")
                        if value.strip()
                    ),
                }
            attacks.append(
                {
                    "name": self._cell_text(row, 0),
                    "attack_bonus": int(self._cell_text(row, 1)),
                    "damage_dice": self._cell_text(row, 2),
                    "damage_modifier": int(self._cell_text(row, 3)),
                    "damage_type": self._cell_text(row, 4),
                    "attack_mode": mode.currentText() if mode is not None else "",
                    "reach_feet": optional_int(self._cell_text(row, 6)),
                    "normal_range_feet": optional_int(self._cell_text(row, 7)),
                    "long_range_feet": optional_int(self._cell_text(row, 8)),
                    "unmodeled_effects": tuple(
                        effect.strip()
                        for effect in self._cell_text(row, 9).splitlines()
                        if effect.strip()
                    ),
                    "condition_effect": condition_effect,
                    "limited_uses": optional_int(self._cell_text(row, 16)),
                    "recharge_min_roll": optional_int(self._cell_text(row, 17)),
                    "spell_slot_level": optional_int(self._cell_text(row, 18)),
                    "action_type": self.attacks.cellWidget(row, 19).currentText(),
                    "spell_slot_pool": self.attacks.cellWidget(row, 20).currentText(),
                    "allow_upcast": self.attacks.cellWidget(row, 21).currentText() == "true",
                    "upcast_damage_dice": self._cell_text(row, 22),
                }
            )
        def comma_values(widget):
            return tuple(
                value.strip()
                for value in widget.text().split(",")
                if value.strip()
            )

        spell_slots, save_actions = self.save_action_editor.values()
        slot_capacity, pact_capacity = self.save_action_editor.capacity_values()
        return monster_from_dict(
            {
                "name": self.name_edit.text().strip(),
                "armor_class": self.ac_spin.value(),
                "max_hp": self.hp_spin.value(),
                "initiative_bonus": self.initiative_spin.value(),
                "saving_throw_bonuses": {
                    ability: spin.value()
                    for ability, spin in self.save_spins.items()
                },
                "ruleset": self.ruleset_edit.text().strip(),
                "source_url": self.source_edit.text().strip(),
                "unmodeled_traits": tuple(
                    line.strip()
                    for line in self.traits_edit.toPlainText().splitlines()
                    if line.strip()
                ),
                "damage_resistances": comma_values(self.resistances_edit),
                "damage_vulnerabilities": comma_values(self.vulnerabilities_edit),
                "damage_immunities": comma_values(self.immunities_edit),
                "condition_immunities": comma_values(
                    self.condition_immunities_edit
                ),
                "creature_tags": comma_values(self.creature_tags_edit),
                "multiattack": comma_values(self.multiattack_edit),
                "undead_fortitude": self.undead_fortitude_check.isChecked(),
                "attacks": attacks,
                "turn_plans": self.turn_plan_editor.values(),
                **{name: check.isChecked() for name, check in self.structured_trait_checks.items()},
                "stealth_bonus": self.stealth_spin.value(),
                "passive_perception": self.perception_spin.value(),
                "pact_slots": self.save_action_editor.pact_values(),
                "spell_slots": spell_slots,
                "spell_slot_capacity": slot_capacity,
                "pact_slot_capacity": pact_capacity,
                "saving_throw_profiles": save_actions,
            }
        )

    def _validate_and_accept(self):
        try:
            self.monster()
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, "Invalid monster", str(error))
            return
        self.accept()
