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
from .gui_helpers import NoWheelComboBox, ROOT, create_card_preview

CONFIG_PATH = ROOT / "config.json"
COORDINATE_FIELDS = {"power_coord", "health_coord", "left_symbol", "right_symbol", "power_sigil_center", "health_sigil_center"}

TEMPLATE_SECTIONS = {
    "Formatting": {
        "write_card_metadata": True,
        "write_art_credit": True,
        "show_power_sigil": True,
        "show_health_sigil": True,
        "allow_colored_sigils": True,
        "colorless_symbols": True,
        "display_tribe_icons": True,
        "show_conduit_sigil_indicators": True,
        "center_card_name": True,
        "traits_at_bottom": True,
        "allow_card_bottom_removal": True,
        "allow_default_formatting": True,
        "allow_shortened_formatting": True,
        "allow_base_game_display": True,
    },
    "Text": {
        "font": "heavyweight",
        "name_font_size": 110,
        "name_max_width": 870,
        "flavor_text_font_size": 45,
        "metadata_font_size": 45,
        "art_credit_font_size": 45,
        "stats_font_size": 110,
        "flavor_text_color_index": 6,
        "metadata_color_index": 6,
        "art_credit_color_index": 6,
        "trait_color_index": 6,
        "name_top_border": 138,
        "name_left_border": 138,
        "metadata_top_border": 15,
        "art_credit_top_border": 1510,
        "flavor_text_top_border": 962,
        "flavor_text_left_border": 300,
        "flavor_text_right_border": 1000,
        "power_coord": [198, 885],
        "health_coord": [895, 225],
        "sigil_name_font_size": 55,
        "sigil_description_font_size": 45,
        "trait_description_font_size": 40,
    },
    "Indicators": {
        "indicator_displacement": 15,
        "left_symbol": [130, 1440],
        "right_symbol": [1000, 1440],
        "tribes_top_border": 265,
        "tribes_left_border": 980,
        "tribes_vertical_displacement": -1,
        "extra_cells_top_border": 26,
        "extra_cells_left_border": 3,
    },
    "Cost": {
        "cost_right_border": 99,
        "cost_left_border": 67,
        "cost_bottom_border": 91,
    },
    "Sigils": {
        "sigil_img_scale": 100,
        "sigil_img_space": 180,
        "sigil_space": 880,
        "sigil_vertical_spacing": 5,
        "sigil_top_displacement": 3,
        "sigil_left_border": 120,
        "sigil_bottom_border": 1430,
        "power_sigil_center": [220, 925],
        "health_sigil_center": [915, 265],
        "traitline_vertical_spacing": 6,
        "trait_vertical_spacing": 0,
    },
    "Gemification": {
        "gemification_font_size": 80,
        "gemification_health_top_border": 17,
        "gemification_health_horizontal_center": 101,
        "gemification_health_text_top_border": 105,
        "gemification_health_text_horizontal_center": 1015,
        "gemification_power_bottom_border": 87,
        "gemification_power_horizontal_center": 9,
        "gemification_power_text_top_border": 865,
        "gemification_power_text_horizontal_center": 95,
        "gemification_cost_bottom_border": 84,
        "gemification_cost_horizontal_center": 103,
        "gemification_cost_text_top_border": 835,
        "gemification_cost_text_horizontal_center": 1035,
        "cost_right_border_gemification_displacement": -2,
        "gemification_sigil_top_displacement": 0,
        "gemification_sigil_bottom_displacement": 0,
        "gemification_sigil_gems_right_border": 14,
        "gemification_sigil_small_max_height": 150,
        "gemification_sigil_medium_max_height": 200,
    },
    "Sigil Conditional": {},
    "Rich Text Colors": {},
}

SUBSECTION_FIELDS = {
    "Cost": {
        "Blood": {"blood_right_displacement": 0},
        "Bones": {"bone_right_displacement": -1},
        "Energy": {},
        "Gems": {"gem_right_displacement": -1},
        "Asterisk": {"asterisk_right_displacement": -1},
    },
    "Sigil Conditional": {
        "Cell": {
            "cell_sigil_top_displacement": 0,
            "cell_sigil_bottom_displacement": 0,
            "cell_sigil_small_max_height": 150,
            "cell_sigil_medium_max_height": 200,
        },
        "Latch": {
            "latch_sigil_top_displacement": 0,
            "latch_sigil_bottom_displacement": 0,
            "left_latch_head_border": 110,
            "right_latch_head_border": 1010,
            "latch_sigil_small_max_height": 150,
            "latch_sigil_medium_max_height": 200,
        },
        "Arcane": {
            "arcane_sigil_top_displacement": -10,
            "arcane_sigil_bottom_displacement": -95,
            "arcane_text": "If you provide 2 mox colors:",
            "arcane_text_y": 20,
            "arcane_font_size": 43,
            "arcane_dark_color_index": 6,
            "arcane_light_color_index": 5,
        },
        "Tribal": {
            "tribal_sigil_top_displacement": -20,
            "tribal_sigil_bottom_displacement": -95,
            "tribal_text": "If this card shares a tribe with another:",
            "tribal_text_y": 30,
            "tribal_font_size": 43,
            "tribal_dark_color_index": 6,
            "tribal_light_color_index": 5,
        },
        "Hint": {"hint_color_index": 6},
    },
}

TEMPLATE_DEFAULTS = {
    **{
        key: value
        for section in TEMPLATE_SECTIONS.values()
        for key, value in section.items()
    },
    **{
        key: value
        for subsections in SUBSECTION_FIELDS.values()
        for fields in subsections.values()
        for key, value in fields.items()
    },
}


def _layer_paths(temple, tier, modifier):
    paths = [("default", "default", "default")]
    if temple != "default":
        paths.append((temple, "default", "default"))
    if tier != "default":
        paths.append(("default", tier, "default"))
        if temple != "default":
            paths.append((temple, tier, "default"))
    if modifier != "default":
        paths.append(("default", "default", modifier))
        if temple != "default":
            paths.append((temple, "default", modifier))
        if tier != "default":
            paths.append(("default", tier, modifier))
            if temple != "default":
                paths.append((temple, tier, modifier))
    return paths


def _effective_config(config_tree, temple, tier, modifier, exclude_path=None):
    effective = {}
    for path in _layer_paths(temple, tier, modifier):
        if path == exclude_path:
            continue
        section = config_tree
        for key in path:
            section = section.get(key, {}) if isinstance(section, dict) else {}
        if isinstance(section, dict):
            effective.update(section)
    return effective


def _target_layer(config_tree, path, create=False):
    section = config_tree
    for key in path:
        if create:
            section = section.setdefault(key, {})
        else:
            section = section.get(key, {})
        if not isinstance(section, dict):
            raise ValueError(f"Configuration layer '{'.'.join(path)}' is not an object.")
    return section


def _read_selector_values(cards_path):
    temples, tiers, modifiers = set(), set(), set()
    with cards_path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            temple = (row.get("Temple") or "").strip()
            tier = (row.get("Tier") or "").strip()
            if temple:
                temples.add(temple)
            if tier:
                tiers.add(tier)
            modifiers.update(tag.strip() for tag in (row.get("Tags") or "").split(",") if tag.strip().lower().endswith("_bg"))
    sort_values = lambda values: sorted(values, key=str.casefold)
    return sort_values(temples), sort_values(tiers), sort_values(modifiers)


class TemplateEditor(QWidget):
    """Load, edit, preview, and save template values across config layers."""

    def __init__(self):
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
            self._temple_options, self._tier_options, self._modifier_options = _read_selector_values(ROOT / DEFAULT_CONFIG["cards_file_path"])
        except (OSError, csv.Error) as error:
            QMessageBox.critical(self, "Could not load template options", str(error))
            self._temple_options, self._tier_options, self._modifier_options = [], [], []

        self._build_ui()
        self._load_selection(self._loaded_selection)

    def _read_config(self):
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                config_tree = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            QMessageBox.critical(self, "Could not load configuration", str(error))
            raise
        if not isinstance(config_tree, dict) or not isinstance(config_tree.get("default"), dict):
            raise ValueError("config.json must contain an object with a 'default' layer.")
        return config_tree

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_sections())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([560, 500])
        root.addWidget(splitter, 1)

    def _build_header(self):
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
        selector = NoWheelComboBox()
        selector.setEditable(True)
        selector.setInsertPolicy(QComboBox.NoInsert)
        selector.setPlaceholderText(placeholder)
        selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selector.addItems(values)
        selector.setCurrentIndex(-1)
        return selector

    def _build_sections(self):
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
                    sub_button.clicked.connect(
                        lambda checked=False, section=section_name, name=subsection_name:
                        self._open_subsection(section, name)
                    )
                    subsection_nav_layout.addWidget(sub_button)
                    self._subsection_buttons[section_name][subsection_name] = sub_button
                section_layout.addWidget(subsection_nav)
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
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(8)
        for key, default_value in options.items():
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

    def _build_color_editor(self, parent_layout):
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
        names = sorted(self._text_colors, key=str.casefold)
        self.color_search.blockSignals(True)
        self.color_search.clear()
        self.color_search.addItems(names)
        self.color_search.setCurrentIndex(-1)
        self.color_search.setEditText(selected)
        self.color_search.blockSignals(False)

    def _select_color_from_search(self, index):
        name = self.color_search.itemText(index)
        self._load_color_editor(name)
        self._request_preview(immediate=True)
        self._update_color_remove_button()

    def _select_color_from_search_text(self):
        name = self.color_search.currentText().strip()
        match = next((key for key in self._text_colors if key.casefold() == name.casefold()), None)
        if match is not None:
            self._load_color_editor(match)
            self._request_preview(immediate=True)
            self._update_color_remove_button()

    def _load_color_editor(self, name):
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
        if isinstance(value, dict) and set(value) == {"index"}:
            entries = [value]
        elif isinstance(value, list) and len(value) == 3 and all(isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255 for channel in value):
            entries = [value]
        elif isinstance(value, list) and value:
            entries = value
        else:
            raise ValueError(f"Text color '{name}' has an unsupported value.")

        parsed = []
        for entry in entries:
            if isinstance(entry, dict) and set(entry) == {"index"}:
                index = entry["index"]
                if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= 1_000_000:
                    raise ValueError(f"Text color '{name}' contains an invalid palette index.")
                parsed.append(("Color index", index))
            elif isinstance(entry, list) and len(entry) == 3 and all(isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255 for channel in entry):
                parsed.append(("RGB color", entry))
            else:
                raise ValueError(f"Text color '{name}' contains an unsupported palette entry.")
        return parsed

    def _clear_color_entries(self):
        while self.color_entries_layout.count():
            item = self.color_entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._color_entries.clear()

    def _add_color_entry(self, entry_type="RGB color", value=None):
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
        record = {"row": row, "type": type_selector, "index": index, "rgb_widget": rgb_widget, "rgb": (red, green, blue), "remove": remove}
        self._color_entries.append(record)
        self.color_entries_layout.addWidget(row)

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
        is_index = entry_type == "Color index"
        record["index"].setVisible(is_index)
        record["rgb_widget"].setVisible(not is_index)
        self._color_editor_changed()

    def _remove_color_entry(self, row):
        record = next(record for record in self._color_entries if record["row"] is row)
        self._color_entries.remove(record)
        self.color_entries_layout.removeWidget(row)
        row.deleteLater()
        self._update_color_entry_buttons()
        self._color_editor_changed()

    def _update_color_entry_buttons(self):
        for record in self._color_entries:
            record["remove"].setEnabled(len(self._color_entries) > 1)

    def _update_color_remove_button(self):
        name = self.color_search.currentText().strip()
        exists = any(key.casefold() == name.casefold() for key in self._text_colors)
        self.remove_color_button.setEnabled(exists)

    def _remove_selected_color(self):
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
        values = []
        for record in self._color_entries:
            if record["type"].currentText() == "Color index":
                values.append({"index": record["index"].value()})
            else:
                values.append([control.value() for control in record["rgb"]])
        return values

    def _color_editor_changed(self, *args):
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
        changed = self._has_unsaved_changes()

    def _create_color(self):
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
            QMessageBox.warning(self, "Color already exists", f"A color named '{name}' already exists.")
            return
        self._text_colors[name] = [[0, 0, 0]]
        self._load_color_editor(name)
        self._field_changed()

    def _make_field_control(self, key, default_value):
        if isinstance(default_value, bool):
            control = QCheckBox()
            control.toggled.connect(self._field_changed)
        elif key == "font":
            control = NoWheelComboBox()
            control.setEditable(False)
            fonts = {path.stem for path in (ROOT / "data" / "fonts").iterdir() if path.is_file() and path.suffix.lower() == ".ttf"}
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
        control = QSpinBox()
        control.setRange(-1_000_000, 1_000_000)
        control.setValue(value)
        control.valueChanged.connect(self._field_changed)
        control.setProperty("config-key", key)
        return control

    def _build_preview(self):
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
        layout.addWidget(QLabel(label))
        control = QSpinBox()
        control.setRange(1, 8)
        control.setValue(1)
        control.valueChanged.connect(self._request_preview)
        layout.addWidget(control, 1)
        return control

    def _selection_from_header(self):
        values = (
            self.temple_selector.currentText().strip(),
            self.tier_selector.currentText().strip(),
            self.modifier_selector.currentText().strip(),
        )
        temple, tier, modifier = (value.lower() for value in values)
        modifier = modifier[:-3] if modifier.endswith("_bg") else modifier
        return temple or "default", tier or "default", modifier or "default"

    def _load_requested(self):
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
        try:
            self._config_tree = self._read_config()
            self._effective_values = _effective_config(self._config_tree, *selection)
            values = {key: self._effective_values.get(key, default_value) for key, default_value in TEMPLATE_DEFAULTS.items()}
        except (OSError, json.JSONDecodeError, ValueError) as error:
            QMessageBox.critical(self, "Could not load template settings", str(error))
            return

        self._loaded_selection = selection
        self._loaded_values = {key: value for key, value in values.items()}
        self._loading = True
        for key, value in values.items():
            self._set_control_value(self._field_controls[key], value)
        text_colors = self._effective_values.get("text_colors", {})
        if not isinstance(text_colors, dict):
            self._loading = False
            QMessageBox.critical(self, "Could not load template settings", "'text_colors' must be an object.")
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
        if not checked and self._active_section == section_name:
            for button in self._section_buttons.values():
                button.setChecked(False)
            for body in self._section_bodies.values():
                body.hide()
            return
        self._open_section(section_name)

    def _open_section(self, section_name):
        for name, button in self._section_buttons.items():
            is_open = name == section_name
            button.setChecked(is_open)
            self._section_bodies[name].setVisible(is_open)
        self._active_section = section_name
        if section_name in SUBSECTION_FIELDS:
            self._open_subsection(
                section_name,
                self._active_subsection[section_name],
                render=False,
            )
        self._request_preview(immediate=True)

    def _open_subsection(self, section_name, subsection_name, render=True):
        self._active_subsection[section_name] = subsection_name
        for name, button in self._subsection_buttons[section_name].items():
            button.setChecked(name == subsection_name)
            self._subsection_bodies[section_name][name].setVisible(name == subsection_name)
        if render:
            self._request_preview(immediate=True)

    def _values_from_controls(self):
        values = {}
        for key, default_value in TEMPLATE_DEFAULTS.items():
            control = self._field_controls[key]
            if isinstance(control, tuple):
                values[key] = [axis.value() for axis in control]
            elif isinstance(control, QCheckBox):
                values[key] = control.isChecked()
            elif isinstance(control, QSpinBox):
                values[key] = control.value()
            elif isinstance(control, QComboBox):
                values[key] = control.currentText()
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
        try:
            if self._editing_color_key is not None:
                name = self.color_name.text().strip()
                if (not name or any(character in name for character in "{}") or any(key != self._editing_color_key and key.casefold() == name.casefold() for key in self._text_colors)):
                    return True
            return (self._values_from_controls() != self._loaded_values or self._text_colors != self._loaded_text_colors)
        except ValueError:
            return True

    def _field_changed(self, *args):
        if self._loading:
            return
        changed = self._has_unsaved_changes()
        self._request_preview()

    def _request_preview(self, *args, immediate=False):
        if hasattr(self, "_preview_timer"):
            self._preview_timer.start(0 if immediate else 100)

    def _render_preview(self):
        try:
            values = self._values_from_controls()
            config = dict(self._effective_values)
            config.update(values)
            config["text_colors"] = self._text_colors
            image = self._create_preview(config)
            pixmap = QPixmap.fromImage(ImageQt(image))
            self.preview.setPixmap(pixmap.scaled(320, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except (OSError, KeyError, ValueError, TypeError, IndexError, RuntimeError) as error:
            self.preview.clear()
            self.preview.setText(f"Preview unavailable: {error}")

    def _create_preview(self, config):
        section = self._active_section or "Formatting"
        subsection = self._active_subsection.get(section, "")
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
        fake_trait = sigils.Sigil("TemplateTrait", r" \n".join(["Sample trait line"] * self.preview_trait_lines.value()), "", is_trait=True,)
        previous_trait = sigils.TRAITS.get("TemplateTrait")
        sigils.SIGILS.update(fake_sigils)
        sigils.TRAITS["TemplateTrait"] = fake_trait
        try:
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
            for name, original in previous.items():
                if original is None:
                    sigils.SIGILS.pop(name, None)
                else:
                    sigils.SIGILS[name] = original
            if previous_trait is None:
                sigils.TRAITS.pop("TemplateTrait", None)
            else:
                sigils.TRAITS["TemplateTrait"] = previous_trait

    def _save(self):
        try:
            values = self._values_from_controls()
            color_name = self.color_name.text().strip()
            if self._editing_color_key is not None and not color_name:
                raise ValueError("Color names cannot be empty.")
            if any(character in color_name for character in "{}"):
                raise ValueError("Color names cannot contain braces.")
            if self._editing_color_key is not None and color_name.casefold() != self._editing_color_key.casefold():
                if any(key != self._editing_color_key and key.casefold() == color_name.casefold() for key in self._text_colors):
                    raise ValueError(f"A color named '{color_name}' already exists.")
                self._color_editor_changed()
            values["text_colors"] = copy.deepcopy(self._text_colors)
            tree = self._read_config()
            selection = self._loaded_selection
            target_path = selection
            inherited = _effective_config(tree, *selection, exclude_path=target_path)
            target = _target_layer(tree, target_path, create=True)
            if target_path == ("default", "default", "default"):
                target.update(values)
            else:
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
            self._write_config(tree)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Could not save template settings", str(error))
            return
        self._load_selection(selection)
        QMessageBox.information(self, "Template saved", "Template settings were saved.")

    def _restore_defaults(self):
        selection = self._loaded_selection
        is_default = selection == ("default", "default", "default")
        prompt = "Restore every template setting in the default configuration to its built-in value?" if is_default else "Remove all values from this configuration layer?"
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
            target = _target_layer(tree, selection, create=is_default)
            if is_default:
                target.update(TEMPLATE_DEFAULTS)
                target["text_colors"] = copy.deepcopy(DEFAULT_CONFIG.get("text_colors", {}))
            else:
                target.clear()
            self._write_config(tree)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "Could not restore template settings", str(error))
            return
        self._load_selection(selection)
        QMessageBox.information(self, "Settings restored", "Template settings were restored.")

    @staticmethod
    def _write_config(config_tree):
        serialized = json.dumps(config_tree, indent=4, ensure_ascii=False) + "\n"
        CONFIG_PATH.write_text(serialized, encoding="utf-8")
