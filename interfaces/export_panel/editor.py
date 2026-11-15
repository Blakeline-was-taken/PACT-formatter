"""Filter, select, and bulk-export cards, sigils, and traits."""

import csv
from pathlib import Path

from PySide6.QtCore import QSize, QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import sigils
from ..card_editor.data import CARDS_PATH, parse_card_tags
from ..gui_helpers import ColorPickerButton, NoWheelComboBox, ROOT, open_folder, set_widget_tooltip
from ..sigil_trait_editor.data import SIGIL_PATH, TRAIT_PATH
from ..tag_data import CARD_TAG_OPTIONS, CARD_TAG_TOOLTIPS, SIGIL_TRAIT_TAG_OPTIONS, SIGIL_TRAIT_TAG_TOOLTIPS
from .data import (
    COST_FILTERS,
    EXPORT_TYPES,
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
    CARD_PREVIEW_SIZE,
    PATCH_PREVIEW_SIZE,
    SIGIL_PREVIEW_SIZE,
    TRAIT_PREVIEW_SIZE,
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
        self.settings = QSettings("Blakeline-was-taken", "PACT Formatter")
        default_output_dir = str(ROOT / "exports")
        self.output_dirs = {item_type: str(self.settings.value(f"exportDirectories/{item_type}", default_output_dir)) for item_type in EXPORT_TYPES}
        self.selected = {}
        self.selected_list_items = {}
        self.visible_rows = []
        self.result_model = ExportResultsModel(self)
        self.result_model.previewFailed.connect(self._preview_failed)
        self._drag_selecting = False
        self._export_jobs = []
        self._progress_dialog = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self._refresh_results)
        self._build_ui()
        self._set_type_content()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        self.main_splitter = splitter

        filter_column = QWidget()
        filter_column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        filter_column_layout = QVBoxLayout(filter_column)
        filter_column_layout.setContentsMargins(0, 0, 0, 0)
        filter_column_layout.setSpacing(8)

        self.header = QGroupBox("Export setup")
        self.header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        header_layout = QFormLayout(self.header)
        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(EXPORT_TYPES)
        self.type_combo.setToolTip("Choose to view and export cards, sigils, or traits.")
        self.type_combo.currentTextChanged.connect(self._change_type)
        header_layout.addRow("Export type", self.type_combo)
        self.options_widget = QWidget()
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addRow("Options", self.options_widget)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(self.output_dirs[self.item_type])
        self.output_edit.setReadOnly(True)
        self.output_edit.setToolTip("Destination folder for the exports.")
        browse = QPushButton("Choose folder...")
        browse.setToolTip("Choose the output folder for the exports.")
        browse.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse)
        self.output_browse_button = browse
        header_layout.addRow("Output folder", output_row)
        filter_column_layout.addWidget(self.header)

        filter_title = QLabel("Filters")
        filter_title.setObjectName("sectionTitle")
        filter_column_layout.addWidget(filter_title)
        self.filter_content = QWidget()
        self.filter_layout = QVBoxLayout(self.filter_content)
        self.filter_layout.setContentsMargins(8, 8, 8, 8)
        self.filter_layout.setSpacing(12)
        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.filter_scroll.setWidget(self.filter_content)
        filter_column_layout.addWidget(self.filter_scroll, 1)
        self.filter_column = filter_column
        splitter.addWidget(filter_column)

        self.collection_column = QWidget()
        collection_layout = QVBoxLayout(self.collection_column)
        collection_layout.setContentsMargins(0, 0, 0, 0)
        collection_layout.setSpacing(8)

        result_header = QHBoxLayout()
        result_title = QLabel("Available Items")
        result_title.setObjectName("sectionTitle")
        self.result_count = QLabel()
        self.result_count.setObjectName("mutedText")
        self.result_count.setToolTip("Number of items matching the current filters.")
        self.preview_button = QPushButton("See preview")
        self.preview_button.setCheckable(True)
        self.preview_button.setToolTip("Toggle between raw assets and rendered export previews.")
        self.preview_button.toggled.connect(self._toggle_preview)
        select_all = QPushButton("Select all")
        select_all.setToolTip("Add every item currently visible after filtering to the export selection.")
        select_all.clicked.connect(self._select_all_visible)
        deselect_all = QPushButton("Deselect all")
        deselect_all.setToolTip("Remove every currently visible item from the export selection.")
        deselect_all.clicked.connect(self._deselect_all_visible)
        result_header.addWidget(result_title)
        result_header.addStretch()
        result_header.addWidget(self.result_count)
        result_header.addWidget(self.preview_button)
        result_header.addWidget(select_all)
        result_header.addWidget(deselect_all)
        collection_layout.addLayout(result_header)
        self.preview_error_label = QLabel()
        self.preview_error_label.setWordWrap(True)
        self.preview_error_label.setObjectName("mutedText")
        self.preview_error_label.setToolTip("Export preview could not be rendered.")
        self.preview_error_label.hide()
        collection_layout.addWidget(self.preview_error_label)
        self.results = ExportResultsView()
        self.results.setModel(self.result_model)
        self.results_delegate = ExportResultsDelegate(self.result_model, self.results)
        self.results.setItemDelegate(self.results_delegate)
        self.results.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results.itemPressed.connect(self._result_item_pressed)
        self.results.itemHovered.connect(self._result_item_hovered)
        self.results.selectionDragFinished.connect(self._finish_result_drag_selection)
        self.results.resized.connect(self._update_result_columns)
        collection_layout.addWidget(self.results, 1)
        self.collection_column.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        splitter.addWidget(self.collection_column)
        self.selected_panel = self._build_sidebar()
        splitter.addWidget(self.selected_panel)
        splitter.setSizes([298, 690, 302])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        root.addWidget(splitter, 1)

    def _build_sidebar(self):
        sidebar = QGroupBox("Selected items")
        sidebar.setToolTip("Items selected for the next export. Drag across items in the collection to select them.")
        layout = QVBoxLayout(sidebar)
        self.selected_count = QLabel("0 selected")
        self.selected_count.setToolTip("Number of items currently selected for export.")
        layout.addWidget(self.selected_count)
        self.selected_list = DragSelectListWidget()
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.setToolTip("Selected items. Select one or more entries here before removing them.")
        layout.addWidget(self.selected_list, 1)
        remove = QPushButton("Remove selected")
        remove.setToolTip("Remove highlighted entries from the export selection.")
        remove.clicked.connect(self._remove_selected)
        layout.addWidget(remove)
        self.export_button = QPushButton("Export")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setToolTip("Export all selected items to the output folder.")
        self.export_button.clicked.connect(self._start_export)
        layout.addWidget(self.export_button)
        return sidebar

    def _change_type(self, item_type):
        if item_type == self.item_type:
            return
        question = QMessageBox.question(
            self,
            "Clear selected items?",
            f"Switching to {item_type.lower()} will clear your {self.item_type.lower()} selection. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if self.selected and question != QMessageBox.Yes:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentText(self.item_type)
            self.type_combo.blockSignals(False)
            return
        self.selected.clear()
        self.item_type = item_type
        self.output_edit.setText(self.output_dirs[item_type])
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
        self._clear_layout(self.filter_layout)
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
        self.filter_layout.addStretch()
        QTimer.singleShot(0, self._refresh_filter_scroll)
        self._refresh_results()

    def _refresh_filter_scroll(self):
        self.filter_scroll.takeWidget()
        self.filter_scroll.setWidget(self.filter_content)

    def _build_card_options(self):
        self.sorted_option = QCheckBox("Sort into Temple/Tier folders")
        self.sorted_option.setChecked(True)
        self.sorted_option.setToolTip("Place exported cards in subfolders named after their temple and tier.")
        self.options_layout.addWidget(self.sorted_option)
        self.options_layout.addStretch()

    def _build_item_options(self, item_type):
        self.export_color = (0, 0, 0)
        self.color_button = ColorPickerButton(self.export_color, "Color")
        self.color_button.setToolTip("Choose the color applied to exported sigils or traits.")
        self.color_button.colorPicked.connect(self._set_export_color)
        self.options_layout.addWidget(self.color_button)
        self.format_checks = {}
        if item_type == "Sigils":
            for label in ("Standard", "Shortened", "Base game", "Patch"):
                check = QCheckBox(label)
                check.setToolTip(f"Include the {label.lower()} sigil variant in the export.")
                check.setChecked(label == "Standard")
                check.toggled.connect(self._preview_options_changed)
                self.options_layout.addWidget(check)
                self.format_checks[label] = check
        else:
            traitline_note = QLabel("Traitline output is unavailable (assets are not installed).")
            traitline_note.setObjectName("mutedText")
            self.options_layout.addWidget(traitline_note)
        self.options_layout.addStretch()

    def _set_export_color(self, color):
        self.export_color = color
        self._preview_options_changed()

    def _preview_options(self):
        if self.item_type == "Sigils":
            return {
                "formats": [name for name, check in self.format_checks.items() if check.isChecked()],
                "color": self.export_color,
            }
        if self.item_type == "Traits":
            return {"color": self.export_color}
        return {}

    def _preview_options_changed(self, *_):
        self.result_model.set_preview_mode(self.preview_button.isChecked(), self._preview_options())
        self._update_result_columns()

    def _toggle_preview(self, enabled):
        self.preview_button.setText("Show raw assets" if enabled else "See preview")
        self.preview_error_label.clear()
        self.preview_error_label.hide()
        self._preview_options_changed()

    def _preview_failed(self, item_name, error):
        self.preview_error_label.setText(f"Could not preview {item_name}: {error}")
        self.preview_error_label.show()

    def _filter_box(self, title):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("filterSectionTitle")
        layout.addWidget(heading)
        self.filter_layout.addWidget(box)
        return layout

    def _labeled_filter(self, label, field, layout):
        tooltip = field.toolTip() or f"Filter available items by {label.lower()}."
        label_widget = QLabel(label)
        label_widget.setToolTip(tooltip)
        set_widget_tooltip(field, tooltip)
        layout.addWidget(label_widget)
        layout.addWidget(field)

    def _autocomplete(self, values, placeholder):
        field = NoWheelComboBox()
        field.setEditable(True)
        field.setInsertPolicy(QComboBox.NoInsert)
        field.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        field.setMinimumContentsLength(6)
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
        data = self._filter_box("Card Data")
        self.name_filter = self._autocomplete(names, "Card name")
        self.temple_filter = self._autocomplete(temples, "Temple")
        self.tier_filter = self._autocomplete(tiers, "Tier")
        self.name_filter.setToolTip("Show cards whose names contain this text.")
        self.temple_filter.setToolTip("Show cards whose temple contains this text.")
        self.tier_filter.setToolTip("Show cards whose tier contains this text.")
        self._labeled_filter("Card Name", self.name_filter, data)
        self._labeled_filter("Temple", self.temple_filter, data)
        self._labeled_filter("Tier", self.tier_filter, data)

        costs_box = self._filter_box("Cost")
        self.cost_checks = {}
        cost_grid = QGridLayout()
        for index, (label, key) in enumerate(COST_FILTERS):
            check = QCheckBox("Overcharge" if key == "max" else label)
            check.setToolTip(f"Include cards that cost {label.lower()}.")
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

        stats = self._filter_box("Stats")
        self.stat_controls = {}
        for stat in ("Power", "Health"):
            row = QHBoxLayout()
            row.addWidget(QLabel(stat))
            operator = NoWheelComboBox()
            operator.addItems(STAT_OPERATORS)
            operator.setToolTip(f"Comparison used to filter cards by {stat.lower()}.")
            value = QLineEdit()
            value.setPlaceholderText("Value")
            value.setToolTip(f"Value compared with the card's {stat.lower()}. Leave blank to ignore.")
            operator.currentTextChanged.connect(self._schedule_results_refresh)
            value.textChanged.connect(self._schedule_results_refresh)
            row.addWidget(operator)
            row.addWidget(value)
            stats.addLayout(row)
            has_sigil = QCheckBox(f"Has {stat.lower()} sigil")
            has_sigil.setToolTip(f"Show only cards with a sigil or trait tagged to replace {stat.lower()}.")
            has_sigil.toggled.connect(self._schedule_results_refresh)
            stats.addWidget(has_sigil)
            setattr(self, f"has_{stat.lower()}_sigil_filter", has_sigil)
            self.stat_controls[stat] = (operator, value)

        for category, field in (
                ("Sigils", "Sigils"),
                ("Traits", "Traits"),
                ("Tribes", "Tribes"),
                ("Artists", "Credit"),
            ):
            box = self._filter_box(category)
            values = []
            for card in self.cards:
                values.extend(_card_filter_values(card, category, field))
            selector = SelectedValues(_unique(values), f"Search {category.lower()}...")
            selector.setToolTip(f"Filter cards by one or more {category.lower()}.")
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

        tags = self._filter_box("Tags")
        self.card_tag_filter = SelectedValues(CARD_TAG_OPTIONS, "Search tags...", option_tooltips=CARD_TAG_TOOLTIPS)
        self.card_tag_filter.setToolTip("Filter by known or custom tags. Background, symbols, and extra cells have separate filters below.")
        self.card_tag_filter.changed.connect(self._schedule_results_refresh)
        self._labeled_filter("General tags", self.card_tag_filter, tags)
        self.card_tag_all = QCheckBox("All")
        self.card_tag_all.setToolTip("Require cards to have every selected general tag.")
        self.card_tag_only = QCheckBox("Only")
        self.card_tag_only.setToolTip("Require cards to have no other general tags besides the selected ones.")
        self.card_tag_all.toggled.connect(self._schedule_results_refresh)
        self.card_tag_only.toggled.connect(self._schedule_results_refresh)
        tags.addWidget(self.card_tag_all)
        tags.addWidget(self.card_tag_only)
        self.background_filter = self._autocomplete((tag[:-3] for card in self.cards for tag in _split_list(card.get("Tags", "")) if tag.endswith("_bg")), "Background sigil tag")
        self.background_filter.setToolTip("Show cards whose background modifier contains this text.")
        self.extra_cells_filter = OptionalSpinBox()
        self.extra_cells_filter.setToolTip("Match this exact number of extra energy cells. Leave blank to ignore.")
        self.extra_cells_filter.valueChanged.connect(self._schedule_results_refresh)
        symbol_names = (_display_name(row.get("Name", "")) for row in self.sigils)
        self.symbol_1_filter = self._autocomplete(symbol_names, "Symbol 1")
        self.symbol_2_filter = self._autocomplete((_display_name(row.get("Name", "")) for row in self.sigils), "Symbol 2")
        self.symbol_1_filter.setToolTip("Filter by a sigil used as a symbol.")
        self.symbol_2_filter.setToolTip("Filter by a sigil used as a symbol.")
        for label, widget in (("Background", self.background_filter), ("Extra Cells", self.extra_cells_filter)):
            self._labeled_filter(label, widget, tags)
        symbols = QWidget()
        symbol_layout = QHBoxLayout(symbols)
        symbol_layout.setContentsMargins(0, 0, 0, 0)
        for label, widget in (("Symbol 1", self.symbol_1_filter), ("Symbol 2", self.symbol_2_filter)):
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            self._labeled_filter(label, widget, column)
            symbol_layout.addLayout(column, 1)
        tags.addWidget(symbols)

    def _build_item_filters(self, rows):
        data = self._filter_box(f"{self.item_type[:-1]} Data")
        self.item_name_filter = self._autocomplete((_display_name(row.get("Name", "")) for row in rows), f"Search {self.item_type[:-1].lower()} name...")
        self.item_name_filter.setToolTip(f"Show {self.item_type.lower()} whose names contain this text.")
        self._labeled_filter(f"{self.item_type[:-1]} Name", self.item_name_filter, data)
        tags = self._filter_box("Tags")
        self.item_tag_filter = SelectedValues(SIGIL_TRAIT_TAG_OPTIONS, "Search tags...", option_tooltips=SIGIL_TRAIT_TAG_TOOLTIPS)
        self.item_tag_filter.setToolTip(f"Filter {self.item_type.lower()} by known or custom tags.")
        self.item_tag_filter.changed.connect(self._schedule_results_refresh)
        self._labeled_filter("Select tags", self.item_tag_filter, tags)
        self.item_tag_all = QCheckBox("All")
        self.item_tag_all.setToolTip(f"Require {self.item_type.lower()} to have every selected tag.")
        self.item_tag_only = QCheckBox("Only")
        self.item_tag_only.setToolTip(f"Require {self.item_type.lower()} to have no other tags besides the selected ones.")
        self.item_tag_all.toggled.connect(self._schedule_results_refresh)
        self.item_tag_only.toggled.connect(self._schedule_results_refresh)
        tags.addWidget(self.item_tag_all)
        tags.addWidget(self.item_tag_only)

    def _matches_values(self, values, selected, require_all, require_only):
        if not selected:
            return True
        normalized = {value.casefold() for value in values}
        requested = {value.casefold() for value in selected}
        has_requested = requested.issubset(normalized) if require_all else bool(requested & normalized)
        return has_requested and (not require_only or normalized.issubset(requested))

    def _matches_item_row(self, row):
        name_filter = self.item_name_filter.currentText().strip().casefold()
        if name_filter and name_filter not in _display_name(row.get("Name", "")).casefold():
            return False
        return self._matches_values(_split_list(row.get("Tags", "")), self.item_tag_filter.selected, self.item_tag_all.isChecked(), self.item_tag_only.isChecked())

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
                if not self._matches_values(parsed["general_tags"], self.card_tag_filter.selected, self.card_tag_all.isChecked(), self.card_tag_only.isChecked()):
                    continue
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
        return [row for row in source if self._matches_item_row(row)]

    def _schedule_results_refresh(self, *_):
        self._refresh_timer.start()

    def _update_result_columns(self):
        if not hasattr(self, "results") or not hasattr(self, "results_delegate"):
            return
        scrollbar = self.results.verticalScrollBar()
        available_width = self.results.viewport().width()
        if scrollbar.isVisible():
            available_width += scrollbar.width()
        available_width = max(available_width - scrollbar.sizeHint().width(), 1)
        large_preview = self.preview_button.isChecked()
        if large_preview:
            preview_size = CARD_PREVIEW_SIZE
            if self.item_type == "Traits":
                preview_size = TRAIT_PREVIEW_SIZE
            elif self.item_type == "Sigils":
                formats = self._preview_options()["formats"]
                if formats and formats[0] == "Patch":
                    preview_size = PATCH_PREVIEW_SIZE
                elif not formats or formats[0] in ("Standard", "Shortened"):
                    preview_size = SIGIL_PREVIEW_SIZE
            self.results_delegate.preview_icon_size = preview_size
            minimum_tile_width = preview_size.width() + 8
        else:
            minimum_tile_width = 120
        columns = max(1, available_width // minimum_tile_width)
        tile_width = max(minimum_tile_width, available_width // columns)
        row_count = (len(self.visible_rows) + columns - 1) // columns
        if large_preview:
            extra_height = 60 if self.item_type == "Cards" else 52
            tile_height = self.results_delegate.preview_icon_size.height() + extra_height
        else:
            tile_height = 150 if row_count == 1 else 130
        tile_size = QSize(tile_width, tile_height)
        self.results_delegate.tile_size = tile_size
        self.results.setGridSize(tile_size)
        self.result_column_count = columns
        self.results.setMinimumHeight(tile_height)
        self.results.doItemsLayout()

    def _refresh_results(self, *_):
        if not hasattr(self, "result_model"):
            return
        rows = self._filtered_rows()
        self.visible_rows = rows
        self.result_count.setText(f"{len(rows)} items")
        self.result_model.set_rows(rows, self.item_type)
        self.result_model.set_selected_keys(self.selected)
        self.result_model.set_preview_mode(self.preview_button.isChecked(), self._preview_options())
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
            self.output_dirs[self.item_type] = folder
            self.settings.setValue(f"exportDirectories/{self.item_type}", folder)

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
        self.output_browse_button.setEnabled(False)
        rows = list(self.selected.values())
        progress = ExportProgressDialog(len(rows), self)
        progress.status.setText(f"Exporting {self.item_type.lower()}...")
        self._progress_dialog = progress

        if self.item_type == "Cards":
            options["all_card_rows"] = self.cards
        output_dir = Path(self.output_edit.text())
        self._active_output_dir = output_dir
        job = ExportJob(rows, self.item_type, options, output_dir, self)
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
        self.output_browse_button.setEnabled(True)
        output_dir = str(self._active_output_dir)
        if errors:
            details = (f"Warnings:\n{warnings}\n\n" if warnings else "") + f"Errors:\n{errors}"
            dialog = ExportSummaryDialog("Export completed with errors", f"Exported {succeeded} of {total} items; {failed} failed.", details, self)
            dialog.exec()
        elif warnings:
            dialog = ExportSummaryDialog("Export completed with warnings", f"Exported {succeeded} {self.item_type.lower()} with warnings to:\n{output_dir}", f"Warnings:\n{warnings}", self)
            dialog.exec()
        if succeeded:
            answer = QMessageBox.question(
                self,
                "Open export folder?",
                f"Exported {succeeded} {self.item_type.lower()} to:\n{output_dir}\n\nOpen this folder?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes and not open_folder(output_dir):
                QMessageBox.warning(self, "Could not open folder", f"Could not open the export folder:\n{output_dir}")

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
