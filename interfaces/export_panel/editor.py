"""Filter, select, and bulk-export cards, sigils, and traits."""

import csv
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGridLayout,
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
    QVBoxLayout,
    QWidget,
)

from model import sigils
from ..card_editor.data import CARDS_PATH, parse_card_tags
from ..gui_helpers import ColorPickerButton, NoWheelComboBox, ROOT
from ..sigil_trait_editor.data import SIGIL_PATH, TRAIT_PATH
from .data import (
    COST_FILTERS,
    EXPORT_TYPES,
    ITEM_TAG_FILTERS,
    STAT_OPERATORS,
    card_filter_values as _card_filter_values,
    cost_tokens as _cost_tokens,
    display_name as _display_name,
    load_csv as _load_csv,
    matches_stat as _matches_stat,
    split_list as _split_list,
    unique as _unique,
)
from .service import ExportJob
from .widgets import (
    DragSelectListWidget,
    ExportProgressDialog,
    ExportResultsDelegate,
    ExportResultsModel,
    ExportResultsView,
    ExportSummaryDialog,
    OptionalSpinBox,
    SelectedValues,
)


class ExportPanel(QWidget):
    """Scrollable filter canvas with a persistent selected-item/export sidebar."""

    def __init__(self):
        super().__init__()
        try:
            self.cards = _load_csv(CARDS_PATH)
            self.sigils = _load_csv(SIGIL_PATH)
            self.traits = _load_csv(TRAIT_PATH)
        except (OSError, UnicodeError, csv.Error) as error:
            QMessageBox.critical(self, "Could not load export data", str(error))
            self.cards, self.sigils, self.traits = [], [], []
        for row in self.sigils:
            sigils.add_sigil(row)
        for row in self.traits:
            sigils.add_trait(row)
        self.effect_tags_by_name = {}
        for row in self.sigils + self.traits:
            name = _display_name(row.get("Name", "")).casefold()
            self.effect_tags_by_name.setdefault(name, set()).update(tag.strip().casefold() for tag in row.get("Tags", "").split(",") if tag.strip())
        self.item_type = "Cards"
        self.selected = {}
        self.selected_list_items = {}
        self.visible_rows = []
        self.result_model = ExportResultsModel(self)
        self._drag_selecting = False
        self.filter_column_count = None
        self._export_jobs = []
        self._progress_dialog = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self._refresh_results)
        self._build_ui()
        self._set_type_content()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        self.left_column = QWidget()
        self.left_column.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        self.canvas = QWidget()
        self.canvas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.canvas_layout = QVBoxLayout(self.canvas)
        self.canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas_layout.setSpacing(12)
        title = QLabel("Export")
        title.setObjectName("pageTitle")
        left_layout.addWidget(title)
        description = QLabel("Filter the available data, select the items to export, then export them together.")
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        left_layout.addWidget(description)

        self.header = QGroupBox("Export setup")
        self.header.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header_layout = QFormLayout(self.header)
        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(EXPORT_TYPES)
        self.type_combo.currentTextChanged.connect(self._change_type)
        header_layout.addRow("Export type", self.type_combo)
        self.options_widget = QWidget()
        self.options_layout = QHBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addRow("Options", self.options_widget)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(ROOT / "exports"))
        self.output_edit.setReadOnly(True)
        browse = QPushButton("Choose folder...")
        browse.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse)
        header_layout.addRow("Output folder", output_row)
        self.canvas_layout.addWidget(self.header)

        self.filter_grid_widget = QWidget()
        self.filter_grid_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.filter_grid = QGridLayout(self.filter_grid_widget)
        self.filter_grid.setContentsMargins(0, 0, 0, 0)
        self.filter_grid.setSpacing(8)
        for column in range(4):
            self.filter_grid.setColumnStretch(column, 1)
        self.canvas_layout.addWidget(self.filter_grid_widget)

        result_header = QHBoxLayout()
        result_title = QLabel("Available items")
        result_title.setObjectName("sectionTitle")
        self.result_count = QLabel()
        self.result_count.setObjectName("mutedText")
        select_all = QPushButton("Select all")
        select_all.clicked.connect(self._select_all_visible)
        deselect_all = QPushButton("Deselect all")
        deselect_all.clicked.connect(self._deselect_all_visible)
        result_header.addWidget(result_title)
        result_header.addStretch()
        result_header.addWidget(self.result_count)
        result_header.addWidget(select_all)
        result_header.addWidget(deselect_all)
        self.canvas_layout.addLayout(result_header)
        self.results = ExportResultsView()
        self.results.setModel(self.result_model)
        self.results_delegate = ExportResultsDelegate(self.result_model, self.results)
        self.results.setItemDelegate(self.results_delegate)
        self.results.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.results.itemPressed.connect(self._result_item_pressed)
        self.results.itemHovered.connect(self._result_item_hovered)
        self.results.selectionDragFinished.connect(self._finish_result_drag_selection)
        self.results.resized.connect(self._update_result_columns)
        self.canvas_layout.addWidget(self.results)

        self.export_panel = QGroupBox("Export panel")
        export_panel_layout = QVBoxLayout(self.export_panel)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.canvas)
        export_panel_layout.addWidget(scroll)
        left_layout.addWidget(self.export_panel, 1)

        root.addWidget(self.left_column, 1)
        root.addWidget(self._build_sidebar())

    def _build_sidebar(self):
        sidebar = QGroupBox("Selected items")
        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(340)
        layout = QVBoxLayout(sidebar)
        self.selected_count = QLabel("0 selected")
        layout.addWidget(self.selected_count)
        self.selected_list = DragSelectListWidget()
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.selected_list, 1)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected)
        layout.addWidget(remove)
        self.export_button = QPushButton("Export")
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self._start_export)
        layout.addWidget(self.export_button)
        return sidebar

    def _change_type(self, item_type):
        if item_type == self.item_type:
            return
        if self.selected and QMessageBox.question(
            self,
            "Clear selected items?",
            f"Switching to {item_type.lower()} will clear your {self.item_type.lower()} selection. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentText(self.item_type)
            self.type_combo.blockSignals(False)
            return
        self.selected.clear()
        self.item_type = item_type
        self._refresh_selected()
        self._set_type_content()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _set_type_content(self):
        self._clear_layout(self.filter_grid)
        self._clear_layout(self.options_layout)
        if self.item_type == "Cards":
            self._build_card_options()
            self._build_card_filters()
        elif self.item_type == "Sigils":
            self._build_item_options("Sigils")
            self._build_item_filters(self.sigils)
        else:
            self._build_item_options("Traits")
            self._build_item_filters(self.traits)
        self._update_filter_columns()
        self._refresh_results()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_filter_columns)

    def _update_filter_columns(self):
        if not hasattr(self, "filter_grid") or not self.filter_grid.count():
            return
        if self.item_type == "Cards":
            scroll = self.export_panel.findChild(QScrollArea)
            available_width = scroll.viewport().width() if scroll else self.export_panel.width()
            columns = 4 if available_width >= 756 else 2
        else:
            columns = 2
        if columns == self.filter_column_count:
            return

        boxes = []
        while self.filter_grid.count():
            item = self.filter_grid.takeAt(0)
            if item.widget():
                boxes.append(item.widget())
        for index, box in enumerate(boxes):
            self.filter_grid.addWidget(box, index // columns, index % columns)
        for column in range(4):
            self.filter_grid.setColumnStretch(column, int(column < columns))
        self.filter_column_count = columns

    def _build_card_options(self):
        self.sorted_option = QCheckBox("Sort into Temple/Tier folders")
        self.sorted_option.setChecked(True)
        self.options_layout.addWidget(self.sorted_option)
        self.options_layout.addStretch()

    def _build_item_options(self, item_type):
        self.export_color = (0, 0, 0)
        self.color_button = ColorPickerButton(self.export_color, "Color")
        self.color_button.colorPicked.connect(self._set_export_color)
        self.options_layout.addWidget(self.color_button)
        self.format_checks = {}
        if item_type == "Sigils":
            for label in ("Standard", "Shortened", "Base game", "Patch"):
                check = QCheckBox(label)
                check.setChecked(label == "Standard")
                self.options_layout.addWidget(check)
                self.format_checks[label] = check
        else:
            traitline_note = QLabel("Traitline output is unavailable (assets are not installed).")
            traitline_note.setObjectName("mutedText")
            self.options_layout.addWidget(traitline_note)
        self.options_layout.addStretch()

    def _set_export_color(self, color):
        self.export_color = color

    def _filter_box(self, title, row, column):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        self.filter_grid.addWidget(box, row, column)
        return layout

    def _labeled_filter(self, label, field, layout):
        layout.addWidget(QLabel(label))
        layout.addWidget(field)

    def _autocomplete(self, values, placeholder):
        field = NoWheelComboBox()
        field.setEditable(True)
        field.setInsertPolicy(QComboBox.NoInsert)
        field.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        field.setMinimumContentsLength(6)
        field.setMinimumWidth(0)
        field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        field.setPlaceholderText(placeholder)
        field.addItems(_unique(values))
        field.setCurrentIndex(-1)
        field.setCurrentText("")
        completer = QCompleter(_unique(values), field)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        field.setCompleter(completer)
        field.currentTextChanged.connect(self._schedule_results_refresh)
        return field

    def _build_card_filters(self):
        names = [_display_name(row.get("Card Name", "")) for row in self.cards]
        temples = [row.get("Temple", "") for row in self.cards]
        tiers = [row.get("Tier", "") for row in self.cards]
        data = self._filter_box("Card Data", 0, 0)
        self.name_filter = self._autocomplete(names, "Card name")
        self.temple_filter = self._autocomplete(temples, "Temple")
        self.tier_filter = self._autocomplete(tiers, "Tier")
        self._labeled_filter("Card Name", self.name_filter, data)
        self._labeled_filter("Temple", self.temple_filter, data)
        self._labeled_filter("Tier", self.tier_filter, data)

        costs_box = self._filter_box("Cost", 0, 1)
        self.cost_checks = {}
        cost_grid = QGridLayout()
        for index, (label, key) in enumerate(COST_FILTERS):
            check = QCheckBox("Overcharge" if key == "max" else label)
            if key == "max":
                check.setToolTip("Overcharge (max)")
            check.toggled.connect(self._schedule_results_refresh)
            self.cost_checks[key] = check
            cost_grid.addWidget(check, index // 2, index % 2)
        costs_box.addLayout(cost_grid)
        self.cost_all = QCheckBox("All")
        self.cost_all.setToolTip("Require cards to have all selected costs.")
        self.cost_only = QCheckBox("Only")
        self.cost_only.setToolTip("Require cards to have no costs besides the selected costs.")
        self.cost_all.toggled.connect(self._schedule_results_refresh)
        self.cost_only.toggled.connect(self._schedule_results_refresh)
        costs_box.addWidget(self.cost_all)
        costs_box.addWidget(self.cost_only)

        stats = self._filter_box("Stats", 0, 2)
        self.stat_controls = {}
        for stat in ("Power", "Health"):
            row = QHBoxLayout()
            row.addWidget(QLabel(stat))
            operator = NoWheelComboBox()
            operator.addItems(STAT_OPERATORS)
            value = QLineEdit()
            value.setPlaceholderText("Value")
            operator.currentTextChanged.connect(self._schedule_results_refresh)
            value.textChanged.connect(self._schedule_results_refresh)
            row.addWidget(operator)
            row.addWidget(value)
            stats.addLayout(row)
            has_sigil = QCheckBox(f"Has {stat.lower()} sigil")
            has_sigil.toggled.connect(self._schedule_results_refresh)
            stats.addWidget(has_sigil)
            setattr(self, f"has_{stat.lower()}_sigil_filter", has_sigil)
            self.stat_controls[stat] = (operator, value)

        for category, field, row, column in (
            ("Sigils", "Sigils", 0, 3),
            ("Traits", "Traits", 1, 0),
            ("Tribes", "Tribes", 1, 1),
            ("Artists", "Credit", 1, 2),
        ):
            box = self._filter_box(category, row, column)
            values = []
            for card in self.cards:
                values.extend(_card_filter_values(card, category, field))
            selector = SelectedValues(_unique(values), f"Search {category.lower()}...")
            selector.changed.connect(self._schedule_results_refresh)
            box.addWidget(QLabel(f"Select {category.lower()}"))
            box.addWidget(selector)
            all_check = QCheckBox("All")
            all_check.setToolTip(f"Require all selected {category.lower()}.")
            only_check = QCheckBox("Only")
            only_check.setToolTip(f"Require no other {category.lower()} besides the selected ones.")
            all_check.toggled.connect(self._schedule_results_refresh)
            only_check.toggled.connect(self._schedule_results_refresh)
            box.addWidget(all_check)
            box.addWidget(only_check)
            setattr(self, f"{category.lower()}_filter", selector)
            setattr(self, f"{category.lower()}_all", all_check)
            setattr(self, f"{category.lower()}_only", only_check)

        tags = self._filter_box("Tags", 1, 3)
        self.background_filter = self._autocomplete(
            (tag[:-3] for card in self.cards for tag in _split_list(card.get("Tags", "")) if tag.endswith("_bg")),
            "Background sigil tag",
        )
        self.extra_cells_filter = OptionalSpinBox()
        self.extra_cells_filter.valueChanged.connect(self._schedule_results_refresh)
        symbol_names = (_display_name(row.get("Name", "")) for row in self.sigils)
        self.symbol_1_filter = self._autocomplete(symbol_names, "Symbol 1")
        self.symbol_2_filter = self._autocomplete(
            (_display_name(row.get("Name", "")) for row in self.sigils),
            "Symbol 2",
        )
        for label, widget in (
            ("Background", self.background_filter),
            ("Extra Cells", self.extra_cells_filter),
        ):
            self._labeled_filter(label, widget, tags)
        symbols = QWidget()
        symbol_layout = QHBoxLayout(symbols)
        symbol_layout.setContentsMargins(0, 0, 0, 0)
        for label, widget in (
            ("Symbol 1", self.symbol_1_filter),
            ("Symbol 2", self.symbol_2_filter),
        ):
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            self._labeled_filter(label, widget, column)
            symbol_layout.addLayout(column, 1)
        tags.addWidget(symbols)

    def _build_item_filters(self, rows):
        data = self._filter_box(f"{self.item_type[:-1]} Data", 0, 0)
        self.item_name_filter = self._autocomplete(
            (_display_name(row.get("Name", "")) for row in rows),
            f"Search {self.item_type[:-1].lower()} name...",
        )
        self._labeled_filter(f"{self.item_type[:-1]} Name", self.item_name_filter, data)
        tags = self._filter_box("Tags", 0, 1)
        self.item_tag_checks = {}
        for tag in ITEM_TAG_FILTERS:
            check = QCheckBox(tag.replace("_", " ").title())
            check.toggled.connect(self._schedule_results_refresh)
            self.item_tag_checks[tag] = check
            tags.addWidget(check)
        self.filter_grid.setColumnStretch(0, 1)
        self.filter_grid.setColumnStretch(1, 1)

    def _matches_values(self, values, selected, require_all, require_only):
        if not selected:
            return True
        normalized = {value.casefold() for value in values}
        requested = {value.casefold() for value in selected}
        has_requested = requested.issubset(normalized) if require_all else bool(requested & normalized)
        return has_requested and (not require_only or normalized.issubset(requested))

    def _filtered_rows(self):
        if self.item_type == "Cards":
            rows = []
            for row in self.cards:
                if self.name_filter.currentText().strip().casefold() not in _display_name(row.get("Card Name", "")).casefold():
                    continue
                if self.temple_filter.currentText().strip().casefold() not in row.get("Temple", "").casefold():
                    continue
                if self.tier_filter.currentText().strip().casefold() not in row.get("Tier", "").casefold():
                    continue
                selected_costs = {key for key, check in self.cost_checks.items() if check.isChecked()}
                if selected_costs:
                    actual_costs = _cost_tokens(row.get("Cost", ""))
                    matches = selected_costs.issubset(actual_costs) if self.cost_all.isChecked() else bool(selected_costs & actual_costs)
                    if not matches or (self.cost_only.isChecked() and not actual_costs.issubset(selected_costs)):
                        continue
                if not all(_matches_stat(row.get(stat, ""), self.stat_controls[stat][0].currentText(), self.stat_controls[stat][1].text()) for stat in self.stat_controls):
                    continue
                if self.has_power_sigil_filter.isChecked() or self.has_health_sigil_filter.isChecked():
                    card_effects = {value.casefold() for value in _card_filter_values(row, "Sigils", "Sigils")}
                    card_effects.update(value.casefold() for value in _card_filter_values(row, "Traits", "Traits"))
                    if self.has_power_sigil_filter.isChecked() and not any("power_sigil" in self.effect_tags_by_name.get(name, set()) for name in card_effects):
                        continue
                    if self.has_health_sigil_filter.isChecked() and not any("health_sigil" in self.effect_tags_by_name.get(name, set()) for name in card_effects):
                        continue
                filters_ok = True
                for category, field in (("sigils", "Sigils"), ("traits", "Traits"), ("tribes", "Tribes"), ("artists", "Credit")):
                    selector = getattr(self, f"{category}_filter")
                    if not self._matches_values(_card_filter_values(row, category.title(), field), selector.selected, getattr(self, f"{category}_all").isChecked(), getattr(self, f"{category}_only").isChecked()):
                        filters_ok = False
                        break
                if not filters_ok:
                    continue
                parsed = parse_card_tags(row.get("Tags", ""))
                if self.background_filter.currentText().strip() and self.background_filter.currentText().strip().casefold() not in parsed["background"].casefold():
                    continue
                if self.extra_cells_filter.lineEdit().text().strip():
                    if parsed["extra_cells"] != self.extra_cells_filter.value():
                        continue
                requested_symbols = [value.strip().casefold() for value in (self.symbol_1_filter.currentText(), self.symbol_2_filter.currentText()) if value.strip()]
                available_symbols = [value.casefold() for value in parsed["symbols"].values() if value]
                if len(requested_symbols) == 1 and not any(requested_symbols[0] in symbol for symbol in available_symbols):
                    continue
                if len(requested_symbols) == 2 and not any(
                    requested_symbols[0] in first and requested_symbols[1] in second
                    or requested_symbols[1] in first and requested_symbols[0] in second
                    for first_index, first in enumerate(available_symbols)
                    for second_index, second in enumerate(available_symbols)
                    if first_index != second_index
                ):
                    continue
                rows.append(row)
            return rows

        source = self.sigils if self.item_type == "Sigils" else self.traits
        name_filter = self.item_name_filter.currentText().strip().casefold()
        selected_tags = {tag for tag, check in self.item_tag_checks.items() if check.isChecked()}
        return [row for row in source if name_filter in _display_name(row.get("Name", "")).casefold() and selected_tags.issubset({tag.strip().lower() for tag in row.get("Tags", "").split(",") if tag.strip()})]

    def _schedule_results_refresh(self, *_):
        self._refresh_timer.start()

    def _update_result_columns(self):
        if not hasattr(self, "results") or not hasattr(self, "results_delegate"):
            return
        available_width = max(self.results.viewport().width(), 1)
        minimum_tile_width = 120
        columns = max(1, available_width // minimum_tile_width)
        tile_width = max(minimum_tile_width, available_width // columns)
        row_count = (len(self.visible_rows) + columns - 1) // columns
        # A single result row otherwise clips labels in the collapsed scroll viewport.
        tile_height = 150 if row_count == 1 else 130
        tile_size = QSize(tile_width, tile_height)
        self.results_delegate.tile_size = tile_size
        self.results.setGridSize(tile_size)
        self.result_column_count = columns
        self.results.setMinimumHeight(max(tile_height, row_count * tile_height))
        self.results.doItemsLayout()

    def _refresh_results(self, *_):
        if not hasattr(self, "result_model"):
            return
        rows = self._filtered_rows()
        self.visible_rows = rows
        self.result_count.setText(f"{len(rows)} items")
        self.result_model.set_rows(rows, self.item_type)
        self.result_model.set_selected_keys(self.selected)
        self._update_result_columns()

    def _result_item_pressed(self, row_index):
        if not 0 <= row_index < len(self.visible_rows):
            return
        row = self.visible_rows[row_index]
        key = id(row)
        self._drag_selecting = True
        self._drag_selection_value = key not in self.selected
        self._set_item_selected(key, row, self._drag_selection_value)

    def _result_item_hovered(self, row_index):
        if not self._drag_selecting or not 0 <= row_index < len(self.visible_rows):
            return
        row = self.visible_rows[row_index]
        self._set_item_selected(id(row), row, self._drag_selection_value)

    def _finish_result_drag_selection(self):
        self._drag_selecting = False

    def _set_item_selected(self, key, row, selected):
        if selected:
            self.selected[key] = row
            if key not in self.selected_list_items:
                self._add_selected_item(key, row)
        else:
            self.selected.pop(key, None)
            self._remove_selected_item(key)
        self.result_model.set_selected(key, selected)
        self.selected_count.setText(f"{len(self.selected)} selected")

    def _add_selected_item(self, key, row):
        name = _display_name(row.get("Card Name", row.get("Name", "")))
        if self.item_type == "Cards":
            name = f"{name} ({row.get('Temple', '')} / {row.get('Tier', '')})"
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, key)
        self.selected_list.addItem(item)
        self.selected_list_items[key] = item

    def _remove_selected_item(self, key):
        item = self.selected_list_items.pop(key, None)
        if item:
            self.selected_list.takeItem(self.selected_list.row(item))

    def _refresh_selected(self):
        self.selected_list.clear()
        self.selected_list_items.clear()
        for key, row in self.selected.items():
            self._add_selected_item(key, row)
        self.selected_count.setText(f"{len(self.selected)} selected")

    def _remove_selected(self):
        for item in self.selected_list.selectedItems():
            key = item.data(Qt.UserRole)
            row = self.selected.pop(key, None)
            if row is not None:
                self._remove_selected_item(key)
                self.result_model.set_selected(key, False)
        self.selected_count.setText(f"{len(self.selected)} selected")

    def _select_all_visible(self):
        for row in self.visible_rows:
            key = id(row)
            if key not in self.selected:
                self.selected[key] = row
                self._add_selected_item(key, row)
        self.result_model.set_selected_keys(self.selected)
        self.selected_count.setText(f"{len(self.selected)} selected")

    def _deselect_all_visible(self):
        for row in self.visible_rows:
            key = id(row)
            self.selected.pop(key, None)
            self._remove_selected_item(key)
        self.result_model.set_selected_keys(self.selected)
        self.selected_count.setText(f"{len(self.selected)} selected")

    def _choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose export folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def _start_export(self):
        if not self.selected:
            QMessageBox.information(self, "Nothing selected", "Select at least one item to export.")
            return
        options = {}
        if self.item_type == "Cards":
            options["sorted"] = self.sorted_option.isChecked()
        elif self.item_type == "Sigils":
            options["formats"] = [name for name, check in self.format_checks.items() if check.isChecked()]
            options["color"] = self.export_color
            if not options["formats"]:
                QMessageBox.warning(self, "No formats selected", "Select at least one sigil export format.")
                return
        else:
            options["color"] = self.export_color
        self.export_button.setEnabled(False)
        self.export_button.setText("Exporting...")
        self.type_combo.setEnabled(False)
        rows = list(self.selected.values())
        progress = ExportProgressDialog(len(rows), self)
        progress.status.setText(f"Exporting {self.item_type.lower()}...")
        self._progress_dialog = progress

        job = ExportJob(rows, self.item_type, options, Path(self.output_edit.text()), self)
        job.progress.connect(self._update_export_progress)
        job.message.connect(self._show_export_message)
        job.finished.connect(self._export_finished)
        job.finished.connect(lambda target=job: self._export_jobs.remove(target) if target in self._export_jobs else None)
        self._export_jobs.append(job)
        progress.show()
        job.start()

    def _update_export_progress(self, completed, total, item_name):
        if self._progress_dialog is None:
            return
        self._progress_dialog.status.setText(f"Exporting {item_name}... ({completed} of {total})")
        self._progress_dialog.progress.setValue(completed)

    def _show_export_message(self, item_name, level, message):
        if self._progress_dialog is not None:
            self._progress_dialog.add_message(item_name, level, message)

    def _export_finished(self, succeeded, failed, total, warnings, errors):
        if self._progress_dialog is not None:
            self._progress_dialog.progress.setValue(total)
            self._progress_dialog.allow_close = True
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
            self._progress_dialog = None
        self.export_button.setEnabled(True)
        self.export_button.setText("Export")
        self.type_combo.setEnabled(True)
        if errors:
            details = (f"Warnings:\n{warnings}\n\n" if warnings else "") + f"Errors:\n{errors}"
            dialog = ExportSummaryDialog(
                "Export completed with errors",
                f"Exported {succeeded} of {total} items; {failed} failed.",
                details,
                self,
            )
            dialog.exec()
        elif warnings:
            dialog = ExportSummaryDialog(
                "Export completed with warnings",
                f"Exported {succeeded} {self.item_type.lower()} with warnings to:\n{self.output_edit.text()}",
                f"Warnings:\n{warnings}",
                self,
            )
            dialog.exec()
        else:
            QMessageBox.information(
                self,
                "Export complete",
                f"Exported {succeeded} {self.item_type.lower()} to:\n{self.output_edit.text()}",
            )

    def closeEvent(self, event):
        active_jobs = [job for job in self._export_jobs if job.is_running()]
        if active_jobs:
            answer = QMessageBox.question(
                self,
                "Export in progress",
                "An export is still running. Wait for it to finish before closing?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            for job in active_jobs:
                job.wait_for_done()
        event.accept()
