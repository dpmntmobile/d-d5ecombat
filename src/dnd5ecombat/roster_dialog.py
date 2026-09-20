"""Choose a roster without changing the single-combat profile selectors."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class RosterDialog(QDialog):
    def __init__(
        self,
        characters,
        monsters,
        selected_character=None,
        selected_monster=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Compare multiple profiles")
        self.resize(760, 430)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Compare every checked character with every checked monster.")
        )
        lists = QHBoxLayout()
        self.character_list = self._list(characters, selected_character)
        self.monster_list = self._list(monsters, selected_monster)
        for title, widget in (
            ("Characters", self.character_list),
            ("Monsters", self.monster_list),
        ):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(widget)
            lists.addLayout(column)
        layout.addLayout(lists)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Compare")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.character_list.itemChanged.connect(self._update_summary)
        self.monster_list.itemChanged.connect(self._update_summary)
        self._update_summary()

    def _list(self, items, selected):
        widget = QListWidget()
        for item in items:
            row = QListWidgetItem(item.label, widget)
            row.setData(Qt.ItemDataRole.UserRole, item)
            row.setCheckState(
                Qt.CheckState.Checked if item == selected else Qt.CheckState.Unchecked
            )
        return widget

    def selection(self):
        return tuple(
            tuple(
                widget.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(widget.count())
                if widget.item(index).checkState() == Qt.CheckState.Checked
            )
            for widget in (self.character_list, self.monster_list)
        )

    def _update_summary(self):
        characters, monsters = self.selection()
        count = len(characters) * len(monsters)
        self.summary.setText(
            f"{len(characters)} characters × {len(monsters)} monsters = {count} comparisons"
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(count > 0)
