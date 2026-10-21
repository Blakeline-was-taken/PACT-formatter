"""Interactive card data editor."""

import csv
import shutil
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
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

from model import cards, sigils
from model.text import strip_rich_text_tags
from .data import (
    ASSET_PATH,
    CARD_FIELDS,
    CARDS_PATH,
    TAG_OPTIONS,
    CardRepository,
    format_card_tags,
    parse_card_tags,
)
from .fields import CostList, ElementList, SigilList
from ..gui_helpers import Gemification, NoWheelComboBox, ROOT, _split, _join


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
        self.repository = CardRepository()
        self._load_data()
        self._load_models()
        self._build_ui()
        self._select_index(0 if self.rows else -1)

    # Startup data and page layout

    def _load_data(self):
        """Read card rows while preserving the CSV header order."""
        try:
            self.fieldnames, self.rows = self.repository.load_cards()
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

    # Card form construction

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

        # Keep the full data form scrollable while the preview remains fixed.
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

        # Basic identity fields and the card's template selectors.
        for name in ("Card Name", "Flavor Text"):
            edit = QLineEdit()
            edit.textChanged.connect(self._changed)
            self.fields[name] = edit
            form.addRow(name, edit)

        self.temple = self._suggested_field(self._unique_column_values("Temple"))
        self.tier = self._suggested_field(self._unique_column_values("Tier"))
        self.background = self._suggested_field(self._unique_background_modifiers())
        self.fields["Temple"] = self.temple
        self.fields["Tier"] = self.tier
        self.fields["Background"] = self.background
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

        # Ordered values use specialized widgets to preserve renderer syntax.
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
        for name in ("Tribes", "Token", "Credit"):
            options = tribes if name == "Tribes" else self._unique_column_values("Credit")
            widget = ElementList(name, options, suggestions=name != "Token")
            widget.delimiter = " " if name == "Tribes" else ", "
            widget.changed.connect(self._changed)
            self.fields[name] = widget
            form.addRow(name, widget)

        # Tags combine simple toggles with background, symbol, and cell options.
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
        value = QLineEdit()
        value.setPlaceholderText("Number...")
        value.textChanged.connect(self._changed)
        layout.addWidget(value, 1)
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
        self.fields[name] = value
        self.fields[name + " toggle"] = toggle
        self.fields[name + " gem"] = gem
        return row

    def _tag_editor(self):
        """Build the fixed set of card tag toggles and extra-cell count."""
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        outer.addLayout(layout)

        self.tag_checks = {}
        for index, tag in enumerate(TAG_OPTIONS):
            check = QPushButton(tag)
            check.setCheckable(True)
            check.toggled.connect(self._changed)
            layout.addWidget(check, index // 4, index % 4)
            self.tag_checks[tag] = check

        background_row = QHBoxLayout()
        background_row.addWidget(QLabel("Background"))
        background_row.addWidget(self.background, 1)
        outer.addLayout(background_row)

        self.extra_cell_amount = QSpinBox()
        self.extra_cell_amount.setRange(0, 99)
        self.extra_cell_amount.setPrefix("Extra cells: ")
        self.extra_cell_amount.valueChanged.connect(self._changed)
        outer.addWidget(self.extra_cell_amount)

        symbol_options = self._load_names("sigils.csv", "Name")
        self.left_symbol = self._suggested_field(symbol_options)
        self.right_symbol = self._suggested_field(symbol_options)
        left_symbol_row = QHBoxLayout()
        left_symbol_row.addWidget(QLabel("Left symbol"))
        left_symbol_row.addWidget(self.left_symbol, 1)
        right_symbol_row = QHBoxLayout()
        right_symbol_row.addWidget(QLabel("Right symbol"))
        right_symbol_row.addWidget(self.right_symbol, 1)
        symbol_row = QHBoxLayout()
        symbol_row.addLayout(left_symbol_row, 1)
        symbol_row.addLayout(right_symbol_row, 1)
        outer.addLayout(symbol_row)

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

    # Suggestions and selection

    def _load_names(self, filename, key):
        """Load suggestion values from a named data CSV."""
        return self.repository.load_names(filename, key)

    def _unique_column_values(self, key):
        """Return unique comma-delimited values used by existing cards."""
        values = set()
        for row in self.rows:
            values.update(_split(row.get(key, "")))
        return sorted(values)

    def _unique_background_modifiers(self):
        """Return modifiers encoded by existing cards' *_bg tags."""
        modifiers = set()
        for row in self.rows:
            for tag in _split(row.get("Tags", "")):
                normalized_tag = tag.lower()
                if normalized_tag.endswith("_bg") and normalized_tag[:-3]:
                    modifiers.add(normalized_tag[:-3])
        return sorted(modifiers)

    def _refresh_background_suggestions(self, text=None):
        """Refresh known modifiers while retaining the current editable value."""
        if text is None:
            text = self.background.currentText()
        self.background.blockSignals(True)
        self.background.clear()
        self.background.addItems(self._unique_background_modifiers())
        self.background.setCurrentText(text)
        self.background.blockSignals(False)

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

    # Card loading and serialization

    def _refresh_search(self, text=""):
        """Repopulate the card selector while retaining the displayed text."""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems([strip_rich_text_tags(row.get("Card Name", "")).strip() for row in self.rows])
        self.search.setCurrentText(strip_rich_text_tags(text).strip())
        self.search.blockSignals(False)

    def _filter_cards(self, text):
        """Filter card names as the user types without loading a card."""
        query = strip_rich_text_tags(text).strip().casefold()
        matches = [strip_rich_text_tags(row.get("Card Name", "")).strip() for row in self.rows if query in strip_rich_text_tags(row.get("Card Name", "")).strip().casefold()]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(matches)
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _search_activated(self):
        """Load the exact selected card after the user presses Load."""
        name = self.search.currentText().strip()
        query = strip_rich_text_tags(name).strip().casefold()
        matches = [index for index, row in enumerate(self.rows) if strip_rich_text_tags(row.get("Card Name", "")).strip().casefold() == query]
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
        card_tags = parse_card_tags(row.get("Tags", ""))

        # Load scalar card details and restore optional stat gemification.
        for name in ("Card Name", "Flavor Text"):
            self.fields[name].setText(row.get(name, ""))
        for name in ("Temple", "Tier"):
            self.fields[name].setCurrentText(row.get(name, ""))
        self.background.setCurrentText(card_tags["background"])
        self.art.setText(row.get("Art File", ""))
        for name in ("Power", "Health"):
            raw = row.get(name, "")
            gemification = cards.parse_stat_gemification(raw)
            if gemification:
                gems, effect, stat_value = gemification
                self.fields[name].setText(stat_value)
                self.fields[name + " toggle"].setChecked(True)
                self.fields[name + " gem"].set_gems(gems)
                self.fields[name + " gem"].effect.setText(effect)
            else:
                self.fields[name].setText(raw or "0")
                self.fields[name + " toggle"].setChecked(False)
        # Restore ordered fields through their own parsers and row widgets.
        self.costs.set_values(row.get("Cost", "").split(" + ") if row.get("Cost") else [])
        self.sigils.set_values(_split(row.get("Sigils", "")))
        self.traits.set_values(_split(row.get("Traits", "")))
        self.fields["Tribes"].set_values(row.get("Tribes", "").replace(",", " ").split())
        self.fields["Token"].set_values(_split(row.get("Token", "")))
        self.fields["Credit"].set_values(_split(row.get("Credit", "")))
        # Restore individual toggles and metadata encoded in the Tags column.
        self.extra_cell_amount.setValue(card_tags["extra_cells"])
        for name, check in self.tag_checks.items():
            check.setChecked(name in card_tags["tags"])
        self.left_symbol.setCurrentText(card_tags["symbols"]["left"])
        self.right_symbol.setCurrentText(card_tags["symbols"]["right"])
        self.loading = False

    def _current_row(self):
        """Serialize controls into the renderer's card dictionary format."""
        row = {field: "" for field in self.fieldnames}

        # Read scalar fields and encode stats/costs with renderer conventions.
        for name in ("Card Name", "Flavor Text"):
            row[name] = self.fields[name].text().strip()
        row["Temple"] = self.fields["Temple"].currentText().strip()
        row["Tier"] = self.fields["Tier"].currentText().strip()
        row["Art File"] = self.art.text().strip()
        for name in ("Power", "Health"):
            value = self.fields[name].text().strip()
            if self.fields[name + " toggle"].isChecked():
                row[name] = self.fields[name + " gem"].value(value)
            else:
                row[name] = value
        row["Cost"] = self.costs.serialized()
        row["Sigils"] = _join(self.sigils.values())
        row["Traits"] = _join(self.traits.values())
        row["Tribes"] = self.fields["Tribes"].serialized()
        row["Token"] = _join(self.fields["Token"].values())
        row["Credit"] = self.fields["Credit"].serialized()

        # Keep the tag sequence consistent with existing editor output.
        row["Tags"] = format_card_tags(
            self.background.currentText(),
            (name for name, check in self.tag_checks.items() if check.isChecked()),
            self.left_symbol.currentText(),
            self.right_symbol.currentText(),
            self.extra_cell_amount.value(),
        )
        return row

    # Preview and navigation

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
            scaled = pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(scaled)
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
        result = QMessageBox.warning(
            self,
            "Unsaved changes",
            "Discard unsaved changes?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
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

    # Save, export, and delete actions

    def _choose_art(self):
        """Choose art from the configured card-art directory."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose card art",
            str(ASSET_PATH),
            "Images (*.png *.jpg *.jpeg)",
        )
        if filename:
            selected = Path(filename)
            display_path = selected.name if selected.parent.resolve() == ASSET_PATH.resolve() else str(selected)
            self.art.setText(display_path)
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
            self.repository.save_cards(self.rows, self.fieldnames)
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not save cards", str(error))
            return False
        self.original = dict(row)
        self._refresh_search(row["Card Name"])
        self._refresh_background_suggestions(self.background.currentText())
        if export:
            try:
                image = cards.create_card(row)
                target = ROOT / "exports" / "cards" / row["Temple"] / row["Tier"] / f"{row['Card Name']}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
            except Exception as error:
                QMessageBox.critical(self, "Export failed", str(error))
                return False
            QMessageBox.information(self, "Card exported", f"{row['Card Name']} was exported to {target}.")
        self._render_preview()
        return True

    def _delete_card(self):
        """Delete the active card after confirmation and optional export cleanup."""
        if self.current_index < 0:
            return
        result = QMessageBox.warning(
            self,
            "Delete card",
            "Delete this card?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        row = self.rows.pop(self.current_index)
        self._refresh_background_suggestions()
        exports = ROOT / "exports" / "cards"
        delete_exports = QMessageBox.question(
            self,
            "Delete exports?",
            "Also delete exports for this card?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if delete_exports == QMessageBox.Yes:
            for candidate in (exports / f"{row['Card Name']}.png", exports / f"{row['Art File']}.png"):
                if candidate.is_file():
                    candidate.unlink()
        self._save_rows()
        self._refresh_search("")
        self._select_index(min(self.current_index, len(self.rows) - 1))

    def _save_rows(self):
        """Persist the in-memory card list using the original CSV columns."""
        self.repository.save_cards(self.rows, self.fieldnames)
