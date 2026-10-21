"""Interactive editor for layered template configuration."""

import csv
import copy
import json

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import DEFAULT_CONFIG, sigils
from ..gui_helpers import NoWheelComboBox, ROOT, create_card_preview
from .data import (
    COORDINATE_FIELDS,
    SUBSECTION_FIELDS,
    TEMPLATE_DEFAULTS,
    TEMPLATE_SECTIONS,
    effective_config,
    read_config,
    read_selector_values,
    target_layer,
    write_config,
)


class TemplateEditor(QWidget):
    """Load, edit, preview, and save template values across config layers."""

    def __init__(self):
        """Load template data, initialize editor state, and build the interface."""
        super().__init__()
        self._loading = False
        self._active_section = ""
        self._loaded_selection = ("default", "default", "default")
        self._loaded_values = {}
        self._effective_values = {}
        self._field_controls = {}
        self._section_bodies = {}
        self._section_buttons = {}
        self._subsection_buttons = {}
        self._subsection_bodies = {}
        self._active_subsection = {}
        self._text_colors = {}
        self._loaded_text_colors = {}
        self._editing_color_key = None
        self._color_entries = []
        self._loading_color_editor = False
        self._config_tree = self._read_config()

        try:
            cards_path = ROOT / DEFAULT_CONFIG["cards_file_path"]
            self._temple_options, self._tier_options, self._modifier_options = read_selector_values(cards_path)
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not load template options", str(error))
            self._temple_options, self._tier_options, self._modifier_options = [], [], []

        self._build_ui()
        self._load_selection(self._loaded_selection)

    # Configuration and main editor layout

    def _read_config(self):
        """Load configuration and display a dialog before propagating read errors."""
        try:
            return read_config()
        except (OSError, json.JSONDecodeError) as error:
            QMessageBox.critical(self, "Could not load configuration", str(error))
            raise

    def _build_ui(self):
        """Arrange the selector header above the settings and preview panes."""
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_sections())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([560, 500])
        root.addWidget(splitter, 1)

    def _build_header(self):
        """Build the temple, tier, and background selectors."""
        box = QGroupBox("Template configuration")
        layout = QHBoxLayout(box)
        self.temple_selector = self._make_selector("Temple", self._temple_options)
        self.tier_selector = self._make_selector("Tier", self._tier_options)
        self.modifier_selector = self._make_selector("Background modifier", self._modifier_options)
        for selector in (self.temple_selector, self.tier_selector, self.modifier_selector):
            layout.addWidget(selector, 1)

        load = QPushButton("Load")
        load.clicked.connect(self._load_requested)
        layout.addWidget(load)
        return box

    @staticmethod
    def _make_selector(placeholder, values):
        """Create an editable selector populated with known values."""
        selector = NoWheelComboBox()
        selector.setEditable(True)
        selector.setInsertPolicy(QComboBox.NoInsert)
        selector.setPlaceholderText(placeholder)
        selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selector.addItems(values)
        selector.setCurrentIndex(-1)
        return selector

    def _build_sections(self):
        """Build collapsible settings sections and their optional subsections."""
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 8, 0)
        title = QLabel("Template settings")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(6)

        for section_name, options in TEMPLATE_SECTIONS.items():
            # Each section owns one body; specialized sections add their own UI.
            button = QPushButton(section_name)
            button.setCheckable(True)
            button.setChecked(False)
            button.setObjectName("templateSectionButton")
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked, name=section_name: self._toggle_section(name, checked))
            body_layout.addWidget(button)
            section_body = QWidget()
            section_layout = QVBoxLayout(section_body)
            section_layout.setContentsMargins(10, 8, 10, 12)
            if section_name == "Rich Text Colors":
                self._build_color_editor(section_layout)
            elif section_name in SUBSECTION_FIELDS:
                # Cost settings have both shared fields and per-cost subsections.
                if section_name == "Cost":
                    self._add_fields(section_layout, options)
                subsection_names = tuple(SUBSECTION_FIELDS[section_name])
                subsection_nav = QWidget()
                subsection_nav_layout = QHBoxLayout(subsection_nav)
                subsection_nav_layout.setContentsMargins(0, 0, 0, 4)
                subsection_nav_layout.setSpacing(4)
                self._subsection_buttons[section_name] = {}
                self._subsection_bodies[section_name] = {}
                self._active_subsection[section_name] = subsection_names[0]
                for subsection_name in subsection_names:
                    sub_button = QPushButton(subsection_name)
                    sub_button.setCheckable(True)
                    sub_button.setObjectName("templateSubsectionButton")
                    sub_button.clicked.connect(lambda checked=False, section=section_name, name=subsection_name: self._open_subsection(section, name))
                    subsection_nav_layout.addWidget(sub_button)
                    self._subsection_buttons[section_name][subsection_name] = sub_button
                section_layout.addWidget(subsection_nav)

                # Build one body for each subsection and display only the active one.
                for subsection_name, fields in SUBSECTION_FIELDS[section_name].items():
                    sub_body = QWidget()
                    sub_layout = QVBoxLayout(sub_body)
                    sub_layout.setContentsMargins(0, 0, 0, 0)
                    if fields:
                        self._add_fields(sub_layout, fields)
                    else:
                        sub_layout.addWidget(QLabel("No additional spacing values for this cost."))
                    sub_body.setVisible(subsection_name == subsection_names[0])
                    section_layout.addWidget(sub_body)
                    self._subsection_bodies[section_name][subsection_name] = sub_body
            else:
                self._add_fields(section_layout, options)
            section_body.hide()
            body_layout.addWidget(section_body)
            self._section_bodies[section_name] = section_body
            self._section_buttons[section_name] = button
        body_layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        restore = QPushButton("Restore Default Settings")
        restore.clicked.connect(self._restore_defaults)
        outer.addWidget(restore)
        return container

    def _add_fields(self, parent_layout, options):
        """Create controls for one group of settings and register each control."""
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(8)
        for key, default_value in options.items():
            # Coordinate settings are edited as paired X/Y values.
            if isinstance(default_value, list) and key in COORDINATE_FIELDS:
                field_widget = QWidget()
                coordinate_layout = QHBoxLayout(field_widget)
                coordinate_layout.setContentsMargins(0, 0, 0, 0)
                coordinates = []
                for axis, value in zip(("X", "Y"), default_value):
                    coordinate_layout.addWidget(QLabel(axis))
                    spin = self._make_number_control(key, value)
                    coordinate_layout.addWidget(spin, 1)
                    coordinates.append(spin)
                control = tuple(coordinates)
                form.addRow(key.replace("_", " ").title(), field_widget)
            else:
                control = self._make_field_control(key, default_value)
                form.addRow(key.replace("_", " ").title(), control)
            self._field_controls[key] = control
        parent_layout.addLayout(form)

    # Rich-text palette editing

    def _build_color_editor(self, parent_layout):
        """Add color search, name, palette-entry, and create/remove controls."""
        search_row = QHBoxLayout()
        self.color_search = NoWheelComboBox()
        self.color_search.setEditable(True)
        self.color_search.setInsertPolicy(QComboBox.NoInsert)
        self.color_search.setPlaceholderText("Search colors")
        self.color_search.activated.connect(self._select_color_from_search)
        self.color_search.lineEdit().returnPressed.connect(self._select_color_from_search_text)
        self.color_search.lineEdit().textEdited.connect(lambda text: self._update_color_remove_button())
        search_row.addWidget(self.color_search, 1)
        create = QPushButton("Create new")
        create.clicked.connect(self._create_color)
        search_row.addWidget(create)
        remove_color = QPushButton("Remove")
        remove_color.clicked.connect(self._remove_selected_color)
        remove_color.setEnabled(False)
        search_row.addWidget(remove_color)
        self.remove_color_button = remove_color
        parent_layout.addLayout(search_row)

        form = QFormLayout()
        self.color_name = QLineEdit()
        self.color_name.textChanged.connect(self._color_editor_changed)
        form.addRow("Name", self.color_name)
        parent_layout.addLayout(form)

        self.color_entries_layout = QVBoxLayout()
        self.color_entries_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addLayout(self.color_entries_layout)
        add_entry = QPushButton("Add palette color")
        add_entry.clicked.connect(lambda: self._add_color_entry())
        parent_layout.addWidget(add_entry)

    def _refresh_color_search(self, selected=""):
        """Refresh color suggestions while preserving the current edit name."""
        names = sorted(self._text_colors, key=str.casefold)
        self.color_search.blockSignals(True)
        self.color_search.clear()
        self.color_search.addItems(names)
        self.color_search.setCurrentIndex(-1)
        self.color_search.setEditText(selected)
        self.color_search.blockSignals(False)

    def _select_color_from_search(self, index):
        """Load the color selected from the suggestion list."""
        name = self.color_search.itemText(index)
        self._load_color_editor(name)
        self._request_preview(immediate=True)
        self._update_color_remove_button()

    def _select_color_from_search_text(self):
        """Load a color when its name is entered and confirmed."""
        name = self.color_search.currentText().strip()
        match = next((key for key in self._text_colors if key.casefold() == name.casefold()), None)
        if match is not None:
            self._load_color_editor(match)
            self._request_preview(immediate=True)
            self._update_color_remove_button()

    def _load_color_editor(self, name):
        """Populate the palette controls from one stored color definition."""
        entries = self._color_entries_from_value(name, self._text_colors[name])
        self._editing_color_key = name
        self._loading_color_editor = True
        self.color_name.blockSignals(True)
        self.color_name.setText(name)
        self.color_name.blockSignals(False)
        self._clear_color_entries()
        for entry_type, value in entries:
            self._add_color_entry(entry_type, value)
        self._loading_color_editor = False
        self._refresh_color_search(name)
        self._update_color_entry_buttons()
        self._request_preview(immediate=True)
        self._update_color_remove_button()

    @staticmethod
    def _color_entries_from_value(name, value):
        """Validate and decode supported RGB and palette-index color formats."""
        # A single RGB triplet or index is accepted alongside a list of entries.
        if isinstance(value, dict) and set(value) == {"index"}:
            entries = [value]
        elif isinstance(value, list) and len(value) == 3 and all(
                isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255 for channel in value
            ):
            entries = [value]
        elif isinstance(value, list) and value:
            entries = value
        else:
            raise ValueError(f"Text color '{name}' has an unsupported value.")

        parsed = []

        # Validate each palette member before it reaches the numeric controls.
        for entry in entries:
            if isinstance(entry, dict) and set(entry) == {"index"}:
                index = entry["index"]
                if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= 1_000_000:
                    raise ValueError(f"Text color '{name}' contains an invalid palette index.")
                parsed.append(("Color index", index))
            elif isinstance(entry, list) and len(entry) == 3 and all(
                    isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255 for channel in entry
                ):
                parsed.append(("RGB color", entry))
            else:
                raise ValueError(f"Text color '{name}' contains an unsupported palette entry.")
        return parsed

    def _clear_color_entries(self):
        """Remove palette-entry widgets and reset their backing records."""
        while self.color_entries_layout.count():
            item = self.color_entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._color_entries.clear()

    def _add_color_entry(self, entry_type="RGB color", value=None):
        """Create a palette row with either RGB channels or a color index."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        type_selector = NoWheelComboBox()
        type_selector.addItems(["RGB color", "Color index"])
        type_selector.setCurrentText(entry_type)
        layout.addWidget(type_selector)

        index = QSpinBox()
        index.setRange(1, 1_000_000)
        red = QSpinBox()
        green = QSpinBox()
        blue = QSpinBox()
        for control in (red, green, blue):
            control.setRange(0, 255)
        rgb_widget = QWidget()
        rgb_layout = QHBoxLayout(rgb_widget)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        for label, control in (("R", red), ("G", green), ("B", blue)):
            channel = QWidget()
            channel_layout = QHBoxLayout(channel)
            channel_layout.setContentsMargins(0, 0, 0, 0)
            channel_layout.setSpacing(4)
            channel_label = QLabel(label)
            channel_label.setFixedWidth(14)
            control.setFixedWidth(72)
            channel_layout.addWidget(channel_label)
            channel_layout.addWidget(control)
            rgb_layout.addWidget(channel)
        layout.addWidget(index)
        layout.addWidget(rgb_widget, 1)

        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: self._remove_color_entry(row))
        layout.addWidget(remove)
        record = {
            "row": row,
            "type": type_selector,
            "index": index,
            "rgb_widget": rgb_widget,
            "rgb": (red, green, blue),
            "remove": remove,
        }
        self._color_entries.append(record)
        self.color_entries_layout.addWidget(row)

        # Restore a saved value, or initialize a new palette entry to black.
        if isinstance(value, int):
            index.setValue(value)
        elif isinstance(value, list) and len(value) == 3:
            for control, channel in zip((red, green, blue), value):
                control.setValue(channel)
        else:
            index.setValue(1)
            red.setValue(0)
            green.setValue(0)
            blue.setValue(0)

        type_selector.currentTextChanged.connect(lambda selected, color_record=record: self._update_color_entry_type(color_record, selected))
        index.valueChanged.connect(self._color_editor_changed)
        for control in (red, green, blue):
            control.valueChanged.connect(self._color_editor_changed)
        self._update_color_entry_type(record, entry_type)
        self._update_color_entry_buttons()
        self._color_editor_changed()

    def _update_color_entry_type(self, record, entry_type):
        """Show only the controls that match a palette row's selected type."""
        is_index = entry_type == "Color index"
        record["index"].setVisible(is_index)
        record["rgb_widget"].setVisible(not is_index)
        self._color_editor_changed()

    def _remove_color_entry(self, row):
        """Remove one palette row and refresh the editor state."""
        record = next(record for record in self._color_entries if record["row"] is row)
        self._color_entries.remove(record)
        self.color_entries_layout.removeWidget(row)
        row.deleteLater()
        self._update_color_entry_buttons()
        self._color_editor_changed()

    def _update_color_entry_buttons(self):
        """Prevent removing the last palette entry from a color."""
        for record in self._color_entries:
            record["remove"].setEnabled(len(self._color_entries) > 1)

    def _update_color_remove_button(self):
        """Enable removal only when the search text matches an existing color."""
        name = self.color_search.currentText().strip()
        exists = any(key.casefold() == name.casefold() for key in self._text_colors)
        self.remove_color_button.setEnabled(exists)

    def _remove_selected_color(self):
        """Remove the selected color and load another color if available."""
        name = self.color_search.currentText().strip()
        match = next((key for key in self._text_colors if key.casefold() == name.casefold()), None)
        if match is None:
            return
        del self._text_colors[match]
        if self._text_colors:
            next_color = sorted(self._text_colors, key=str.casefold)[0]
            self._load_color_editor(next_color)
        else:
            self._editing_color_key = None
            self._loading_color_editor = True
            self.color_name.clear()
            self._loading_color_editor = False
            self._clear_color_entries()
            self._refresh_color_search()
            self.remove_color_button.setEnabled(False)
            self._request_preview(immediate=True)
        self._field_changed()

    def _color_editor_value(self):
        """Serialize the current palette rows into the config color format."""
        values = []
        for record in self._color_entries:
            if record["type"].currentText() == "Color index":
                values.append({"index": record["index"].value()})
            else:
                values.append([control.value() for control in record["rgb"]])
        return values

    def _color_editor_changed(self, *args):
        """Update the in-memory palette when the active color is edited."""
        if self._loading or self._loading_color_editor or self._editing_color_key is None:
            return
        name = self.color_name.text().strip()
        colors = copy.deepcopy(self._text_colors)
        colors.pop(self._editing_color_key, None)
        colors[name] = self._color_editor_value()
        self._text_colors = colors
        self._editing_color_key = name
        self._refresh_color_search(name)
        self._request_preview()

    def _create_color(self):
        """Prompt for a unique color name and initialize a black RGB entry."""
        name, accepted = QInputDialog.getText(self, "Create rich text color", "Color name:")
        name = name.strip()
        if not accepted:
            return
        if not name:
            QMessageBox.warning(self, "Invalid color name", "Color names cannot be empty.")
            return
        if any(character in name for character in "{}"):
            QMessageBox.warning(self, "Invalid color name", "Color names cannot contain braces.")
            return
        if any(key.casefold() == name.casefold() for key in self._text_colors):
            QMessageBox.warning(
                self,
                "Color already exists",
                f"A color named '{name}' already exists.",
            )
            return
        self._text_colors[name] = [[0, 0, 0]]
        self._load_color_editor(name)
        self._field_changed()

    # Settings controls and card preview

    def _make_field_control(self, key, default_value):
        """Choose a widget based on the setting's default value type."""
        if isinstance(default_value, bool):
            control = QCheckBox()
            control.toggled.connect(self._field_changed)
        elif key == "font":
            control = NoWheelComboBox()
            control.setEditable(False)
            fonts_dir = ROOT / "data" / "fonts"
            fonts = {path.stem for path in fonts_dir.iterdir() if path.is_file() and path.suffix.lower() == ".ttf"}
            control.addItems(sorted(fonts, key=str.casefold))
            control.setMaxVisibleItems(12)
            control.currentTextChanged.connect(self._field_changed)
        elif isinstance(default_value, int):
            control = self._make_number_control(key, default_value)
        else:
            control = QLineEdit()
            control.textChanged.connect(self._field_changed)
        control.setProperty("config-key", key)
        return control

    def _make_number_control(self, key, value):
        """Create a bounded numeric control connected to change tracking."""
        control = QSpinBox()
        control.setRange(-1_000_000, 1_000_000)
        control.setValue(value)
        control.valueChanged.connect(self._field_changed)
        control.setProperty("config-key", key)
        return control

    def _build_preview(self):
        """Create the preview image, line-count controls, and save action."""
        box = QGroupBox("Card preview")
        layout = QVBoxLayout(box)
        self.preview = QLabel("Load template values")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 420)
        self.preview.setStyleSheet("background: #e8edf5;")
        layout.addWidget(self.preview, 1)

        preview_lines = QHBoxLayout()
        self.preview_sigil_lines = self._make_preview_line_control("Sigil lines", preview_lines)
        self.preview_trait_lines = self._make_preview_line_control("Trait lines", preview_lines)
        layout.addLayout(preview_lines)

        save = QPushButton("Save")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._render_preview)
        return box

    def _make_preview_line_control(self, label, layout):
        """Add a bounded line-count control to the preview options."""
        layout.addWidget(QLabel(label))
        control = QSpinBox()
        control.setRange(1, 8)
        control.setValue(1)
        control.valueChanged.connect(self._request_preview)
        layout.addWidget(control, 1)
        return control

    # Selection, loading, and form-state conversion

    def _selection_from_header(self):
        """Normalize the selector values into a config-layer tuple."""
        values = (
            self.temple_selector.currentText().strip(),
            self.tier_selector.currentText().strip(),
            self.modifier_selector.currentText().strip(),
        )
        temple, tier, modifier = (value.lower() for value in values)
        modifier = modifier[:-3] if modifier.endswith("_bg") else modifier
        return temple or "default", tier or "default", modifier or "default"

    def _load_requested(self):
        """Confirm discarding edits before loading the selected config layer."""
        if self._has_unsaved_changes():
            answer = QMessageBox.question(
                self,
                "Discard template changes?",
                "Loading another template configuration will discard your unsaved changes. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        self._load_selection(self._selection_from_header())

    def _load_selection(self, selection):
        """Load inherited settings and refresh the controls for one layer."""
        try:
            self._config_tree = self._read_config()
            self._effective_values = effective_config(self._config_tree, *selection)

            # Start with defaults, then apply values inherited from this layer path.
            values = {key: self._effective_values.get(key, default_value) for key, default_value in TEMPLATE_DEFAULTS.items()}
        except (OSError, json.JSONDecodeError, ValueError) as error:
            QMessageBox.critical(self, "Could not load template settings", str(error))
            return

        self._loaded_selection = selection
        self._loaded_values = {key: value for key, value in values.items()}
        self._loading = True

        # Update controls without triggering preview work for each individual field.
        for key, value in values.items():
            self._set_control_value(self._field_controls[key], value)
        # Validate rich-text colors before populating the palette editor.
        text_colors = self._effective_values.get("text_colors", {})
        if not isinstance(text_colors, dict):
            self._loading = False
            QMessageBox.critical(
                self,
                "Could not load template settings",
                "'text_colors' must be an object.",
            )
            return
        try:
            for name, value in text_colors.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Text color names must be non-empty strings.")
                self._color_entries_from_value(name, value)
        except ValueError as error:
            self._loading = False
            QMessageBox.critical(self, "Could not load template settings", str(error))
            return
        self._text_colors = copy.deepcopy(text_colors)
        self._loaded_text_colors = copy.deepcopy(text_colors)
        if text_colors:
            first_color = sorted(text_colors, key=str.casefold)[0]
            self._load_color_editor(first_color)
        else:
            self._editing_color_key = None
            self.color_name.clear()
            self._clear_color_entries()
            self._refresh_color_search()
        self._loading = False
        self._active_section = ""
        for name, button in self._section_buttons.items():
            button.setChecked(False)
            self._section_bodies[name].hide()
        self._open_section("Formatting")
        self._request_preview()

    @staticmethod
    def _set_control_value(control, value):
        """Set a setting control from its decoded configuration value."""
        if isinstance(control, QCheckBox):
            control.setChecked(bool(value))
        elif isinstance(control, tuple):
            for axis_control, coordinate in zip(control, value):
                axis_control.setValue(coordinate)
        elif isinstance(control, QSpinBox):
            control.setValue(value)
        elif isinstance(control, QComboBox):
            control.setCurrentText(str(value))
        elif isinstance(value, list):
            control.setText(", ".join(str(part) for part in value))
        else:
            control.setText(str(value))

    def _toggle_section(self, section_name, checked):
        """Toggle the active settings section or open another section."""
        if not checked and self._active_section == section_name:
            for button in self._section_buttons.values():
                button.setChecked(False)
            for body in self._section_bodies.values():
                body.hide()
            return
        self._open_section(section_name)

    def _open_section(self, section_name):
        """Show one settings section and restore its selected subsection."""
        for name, button in self._section_buttons.items():
            is_open = name == section_name
            button.setChecked(is_open)
            self._section_bodies[name].setVisible(is_open)
        self._active_section = section_name
        if section_name in SUBSECTION_FIELDS:
            self._open_subsection(section_name, self._active_subsection[section_name], render=False)
        self._request_preview(immediate=True)

    def _open_subsection(self, section_name, subsection_name, render=True):
        """Select a subsection and optionally request an updated preview."""
        self._active_subsection[section_name] = subsection_name
        for name, button in self._subsection_buttons[section_name].items():
            button.setChecked(name == subsection_name)
            self._subsection_bodies[section_name][name].setVisible(name == subsection_name)
        if render:
            self._request_preview(immediate=True)

    def _values_from_controls(self):
        """Read and validate every setting value from its editor control."""
        values = {}
        for key, default_value in TEMPLATE_DEFAULTS.items():
            control = self._field_controls[key]

            # Handle compound coordinates and native Qt controls directly.
            if isinstance(control, tuple):
                values[key] = [axis.value() for axis in control]
            elif isinstance(control, QCheckBox):
                values[key] = control.isChecked()
            elif isinstance(control, QSpinBox):
                values[key] = control.value()
            elif isinstance(control, QComboBox):
                values[key] = control.currentText()
            # Text controls need explicit conversion and clear validation errors.
            elif isinstance(default_value, int):
                text = control.text().strip()
                try:
                    values[key] = int(text)
                except ValueError as error:
                    raise ValueError(f"'{key}' must be an integer.") from error
            elif isinstance(default_value, list):
                try:
                    values[key] = [int(part.strip()) for part in control.text().split(",")]
                except ValueError as error:
                    raise ValueError(f"'{key}' must be a comma-separated list of integers.") from error
                if len(values[key]) != len(default_value):
                    raise ValueError(f"'{key}' must contain {len(default_value)} values.")
            else:
                values[key] = control.text()
        return values

    def _has_unsaved_changes(self):
        """Compare the active form and palette with their loaded snapshots."""
        try:
            if self._editing_color_key is not None:
                name = self.color_name.text().strip()
                invalid_name = not name or any(character in name for character in "{}")
                duplicate_name = any(key != self._editing_color_key and key.casefold() == name.casefold() for key in self._text_colors)
                if invalid_name or duplicate_name:
                    return True
            return (self._values_from_controls() != self._loaded_values or self._text_colors != self._loaded_text_colors)
        except ValueError:
            return True

    def _field_changed(self, *args):
        """Schedule a preview refresh after a setting or color change."""
        if self._loading:
            return
        self._request_preview()

    def _request_preview(self, *args, immediate=False):
        """Debounce preview work unless an immediate refresh was requested."""
        if hasattr(self, "_preview_timer"):
            self._preview_timer.start(0 if immediate else 100)

    def _render_preview(self):
        """Render the current sample card and show recoverable errors in-pane."""
        try:
            values = self._values_from_controls()
            config = dict(self._effective_values)
            config.update(values)
            config["text_colors"] = self._text_colors
            image = self._create_preview(config)
            pixmap = QPixmap.fromImage(ImageQt(image))
            scaled = pixmap.scaled(320, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(scaled)
        except (OSError, KeyError, ValueError, TypeError, IndexError, RuntimeError) as error:
            self.preview.clear()
            self.preview.setText(f"Preview unavailable: {error}")

    def _create_preview(self, config):
        """Build section-specific sample data and render it with the given config."""
        section = self._active_section or "Formatting"
        subsection = self._active_subsection.get(section, "")

        # Choose sample card content that highlights the selected settings group.
        sample_sigil = ""
        sample_trait = ""
        cost = ""
        power = ""
        health = ""
        credit = ""
        flavor_text = ""
        tribes = ""
        name = ""
        tags = []

        if section == "Formatting":
            name = "Template Preview"
            credit = "Template Artist"
            power, health = "2", "3"
            sample_sigil = "TemplateIndicators"
            sample_trait = "TemplateTrait"
            tribes = "Test Test"
            tags.extend(("Template_left_symbol", "Template_right_symbol"))
        elif section == "Text":
            name = "Template Preview"
            credit = "Template Artist"
            flavor_text = "Sample flavor text for previewing typography and layout."
            power, health = "2", "3"
            sample_sigil = "Template"
            sample_trait = "TemplateTrait"
        elif section == "Indicators":
            flavor_text = "Sample flavor text."
            tribes = "Test Test"
            tags.extend((
                "Template_left_symbol",
                "Template_right_symbol",
                "mox_indicator",
                "mox_green",
                "conduit_indicator",
                "2_extra_cell",
            ))
        elif section == "Cost":
            cost = {
                "Blood": "2 blood",
                "Bones": "3 bones",
                "Energy": "2 max + 3 energy",
                "Gems": "1 emerald + 1 sapphire + 1 ruby",
                "Asterisk": "4 bones + 2 blood + asterisk",
                "Gemified": "green_1 blood",
            }[subsection]
        elif section == "Sigils":
            flavor_text = "Sample flavor text."
            sample_sigil = "Template, Template"
            sample_trait = "TemplateTrait, TemplateTrait"
        elif section == "Gemification":
            sample_sigil = "green_blue_Template, Template"
            cost, power, health = "blue_-1_1 blood", "orange_+1_1", "green_+2_2"
        elif section == "Sigil Conditional":
            sample_sigil = {
                "Cell": "CELL_Template, Template",
                "Latch": "LATCH_Template, Template",
                "Arcane": "RAINBOW, Template",
                "Tribal": "TRIBAL, Template",
                "Hint": "HINT_Template",
            }[subsection]
        elif section == "Rich Text Colors" and self._editing_color_key:
            flavor_text = "{color:" + self._editing_color_key + "}Sample rich text color: " + self._editing_color_key + "{/color}"

        if self._loaded_selection[2] != "default":
            tags.append(f"{self._loaded_selection[2]}_bg")

        sigil_desc = r" \n".join(["Sample sigil line"] * self.preview_sigil_lines.value())
        fake_sigils = {
            "Template": sigils.Sigil("Template", sigil_desc, ""),
            "TemplateIndicators": sigils.Sigil("Template", sigil_desc, "power_sigil, health_sigil, conduit_sigil"),
        }
        previous = {name: sigils.SIGILS.get(name) for name in fake_sigils}
        trait_desc = r" \n".join(["Sample trait line"] * self.preview_trait_lines.value())
        fake_trait = sigils.Sigil("TemplateTrait", trait_desc, "", is_trait=True)
        previous_trait = sigils.TRAITS.get("TemplateTrait")
        sigils.SIGILS.update(fake_sigils)
        sigils.TRAITS["TemplateTrait"] = fake_trait
        try:
            # Preview-only definitions temporarily replace renderer lookups.
            return create_card_preview(
                card_name=name,
                temple=self._loaded_selection[0] if self._loaded_selection[0] != "default" else "test",
                tier=self._loaded_selection[1] if self._loaded_selection[1] != "default" else "test",
                cost=cost,
                power=power,
                health=health,
                sigils=sample_sigil,
                traits=sample_trait,
                tribes=tribes,
                flavor_text=flavor_text,
                credit=credit,
                tags=", ".join(tags),
                config=config,
            )
        finally:
            # Restore global renderer state even when rendering raises.
            for name, original in previous.items():
                if original is None:
                    sigils.SIGILS.pop(name, None)
                else:
                    sigils.SIGILS[name] = original
            if previous_trait is None:
                sigils.TRAITS.pop("TemplateTrait", None)
            else:
                sigils.TRAITS["TemplateTrait"] = previous_trait

    # Configuration persistence

    def _save(self):
        """Persist the active layer, omitting values inherited from parent layers."""
        try:
            values = self._values_from_controls()
            color_name = self.color_name.text().strip()
            if self._editing_color_key is not None and not color_name:
                raise ValueError("Color names cannot be empty.")
            if any(character in color_name for character in "{}"):
                raise ValueError("Color names cannot contain braces.")
            renamed_color = self._editing_color_key is not None and color_name.casefold() != self._editing_color_key.casefold()
            if renamed_color:
                duplicate_name = any(
                    key != self._editing_color_key
                    and key.casefold() == color_name.casefold()
                    for key in self._text_colors
                )
                if duplicate_name:
                    raise ValueError(f"A color named '{color_name}' already exists.")
                self._color_editor_changed()
            values["text_colors"] = copy.deepcopy(self._text_colors)
            tree = self._read_config()
            selection = self._loaded_selection
            target_path = selection

            # Compare with parent layers so overrides store only changed values.
            inherited = effective_config(tree, *selection, exclude_path=target_path)
            target = target_layer(tree, target_path, create=True)
            if target_path == ("default", "default", "default"):
                # The root layer defines baseline values instead of overrides.
                target.update(values)
            else:
                # Remove overrides that now match inherited values.
                for key, value in values.items():
                    if key == "text_colors":
                        if value == inherited.get(key, {}):
                            target.pop(key, None)
                        else:
                            target[key] = value
                        continue
                    if key in inherited and inherited[key] == value:
                        target.pop(key, None)
                    else:
                        target[key] = value
            write_config(tree)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Could not save template settings", str(error))
            return
        self._load_selection(selection)
        QMessageBox.information(self, "Template saved", "Template settings were saved.")

    def _restore_defaults(self):
        """Reset built-in defaults or clear the selected override layer."""
        selection = self._loaded_selection
        is_default = selection == ("default", "default", "default")
        if is_default:
            prompt = "Restore every template setting in the default configuration to its built-in value?"
        else:
            prompt = "Remove all values from this configuration layer?"
        answer = QMessageBox.warning(
            self,
            "Restore default settings",
            prompt,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            tree = self._read_config()
            target = target_layer(tree, selection, create=is_default)
            if is_default:
                target.update(TEMPLATE_DEFAULTS)
                target["text_colors"] = copy.deepcopy(DEFAULT_CONFIG.get("text_colors", {}))
            else:
                target.clear()
            write_config(tree)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Could not restore template settings", str(error))
            return
        self._load_selection(selection)
        QMessageBox.information(self, "Settings restored", "Template settings were restored.")
