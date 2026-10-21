"""Reusable card-editor field widgets."""

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .data import COST_OPTIONS
from ..gui_helpers import Gemification, NoWheelComboBox


class DraggableRow(QFrame):
    """Base row that supports custom drag-and-drop reordering."""

    removeRequested = Signal()
    changed = Signal()

    def __init__(self, parent=None):
        """Initialize row styling, drag state, and the shared row contract."""
        super().__init__(parent)
        self._drag_start = QPoint()
        self.setObjectName("editorRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.OpenHandCursor))
        self.setStyleSheet(
            "QFrame#editorRow { background-color: #eef1f5; border: 1px solid #d9dee6; "
            "border-left: 4px solid #c4cbd5; border-radius: 4px; }"
            "QFrame#editorRow:hover { border-color: #91a6c2; border-left-color: #8392a6; "
            "background-color: #dfe6f0; }"
        )

    def _add_remove_button(self, layout):
        """Add the explicit row-removal control shared by all row types."""
        remove = QPushButton("X")
        remove.setToolTip("Remove this entry")
        remove.setFixedWidth(28)
        remove.clicked.connect(self.removeRequested)
        layout.addWidget(remove)

    def mousePressEvent(self, event):
        """Remember where a drag began without interfering with child controls."""
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Start a row drag after the pointer moves beyond the drag threshold."""
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 8:
            return
        container = self.parentWidget()
        if not isinstance(container, RowContainer):
            return
        drag = QDrag(self)
        mime = QMimeData()
        # The container resolves this identifier only among its own rows.
        mime.setText(str(id(self)))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)
        self.setCursor(QCursor(Qt.OpenHandCursor))


class RowContainer(QWidget):
    """Owns reorderable rows without QListWidget item ownership semantics."""
    reordered = Signal()

    def __init__(self, parent=None):
        """Initialize row storage, layout ownership, and drop feedback."""
        super().__init__(parent)
        self.rows = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.drop_marker = QFrame(self)
        self.drop_marker.setObjectName("dropMarker")
        self.drop_marker.setFixedHeight(5)
        self.drop_marker.hide()
        self.drop_marker.setStyleSheet(
            "#dropMarker { background: #3f78c5; border: 1px solid #245a9f; "
            "border-radius: 2px; }"
        )
        self.setStyleSheet(
            "RowContainer { border: 1px solid #dce2ec; border-radius: 4px; }"
        )

    def add_row(self, row):
        """Append a row and connect its explicit remove action."""
        row.setParent(self)
        row.removeRequested.connect(lambda target=row: self._remove_row(target))
        self.rows.append(row)
        self.layout.addWidget(row)

    def _remove_row(self, row):
        """Remove one row from both the Python list and Qt layout."""
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.layout.removeWidget(row)
        row.deleteLater()
        self.reordered.emit()

    def dragEnterEvent(self, event):
        """Accept drags originating from one of this container's own rows."""
        if event.mimeData().hasText() and self._row_from_mime(event.mimeData()) is not None:
            self._show_drop_marker(event.position().toPoint().y())
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Keep the insertion marker synchronized with the pointer position."""
        if event.mimeData().hasText() and self._row_from_mime(event.mimeData()) is not None:
            self._show_drop_marker(event.position().toPoint().y())
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Move the dragged row to the insertion marker's position."""
        row = self._row_from_mime(event.mimeData())
        if row is None:
            event.ignore()
            return
        target = self._drop_index(event.position().toPoint().y())
        source = self.rows.index(row)
        # Removing a row above the target shifts the insertion index left.
        if target > source:
            target -= 1
        self.move_row(source, target)
        self._hide_drop_marker()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """Hide the insertion marker when a drag leaves the container."""
        self._hide_drop_marker()
        event.accept()

    def _drop_index(self, y):
        """Return the row index before which a pointer at y should insert."""
        for index, row in enumerate(self.rows):
            if y < row.geometry().center().y():
                return index
        return len(self.rows)

    def _show_drop_marker(self, y):
        """Place a visible insertion marker before the row under the cursor."""
        index = self._drop_index(y)
        if index == len(self.rows):
            marker_y = self.rows[-1].geometry().bottom() + 1 if self.rows else 0
        else:
            marker_y = self.rows[index].geometry().top() - 3
        self.drop_marker.setGeometry(4, marker_y, max(20, self.width() - 8), 5)
        self.drop_marker.show()
        self.drop_marker.raise_()

    def _hide_drop_marker(self):
        """Hide the visual insertion target after a completed or cancelled drag."""
        self.drop_marker.hide()

    def _row_from_mime(self, mime):
        """Resolve the in-process row identity encoded in drag MIME data."""
        row_id = mime.text()
        return next((row for row in self.rows if str(id(row)) == row_id), None)

    def clear_rows(self):
        """Remove all row widgets without relying on Qt item ownership."""
        while self.rows:
            row = self.rows.pop()
            self.layout.removeWidget(row)
            row.deleteLater()

    def move_row(self, source, target):
        """Reorder the Python-owned row list and rebuild its layout order."""
        if source < 0 or source >= len(self.rows):
            return False
        target = max(0, min(target, len(self.rows) - 1))
        if source == target:
            return False
        row = self.rows.pop(source)
        self.rows.insert(target, row)

        # Rebuild the layout so its visual order matches the backing row list.
        while self.layout.count():
            self.layout.takeAt(0)
        for current in self.rows:
            self.layout.addWidget(current)
        self.reordered.emit()
        return True


class CostRow(DraggableRow):
    """Editable cost resource row with amount and removal controls."""

    def __init__(self, resource, amount=1, enabled=True, parent=None):
        """Create a resource row with an editable amount."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLineEdit(resource)
        self.label.setFrame(False)
        self.label.textChanged.connect(self.changed)
        self.amount = QSpinBox()
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
        self.label.textChanged.connect(self.changed)
        self.conditional = NoWheelComboBox()
        self.conditional.addItems(["None", "Cell", "Latch", "Hint", "Gemified"])
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
        self.label.textChanged.connect(self.changed)
        layout.addWidget(self.label, 1)
        self._add_remove_button(layout)


class ElementList(QWidget):
    """Search-and-list editor for ordered card fields."""
    changed = Signal()

    def __init__(self, title, options, delimiter=", ", suggestions=True):
        """Build a reusable ordered-field editor.

        delimiter controls how the visible row order is serialized.
        Costs use " + " while most CSV fields use commas.
        """
        super().__init__()
        self.delimiter = delimiter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.search = NoWheelComboBox() if suggestions else QLineEdit()
        if suggestions:
            self.search.setEditable(True)
            self.search.setInsertPolicy(QComboBox.NoInsert)
            self.search.addItems(options)
        self.search.setPlaceholderText(f"Input {title.lower()}...")
        controls.addWidget(self.search, 1)
        add = QPushButton("+ Add")
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

    def add_item(self):
        """Append a basic text row from the add-entry control."""
        value = self._input_text().strip()
        if value:
            row = BasicRow(value)
            row.changed.connect(self.changed)
            self.items.add_row(row)
            self._clear_input()
            self.changed.emit()

    def set_values(self, values):
        """Replace the current rows with values loaded from a CSV field."""
        self.items.clear_rows()
        for value in values:
            row = BasicRow(value)
            row.changed.connect(self.changed)
            self.items.add_row(row)

    def values(self):
        """Return row text in the current visual order."""
        return [row.label.text() for row in self.items.rows]

    def serialized(self):
        """Serialize ordered resources in the renderer's " + " format."""
        return self.delimiter.join(self.values())


class CostList(ElementList):
    """Ordered cost editor with per-resource amounts and whole-cost gems."""

    def __init__(self):
        """Create a cost editor using renderer-compatible cost segments."""
        super().__init__("Costs", COST_OPTIONS, delimiter=" + ")
        self.gemified = QPushButton("Gemified")
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
        row = CostRow(value, enabled=value not in ("asterisk", "free"))
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
            row = CostRow(resource, amount, enabled="_" not in value and resource not in ("asterisk", "free"))
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
            elif resource == "free":
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
