import csv
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from model import DEFAULT_CONFIG, cards, sigils
from .gui_helpers import Gemification, NoWheelComboBox, ROOT, _split, _join

SIGIL_PATH = ROOT / DEFAULT_CONFIG["sigils_file_path"]
TRAIT_PATH = ROOT / DEFAULT_CONFIG["traits_file_path"]
SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "sigils"
CONDUIT_SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "conduit_sigil_indicators"

SIGIL_TAG_OPTIONS = [
    "power_sigil",
    "health_sigil",
    "conduit_sigil",
    "mox_green",
    "mox_orange",
    "mox_blue",
    "mox_prism",
]


def _normalize_sigil_name(name):
    return name.translate(str.maketrans("", "", " ',-!?"))


def _csv_rows(path):
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error):
        return []


class SigilTraitEditor(QWidget):
    """Search, edit, preview, and save sigils and traits from their shared CSV files."""

    def __init__(self):
        super().__init__()
        self.data = {"Sigils": _csv_rows(SIGIL_PATH), "Traits": _csv_rows(TRAIT_PATH)}
        self.current_section = "Sigils"
        self.current_name = ""
        self.original = {}
        self.loading = False
        self._build_ui()
        self._refresh_search()
        self._select_name(self._names_for_current_section()[0] if self._names_for_current_section() else "")

    def _names_for_current_section(self):
        return [row.get("Name", "") for row in self.data.get(self.current_section, []) if row.get("Name")]

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(self._build_header())
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_form())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([560, 500])
        root.addWidget(splitter, 1)

    def _build_header(self):
        box = QGroupBox("Sigil/Trait selection")
        layout = QHBoxLayout(box)
        self.category = NoWheelComboBox()
        self.category.addItems(["Sigils", "Traits"])
        self.category.currentTextChanged.connect(self._switch_section)
        layout.addWidget(self.category)

        self.search = NoWheelComboBox()
        self.search.setEditable(True)
        self.search.setPlaceholderText("Search sigils and traits...")
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.lineEdit().textEdited.connect(self._filter_names)
        layout.addWidget(self.search, 1)

        load = QPushButton("Edit")
        load.clicked.connect(self._search_activated)
        layout.addWidget(load)

        new = QPushButton("+ New item")
        new.clicked.connect(self._new_item)
        layout.addWidget(new)
        return box

    def _build_form(self):
        container = QWidget()
        outer = QVBoxLayout(container)
        title = QLabel("Item data")
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

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._changed)
        form.addRow("Name", self.name_edit)

        self.description_edit = QLineEdit()
        self.description_edit.textChanged.connect(self._changed)
        form.addRow("Description", self.description_edit)

        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(["Sigil", "Trait"])
        self.type_combo.currentTextChanged.connect(self._changed)
        form.addRow("Type", self.type_combo)

        self.icon_edit = QLineEdit()
        self.icon_edit.setReadOnly(True)
        choose_icon = QPushButton("Choose icon...")
        choose_icon.clicked.connect(self._choose_icon)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon_edit, 1)
        icon_row.addWidget(choose_icon)
        form.addRow("Icon", icon_row)
        
        self.colorless_icon_edit = QLineEdit()
        self.colorless_icon_edit.setReadOnly(True)
        colorless_choose_icon = QPushButton("Choose colorless icon...")
        colorless_choose_icon.clicked.connect(lambda: self._choose_icon(colorless=True))
        colorless_delete_icon = QPushButton("X")
        colorless_delete_icon.setFixedWidth(30)
        colorless_delete_icon.clicked.connect(self._delete_colorless_icon)
        colorless_icon_row = QHBoxLayout()
        colorless_icon_row.addWidget(self.colorless_icon_edit, 1)
        colorless_icon_row.addWidget(colorless_choose_icon)
        colorless_icon_row.addWidget(colorless_delete_icon)
        form.addRow("Colorless Icon", colorless_icon_row)

        self.conduit_icon_edit = QLineEdit()
        self.conduit_icon_edit.setReadOnly(True)
        conduit_choose_icon = QPushButton("Choose conduit image...")
        conduit_choose_icon.clicked.connect(lambda: self._choose_icon(conduit=True))
        self.conduit_icon_row = QWidget()
        conduit_icon_layout = QHBoxLayout(self.conduit_icon_row)
        conduit_icon_layout.setContentsMargins(0, 0, 0, 0)
        conduit_icon_layout.addWidget(self.conduit_icon_edit, 1)
        conduit_icon_layout.addWidget(conduit_choose_icon)
        
        self.tags = QWidget()
        tags_layout = QVBoxLayout(self.tags)
        self.tag_checks = {}
        for tag in SIGIL_TAG_OPTIONS:
            check = QPushButton(tag)
            check.setCheckable(True)
            check.toggled.connect(self._changed)
            self.tag_checks[tag] = check
            tags_layout.addWidget(check)
        form.addRow("Tags", self.tags)
        form.addRow("Conduit image", self.conduit_icon_row)
        self.conduit_icon_label = form.labelForField(self.conduit_icon_row)

        scroll.setWidget(body)
        outer.addWidget(scroll)

        actions = QHBoxLayout()
        delete = QPushButton("Delete item")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_item)
        actions.addWidget(delete)
        outer.addLayout(actions)
        return container

    def _build_preview(self):
        box = QGroupBox("Live preview")
        layout = QVBoxLayout(box)

        self.preview = QLabel("Select an item")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 420)
        self.preview.setStyleSheet("background: #e8edf5;")
        layout.addWidget(self.preview, 1)

        self.preview_bar = QWidget()
        preview_layout = QHBoxLayout(self.preview_bar)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_condition = NoWheelComboBox()
        self.preview_condition.addItems(["None", "Cell", "Latch", "Hint", "Gemified", "Tribal", "Rainbow"])
        self.preview_condition.setCurrentText("None")
        self.preview_condition.currentTextChanged.connect(self._condition_changed)
        preview_layout.addWidget(self.preview_condition)
        self.preview_gems = Gemification(False)
        self.preview_gems.setVisible(False)
        self.preview_gems.changed.connect(self._render_preview)
        preview_layout.addWidget(self.preview_gems)
        self.preview_condition.setVisible(False)
        self.preview_gems.setVisible(False)
        layout.addWidget(self.preview_bar)

        buttons = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        save_export = QPushButton("Save and Export")
        save_export.clicked.connect(lambda: self._save(export=True))
        buttons.addWidget(save)
        buttons.addWidget(save_export)
        layout.addLayout(buttons)
        return box

    def _switch_section(self, section):
        self.current_section = section
        self._update_conduit_icon_visibility()
        self._refresh_search()

    def _refresh_search(self, text=""):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(self._names_for_current_section())
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _filter_names(self, text):
        query = text.lower()
        matches = [name for name in self._names_for_current_section() if query in name.lower()]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.addItems(matches)
        self.search.setCurrentText(text)
        self.search.blockSignals(False)

    def _search_activated(self):
        name = self.search.currentText().strip()
        if name and name in self._names_for_current_section():
            self._select_name(name)

    def _select_name(self, name):
        if not name:
            self._new_item()
            return
        self.current_name = name
        row = next((item for item in self.data[self.current_section] if item.get("Name") == name), {})
        self.original = dict(row)
        self.original["Type"] = "Sigil" if self.current_section == "Sigils" else "Trait"
        self._populate(row)
        self._refresh_search(name)
        self._render_preview()

    def _new_item(self):
        self.current_name = ""
        self.original = {}
        self._populate({"Name": "", "Description": "", "Tags": "", "Type": "Sigil" if self.current_section == "Sigils" else "Trait"})
        self._render_preview()

    def _populate(self, row):
        self.loading = True
        self.name_edit.setText(row.get("Name", ""))
        self.description_edit.setText(row.get("Description", ""))
        self.type_combo.setCurrentText(row.get("Type", "Sigil" if self.current_section == "Sigils" else "Trait"))
        
        icon_name = _normalize_sigil_name(row.get("Name", ""))
        icon_path = SIGIL_ICON_DIR / f"{icon_name}.png"
        self.icon_edit.setText(icon_path.name if icon_name and icon_path.is_file() else "")
        icon_path = SIGIL_ICON_DIR / f"{icon_name}_outline.png"
        self.colorless_icon_edit.setText(icon_path.name if icon_name and icon_path.is_file() else "")
        conduit_icon_path = CONDUIT_SIGIL_ICON_DIR / f"{row.get('Name', '').replace(' ', '')}.png"
        self.conduit_icon_edit.setText(
            conduit_icon_path.name if row.get("Name") and conduit_icon_path.is_file() else ""
        )

        tags = set(_split(row.get("Tags", "")))
        for tag, check in self.tag_checks.items():
            check.setChecked(tag in tags)
        self.loading = False
        self._update_conduit_icon_visibility()
        self._update_preview_visibility()

    def _update_conduit_icon_visibility(self):
        """Offer conduit-image selection only for conduit sigils."""
        is_conduit = (
            self.current_section == "Sigils"
            and self.type_combo.currentText() == "Sigil"
            and self.tag_checks["conduit_sigil"].isChecked()
        )
        self.conduit_icon_row.setVisible(is_conduit)
        self.conduit_icon_label.setVisible(is_conduit)

    def _update_preview_visibility(self):
        item_type = self.type_combo.currentText()
        is_sigil = item_type == "Sigil"
        self.preview_condition.setVisible(is_sigil)
        self.preview_gems.setVisible(is_sigil and self.preview_condition.currentText() == "Gemified")

    def _current_data(self):
        name = self.name_edit.text().strip()
        description = self.description_edit.text().strip()
        tags = [tag for tag, check in self.tag_checks.items() if check.isChecked()]
        return {
            "Name": name,
            "Description": description,
            "Tags": _join(tags),
            "Type": self.type_combo.currentText(),
        }

    def _changed(self):
        if not self.loading:
            self._update_conduit_icon_visibility()
            self._update_preview_visibility()
            self._render_preview()

    def _condition_changed(self):
        self._update_preview_visibility()
        self._render_preview()

    def _preview_entry(self):
        row = self._current_data()
        name = row["Name"] or "Example sigil"
        description = row["Description"]
        tags = _split(row["Tags"])
        preview_type = row["Type"]

        if preview_type == "Sigil":
            conditional = self.preview_condition.currentText()
            current = []
            if conditional == "Tribal":
                current.append("TRIBAL")
            elif conditional == "Rainbow":
                current.append("RAINBOW")
            if conditional in ("Cell", "Latch", "Hint"):
                current.append(f"{conditional}_{name}")
            elif conditional == "Gemified":
                current.append(self.preview_gems.value(name))
            elif conditional == "None":
                current.append(name)
            else:
                current.append(name)
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
        try:
            row = self._preview_entry()
            current_name = row["Name"]
            current_description = row["Description"]
            current_tags = row["Tags"]
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

            preview_row = {
                "Card Name": "",
                "Art File": "",
                "Temple": "",
                "Tier": "",
                "Power": "",
                "Health": "",
                "Cost": "",
                "Sigils": row["Sigils"],
                "Token": "",
                "Traits": row["Traits"],
                "Tribes": "",
                "Flavor Text": "",
                "Credit": "",
                "Tags": "mox_indicator" if "mox_" in current_tags else "",
            }
            image = cards.create_card(preview_row)
            pixmap = self._pixmap_for(image)
            self.preview.setPixmap(pixmap)
        except Exception as error:
            self.preview.clear()
            self.preview.setText(f"Preview unavailable: {error}")

    @staticmethod
    def _pixmap_for(image):
        from PySide6.QtGui import QPixmap
        from PIL.ImageQt import ImageQt

        return QPixmap.fromImage(ImageQt(image)).scaled(320, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _choose_icon(self, colorless=False, conduit=False):
        name = self.name_edit.text().strip()
        icon_to_edit = (
            self.conduit_icon_edit
            if conduit
            else self.colorless_icon_edit
            if colorless
            else self.icon_edit
        )
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter a name before choosing an icon.")
            return

        icon_dir = CONDUIT_SIGIL_ICON_DIR if conduit else SIGIL_ICON_DIR
        title = "Choose conduit image" if conduit else "Choose sigil icon"
        filename, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(icon_dir),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not filename:
            return

        source = Path(filename)
        outline = "_outline" if colorless else ""
        target_name = name.replace(" ", "") if conduit else _normalize_sigil_name(name)
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
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        icon_to_edit.setText(str(target.name))
        self._render_preview()

    def _delete_colorless_icon(self):
        name = self.name_edit.text().strip()
        if not name:
            return

        icon_name = _normalize_sigil_name(name)
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
                QMessageBox.warning(self, "Error", f"Could not delete icon: {error}")
                return
            self.colorless_icon_edit.setText("")
            self._render_preview()

    def _save(self, export=False):
        data = self._current_data()
        name = data["Name"]
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
                f"Changing '{old_name}' from {current_type} to {target_type} will remove the old entry and create a new one in the {target_type.lower()} file. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if warning != QMessageBox.Yes:
                return False

        if old_name and old_name != name and source_section != target_section:
            prompt = QMessageBox.question(
                self,
                "Update related cards?",
                f"Update cards that reference '{old_name}' so they move it from {source_section.lower()} to {target_section.lower()}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if prompt == QMessageBox.Yes:
                self._update_cards_for_type_change(old_name, name, source_section, target_section)

        self._write_item(name, data, source_section, target_section)
        self.current_name = name
        self.original = dict(data)
        self.original["Type"] = target_type
        self._refresh_search(name)
        self.category.setCurrentText(target_section)
        self._render_preview()

        if export:
            export_dir = ROOT / "exports" / ("sigils" if target_type == "Sigil" else "traits")
            export_dir.mkdir(parents=True, exist_ok=True)
            preview_row = self._preview_entry()
            preview_row["Card Name"] = ""
            preview_row["Temple"] = "beast"
            preview_row["Tier"] = "common"
            preview_image = cards.create_card({
                "Card Name": "",
                "Art File": "",
                "Temple": "beast",
                "Tier": "common",
                "Power": "0",
                "Health": "0",
                "Cost": "",
                "Sigils": preview_row.get("Sigils", ""),
                "Token": "",
                "Traits": preview_row.get("Traits", ""),
                "Tribes": "",
                "Flavor Text": "",
                "Credit": "",
                "Tags": "",
            })
            target = export_dir / f"{name}.png"
            preview_image.save(target)
            QMessageBox.information(self, "Exported", f"{name} was exported to {target}.")
        return True

    def _write_item(self, name, data, source_section, target_section):
        new_row = {"Name": name, "Description": data["Description"], "Tags": data["Tags"]}
        if source_section == target_section:
            rows = [row for row in self.data[source_section] if row.get("Name") != name]
        else:
            rows = [row for row in self.data[source_section] if row.get("Name") != name]
            self.data[source_section] = rows
            self.data[source_section] = [row for row in self.data[source_section] if row.get("Name") != name]

        target_rows = [row for row in self.data.get(target_section, []) if row.get("Name") != name]
        target_rows.append(new_row)
        self.data[target_section] = target_rows

        for section, path in (("Sigils", SIGIL_PATH), ("Traits", TRAIT_PATH)):
            rows = self.data.get(section, [])
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Name", "Description", "Tags"])
                writer.writeheader()
                writer.writerows(rows)

    def _update_cards_for_type_change(self, old_name, new_name, source_section, target_section):
        cards_path = ROOT / DEFAULT_CONFIG["cards_file_path"]
        try:
            with cards_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            return

        source_field = "Sigils" if source_section == "Sigils" else "Traits"
        target_field = "Sigils" if target_section == "Sigils" else "Traits"
        for row in rows:
            source_values = _split(row.get(source_field, ""))
            if old_name in source_values:
                source_values = [value for value in source_values if value != old_name]
                target_values = _split(row.get(target_field, ""))
                if new_name not in target_values:
                    target_values.append(new_name)
                row[source_field] = _join(source_values)
                row[target_field] = _join(target_values)
        with cards_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["Card Name", "Art File", "Temple", "Tier", "Cost", "Power", "Health", "Sigils", "Token", "Traits", "Tribes", "Flavor Text", "Credit", "Tags"])
            writer.writeheader()
            writer.writerows(rows)

    def _delete_item(self):
        if not self.current_name:
            return
        if self.current_section not in self.data:
            return
        result = QMessageBox.warning(
            self,
            "Delete item",
            f"Delete '{self.current_name}' from the {self.current_section.lower()} file?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        self.data[self.current_section] = [row for row in self.data[self.current_section] if row.get("Name") != self.current_name]
        for section, path in (("Sigils", SIGIL_PATH), ("Traits", TRAIT_PATH)):
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Name", "Description", "Tags"])
                writer.writeheader()
                writer.writerows(self.data.get(section, []))
        self.current_name = ""
        self._refresh_search()
        self._new_item()