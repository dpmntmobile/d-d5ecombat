"""Reusable Qt models and charts for simulation result tables."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from .gui_service import TableData


def format_table_value(value, kind):
    if kind == "percent":
        return f"{value:.1%}"
    if kind == "float":
        return f"{value:.3f}"
    if kind == "signed":
        return f"{value:+d}"
    if kind == "integer":
        return f"{value:,}"
    return str(value)


class ResultsTableModel(QAbstractTableModel):
    def __init__(self, table_data=None, parent=None):
        super().__init__(parent)
        self._table_data = table_data or TableData((), ())
        self._best_cells = self._find_best_cells()

    def _find_best_cells(self):
        best_cells = set()
        for column_index, column in enumerate(self._table_data.columns):
            if column.best not in {"min", "max"} or not self._table_data.rows:
                continue
            values = [row[column_index] for row in self._table_data.rows]
            best_value = min(values) if column.best == "min" else max(values)
            best_cells.update(
                (row_index, column_index)
                for row_index, value in enumerate(values)
                if value == best_value
            )
        return best_cells

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._table_data.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._table_data.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self._table_data.rows[index.row()][index.column()]
        column = self._table_data.columns[index.column()]
        is_best = (index.row(), index.column()) in self._best_cells
        if role == Qt.ItemDataRole.UserRole:
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            suffix = " Best result (ties included)." if is_best else ""
            return (column.tooltip + suffix).strip() or None
        if role == Qt.ItemDataRole.BackgroundRole and is_best:
            return QBrush(QColor("#d8f3dc"))
        if role == Qt.ItemDataRole.FontRole and is_best:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and column.kind != "text":
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return format_table_value(value, column.kind)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            column = self._table_data.columns[section]
            if role == Qt.ItemDataRole.DisplayRole:
                return column.title
            if role == Qt.ItemDataRole.ToolTipRole:
                return column.tooltip or None
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return section + 1
        return None


class ResultsBarChart(QWidget):
    """Small dependency-free bar chart for the primary result metric."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._table_data = TableData((), ())
        self.setMinimumHeight(150)

    def set_table_data(self, table_data):
        self._table_data = table_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        chart_index = next(
            (
                index
                for index, column in enumerate(self._table_data.columns)
                if column.chart
            ),
            None,
        )
        if chart_index is None or not self._table_data.rows:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter),
                "No chart data for this result.",
            )
            return
        column = self._table_data.columns[chart_index]
        rows = self._table_data.rows[:12]
        values = [max(0.0, float(row[chart_index])) for row in rows]
        maximum = max(values) if values else 1.0
        maximum = maximum if maximum > 0 else 1.0
        painter.setPen(self.palette().text().color())
        painter.drawText(12, 20, column.title)
        top = 30
        row_height = max(19, (self.height() - top - 8) // max(1, len(rows)))
        label_width = min(230, max(110, self.width() // 3))
        bar_left = label_width + 18
        bar_width = max(20, self.width() - bar_left - 75)
        metrics = painter.fontMetrics()
        for index, (row, value) in enumerate(zip(rows, values)):
            y = top + index * row_height
            label = metrics.elidedText(
                str(row[0]), Qt.TextElideMode.ElideRight, label_width
            )
            painter.setPen(self.palette().text().color())
            painter.drawText(8, y + row_height - 5, label)
            width = int(bar_width * value / maximum)
            painter.fillRect(
                bar_left,
                y + 3,
                width,
                max(8, row_height - 7),
                QColor("#457b9d"),
            )
            display = format_table_value(row[chart_index], column.kind)
            painter.drawText(bar_left + width + 6, y + row_height - 5, display)
