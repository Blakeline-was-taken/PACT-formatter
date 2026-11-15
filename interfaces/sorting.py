"""Reusable sort dialog and ordering helpers for CSV-backed editors."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
)

from model.text import strip_rich_text_tags
from .reorderable import DraggableRow, RowContainer

MULTI_VALUE_COLUMNS = {"sigils", "traits", "tribes", "tags", "token", "credit"}


class SortRuleRow(DraggableRow):
    """Reorderable sort rule with an inline direction selector."""

    def __init__(self, column, parent=None):
        super().__init__(parent)
        self.column = column
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLabel(column)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label, 1)
        self.direction = QComboBox()
        self.direction.addItem("Ascending", False)
        self.direction.addItem("Descending", True)
        self.direction.setToolTip("Choose the direction for this sort rule.")
        layout.addWidget(self.direction)
        self._add_remove_button(layout)
        layout.itemAt(layout.count() - 1).widget().setToolTip("Remove this sort rule.")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class SortDialog(QDialog):
    """Choose, order, and apply multiple sort criteria."""

    def __init__(self, columns, item_type, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sort {item_type}")
        self.setMinimumSize(520, 420)
        self.save_on_apply = False
        self.columns = list(columns)

        layout = QVBoxLayout(self)
        instructions = QLabel("Rules apply top to bottom. Multi-value fields sort by count, then by values in listed order using natural text ordering.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Sort by"))
        self.column_combo = QComboBox()
        self.column_combo.addItems(self.columns)
        self.column_combo.setToolTip("Choose an item attribute to sort by.")
        add_row.addWidget(self.column_combo, 1)

        add_rule = QPushButton("+ Add sort rule")
        add_rule.setToolTip("Add this attribute, then choose its direction in the sort rule.")
        add_rule.clicked.connect(self._add_rule)
        add_row.addWidget(add_rule)
        layout.addLayout(add_row)

        self.rules = RowContainer()
        self.rules.layout.setAlignment(Qt.AlignTop)
        self.rules_scroll = QScrollArea()
        self.rules_scroll.setWidgetResizable(True)
        self.rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rules_scroll.setWidget(self.rules)
        layout.addWidget(self.rules_scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(lambda: self._finish(save=False))
        buttons.addWidget(apply_button)
        apply_and_save_button = QPushButton("Apply and Save")
        apply_and_save_button.clicked.connect(lambda: self._finish(save=True))
        buttons.addWidget(apply_and_save_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def _add_rule(self):
        if not self.columns:
            return
        column = self.column_combo.currentText()
        self.rules.add_row(SortRuleRow(column))

    def _finish(self, save):
        self.save_on_apply = save
        self.accept()

    def sort_specifications(self):
        return [(row.column, bool(row.direction.currentData())) for row in self.rules.rows]


def sort_records(records, specifications):
    """Sort records stably using ordered (column, descending) criteria."""
    ordered = list(records)
    for column, descending in reversed(specifications):
        if column.casefold() == "cost":
            ordered.sort(key=lambda record: _cost_key(record.get(column, "")), reverse=descending)
            ordered.sort(key=lambda record: not _is_free_cost(record.get(column, "")), reverse=descending)
        else:
            ordered.sort(key=lambda record: _sort_key(record.get(column, ""), column), reverse=descending)
    return ordered


def _sort_key(value, column):
    value = "" if value is None else str(value)
    if column.casefold() == "cost":
        return _cost_key(value)
    if column.casefold() in MULTI_VALUE_COLUMNS:
        values = _multi_value_values(value, column)
        return len(values), tuple(_natural_text_key(item) for item in values)
    return _natural_text_key(value)


def _natural_text_key(value):
    text = strip_rich_text_tags(value).casefold()
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in re.split(r"(\d+)", text))


def _multi_value_values(value, column):
    text = "" if value is None else str(value).strip()
    if text.casefold() in {"", "none"}:
        return []
    if column.casefold() == "tribes":
        return [item for item in re.split(r"[\s,]+", text) if item]
    return [item.strip() for item in text.split(",") if item.strip()]


def _cost_key(value):
    """Compare cost components alphabetically by resource, then by amount."""
    value = "" if value is None else str(value)
    if _is_free_cost(value):
        return ()

    components = []
    for component in value.casefold().split(" + "):
        component = component.strip()
        gemified = re.fullmatch(r".+_[+-]?\d+_(.+)", component)
        if gemified:
            component = gemified.group(1).strip()

        amount_match = re.fullmatch(r"([+-]?\d+)\s+(.+)", component)
        if amount_match:
            amount = int(amount_match.group(1))
            resource = amount_match.group(2).strip()
        else:
            amount = 0 if component == "free" else 1
            resource = component
        components.append((resource, amount))

    return tuple(sorted(components))


def _is_free_cost(value):
    return value is None or str(value).strip().casefold() in {"", "none", "free"}
