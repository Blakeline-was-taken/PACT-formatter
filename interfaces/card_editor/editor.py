"""Interactive card data editor."""

import csv
import shutil
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRegularExpression, QTimer, Qt
from PySide6.QtGui import QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import cards, sigils
from model.text import strip_rich_text_tags
from .data import (
    ASSET_PATH,
    CARD_FIELDS,
    CardRepository,
    card_export_filenames,
    card_export_path,
    format_card_tags,
    parse_card_tags,
)
from .fields import CostList, ElementList, SigilList, TagList
from ..gui_helpers import AspectRatioPixmapLabel, Gemification, NoWheelComboBox, ROOT, _split, _join, set_widget_tooltip
from ..sorting import SortDialog, sort_records

class CardEditor(QWidget):
    """Search, edit, preview, save, export, and delete card records."""

    _SIDEBAR_DEFAULT_WIDTH = 300

    def __init__(self):
        """Load card data, build the editor, and select an initial record."""
        super().__init__()
        self._sidebar_default_pending = True
        self.rows = []
        self.fieldnames = CARD_FIELDS
        self.current_index = -1
        self.original = {}
        self.loading = False
        self.repository = CardRepository()
        self._load_data()
        self._load_models()
        self._build_ui()
        self._refresh_order_list()
        self._select_index(0 if self.rows else -1)

    def showEvent(self, event):
        super().showEvent(event)
        if self._sidebar_default_pending:
            self._sidebar_default_pending = False
            QTimer.singleShot(0, self._set_default_sidebar_width)

    def _set_default_sidebar_width(self):
        splitter = self._sidebar_splitter
        available_width = max(0, splitter.width() - splitter.handleWidth())
        sidebar_width = min(self._SIDEBAR_DEFAULT_WIDTH, available_width)
        splitter.setSizes([sidebar_width, available_width - sidebar_width])

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
        """Create the left selection/order panel and editor/preview area."""
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_sidebar())

        content = QSplitter(Qt.Horizontal)
        content.addWidget(self._build_form())
        content.addWidget(self._build_preview())
        content.setSizes([300, 360])
        content.setStretchFactor(0, 1)
        content.setStretchFactor(1, 0)
        splitter.addWidget(content)
        splitter.setSizes([self._SIDEBAR_DEFAULT_WIDTH, 830])
        self._sidebar_splitter = splitter
        root.addWidget(splitter, 1)

    def _build_sidebar(self):
        """Build card selection controls and the draggable card-order list."""
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_header())

        order_box = QGroupBox("Card order")
        order_layout = QVBoxLayout(order_box)
        self.order_list = QListWidget()
        self.order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.order_list.setDefaultDropAction(Qt.MoveAction)
        self.order_list.setDragDropOverwriteMode(False)
        self.order_list.setDropIndicatorShown(True)
        self.order_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.order_list.setToolTip("Drag cards to change their order in cards.csv.")
        self.order_list.model().rowsMoved.connect(self._order_list_moved)
        order_layout.addWidget(self.order_list, 1)

        order_actions = QHBoxLayout()
        load_selected = QPushButton("Load")
        load_selected.setToolTip("Load the card selected in the order list.")
        load_selected.clicked.connect(self._load_order_selection)
        order_actions.addWidget(load_selected, 1)
        save_order = QPushButton("Save order")
        save_order.setToolTip("Save the card order to cards.csv.")
        save_order.clicked.connect(self._save_order)
        order_actions.addWidget(save_order, 1)
        sort = QPushButton("Sort")
        sort.setToolTip("Sort cards by one or more attributes.")
        sort.clicked.connect(self._sort_cards)
        order_actions.addWidget(sort, 1)
        order_layout.addLayout(order_actions)
        layout.addWidget(order_box, 1)
        return sidebar

    # Card form construction

    def _build_header(self):
        """Build the searchable card selector and new-card actions."""
        box = QGroupBox("Card selection")
        layout = QVBoxLayout(box)
        self.search = NoWheelComboBox()
        self.search.setEditable(True)
        self.search.setPlaceholderText("Search cards by name...")
        self.search.setToolTip("Search existing cards by name, then load one to edit.")
        self.search.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.search.lineEdit().textEdited.connect(self._filter_cards)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        edit = QPushButton("Edit")
        edit.setText("Load")
        edit.setToolTip("Load the card currently selected in the search field.")
        edit.clicked.connect(self._search_activated)
        search_row.addWidget(edit)
        layout.addLayout(search_row)
        new = QPushButton("+ New card")
        new.setToolTip("Clear the form and start a new card record.")
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
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.fields = {}

        # Basic identity fields and the card's template selectors.
        for name in ("Card Name", "Flavor Text"):
            edit = QLineEdit()
            edit.setToolTip("Name shown on the card." if name == "Card Name" else "Narrative text shown on the card.")
            edit.textChanged.connect(self._changed)
            self.fields[name] = edit
            form.addRow(name, edit)

        self.temple = self._suggested_field(self._unique_column_values("Temple"))
        self.tier = self._suggested_field(self._unique_column_values("Tier"))
        self.background = self._suggested_field(self._unique_background_modifiers())
        self.temple.setToolTip("Temple used to choose the card's assets and template.")
        self.tier.setToolTip("Tier used to choose the card's assets and template.")
        self.background.setToolTip("Optional background modifier used to select assets and template.")
        self.fields["Temple"] = self.temple
        self.fields["Tier"] = self.tier
        self.fields["Background"] = self.background
        form.addRow("Temple", self.temple)
        form.addRow("Tier", self.tier)

        self.art = QLineEdit()
        self.art.setReadOnly(True)
        self.art.setToolTip("Card-art image filename from the general card-art asset folder.")
        choose = QPushButton("Choose file...")
        choose.setToolTip("Choose the image used as this card's artwork.")
        choose.clicked.connect(self._choose_art)
        art_row = QHBoxLayout()
        art_row.addWidget(self.art, 1)
        art_row.addWidget(choose)
        form.addRow("Art file", art_row)

        # Ordered values use specialized widgets to preserve renderer syntax.
        self.power = self._stat_editor("Power", form)
        self.health = self._stat_editor("Health", form)
        self.costs = CostList()
        set_widget_tooltip(self.costs, "Build the card's cost by adding resources.")
        self.costs.changed.connect(self._changed)
        form.addRow("Cost", self.costs)
        sigil_options = self._load_names("sigils.csv", "Name") + ["TRIBAL", "RAINBOW"]
        self.sigils = SigilList(sigil_options)
        set_widget_tooltip(self.sigils, "Add sigils, or \"TRIBAL\"/\"ARCANE\" for the non-sigil-specific conditionals. Each row can have a conditional.")
        self.sigils.changed.connect(self._changed)
        form.addRow("Sigils", self.sigils)
        self.traits = ElementList("Traits", self._load_names("traits.csv", "Name"))
        set_widget_tooltip(self.traits, "Add traits.")
        self.traits.changed.connect(self._changed)
        form.addRow("Traits", self.traits)
        tribes = self._unique_tribes()
        for name in ("Tribes", "Token", "Credit"):
            options = tribes if name == "Tribes" else self._unique_column_values("Credit")
            widget = ElementList(name, options, suggestions=name != "Token")
            widget.delimiter = " " if name == "Tribes" else ", "
            descriptions = {
                "Tribes": "Tribes displayed with tribe icons.",
                "Token": "Values inserted in order wherever a sigil or trait description contains the TOKEN keyword.",
                "Credit": "Artist attributions shown at the bottom of the card.",
            }
            set_widget_tooltip(widget, descriptions[name])
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
        delete.setToolTip("Delete this card's data record.")
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
        value.setToolTip(f"Base {name.lower()} value, or the text value used for gemification.")
        value.textChanged.connect(self._changed)
        layout.addWidget(value, 1)
        toggle = QPushButton("Gemified")
        toggle.setToolTip(f"Enable gemification controls for the card's {name.lower()}.")
        toggle.setCheckable(True)
        gem = Gemification(True)
        set_widget_tooltip(gem, "Choose the gem color and optional gemification text for this stat.")
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
        """Build the free-form tag list and dedicated special-tag controls."""
        widget = QWidget()
        widget.setToolTip("Appearance and layout tags used when rendering this card.")
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tag_list = TagList()
        self.tag_list.setToolTip("This is a custom tag that does nothing.")
        self.tag_list.changed.connect(self._changed)
        outer.addWidget(self.tag_list)

        self.display_name_enabled = QCheckBox("Override displayed name")
        self.display_name_enabled.setToolTip("When checked, display the value below instead of Card Name.")
        self.display_name_enabled.toggled.connect(self._changed)
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("Leave blank to hide the card name")
        self.display_name.setToolTip("Displayed card name. An empty value hides the name; commas are reserved as tag separators.")
        self.display_name.setValidator(QRegularExpressionValidator(QRegularExpression("[^,]*"), self.display_name))
        self.display_name.setEnabled(False)
        self.display_name_enabled.toggled.connect(self.display_name.setEnabled)
        self.display_name.textChanged.connect(self._changed)
        display_name_row = QHBoxLayout()
        display_name_row.addWidget(self.display_name_enabled)
        display_name_row.addWidget(self.display_name, 1)
        outer.addLayout(display_name_row)

        background_row = QHBoxLayout()
        background_label = QLabel("Background")
        background_label.setToolTip("Optional background modifier used to select assets and template.")
        background_row.addWidget(background_label)
        background_row.addWidget(self.background, 1)
        outer.addLayout(background_row)

        self.extra_cell_amount = QSpinBox()
        self.extra_cell_amount.setRange(0, 99)
        self.extra_cell_amount.setPrefix("Extra cells: ")
        set_widget_tooltip(self.extra_cell_amount, "Number of extra energy cells to show.")
        self.extra_cell_amount.valueChanged.connect(self._changed)
        outer.addWidget(self.extra_cell_amount)

        symbol_options = self._load_names("sigils.csv", "Name")
        self.left_symbol = self._suggested_field(symbol_options)
        self.right_symbol = self._suggested_field(symbol_options)
        self.left_symbol.setToolTip("Sigil symbol shown at the bottom-left of the card.")
        self.right_symbol.setToolTip("Sigil symbol shown at the bottom-right of the card.")
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
        self.preview = AspectRatioPixmapLabel("Select a card")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(200, 320)
        self.preview.setStyleSheet("background: #e8edf5;")
        self.preview.setToolTip("Live card preview. Changes appear here before you save or export.")
        layout.addWidget(self.preview, 1)
        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.setToolTip("Save the current card data without exporting an image.")
        save.clicked.connect(self._save)
        save_export = QPushButton("Save and Export")
        save_export.setToolTip("Save the current card data and render its image.")
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
        self._select_order_record(self.rows[index])
        self._render_preview()

    def _refresh_order_list(self, selected_record=None):
        """Rebuild the order list while retaining the active record selection."""
        if selected_record is None and 0 <= self.current_index < len(self.rows):
            selected_record = self.rows[self.current_index]
        self.order_list.clear()
        self._order_records = {}
        selected_item = None
        for row in self.rows:
            name = strip_rich_text_tags(row.get("Card Name", "")).strip()
            item = QListWidgetItem(name or "(unnamed card)")
            record_id = id(row)
            self._order_records[record_id] = row
            item.setData(Qt.UserRole, record_id)
            self.order_list.addItem(item)
            if row is selected_record:
                selected_item = item
        if selected_item is not None:
            self.order_list.setCurrentItem(selected_item)
        else:
            self.order_list.setCurrentRow(-1)

    def _select_order_record(self, row):
        """Highlight the row corresponding to the card currently in the form."""
        for index in range(self.order_list.count()):
            item = self.order_list.item(index)
            if item.data(Qt.UserRole) == id(row):
                self.order_list.setCurrentItem(item)
                return

    def _sync_rows_from_order_list(self):
        """Apply the visible list order to the in-memory CSV rows."""
        active_record = self.rows[self.current_index] if 0 <= self.current_index < len(self.rows) else None
        self.rows = [self._order_records[self.order_list.item(index).data(Qt.UserRole)] for index in range(self.order_list.count())]
        if active_record is not None:
            self.current_index = next((index for index, row in enumerate(self.rows) if row is active_record), -1)
        self._refresh_search(self.original.get("Card Name", "") if self.current_index >= 0 else self.search.currentText())

    def _order_list_moved(self, *args):
        """Keep the editor's record indices synchronized with drag-and-drop."""
        self._sync_rows_from_order_list()

    def _load_order_selection(self):
        """Load the selected card from the order list after dirty-state checks."""
        item = self.order_list.currentItem()
        if item is None:
            return
        row = self._order_records.get(item.data(Qt.UserRole))
        if row is None:
            return
        index = next((index for index, candidate in enumerate(self.rows) if candidate is row), -1)
        if index >= 0 and self._confirm_navigation():
            self._select_index(index)

    def _save_order(self):
        """Persist the reordered card rows without serializing current form edits."""
        self._sync_rows_from_order_list()
        try:
            self.repository.save_cards(self.rows, self.fieldnames)
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not save card order", str(error))
            return
        self._refresh_order_list()
        QMessageBox.information(self, "Card order saved", "The card order was saved to cards.csv.")

    def _sort_cards(self):
        dialog = SortDialog(self.fieldnames or CARD_FIELDS, "Cards", self)
        if dialog.exec() != QDialog.Accepted:
            return

        active_record = self.rows[self.current_index] if 0 <= self.current_index < len(self.rows) else None
        self.rows = sort_records(self.rows, dialog.sort_specifications())
        if active_record is not None:
            self.current_index = next((index for index, row in enumerate(self.rows) if row is active_record), -1)
        self._refresh_order_list(active_record)
        search_text = self.original.get("Card Name", "") if self.current_index >= 0 else self.search.currentText()
        self._refresh_search(search_text)
        if dialog.save_on_apply:
            self._save_order()

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
                self.fields[name].setText(raw or ("1" if name == "Health" else "0"))
                self.fields[name + " toggle"].setChecked(False)
        # Restore ordered fields through their own parsers and row widgets.
        self.costs.set_values(row.get("Cost", "").split(" + ") if row.get("Cost") else [])
        self.sigils.set_values(_split(row.get("Sigils", "")))
        self.traits.set_values(_split(row.get("Traits", "")))
        self.fields["Tribes"].set_values(row.get("Tribes", "").replace(",", " ").split())
        self.fields["Token"].set_values(_split(row.get("Token", "")))
        self.fields["Credit"].set_values(_split(row.get("Credit", "")))
        # Restore tags and special metadata encoded in the Tags column.
        self.extra_cell_amount.setValue(card_tags["extra_cells"])
        self.tag_list.set_values(card_tags["general_tags"])
        self.display_name_enabled.setChecked(card_tags["display_name_enabled"])
        self.display_name.setText(card_tags["display_name"])
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
            self.tag_list.values(),
            self.left_symbol.currentText(),
            self.right_symbol.currentText(),
            self.extra_cell_amount.value(),
            self.display_name.text(),
            self.display_name_enabled.isChecked(),
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
            self.preview.set_source_pixmap(pixmap)
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
        new_row = {field: "" for field in CARD_FIELDS}
        new_row["Health"] = "1"
        self._populate(new_row)
        self.art.setText("")
        self._refresh_search("")
        self.order_list.setCurrentRow(-1)
        self._render_preview()

    # Save, export, and delete actions

    def _choose_art(self):
        """Choose art from the configured card-art directory."""
        filename, _ = QFileDialog.getOpenFileName(self, "Choose card art", str(ASSET_PATH), "Images (*.png *.jpg *.jpeg)")
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
            self._refresh_order_list(row)
            QMessageBox.critical(self, "Could not save cards", str(error))
            return False
        self.original = dict(row)
        self._refresh_search(row["Card Name"])
        self._refresh_background_suggestions(self.background.currentText())
        self._refresh_order_list(row)
        if export:
            try:
                image = cards.create_card(row)
                filenames = card_export_filenames(self.rows, sorted_by_folder=True)
                target = card_export_path(row, filenames[self.current_index], ROOT / "exports", sorted_by_folder=True)
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
        self._refresh_order_list()
