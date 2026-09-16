"""Monster editor controls for save actions and starting spell slots."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox,
)


class SaveActionEditor(QWidget):
    fields = ("name", "difficulty_class", "save_ability", "damage_dice",
              "damage_modifier", "damage_type", "damage_on_success", "range_feet",
              "limited_uses", "recharge_min_roll", "spell_slot_level", "action_type",
              "unmodeled_effects", "spell_slot_pool", "allow_upcast", "upcast_damage_dice")
    choices = {
        "spell_slot_pool": ("spellcasting", "pact", "any"),
        "allow_upcast": ("false", "true"),
        "save_ability": ("str", "dex", "con", "int", "wis", "cha"),
        "damage_on_success": ("no_damage", "half_damage"),
        "action_type": ("action", "bonus_action", "reaction"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        slots = QHBoxLayout()
        slots.addWidget(QLabel("Starting slots"))
        self.slot_spins = {}
        for level in range(1, 10):
            slots.addWidget(QLabel(str(level)))
            spin = QSpinBox()
            spin.setRange(0, 100000)
            self.slot_spins[level] = spin
            slots.addWidget(spin)
        layout.addLayout(slots)
        capacities = QHBoxLayout()
        capacities.addWidget(QLabel("Full slot capacity"))
        self.capacity_spins = {}
        for level in range(1, 10):
            capacities.addWidget(QLabel(str(level)))
            spin = QSpinBox()
            spin.setRange(0, 100000)
            self.capacity_spins[level] = spin
            capacities.addWidget(spin)
        layout.addLayout(capacities)
        pact = QHBoxLayout()
        pact.addWidget(QLabel("Pact Magic: slot level / available slots"))
        self.pact_level = QSpinBox()
        self.pact_level.setRange(1, 5)
        self.pact_count = QSpinBox()
        self.pact_count.setRange(0, 100000)
        pact.addWidget(self.pact_level)
        pact.addWidget(self.pact_count)
        pact.addWidget(QLabel("Full Pact capacity"))
        self.pact_capacity = QSpinBox()
        self.pact_capacity.setRange(0, 100000)
        pact.addWidget(self.pact_capacity)
        layout.addLayout(pact)
        layout.addWidget(QLabel("Duel save actions need a slot level (0 for cantrip), uses, or recharge. Range is required for positioning."))
        buttons = QHBoxLayout()
        add = QPushButton("Add save action")
        remove = QPushButton("Remove selected save actions")
        buttons.addWidget(add)
        buttons.addWidget(remove)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, len(self.fields))
        self.table.setHorizontalHeaderLabels(("Name", "DC", "Save", "Damage dice", "Modifier",
            "Damage type", "On save", "Range (ft)", "Uses", "Recharge minimum", "Slot level",
            "Action type", "Unmodeled effects", "Slot pool", "Allow upcast", "Extra dice per slot level"))
        layout.addWidget(self.table)
        add.clicked.connect(lambda: self.add_action())
        remove.clicked.connect(self.remove_selected)

    def add_action(self, data=None):
        if data is None:
            data = dict(name="Save action", difficulty_class=12, save_ability="dex",
                        damage_dice="1d6", damage_modifier=0, damage_on_success="half_damage",
                        range_feet=30, limited_uses=1, action_type="action")
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, field in enumerate(self.fields):
            value = data.get(field)
            if field in self.choices:
                widget = QComboBox()
                widget.addItems(self.choices[field])
                widget.setCurrentText(str(value).lower() if isinstance(value, bool) else value or self.choices[field][0])
                self.table.setCellWidget(row, column, widget)
            else:
                if field == "unmodeled_effects":
                    value = "\n".join(value or ())
                self.table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))

    def remove_selected(self):
        for row in sorted({item.row() for item in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def pact_values(self):
        return ({str(self.pact_level.value()): self.pact_count.value()}
                if self.pact_count.value() or self.pact_capacity.value() else {})

    def capacity_values(self):
        ordinary = {str(level): spin.value() for level, spin in self.capacity_spins.items() if spin.value()}
        pact = {str(self.pact_level.value()): self.pact_capacity.value()} if self.pact_capacity.value() else {}
        return ordinary, pact

    def populate(self, data):
        for level, spin in self.capacity_spins.items():
            spin.setValue(data.get("spell_slot_capacity", data["spell_slots"]).get(str(level), 0))
        for level, count in data.get("pact_slot_capacity", {}).items():
            self.pact_level.setValue(int(level))
            self.pact_capacity.setValue(count)
        for level, count in data.get("pact_slots", {}).items():
            self.pact_level.setValue(int(level))
            self.pact_count.setValue(count)
        for level, spin in self.slot_spins.items():
            spin.setValue(data["spell_slots"].get(str(level), 0))
        for effect in data["saving_throw_profiles"]:
            self.add_action(effect)

    def values(self):
        actions = []
        for row in range(self.table.rowCount()):
            data = {}
            for column, field in enumerate(self.fields):
                if field in self.choices:
                    value = self.table.cellWidget(row, column).currentText()
                else:
                    value = self.table.item(row, column).text().strip()
                if field == "allow_upcast":
                    value = value == "true"
                elif field in {"difficulty_class", "damage_modifier"}:
                    value = int(value)
                elif field in {"range_feet", "limited_uses", "recharge_min_roll", "spell_slot_level"}:
                    value = int(value) if value else None
                elif field == "unmodeled_effects":
                    value = [line.strip() for line in value.splitlines() if line.strip()]
                data[field] = value
            actions.append(data)
        slots = {str(level): spin.value() for level, spin in self.slot_spins.items() if spin.value()}
        return slots, actions
