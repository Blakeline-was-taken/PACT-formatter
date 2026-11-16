"""Qt interface for editing and previewing sigils and traits."""

import csv
import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import DEFAULT_CONFIG, sigils
from ..gui_helpers import (
    Gemification,
    AspectRatioPixmapLabel,
    NoWheelComboBox,
    ROOT,
    _split,
    _join,
    create_card_preview,
    safe_filename,
    set_widget_tooltip,
)
from .data import CONDUIT_SIGIL_ICON_DIR, SIGIL_ICON_DIR, SigilTraitRepository, normalize_sigil_name
from ..tag_data import SIGIL_TRAIT_TAG_OPTIONS
from ..card_editor.fields import TagList
from ..sorting import SortDialog, sort_records
from ..error_handling import exception_details, log_exception, show_error

class SigilTraitEditor(QWidget):
    """Search, edit, preview, and save sigils and traits from their shared CSV files."""

    def __init__(self):
        """Load item data and build the initial editor state."""
        super().__init__()
        self.repository = SigilTraitRepository()
        self.data = self.repository.load_items()
        self.current_section = "Sigils"
        self.current_name = ""
        self.original = {}
        self.loading = False
        self._build_ui()
        self._refresh_search()
        self._refresh_order_list()
        names = self._names_for_current_section()
        self._select_name(names[0] if names else "")

    # Selection and form construction

    def _names_for_current_section(self):
        """Return available item names for the active category."""
        return [row.get("Name", "") for row in self.data.get(self.current_section, []) if row.get("Name")]

    def _build_ui(self):
        """Arrange the selection/order panel beside the form and preview."""
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
        splitter.setSizes([300, 860])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    def _build_sidebar(self):
        """Build the existing selectors and a draggable sigil/trait order list."""
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_header())

        order_box = QGroupBox("Sigil/Trait list")
        order_layout = QVBoxLayout(order_box)
        self.order_list = QListWidget()
        self.order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.order_list.setDefaultDropAction(Qt.MoveAction)
        self.order_list.setDragDropOverwriteMode(False)
        self.order_list.setDropIndicatorShown(True)
        self.order_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.order_list.setToolTip("Drag items to change their order in the current CSV file.")
        self.order_list.model().rowsMoved.connect(self._order_list_moved)
        self.order_list.itemDoubleClicked.connect(lambda _item: self._load_order_selection())
        order_layout.addWidget(self.order_list, 1)

        order_actions = QHBoxLayout()
        load_selected = QPushButton("Load")
        load_selected.setToolTip("Load the sigil or trait selected in the order list.")
        load_selected.clicked.connect(self._load_order_selection)
        order_actions.addWidget(load_selected, 1)
        save_order = QPushButton("Save order")
        save_order.setToolTip("Save the current collection order without saving unsaved form edits.")
        save_order.clicked.connect(self._save_order)
        order_actions.addWidget(save_order, 1)
        sort = QPushButton("Sort")
        sort.setToolTip("Sort items by one or more attributes.")
        sort.clicked.connect(self._sort_items)
        order_actions.addWidget(sort, 1)
        order_layout.addLayout(order_actions)
        layout.addWidget(order_box, 1)
        return sidebar

    # Loading and selecting items

    def _build_header(self):
        """Create the category selector, searchable item list, and new-item action."""
        box = QGroupBox("Sigil/Trait selection")
        layout = QVBoxLayout(box)
        self.category = NoWheelComboBox()
        self.category.addItems(["Sigils", "Traits"])
        self.category.setToolTip("Choose which collection to search and edit.")
        self.category.currentTextChanged.connect(self._switch_section)
        layout.addWidget(self.category)

        self.search = NoWheelComboBox()
        self.search.setEditable(True)
        self.search.setPlaceholderText("Search sigils and traits...")
        self.search.setToolTip("Search for a sigil or trait in the selected collection.")
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.lineEdit().textEdited.connect(self._filter_names)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)

        load = QPushButton("Edit")
        load.setToolTip("Load the item currently selected in the search field.")
        load.clicked.connect(self._search_activated)
        search_row.addWidget(load)
        layout.addLayout(search_row)

        new = QPushButton("+ New item")
        new.setToolTip("Clear the form and start a new sigil or trait.")
        new.clicked.connect(self._new_item)
        layout.addWidget(new)
        return box

    def _build_form(self):
        """Build the scrollable item fields and delete action."""
        container = QWidget()
        outer = QVBoxLayout(container)

        # Names and descriptions are shared by both item types.
        title = QLabel("Item data")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setToolTip("Name used by card data and to locate the item's icon asset.")
        self.name_edit.textChanged.connect(self._changed)
        form.addRow("Name", self.name_edit)

        self.display_name_enabled = QCheckBox("Override displayed name")
        self.display_name_enabled.setToolTip("Use an alternate displayed name for this sigil. Traits do not display a name.")
        self.display_name_enabled.toggled.connect(self._changed)
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("Leave blank to hide the sigil name")
        self.display_name.setToolTip("Displayed sigil name. An empty value hides the name.")
        self.display_name.setValidator(QRegularExpressionValidator(QRegularExpression("[^,]*"), self.display_name))
        self.display_name.setEnabled(False)
        self.display_name_enabled.toggled.connect(self.display_name.setEnabled)
        display_name_row = QWidget()
        display_name_layout = QHBoxLayout(display_name_row)
        display_name_layout.setContentsMargins(0, 0, 0, 0)
        display_name_layout.addWidget(self.display_name_enabled)
        display_name_layout.addWidget(self.display_name, 1)
        form.addRow("Display name", display_name_row)
        self.display_name_row = display_name_row
        self.display_name_label = form.labelForField(display_name_row)
        self.display_name.textChanged.connect(self._changed)

        self.description_edit = QLineEdit()
        self.description_edit.setToolTip("Description shown with this sigil or trait. Supports line breaks and rich-text markup.")
        self.description_edit.textChanged.connect(self._changed)
        form.addRow("Description", self.description_edit)

        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(["Sigil", "Trait"])
        self.type_combo.setToolTip("Select whether this item belongs to the sigil or trait collection.")
        self.type_combo.currentTextChanged.connect(self._changed)
        form.addRow("Type", self.type_combo)

        # These paths are discovered from the item name and selected separately.
        self.icon_edit = QLineEdit()
        self.icon_edit.setReadOnly(True)
        self.icon_edit.setToolTip("Primary icon asset used to render this sigil or trait.")
        choose_icon = QPushButton("Choose icon...")
        choose_icon.setToolTip("Choose the primary icon image for this item.")
        choose_icon.clicked.connect(self._choose_icon)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon_edit, 1)
        icon_row.addWidget(choose_icon)
        form.addRow("Icon", icon_row)

        self.colorless_icon_edit = QLineEdit()
        self.colorless_icon_edit.setReadOnly(True)
        self.colorless_icon_edit.setToolTip("Optional monochrome outline icon used for colorless exports.")
        colorless_choose_icon = QPushButton("Choose colorless icon...")
        colorless_choose_icon.setToolTip("Choose the monochrome outline icon used for colorless exports.")
        colorless_choose_icon.clicked.connect(lambda: self._choose_icon(colorless=True))
        colorless_delete_icon = QPushButton("X")
        colorless_delete_icon.setToolTip("Remove the optional colorless outline icon.")
        colorless_delete_icon.setFixedWidth(30)
        colorless_delete_icon.clicked.connect(self._delete_colorless_icon)
        colorless_icon_row = QHBoxLayout()
        colorless_icon_row.addWidget(self.colorless_icon_edit, 1)
        colorless_icon_row.addWidget(colorless_choose_icon)
        colorless_icon_row.addWidget(colorless_delete_icon)
        form.addRow("Colorless Icon", colorless_icon_row)

        self.conduit_icon_edit = QLineEdit()
        self.conduit_icon_edit.setReadOnly(True)
        self.conduit_icon_edit.setToolTip("Optional indicator artwork used when this sigil is tagged conduit_sigil.")
        conduit_choose_icon = QPushButton("Choose conduit image...")
        conduit_choose_icon.setToolTip("Choose the conduit indicator artwork for this sigil.")
        conduit_choose_icon.clicked.connect(lambda: self._choose_icon(conduit=True))
        self.conduit_icon_row = QWidget()
        conduit_icon_layout = QHBoxLayout(self.conduit_icon_row)
        conduit_icon_layout.setContentsMargins(0, 0, 0, 0)
        conduit_icon_layout.addWidget(self.conduit_icon_edit, 1)
        conduit_icon_layout.addWidget(conduit_choose_icon)

        self.tags = TagList(SIGIL_TRAIT_TAG_OPTIONS)
        self.tags.setToolTip("Add known or custom tags.")
        self.tags.changed.connect(self._changed)
        form.addRow("Tags", self.tags)
        form.addRow("Conduit image", self.conduit_icon_row)
        self.conduit_icon_label = form.labelForField(self.conduit_icon_row)

        scroll.setWidget(body)
        outer.addWidget(scroll)

        actions = QHBoxLayout()
        delete = QPushButton("Delete item")
        delete.setObjectName("dangerButton")
        delete.setToolTip("Delete this sigil or trait data record after confirmation.")
        delete.clicked.connect(self._delete_item)
        actions.addWidget(delete)
        outer.addLayout(actions)
        return container

    def _build_preview(self):
        """Create the live card preview and save/export actions."""
        box = QGroupBox("Live preview")
        layout = QVBoxLayout(box)

        self.preview = AspectRatioPixmapLabel("Select an item")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(200, 320)
        self.preview.setStyleSheet("background: #e8edf5;")
        self.preview.setToolTip("Live card preview showing this item in a sample card.")
        layout.addWidget(self.preview, 1)

        self.preview_bar = QWidget()
        preview_layout = QHBoxLayout(self.preview_bar)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_condition = NoWheelComboBox()
        self.preview_condition.addItems(["None", "Cell", "Latch", "Hint", "Gemified", "Tribal", "Rainbow"])
        self.preview_condition.setCurrentText("None")
        self.preview_condition.setToolTip("Choose a conditional style for the sample sigil preview.")
        self.preview_condition.currentTextChanged.connect(self._condition_changed)
        preview_layout.addWidget(self.preview_condition)
        self.preview_gems = Gemification(False)
        set_widget_tooltip(self.preview_gems, "Choose gem colors for the sample sigil preview.")
        self.preview_gems.setVisible(False)
        self.preview_gems.changed.connect(self._render_preview)
        preview_layout.addWidget(self.preview_gems)
        self.preview_condition.setVisible(False)
        self.preview_gems.setVisible(False)
        layout.addWidget(self.preview_bar)

        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.setToolTip("Save the current item data without exporting an icon.")
        save.clicked.connect(self._save)
        save_export = QPushButton("Save and Export")
        save_export.setToolTip("Save this item and export its selected icon assets.")
        save_export.clicked.connect(lambda: self._save(export=True))
        buttons.addWidget(save)
        buttons.addWidget(save_export)
        layout.addLayout(buttons)
        return box

    def _switch_section(self, section):
        """Switch between the sigil and trait collections."""
        self.current_section = section
        self._update_conduit_icon_visibility()
        self._update_preview_visibility()
        self._refresh_search()
        self._refresh_order_list()
        self.order_list.setCurrentRow(-1)

    def _refresh_search(self, text=""):
        """Rebuild the searchable name list while retaining the selected text."""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(self._names_for_current_section())
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _refresh_order_list(self, selected_row=None):
        """Rebuild the order list for the active collection."""
        if selected_row is None:
            selected_row = None
            for row in self.data.get(self.current_section, []):
                if row.get("Name") == self.current_name:
                    selected_row = row
                    break
        self.order_list.clear()
        self._order_records = {}
        selected_item = None
        for row in self.data.get(self.current_section, []):
            name = row.get("Name", "")
            item = QListWidgetItem(name or "(unnamed item)")
            record_id = id(row)
            self._order_records[record_id] = row
            item.setData(Qt.UserRole, record_id)
            self.order_list.addItem(item)
            if row is selected_row:
                selected_item = item
        if selected_item is not None:
            self.order_list.setCurrentItem(selected_item)
        else:
            self.order_list.setCurrentRow(-1)

    def _sync_items_from_order_list(self):
        """Apply the visible list order to the active in-memory collection."""
        self.data[self.current_section] = [self._order_records[self.order_list.item(index).data(Qt.UserRole)] for index in range(self.order_list.count())]
        self._refresh_search(self.search.currentText())

    def _order_list_moved(self, *args):
        """Keep the active collection synchronized with drag-and-drop order."""
        self._sync_items_from_order_list()

    def _load_order_selection(self):
        """Load the selected record from the order list."""
        item = self.order_list.currentItem()
        if item is not None:
            row = self._order_records.get(item.data(Qt.UserRole))
            if row is not None:
                self._select_row(row)

    def _save_order(self):
        """Persist the active collection order without serializing form edits."""
        self._sync_items_from_order_list()
        try:
            self.repository.save_items(self.data)
        except (OSError, csv.Error) as error:
            show_error(self, "Could not save item order", f"Could not save the {self.current_section.lower()} data file order.", error)
            return
        self._refresh_order_list()
        QMessageBox.information(self, "Item order saved", f"The {self.current_section.lower()} order was saved.")

    def _sort_items(self):
        rows = self.data.get(self.current_section, [])
        columns = list(rows[0].keys()) if rows else ["Name", "Description", "Tags"]
        dialog = SortDialog(columns, self.current_section, self)
        if dialog.exec() != QDialog.Accepted:
            return

        current_item = self.order_list.currentItem()
        active_record = (self._order_records.get(current_item.data(Qt.UserRole)) if current_item is not None else None)
        self.data[self.current_section] = sort_records(rows, dialog.sort_specifications())
        self._refresh_search(self.search.currentText())
        self._refresh_order_list(active_record)
        if dialog.save_on_apply:
            self._save_order()

    def _filter_names(self, text):
        """Show only active-section names containing the current query."""
        query = text.lower()
        matches = [name for name in self._names_for_current_section() if query in name.lower()]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(matches)
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _search_activated(self):
        """Load the exact item selected in the search control."""
        name = self.search.currentText().strip()
        if name and name in self._names_for_current_section():
            self._select_name(name)

    def _select_name(self, name):
        """Populate the editor from an existing item by name."""
        if not name:
            self._new_item()
            return
        row = next((item for item in self.data[self.current_section] if item.get("Name") == name), {})
        self._select_row(row)

    def _select_row(self, row):
        """Populate the editor from one exact row in the active collection."""
        name = row.get("Name", "")
        if not name:
            return
        self.current_name = name
        self.original = dict(row)
        self.original["Type"] = "Sigil" if self.current_section == "Sigils" else "Trait"
        self._populate(row)
        self._refresh_search(name)
        self._refresh_order_list(row)
        self._render_preview()

    # Preview construction and rendering

    def _new_item(self):
        """Clear the form and prepare a new item in the current category."""
        self.current_name = ""
        self.original = {}
        item_type = "Sigil" if self.current_section == "Sigils" else "Trait"
        self._populate({"Name": "", "Description": "", "Tags": "", "Type": item_type})
        self.order_list.setCurrentRow(-1)
        self._render_preview()

    def _populate(self, row):
        """Load item values and discover the corresponding icon files."""
        self.loading = True

        # Load text fields and locate standard, outline, and conduit images.
        self.name_edit.setText(row.get("Name", ""))
        self.description_edit.setText(row.get("Description", ""))
        default_type = "Sigil" if self.current_section == "Sigils" else "Trait"
        self.type_combo.setCurrentText(row.get("Type", default_type))

        icon_name = normalize_sigil_name(row.get("Name", ""))
        icon_path = SIGIL_ICON_DIR / f"{icon_name}.png"
        self.icon_edit.setText(icon_path.name if icon_name and icon_path.is_file() else "")
        icon_path = SIGIL_ICON_DIR / f"{icon_name}_outline.png"
        colorless_icon = icon_path.name if icon_name and icon_path.is_file() else ""
        self.colorless_icon_edit.setText(colorless_icon)
        conduit_icon_path = CONDUIT_SIGIL_ICON_DIR / f"{row.get('Name', '').replace(' ', '')}.png"
        conduit_icon = conduit_icon_path.name if row.get("Name") and conduit_icon_path.is_file() else ""
        self.conduit_icon_edit.setText(conduit_icon)

        tag_values = _split(row.get("Tags", ""))
        is_sigil = self.type_combo.currentText() == "Sigil"
        if is_sigil:
            display_name, display_name_enabled = sigils.parse_display_name_tag(row.get("Name", ""), tag_values)
            tag_values = [tag for tag in tag_values if tag.partition("=")[0].strip().casefold() != "display_name"]
        else:
            display_name, display_name_enabled = "", False
        self.display_name.setText(display_name if display_name_enabled else "")
        self.display_name_enabled.setChecked(display_name_enabled)
        self.tags.set_values(tag_values)
        self.loading = False
        self._update_conduit_icon_visibility()
        self._update_preview_visibility()

    def _update_conduit_icon_visibility(self):
        """Offer conduit-image selection only for conduit sigils."""
        is_conduit = self.current_section == "Sigils" and self.type_combo.currentText() == "Sigil" and any(tag.casefold() == "conduit_sigil" for tag in self.tags.values())
        self.conduit_icon_row.setVisible(is_conduit)
        self.conduit_icon_label.setVisible(is_conduit)

    def _update_preview_visibility(self):
        """Show conditional controls only when the selected item is a sigil."""
        is_sigil = self.type_combo.currentText() == "Sigil"
        self.preview_condition.setVisible(is_sigil)
        is_gemified = self.preview_condition.currentText() == "Gemified"
        self.preview_gems.setVisible(is_sigil and is_gemified)
        self.display_name_row.setVisible(is_sigil)
        self.display_name_label.setVisible(is_sigil)

    def _current_data(self):
        """Collect the current form values in the CSV item shape."""
        name = self.name_edit.text().strip()
        description = self.description_edit.text().strip()
        tags = self.tags.values()
        item_type = self.type_combo.currentText()
        if item_type == "Sigil":
            tags = [tag for tag in tags if tag.partition("=")[0].strip().casefold() != "display_name"]
            if self.display_name_enabled.isChecked():
                tags.append(f"display_name={self.display_name.text().strip()}")
        return {"Name": name, "Description": description, "Tags": _join(tags), "Type": item_type}

    def _changed(self):
        """Refresh dependent controls and preview after a user edit."""
        if not self.loading:
            self._update_conduit_icon_visibility()
            self._update_preview_visibility()
            self._render_preview()

    def _condition_changed(self):
        """Update the conditional controls and preview after condition selection."""
        self._update_preview_visibility()
        self._render_preview()

    def _preview_entry(self):
        """Build a sample card entry matching the current preview settings."""
        row = self._current_data()
        name = row["Name"] or "Example sigil"
        description = row["Description"]
        preview_type = row["Type"]

        if preview_type == "Sigil":
            conditional = self.preview_condition.currentText()
            if conditional in ("Tribal", "Rainbow"):
                current = [conditional.upper(), name]
            elif conditional in ("Cell", "Latch", "Hint"):
                current = [f"{conditional}_{name}"]
            elif conditional == "Gemified":
                current = [self.preview_gems.value(name)]
            else:
                current = [name]
            return {
                "Type": "Sigil",
                "Name": name,
                "Description": description,
                "Tags": row["Tags"],
                "Sigils": ", ".join(current),
                "Traits": "",
            }

        return {
            "Type": "Trait",
            "Name": name,
            "Description": description,
            "Tags": row["Tags"],
            "Sigils": "",
            "Traits": name,
        }

    def _render_preview(self):
        """Render the sample card and show a useful message if rendering fails."""
        try:
            row = self._preview_entry()
            current_name = row["Name"]
            current_description = row["Description"]
            current_tags = row["Tags"]

            # Preview rendering uses global lookup tables so we register the edited
            # definition and remove any conflicting entry of the other type.
            if row["Type"] == "Sigil":
                sigils.SIGILS[current_name] = sigils.Sigil(current_name, current_description, current_tags)
                for key in list(sigils.TRAITS.keys()):
                    if key == current_name:
                        del sigils.TRAITS[key]
            else:
                sigils.TRAITS[current_name] = sigils.Sigil(current_name, current_description, current_tags, is_trait=True)
                for key in list(sigils.SIGILS.keys()):
                    if key == current_name:
                        del sigils.SIGILS[key]

            # Add symbol tags so the preview displays the edited item's icon.
            card_tags = f"{current_name}_left_symbol, {current_name}_right_symbol"
            if "mox_" in current_tags:
                card_tags += ", mox_indicator"
            image = create_card_preview(sigils=row["Sigils"], traits=row["Traits"], tags=card_tags)
            pixmap = self._pixmap_for(image)
            self.preview.set_source_pixmap(pixmap)
            self.preview.setToolTip("Live card preview showing this item in a sample card.")
        except Exception as error:
            item_name = self.name_edit.text().strip() or "(unnamed item)"
            context = f"Could not render the preview for {self.current_section[:-1].lower()} {item_name!r}."
            summary = log_exception(context, error)
            self.preview.clear()
            self.preview.setText(f"Preview unavailable for {item_name}.\n{summary}")
            self.preview.setToolTip(exception_details(error))

    @staticmethod
    def _pixmap_for(image):
        """Convert a PIL image into a consistently scaled Qt preview pixmap."""
        from PySide6.QtGui import QPixmap
        from PIL.ImageQt import ImageQt

        return QPixmap.fromImage(ImageQt(image))

    # Icon and item actions

    def _choose_icon(self, colorless=False, conduit=False):
        """Copy a chosen image into the matching configured icon directory."""
        name = self.name_edit.text().strip()
        if conduit:
            icon_to_edit = self.conduit_icon_edit
        elif colorless:
            icon_to_edit = self.colorless_icon_edit
        else:
            icon_to_edit = self.icon_edit
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter a name before choosing an icon.")
            return

        icon_dir = CONDUIT_SIGIL_ICON_DIR if conduit else SIGIL_ICON_DIR
        title = "Choose conduit image" if conduit else "Choose sigil icon"
        filename, _ = QFileDialog.getOpenFileName(self, title, str(icon_dir), "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not filename:
            return

        source = Path(filename)
        outline = "_outline" if colorless else ""
        target_name = name.replace(" ", "") if conduit else normalize_sigil_name(name)
        target = icon_dir / f"{target_name}{outline}.png"
        if source.resolve() == target.resolve():
            icon_to_edit.setText(str(target.name))
            return
        if target.exists() and source.resolve() != target.resolve():
            result = QMessageBox.warning(
                self,
                "Overwrite image?",
                f"Replace the existing {target.name} image?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except OSError as error:
            show_error(self, "Could not copy icon", f"Could not copy {source} to {target}.", error)
            return
        icon_to_edit.setText(str(target.name))
        self._render_preview()

    def _delete_colorless_icon(self):
        """Confirm and remove the current item's optional outline icon."""
        name = self.name_edit.text().strip()
        if not name:
            return

        icon_name = normalize_sigil_name(name)
        target = SIGIL_ICON_DIR / f"{icon_name}_outline.png"

        if not target.is_file():
            self.colorless_icon_edit.setText("")
            return

        result = QMessageBox.warning(
            self,
            "Delete icon?",
            f"Are you sure you want to delete {target.name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            try:
                target.unlink()
            except OSError as error:
                show_error(self, "Could not delete icon", f"Could not delete icon file {target}.", error)
                return
            self.colorless_icon_edit.setText("")
            self._render_preview()

    def _save(self, export=False):
        """Validate, persist, and optionally export the current item."""
        data = self._current_data()
        name = data["Name"]

        # A type change moves the record between files and may affect card rows.
        if not name:
            QMessageBox.warning(self, "Cannot save item", "Name is required.")
            return False

        current_section = self.current_section
        current_type = "Sigil" if current_section == "Sigils" else "Trait"
        target_type = data["Type"]
        source_section = "Sigils" if current_type == "Sigil" else "Traits"
        target_section = "Sigils" if target_type == "Sigil" else "Traits"

        old_name = self.current_name
        if old_name and old_name != name and source_section != target_section:
            warning = QMessageBox.warning(
                self,
                "Type change",
                f"Changing '{old_name}' from {current_type} to {target_type} "
                f"will remove the old entry and create a new one in the "
                f"{target_type.lower()} file. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if warning != QMessageBox.Yes:
                return False

        if old_name and old_name != name and source_section != target_section:
            prompt = QMessageBox.question(
                self,
                "Update related cards?",
                f"Update cards that reference '{old_name}' so they move it "
                f"from {source_section.lower()} to {target_section.lower()}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if prompt == QMessageBox.Yes:
                try:
                    self._update_cards_for_type_change(old_name, name, source_section, target_section)
                except (OSError, csv.Error) as error:
                    show_error(self, "Could not update related cards", f"Could not update references to {old_name!r} in {self.repository.cards_path}.", error)
                    return False

        # Persist once confirmations and any related-card updates are complete.
        try:
            self.data = self.repository.write_item(self.data, old_name, name, data, target_section)
        except (OSError, csv.Error) as error:
            show_error(self, "Could not save item", f"Could not save {target_type.lower()} {name!r} to the item data files.", error)
            return False
        self.current_name = name
        self.original = dict(data)
        self.original["Type"] = target_type
        self._refresh_search(name)
        self.category.setCurrentText(target_section)
        saved_row = next(row for row in self.data[target_section] if row.get("Name") == name)
        self._refresh_order_list(saved_row)
        self._render_preview()

        # Export the matching renderer model after saving the CSV definition.
        if export:
            try:
                if target_type == "Sigil":
                    img = sigils.SIGILS[self.current_name].getImage(config=DEFAULT_CONFIG, color_map=sigils.get_color_mapping("default"))
                    export_dir = ROOT / "exports" / "sigils"
                else:
                    img = sigils.TRAITS[self.current_name].getImage(config=DEFAULT_CONFIG, color_map=sigils.get_color_mapping("default"))
                    export_dir = ROOT / "exports" / "traits"
                export_dir.mkdir(parents=True, exist_ok=True)
                target = export_dir / f"{safe_filename(name)}.png"
                img.save(target)
            except Exception as error:
                show_error(self, "Item export failed", f"Could not render or save {target_type.lower()} {name!r} to {ROOT / 'exports'}.", error)
                return False
            QMessageBox.information(self, "Exported", f"{name} was exported to {target}.")
        return True

    def _update_cards_for_type_change(self, old_name, new_name, source_section, target_section):
        """Move card references after the user approves an item type change."""
        self.repository.update_card_references(old_name, new_name, source_section, target_section)

    def _delete_item(self):
        """Confirm deletion, persist it, and reset the editor to a new item."""
        if not self.current_name:
            return
        if self.current_section not in self.data:
            return
        result = QMessageBox.warning(
            self,
            "Delete item",
            f"Delete '{self.current_name}' from the "
            f"{self.current_section.lower()} file?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        item_name = self.current_name
        try:
            self.data = self.repository.delete_item(self.data, self.current_section, item_name)
        except (OSError, csv.Error) as error:
            show_error(self, "Could not delete item", f"Could not remove {item_name!r} from the {self.current_section.lower()} data files.", error)
            return
        if self.current_section == "Sigils":
            export_dirs = (
                ("sigils", f"{item_name}.png"),
                ("short sigils", f"{item_name}.png"),
                ("base game sigils", f"{item_name}.png"),
                ("sigil patches", f"{item_name}_patch.png"),
                ("sigil icons", f"{item_name}.png"),
            )
        else:
            export_dirs = (("traits", f"{item_name}.png"),)
        delete_exports = QMessageBox.question(
            self,
            "Delete exports?",
            f"Also delete exports for '{item_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if delete_exports == QMessageBox.Yes:
            export_root = ROOT / "exports"
            failures = []
            for folder, filename in export_dirs:
                target = export_root / folder / safe_filename(filename)
                try:
                    if target.is_file():
                        target.unlink()
                except OSError as error:
                    failures.append(f"{target}: {error}")
            if failures:
                for failure in failures:
                    logging.getLogger("pact").error("Could not delete export: %s", failure)
                QMessageBox.warning(
                    self,
                    "Could not delete all exports",
                    "Some export files could not be deleted. See error.log for details.\n\n" + "\n".join(failures),
                )
        self.current_name = ""
        self._refresh_search()
        self._refresh_order_list()
        self._new_item()
