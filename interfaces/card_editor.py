"""Interactive card data editor."""

import csv
import shutil
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QPixmap, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QGridLayout,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import DEFAULT_CONFIG, cards, sigils
from .gui_helpers import Gemification, NoWheelComboBox, ROOT, _split, _join


CARDS_PATH = ROOT / DEFAULT_CONFIG["cards_file_path"]
ASSET_PATH = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "card_art"
# Keep this order aligned with data/cards.csv so newly written files remain
# compatible with the existing CLI and renderer.
CARD_FIELDS = [
    "Card Name", "Art File", "Temple", "Tier", "Cost", "Power", "Health",
    "Sigils", "Token", "Traits", "Tribes", "Flavor Text", "Credit", "Tags",
]
TAG_OPTIONS = [
    "bloodless_bg", "conduit_indicator", "mox_indicator", "mox_green",
    "mox_orange", "mox_blue", "mox_prism", "gemified_vanilla",
    "conduit_sigil_indicator",
]
COST_OPTIONS = [
    "blood", "bones", "energy", "max",
    "emerald", "sapphire", "ruby", "prism",
    "shattered emerald", "shattered sapphire", "shattered ruby", "shattered prism",
    "asterisk",
]


class DraggableRow(QFrame):
    """Base row that supports custom drag-and-drop reordering."""

    removeRequested = Signal()

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
        self.label = QLabel(resource)
        self.amount = QSpinBox()
        self.amount.setRange(0, 99)
        self.amount.setValue(amount)
        self.amount.setFixedWidth(78)
        self.amount.setMinimumHeight(28)
        self.amount.setEnabled(enabled)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.amount)
        self._add_remove_button(layout)


class SigilRow(DraggableRow):
    """Sigil row with a per-sigil conditional and gem selection."""
    changed = Signal()

    def __init__(self, name, conditional="None", gems="", parent=None):
        """Create a sigil row and restore its conditional gem state."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLabel(name)
        self.conditional = NoWheelComboBox()
        self.conditional.addItems(["None", "Cell", "Latch", "Hint", "Gemified"])
        self.conditional.setCurrentText(conditional)
        self.gemification = Gemification(False)
        self.gemification.setVisible(conditional == "Gemified")
        self.gemification.set_gems(gems.split("_") if gems else [])
        self.conditional.currentTextChanged.connect(
            lambda value: self.gemification.setVisible(value == "Gemified")
        )
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
        self.label = QLabel(value)
        layout.addWidget(self.label, 1)
        self._add_remove_button(layout)

class ElementList(QWidget):
    """Search-and-list editor for ordered card fields."""
    changed = Signal()

    def __init__(self, title, options, conditional=False, delimiter=", ", suggestions=True):
        """Build a reusable ordered-field editor.

        delimiter controls how the visible row order is serialized. Costs
        use " + " while most CSV fields use commas.
        """
        super().__init__()
        self.conditional = conditional
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
            self.items.add_row(row)
            self._clear_input()
            self.changed.emit()

    def set_values(self, values):
        """Replace the current rows with values loaded from a CSV field."""
        self.items.clear_rows()
        for value in values:
            row = BasicRow(value)
            self.items.add_row(row)

    def values(self):
        """Return row text in the current visual order."""
        return [
            row.label.text() for row in self.items.rows
        ]

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
        row.amount.valueChanged.connect(self.changed)
        self.items.add_row(row)
        self._clear_input()
        self.changed.emit()

    def set_values(self, values):
        """Load cost segments and restore whole-cost gemification if present."""
        self.items.clear_rows()
        self.gemified.setChecked(False)
        self.gemification.set_value("")
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
            row.amount.valueChanged.connect(self.changed)
            self.items.add_row(row)

    def serialized(self):
        """Serialize the cost rows, including optional whole-cost gemification."""
        result = []
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
        row.conditional.currentTextChanged.connect(self.changed)
        row.changed.connect(self.changed)
        self.items.add_row(row)
        self._clear_input()
        self.changed.emit()

    def set_values(self, values):
        """Decode stored conditional syntax into per-row controls."""
        self.items.clear_rows()
        for value in values:
            name, conditional, gems = self._parse(value)
            row = SigilRow(name, conditional, gems)
            row.conditional.currentTextChanged.connect(self.changed)
            row.changed.connect(self.changed)
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


class CardEditor(QWidget):
    """Search, edit, preview, save, export, and delete card records."""

    def __init__(self):
        """Load card data, build the editor, and select an initial record."""
        super().__init__()
        self.rows = []
        self.fieldnames = CARD_FIELDS
        self.current_index = -1
        self.original = {}
        self.loading = False
        self._load_data()
        self._load_models()
        self._build_ui()
        self._select_index(0 if self.rows else -1)

    def _load_data(self):
        """Read card rows while preserving the CSV header order."""
        try:
            with CARDS_PATH.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.fieldnames = reader.fieldnames or CARD_FIELDS
                self.rows = [dict(row) for row in reader]
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not load cards", str(error))

    def _load_models(self):
        """Populate renderer lookup tables used by card preview rendering."""
        for filename, loader in (("sigils.csv", sigils.add_sigil), ("traits.csv", sigils.add_trait)):
            try:
                with (ROOT / "data" / filename).open(newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        loader(row)
            except (OSError, csv.Error):
                continue

    def _build_ui(self):
        """Create the selection header, editable form, and preview splitter."""
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(self._build_header())
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_form())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([600, 500])
        root.addWidget(splitter, 1)

    def _build_header(self):
        """Build the searchable card selector and new-card actions."""
        box = QGroupBox("Card selection")
        layout = QHBoxLayout(box)
        self.search = NoWheelComboBox()
        self.search.setEditable(True)
        self.search.setPlaceholderText("Search cards by name...")
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.lineEdit().textEdited.connect(self._filter_cards)
        layout.addWidget(self.search, 1)
        edit = QPushButton("Edit")
        edit.setText("Load")
        edit.clicked.connect(self._search_activated)
        layout.addWidget(edit)
        new = QPushButton("+ New card")
        new.clicked.connect(self._new_card)
        layout.addWidget(new)
        self._refresh_search()
        return box

    def _build_form(self):
        """Build the vertically scrollable card-data form."""
        container = QWidget()
        outer = QVBoxLayout(container)
        title = QLabel("Card data")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        body.setMinimumWidth(0)
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.fields = {}
        for name in ("Card Name", "Flavor Text"):
            edit = QLineEdit()
            edit.textChanged.connect(self._changed)
            self.fields[name] = edit
            form.addRow(name, edit)

        self.temple = self._suggested_field(self._unique_column_values("Temple"))
        self.tier = self._suggested_field(self._unique_column_values("Tier"))
        self.fields["Temple"] = self.temple
        self.fields["Tier"] = self.tier
        form.addRow("Temple", self.temple)
        form.addRow("Tier", self.tier)

        self.art = QLineEdit()
        self.art.setReadOnly(True)
        choose = QPushButton("Choose file...")
        choose.clicked.connect(self._choose_art)
        art_row = QHBoxLayout()
        art_row.addWidget(self.art, 1)
        art_row.addWidget(choose)
        form.addRow("Art file", art_row)

        self.power = self._stat_editor("Power", form)
        self.health = self._stat_editor("Health", form)
        self.costs = CostList()
        self.costs.changed.connect(self._changed)
        form.addRow("Cost", self.costs)
        sigil_options = self._load_names("sigils.csv", "Name") + ["TRIBAL", "RAINBOW"]
        self.sigils = SigilList(sigil_options)
        self.sigils.changed.connect(self._changed)
        form.addRow("Sigils", self.sigils)
        self.traits = ElementList("Traits", self._load_names("traits.csv", "Name"))
        self.traits.changed.connect(self._changed)
        form.addRow("Traits", self.traits)
        tribes = self._unique_tribes()
        for name, suggested in (("Tribes", True), ("Token", False), ("Credit", True)):
            widget = ElementList(
                name,
                tribes if name == "Tribes" else self._unique_column_values("Credit"),
                suggestions=name != "Token",
            )
            widget.delimiter = " " if name == "Tribes" else ", "
            widget.changed.connect(self._changed)
            self.fields[name] = widget
            form.addRow(name, widget)
        self.tags = self._tag_editor()
        form.addRow("Tags", self.tags)
        scroll.setWidget(body)
        self.form_scroll = scroll
        self.form_body = body
        outer.addWidget(scroll)
        delete = QPushButton("Delete card")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_card)
        outer.addWidget(delete)
        return container

    def _stat_editor(self, name, form):
        """Create a numeric stat field and its optional gemification controls."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        number = QSpinBox()
        number.setRange(-99, 99)
        number.valueChanged.connect(self._changed)
        layout.addWidget(number, 1)
        toggle = QPushButton("Gemified")
        toggle.setCheckable(True)
        gem = Gemification(True)
        gem.setVisible(False)
        toggle.toggled.connect(gem.setVisible)
        toggle.toggled.connect(self._changed)
        gem.changed.connect(self._changed)
        layout.addWidget(toggle)
        layout.addWidget(gem, 2)
        form.addRow(name, row)
        self.fields[name] = number
        self.fields[name + " toggle"] = toggle
        self.fields[name + " gem"] = gem
        return row

    def _tag_editor(self):
        """Build the fixed set of card tag toggles and extra-cell count."""
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.tag_checks = {}
        for index, tag in enumerate(TAG_OPTIONS):
            check = QPushButton(tag)
            check.setCheckable(True)
            check.toggled.connect(self._changed)
            layout.addWidget(check, index // 4, index % 4)
            self.tag_checks[tag] = check
        self.extra_cell_amount = QSpinBox()
        self.extra_cell_amount.setRange(0, 99)
        self.extra_cell_amount.setPrefix("Extra cells: ")
        self.extra_cell_amount.valueChanged.connect(self._changed)
        layout.addWidget(self.extra_cell_amount, 3, 0, 1, 4)
        return widget

    def _build_preview(self):
        """Build the preview surface and save/export actions."""
        box = QGroupBox("Live preview")
        layout = QVBoxLayout(box)
        self.preview = QLabel("Select a card")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(300, 420)
        self.preview.setStyleSheet("background: #e8edf5;")
        layout.addWidget(self.preview, 1)
        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        save_export = QPushButton("Save and Export")
        save_export.clicked.connect(lambda: self._save(True))
        buttons.addWidget(save)
        buttons.addWidget(save_export)
        layout.addLayout(buttons)
        return box

    def _load_names(self, filename, key):
        """Load suggestion values from a named data CSV."""
        try:
            with (ROOT / "data" / filename).open(newline="", encoding="utf-8") as handle:
                return [row[key] for row in csv.DictReader(handle) if row.get(key)]
        except (OSError, csv.Error, KeyError):
            return []

    def _unique_column_values(self, key):
        """Return unique comma-delimited values used by existing cards."""
        values = set()
        for row in self.rows:
            values.update(_split(row.get(key, "")))
        return sorted(values)

    def _unique_tribes(self):
        """Return unique tribe words because the renderer separates tribes by spaces."""
        values = set()
        for row in self.rows:
            values.update(row.get("Tribes", "").replace(",", " ").split())
        return sorted(values)

    def _suggested_field(self, options):
        """Create an editable selector that also accepts values outside suggestions."""
        field = NoWheelComboBox()
        field.setEditable(True)
        field.setInsertPolicy(QComboBox.NoInsert)
        field.addItems(options)
        field.currentTextChanged.connect(self._changed)
        return field

    def _refresh_search(self, text=""):
        """Repopulate the card selector while retaining the displayed text."""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems([row.get("Card Name", "") for row in self.rows])
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _filter_cards(self, text):
        """Filter card names as the user types without loading a card."""
        query = text.lower()
        matches = [row["Card Name"] for row in self.rows if query in row.get("Card Name", "").lower()]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(matches)
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _search_activated(self):
        """Load the exact selected card after the user presses Load."""
        name = self.search.currentText().strip()
        matches = [i for i, row in enumerate(self.rows) if row.get("Card Name") == name]
        if matches and self._confirm_navigation():
            self._select_index(matches[0])

    def _select_index(self, index):
        """Switch the form to a row index after unsaved-change checks."""
        if index < 0 or index >= len(self.rows):
            return
        self.current_index = index
        self.original = dict(self.rows[index])
        self._populate(self.original)
        self._refresh_search(self.original.get("Card Name", ""))
        self._render_preview()

    def _populate(self, row):
        """Populate every editor control from one CSV row."""
        self.loading = True
        for name in ("Card Name", "Flavor Text"):
            self.fields[name].setText(row.get(name, ""))
        for name in ("Temple", "Tier"):
            self.fields[name].setCurrentText(row.get(name, ""))
        self.art.setText(row.get("Art File", ""))
        for name in ("Power", "Health"):
            raw = row.get(name, "")
            try:
                self.fields[name].setValue(int(raw.split("_")[-1] if "_" in raw else raw or 0))
            except ValueError:
                self.fields[name].setValue(0)
            self.fields[name + " toggle"].setChecked("_" in raw)
            if "_" in raw:
                self.fields[name + " gem"].set_value(raw)
        self.costs.set_values(row.get("Cost", "").split(" + ") if row.get("Cost") else [])
        self.sigils.set_values(_split(row.get("Sigils", "")))
        self.traits.set_values(_split(row.get("Traits", "")))
        self.fields["Tribes"].set_values(row.get("Tribes", "").replace(",", " ").split())
        self.fields["Token"].set_values(_split(row.get("Token", "")))
        self.fields["Credit"].set_values(_split(row.get("Credit", "")))
        tags = set(_split(row.get("Tags", "")))
        self.extra_cell_amount.setValue(0)
        for name, check in self.tag_checks.items():
            check.setChecked(name in tags)
        for tag in _split(row.get("Tags", "")):
            if tag.endswith("_extra_cell") and tag.split("_", 1)[0].isdigit():
                self.extra_cell_amount.setValue(int(tag.split("_", 1)[0]))
        self.loading = False

    def _current_row(self):
        """Serialize controls into the renderer's card dictionary format."""
        row = {field: "" for field in self.fieldnames}
        for name in ("Card Name", "Flavor Text"):
            row[name] = self.fields[name].text().strip()
        row["Temple"] = self.fields["Temple"].currentText().strip()
        row["Tier"] = self.fields["Tier"].currentText().strip()
        row["Art File"] = self.art.text().strip()
        for name in ("Power", "Health"):
            value = str(self.fields[name].value())
            row[name] = self.fields[name + " gem"].value(value) if self.fields[name + " toggle"].isChecked() else value
        row["Cost"] = self.costs.serialized()
        row["Sigils"] = _join(self.sigils.values())
        row["Traits"] = _join(self.traits.values())
        row["Tribes"] = self.fields["Tribes"].serialized()
        row["Token"] = _join(self.fields["Token"].values())
        row["Credit"] = self.fields["Credit"].serialized()
        tags = [name for name, check in self.tag_checks.items() if check.isChecked()]
        if self.extra_cell_amount.value() > 0:
            tags.append(f"{self.extra_cell_amount.value()}_extra_cell")
        row["Tags"] = _join(tags)
        return row

    def _changed(self):
        """Refresh the preview after user edits, except during bulk loading."""
        if not self.loading:
            self._render_preview()

    def _render_preview(self):
        """Render the current form state and show failures in the preview pane."""
        row = self._current_row()
        try:
            image = cards.create_card(row)
            pixmap = QPixmap.fromImage(ImageQt(image))
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as error:
            self.preview.clear()
            self.preview.setText(f"Preview unavailable: {error}")

    def resizeEvent(self, event):
        """Keep the form body exactly as wide as the scroll viewport."""
        super().resizeEvent(event)
        if hasattr(self, "form_scroll"):
            self.form_body.setMinimumWidth(self.form_scroll.viewport().width())
        if self.current_index >= 0:
            self._render_preview()

    def _dirty(self):
        """Return whether the current controls differ from the loaded snapshot."""
        return self.current_index >= 0 and self._current_row() != self.original

    def _confirm_navigation(self):
        """Ask before discarding edits when changing the active card."""
        if not self._dirty():
            return True
        result = QMessageBox.warning(self, "Unsaved changes", "Discard unsaved changes?",
                                      QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        return result == QMessageBox.Discard

    def _new_card(self):
        """Reset the form into a new-card state after confirmation."""
        if not self._confirm_navigation():
            return
        self.current_index = -1
        self.original = {}
        self._populate({field: "" for field in CARD_FIELDS})
        self.art.setText("")
        self._refresh_search("")
        self._render_preview()

    def _choose_art(self):
        """Choose art from the configured card-art directory."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose card art", str(ASSET_PATH), "Images (*.png *.jpg *.jpeg)"
        )
        if filename:
            selected = Path(filename)
            self.art.setText(selected.name if selected.parent.resolve() == ASSET_PATH.resolve() else str(selected))
            self._render_preview()

    def _save(self, export=False):
        """Write the current row, optionally render it, and report export success."""
        row = self._current_row()
        if not row["Card Name"]:
            QMessageBox.warning(self, "Cannot save card", "Card Name is required.")
            return False
        source = Path(row["Art File"])
        if source.is_file() and source.parent.resolve() != ASSET_PATH.resolve():
            ASSET_PATH.mkdir(parents=True, exist_ok=True)
            target = ASSET_PATH / source.name
            shutil.copy2(source, target)
            row["Art File"] = target.name
            self.art.setText(target.name)
        elif source.name:
            row["Art File"] = source.name
        if self.current_index < 0:
            self.rows.append(row)
            self.current_index = len(self.rows) - 1
        else:
            self.rows[self.current_index] = row
        try:
            with CARDS_PATH.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.rows)
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not save cards", str(error))
            return False
        self.original = dict(row)
        self._refresh_search(row["Card Name"])
        if export:
            try:
                image = cards.create_card(row)
                target = ROOT / "exports" / "cards" / f"{row['Card Name']}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
            except Exception as error:
                QMessageBox.critical(self, "Export failed", str(error))
                return False
            QMessageBox.information(
                self,
                "Card exported",
                f"{row['Card Name']} was exported to {target}.",
            )
        self._render_preview()
        return True

    def _delete_card(self):
        """Delete the active card after confirmation and optional export cleanup."""
        if self.current_index < 0:
            return
        result = QMessageBox.warning(self, "Delete card", "Delete this card?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if result != QMessageBox.Yes:
            return
        row = self.rows.pop(self.current_index)
        exports = ROOT / "exports" / "cards"
        if QMessageBox.question(self, "Delete exports?", "Also delete exports for this card?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for candidate in (exports / f"{row['Card Name']}.png", exports / f"{row['Art File']}.png"):
                if candidate.is_file():
                    candidate.unlink()
        self._save_rows()
        self._refresh_search("")
        self._select_index(min(self.current_index, len(self.rows) - 1))

    def _save_rows(self):
        """Persist the in-memory card list using the original CSV columns."""
        with CARDS_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows)
