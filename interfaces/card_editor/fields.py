"""Reusable card-editor field widgets."""

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from .data import COST_OPTIONS
from ..gui_helpers import Gemification, NoWheelComboBox, set_widget_tooltip
from ..reorderable import DraggableRow, RowContainer
from ..tag_data import CARD_TAG_OPTIONS, CARD_TAG_TOOLTIPS


class CostRow(DraggableRow):
    """Editable cost resource row with amount and removal controls."""

    def __init__(self, resource, amount=1, enabled=True, parent=None):
        """Create a resource row with an editable amount."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLineEdit(resource)
        self.label.setFrame(False)
        self.label.setToolTip("Cost resource name.")
        self.label.textChanged.connect(self.changed)
        self.amount = QSpinBox()
        set_widget_tooltip(self.amount, "Amount of this resource.")
        self.amount.setRange(0, 99)
        self.amount.setValue(amount)
        self.amount.setFixedWidth(78)
        self.amount.setMinimumHeight(28)
        self.amount.setEnabled(enabled)
        self.amount.valueChanged.connect(self.changed)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.amount)
        self._add_remove_button(layout)


class SigilRow(DraggableRow):
    """Sigil row with a per-sigil conditional and gem selection."""

    def __init__(self, name, conditional="None", gems="", parent=None):
        """Create a sigil row and restore its conditional gem state."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLineEdit(name)
        self.label.setFrame(False)
        self.label.setToolTip("Sigil name.")
        self.label.textChanged.connect(self.changed)
        self.conditional = NoWheelComboBox()
        self.conditional.addItems(["None", "Cell", "Latch", "Hint", "Gemified"])
        self.conditional.setToolTip("Apply a conditional to this sigil.")
        self.conditional.setCurrentText(conditional)
        self.gemification = Gemification(False)
        self.gemification.setVisible(conditional == "Gemified")
        self.gemification.set_gems(gems.split("_") if gems else [])
        self.conditional.currentTextChanged.connect(lambda value: self.gemification.setVisible(value == "Gemified"))
        self.gemification.changed.connect(self.changed)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.conditional)
        layout.addWidget(self.gemification)
        self._add_remove_button(layout)


class BasicRow(DraggableRow):
    """Simple reorderable text row used for traits and metadata lists."""

    def __init__(self, value, parent=None):
        """Create a simple text row with an explicit remove button."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLineEdit(value)
        self.label.setFrame(False)
        self.label.setToolTip("Entry value. Drag its row to change the order.")
        self.label.textChanged.connect(self.changed)
        layout.addWidget(self.label, 1)
        self._add_remove_button(layout)


class TagRow(DraggableRow):
    """Non-editable tag row that displays its name as plain text."""

    def __init__(self, value, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLabel(value)
        layout.addWidget(self.label, 1)
        self._add_remove_button(layout)


class ElementList(QWidget):
    """Search-and-list editor for ordered card fields."""
    changed = Signal()

    def __init__(self, title, options, delimiter=", ", suggestions=True, item_tooltips=None):
        """Build a reusable ordered-field editor.

        delimiter controls how the visible row order is serialized.
        Costs use " + " while most CSV fields use commas.
        """
        super().__init__()
        self.delimiter = delimiter
        self.item_tooltips = {key.casefold(): value for key, value in (item_tooltips or {}).items()}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.search = NoWheelComboBox() if suggestions else QLineEdit()
        if suggestions:
            self.search.setEditable(True)
            self.search.setInsertPolicy(QComboBox.NoInsert)
            self.search.addItems(options)
            for index, option in enumerate(options):
                tooltip = self.item_tooltips.get(option.casefold())
                if tooltip:
                    self.search.setItemData(index, tooltip, Qt.ToolTipRole)
        self.search.setPlaceholderText(f"Input {title.lower()}...")
        self.search.setToolTip(f"Enter a {title.lower()} value to add it to the list.")
        controls.addWidget(self.search, 1)
        add = QPushButton("+ Add")
        add.setToolTip(f"Add the entered {title.lower()} value.")
        add.clicked.connect(self.add_item)
        controls.addWidget(add)
        layout.addLayout(controls)

        self.items = RowContainer()
        self.items.reordered.connect(self.changed)
        layout.addWidget(self.items)

    def _input_text(self):
        """Read the current value from either a suggestion selector or text input."""
        return self.search.currentText() if isinstance(self.search, QComboBox) else self.search.text()

    def _clear_input(self):
        """Clear the add-entry control without changing its available options."""
        self.search.setCurrentText("") if isinstance(self.search, QComboBox) else self.search.clear()

    def _new_basic_row(self, value):
        """Create a row and apply optional value-specific help."""
        row = BasicRow(value)
        return row

    def add_item(self):
        """Append a basic text row from the add-entry control."""
        value = self._input_text().strip()
        if value:
            row = self._new_basic_row(value)
            row.changed.connect(self.changed)
            self.items.add_row(row)
            self._clear_input()
            self.changed.emit()

    def set_values(self, values):
        """Replace the current rows with values loaded from a CSV field."""
        self.items.clear_rows()
        for value in values:
            row = self._new_basic_row(value)
            row.changed.connect(self.changed)
            self.items.add_row(row)

    def values(self):
        """Return row text in the current visual order."""
        return [row.label.text() for row in self.items.rows]

    def serialized(self):
        """Serialize ordered resources in the renderer's " + " format."""
        return self.delimiter.join(self.values())


class TagList(ElementList):
    """List of known or custom tags with tag-specific help."""

    def __init__(self, options=CARD_TAG_OPTIONS):
        item_tooltips = {tag: CARD_TAG_TOOLTIPS[tag] for tag in options if tag in CARD_TAG_TOOLTIPS}
        super().__init__("Tags", options, item_tooltips=item_tooltips)
        self.search.lineEdit().setValidator(QRegularExpressionValidator(QRegularExpression("[^,]*"), self.search.lineEdit()))
        self.search.setToolTip("Choose a known tag or enter a custom tag. Add one tag per row; commas are reserved as separators.")

    def _new_basic_row(self, value):
        row = TagRow(value)
        tooltip = self.item_tooltips.get(value.strip().casefold())
        row.setToolTip(tooltip)
        row.label.setToolTip(tooltip)
        return row

    def add_item(self):
        value = self._input_text().strip()
        if "," in value:
            QMessageBox.warning(self, "Invalid tag", "Tags cannot contain commas. Add one tag per row.")
            return
        super().add_item()


class CostList(ElementList):
    """Ordered cost editor with per-resource amounts and whole-cost gems."""

    def __init__(self):
        """Create a cost editor using renderer-compatible cost segments."""
        super().__init__("Costs", COST_OPTIONS, delimiter=" + ")
        self.gemified = QPushButton("Gemified")
        self.gemified.setToolTip("Apply gemification to the cost.")
        self.gemified.setCheckable(True)
        self.gemification = Gemification(True)
        self.gemification.setVisible(False)
        self.gemified.toggled.connect(self.gemification.setVisible)
        self.gemified.toggled.connect(self.changed)
        self.gemification.changed.connect(self.changed)
        self.layout().addWidget(self.gemified)
        self.layout().addWidget(self.gemification)

    def add_item(self):
        """Append a cost row with an independent amount control."""
        value = self._input_text().strip()
        if not value:
            return
        row = CostRow(value, enabled=value.casefold() not in ("asterisk", "free"))
        row.changed.connect(self.changed)
        self.items.add_row(row)
        self._clear_input()
        self.changed.emit()

    def set_values(self, values):
        """Load cost segments and restore whole-cost gemification if present."""
        self.items.clear_rows()
        self.gemified.setChecked(False)
        self.gemification.set_value("")

        # A single underscore-encoded segment represents whole-cost gemification.
        if len(values) == 1 and "_" in values[0]:
            encoded = values[0]
            self.gemified.setChecked(True)
            self.gemification.set_value(encoded)
            base = encoded.split("_")[-1]
            values = [base]
        for value in values:
            parts = value.strip().split(" ", 1)
            if parts[0].isdigit() and len(parts) == 2:
                amount, resource = int(parts[0]), parts[1]
            else:
                amount, resource = 1, value.strip()
            if "_" in value:
                amount, resource = 0, value.strip()
            row = CostRow(resource, amount, enabled="_" not in value and resource.casefold() not in ("asterisk", "free"))
            row.changed.connect(self.changed)
            self.items.add_row(row)

    def serialized(self):
        """Serialize the cost rows, including optional whole-cost gemification."""
        result = []

        # Convert UI labels to the special spellings expected by the renderer.
        for row in self.items.rows:
            resource = row.label.text()
            if resource == "asterisk":
                result.append("*")
            elif "_" in resource:
                result.append(resource)
            elif resource.casefold() == "free":
                result.append("free")
            else:
                result.append(f"{row.amount.value()} {resource}")
        value = " + ".join(result)
        return self.gemification.value(value) if self.gemified.isChecked() else value


class SigilList(ElementList):
    """Ordered sigil editor with per-row conditional controls."""

    def __init__(self, options):
        """Create a sigil editor backed by the known sigil suggestions."""
        super().__init__("Sigils", options)

    @staticmethod
    def _parse(value):
        """Decode stored conditional and gemified sigil syntax."""
        if value.lower() == "rainbow":
            return value, "None", ""
        if value.lower() == "tribal":
            return value, "None", ""
        parts = value.split("_")
        if parts[0].lower() in ("cell", "latch", "hint"):
            return "_".join(parts[1:]), parts[0].title(), ""

        # Gem names precede the sigil name in the stored underscore format.
        gems = [part for part in parts[:-1] if part.lower() in ("green", "blue", "orange", "prism")]
        if gems:
            return parts[-1], "Gemified", "_".join(gems)
        return value, "None", ""

    def add_item(self):
        """Append a sigil row with its conditional initially set to None."""
        value = self.search.currentText().strip()
        if not value:
            return
        row = SigilRow(value)
        row.changed.connect(self.changed)
        row.conditional.currentTextChanged.connect(self.changed)
        self.items.add_row(row)
        self._clear_input()
        self.changed.emit()

    def set_values(self, values):
        """Decode stored conditional syntax into per-row controls."""
        self.items.clear_rows()
        for value in values:
            name, conditional, gems = self._parse(value)
            row = SigilRow(name, conditional, gems)
            row.changed.connect(self.changed)
            row.conditional.currentTextChanged.connect(self.changed)
            self.items.add_row(row)

    def values(self):
        """Encode per-row conditional controls back to renderer syntax."""
        result = []
        for row in self.items.rows:
            name = row.label.text()
            conditional = row.conditional.currentText()
            if name.lower() == "rainbow":
                result.append("rainbow")
            elif name.lower() == "tribal":
                result.append("tribal")
            elif conditional in ("Cell", "Latch", "Hint"):
                result.append(f"{conditional}_{name}")
            elif conditional == "Gemified":
                value = row.gemification.value(name)
                result.append(value)
            else:
                result.append(name)
        return result
