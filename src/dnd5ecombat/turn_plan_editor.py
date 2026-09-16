"""Monster attack-plan and once-per-turn rider controls."""

from copy import deepcopy

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
)

from .dice_parser import extract_damage_dice


class TurnPlanEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Action attacks first, then one bonus attack. Rider positions start at 1."
            )
        )
        buttons = QHBoxLayout()
        add = QPushButton("Add turn plan")
        remove = QPushButton("Remove selected plans")
        buttons.addWidget(add)
        buttons.addWidget(remove)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            (
                "Name",
                "Attack names (comma-separated)",
                "First-hit rider",
                "Rider dice",
                "Eligible positions",
                "Requires advantage",
                "Nearby ally also qualifies",
            )
        )
        layout.addWidget(self.table)
        self.originals = []
        add.clicked.connect(lambda: self.add_plan())
        remove.clicked.connect(self.remove_selected)

    def add_plan(self, data=None):
        data = deepcopy(data or dict(name="Turn plan", attacks=[]))
        self.originals.append(data)
        bonus = data.get("first_hit_bonus_damage") or {}
        values = (
            data["name"],
            ", ".join(s["attack_name"] for s in data["attacks"]),
            bonus.get("name", ""),
            "+".join(
                f"{d['number']}d{d['sides']}" for d in bonus.get("damage_dice", ())
            ),
            ", ".join(str(i + 1) for i in bonus.get("eligible_attack_indices", ())),
            str(bonus.get("requires_advantage", False)).lower(),
            str(bonus.get("allows_nearby_ally", False)).lower(),
        )
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate(values):
            if column >= 5:
                choice = QComboBox()
                choice.addItems(("false", "true"))
                choice.setCurrentText(value)
                self.table.setCellWidget(row, column, choice)
            else:
                self.table.setItem(row, column, QTableWidgetItem(value))

    def remove_selected(self):
        for row in sorted(
            {i.row() for i in self.table.selectedIndexes()}, reverse=True
        ):
            self.table.removeRow(row)
            self.originals.pop(row)

    def values(self):
        plans = []
        for row, original in enumerate(self.originals):

            def text(col):
                return self.table.item(row, col).text().strip()

            names = [name.strip() for name in text(1).split(",") if name.strip()]
            attacks = []
            for index, name in enumerate(names):
                old = (
                    original["attacks"][index]
                    if index < len(original["attacks"])
                    else {}
                )
                scenario = (
                    deepcopy(old)
                    if old.get("attack_name") == name
                    else dict(name=name, attack_name=name)
                )
                attacks.append(scenario)
            bonus = None
            if text(2) or text(3):
                bonus = dict(
                    name=text(2),
                    damage_dice=[
                        dict(number=d.number, sides=d.sides)
                        for d in extract_damage_dice(text(3))
                    ],
                    eligible_attack_indices=[
                        int(i.strip()) - 1 for i in text(4).split(",") if i.strip()
                    ],
                    requires_advantage=self.table.cellWidget(row, 5).currentText()
                    == "true",
                    allows_nearby_ally=self.table.cellWidget(row, 6).currentText()
                    == "true",
                )
            plans.append(
                dict(name=text(0), attacks=attacks, first_hit_bonus_damage=bonus)
            )
        return plans
