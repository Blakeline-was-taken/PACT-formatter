"""Reusable Qt controls and result-grid components for export."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)
from PIL.ImageQt import ImageQt

from model import ASSETS_DIR, GENERAL_ASSETS_DIR
from ..gui_helpers import NoWheelComboBox, NoWheelSpinBox
from ..card_editor.data import ASSET_PATH
from ..sigil_trait_editor.data import SIGIL_ICON_DIR, normalize_sigil_name
from .data import crop_card_art as _crop_card_art, display_name as _display_name


CARD_THUMBNAIL_SIZE = QSize(104, 86)
CARD_PREVIEW_SIZE = QSize(176, 220)
SIGIL_PREVIEW_SIZE = QSize(176, 66)
TRAIT_PREVIEW_SIZE = QSize(176, 82)
PATCH_PREVIEW_SIZE = QSize(176, 168)
_TEMPLE_BACKGROUND_COLORS = {}


def _temple_background_color(temple):
    key = (temple or "").casefold()
    if key not in _TEMPLE_BACKGROUND_COLORS:
        palette_path = ASSETS_DIR / key / "colors.png"
        if not palette_path.is_file():
            palette_path = GENERAL_ASSETS_DIR / "colors.png"
        palette = QImage(str(palette_path))
        if palette.isNull() or palette.width() < 2:
            raise ValueError(f"Could not read the second temple palette color from {palette_path}.")
        _TEMPLE_BACKGROUND_COLORS[key] = palette.pixelColor(1, 0)
    return _TEMPLE_BACKGROUND_COLORS[key]


def _framed_card_pixmap(art, temple, size=CARD_THUMBNAIL_SIZE, use_temple_color=True):
    thumbnail = QPixmap(size)
    thumbnail.fill(Qt.transparent)
    available_size = size - QSize(4, 4)
    scaled_art = art.scaled(available_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    left = (thumbnail.width() - scaled_art.width()) // 2
    top = (thumbnail.height() - scaled_art.height()) // 2
    painter = QPainter(thumbnail)
    if use_temple_color:
        painter.fillRect(QRect(left, top, scaled_art.width(), scaled_art.height()), _temple_background_color(temple),)
    painter.drawPixmap(left, top, scaled_art)
    painter.setPen(QPen(QColor(Qt.black), 2))
    painter.drawRect(QRect(left, top, scaled_art.width() - 1, scaled_art.height() - 1))
    painter.end()
    return thumbnail


class ExportProgressDialog(QDialog):
    """Modal export progress view with a scrolling warning/error log."""

    def __init__(self, total, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporting")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        self.status = QLabel("Preparing export...")
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setPlaceholderText("Warnings and errors will appear here.")
        self.messages.setMaximumHeight(150)
        layout.addWidget(self.messages)
        self.allow_close = False

    def add_message(self, item_name, level, message):
        first_line = message.splitlines()[0] if message else ""
        self.messages.appendPlainText(f"{level}: {item_name}: {first_line}")

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()


class ExportSummaryDialog(QDialog):
    """Show a concise result summary with scrollable diagnostic details."""

    def __init__(self, title, summary, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 360)
        layout = QVBoxLayout(self)
        self.summary = QLabel(summary)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.details.setPlainText(details)
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class OptionalSpinBox(NoWheelSpinBox):
    """Nonnegative spin box whose initial zero value is displayed as empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blank = True
        self.setRange(0, 2147483647)
        self.setKeyboardTracking(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lineEdit().textEdited.connect(self._mark_nonblank)
        self.valueChanged.connect(self._mark_nonblank)
        self.lineEdit().clear()

    def textFromValue(self, value):
        if value == 0 and self._blank:
            return ""
        return super().textFromValue(value)

    def _mark_nonblank(self, *_):
        self._blank = False

    def focusOutEvent(self, event):
        was_empty = not self.lineEdit().text()
        super().focusOutEvent(event)
        if was_empty and self._blank and self.value() == 0:
            self.lineEdit().clear()

    def stepBy(self, steps):
        if not self.lineEdit().text() and steps < 0:
            return
        super().stepBy(steps)


class DragSelectListWidget(QListWidget):
    """List that supports painting a selection by dragging over its items."""

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and item:
            self._paint_selection = not item.isSelected()
            item.setSelected(self._paint_selection)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and hasattr(self, "_paint_selection"):
            item = self.itemAt(event.position().toPoint())
            if item:
                item.setSelected(self._paint_selection)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and hasattr(self, "_paint_selection"):
            del self._paint_selection
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ExportResultsModel(QAbstractListModel):
    """Lightweight filtered item model with lazily loaded thumbnail icons."""

    previewFailed = Signal(str, str)
    ITEM_KEY_ROLE = Qt.UserRole + 1
    SELECTED_ROLE = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.selected_keys = set()
        self.icons = {}
        self.row_indexes = {}
        self.item_type = "Cards"
        self.preview_mode = False
        self.preview_options = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        key = id(row)
        name = _display_name(row.get("Card Name", row.get("Name", "")))
        if role == Qt.DisplayRole:
            return name
        if role == Qt.DecorationRole:
            return self._icon_for_row(row, key)
        if role == Qt.ToolTipRole:
            return name
        if role == self.ITEM_KEY_ROLE:
            return key
        if role == self.SELECTED_ROLE:
            return key in self.selected_keys
        return None

    def set_rows(self, rows, item_type):
        if self.item_type != item_type:
            self.icons.clear()
        self.beginResetModel()
        self.rows = rows
        self.item_type = item_type
        self.row_indexes = {id(row): index for index, row in enumerate(rows)}
        self.endResetModel()

    def set_preview_mode(self, enabled, options=None):
        options = dict(options or {})
        if self.preview_mode == enabled and self.preview_options == options:
            return
        self.preview_mode = enabled
        self.preview_options = options
        self.icons.clear()
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0), [Qt.DecorationRole])

    def set_selected(self, key, selected):
        if selected:
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)
        row_index = self.row_indexes.get(key)
        if row_index is not None:
            model_index = self.index(row_index, 0)
            self.dataChanged.emit(model_index, model_index, [self.SELECTED_ROLE])

    def set_selected_keys(self, keys):
        self.selected_keys = set(keys)
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0), [self.SELECTED_ROLE])

    def _icon_for_row(self, row, key):
        if key not in self.icons:
            if self.preview_mode:
                try:
                    from .service import render_export_preview

                    image = render_export_preview(row, self.item_type, self.preview_options)
                    pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
                    if self.item_type == "Cards":
                        pixmap = _framed_card_pixmap(pixmap, row.get("Temple", ""), CARD_PREVIEW_SIZE, use_temple_color=False)
                    self.icons[key] = QIcon(pixmap)
                except Exception as error:
                    item_name = row.get("Card Name", row.get("Name", "Item"))
                    self.icons[key] = QIcon()
                    self.previewFailed.emit(item_name, str(error) or type(error).__name__)
            elif self.item_type == "Cards":
                art_path = ASSET_PATH / (row.get("Art File") or "")
                if art_path.is_file():
                    pixmap = QPixmap(str(art_path))
                    self.icons[key] = QIcon(_framed_card_pixmap(_crop_card_art(pixmap), row.get("Temple", "")))
                else:
                    self.icons[key] = QIcon()
            elif self.item_type == "Sigils":
                icon_path = SIGIL_ICON_DIR / f"{normalize_sigil_name(row.get('Name', ''))}.png"
                if icon_path.is_file():
                    self.icons[key] = QIcon(QPixmap(str(icon_path)))
                else:
                    self.icons[key] = QIcon()
            else:
                self.icons[key] = QIcon()
        return self.icons[key]


class ExportResultsDelegate(QStyledItemDelegate):
    """Paint compact result tiles without allocating a widget per item."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.tile_size = QSize(120, 130)
        self.preview_icon_size = CARD_PREVIEW_SIZE

    def sizeHint(self, option, index):
        return self.tile_size

    def paint(self, painter, option, index):
        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = index.data(ExportResultsModel.SELECTED_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#3978c5" if selected else "#dce2ec"), 2 if selected else 1))
        painter.setBrush(QColor("#dce9fa" if selected else "#ffffff"))
        painter.drawRoundedRect(rect, 5, 5)

        icon = index.data(Qt.DecorationRole)
        item_type = self.model.item_type
        if self.model.preview_mode:
            icon_size = self.preview_icon_size
        elif item_type == "Cards":
            icon_size = CARD_THUMBNAIL_SIZE
        else:
            icon_size = QSize(54, 86)
        icon_rect = QRect(rect.center().x() - icon_size.width() // 2, rect.top() + 6, icon_size.width(), icon_size.height())
        if not icon.isNull():
            icon.paint(painter, icon_rect, Qt.AlignCenter)

        text_rect = QRect(rect.left() + 5, icon_rect.bottom() + 4, rect.width() - 10, rect.bottom() - icon_rect.bottom() - 5)
        painter.setPen(QColor("#202938"))
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, index.data(Qt.DisplayRole))
        painter.restore()


class ExportResultsView(QListView):
    """Virtualized result grid supporting click-and-drag item selection."""

    itemPressed = Signal(int)
    itemHovered = Signal(int)
    selectionDragFinished = Signal()
    resized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setSpacing(10)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._drag_selecting = False

    def mousePressEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and index.isValid():
            self._drag_selecting = True
            self.itemPressed.emit(index.row())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_selecting and event.buttons() & Qt.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                self.itemHovered.emit(index.row())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_selecting:
            self._drag_selecting = False
            self.selectionDragFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.model() and self.model().rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#788397"))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, "No items match these filters.")


class SelectedValues(QWidget):
    """Editable multi-value selector displaying removable selections."""

    changed = Signal()

    def __init__(self, choices, placeholder):
        super().__init__()
        self.selected = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search = NoWheelComboBox()
        self.search.setEditable(True)
        self.search.setInsertPolicy(QComboBox.NoInsert)
        self.search.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.search.setMinimumContentsLength(6)
        self.search.setMinimumWidth(0)
        self.search.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.search.setPlaceholderText(placeholder)
        self.search.addItems(choices)
        self.search.setCurrentIndex(-1)
        self.search.setCurrentText("")
        completer = QCompleter(choices, self.search)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.search.setCompleter(completer)
        self.search.lineEdit().returnPressed.connect(self.add_value)
        add = QPushButton("Add")
        add.setFixedWidth(44)
        add.clicked.connect(self.add_value)
        row.addWidget(self.search, 1)
        row.addWidget(add)
        layout.addLayout(row)
        self.chips_widget = QWidget()
        self.chips_widget.setFixedHeight(58)
        self.chips = QGridLayout(self.chips_widget)
        self.chips.setContentsMargins(0, 0, 0, 0)
        self.chips.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chips_scroll.setFixedHeight(64)
        chips_scroll.setWidget(self.chips_widget)
        layout.addWidget(chips_scroll)

    def add_value(self):
        value = self.search.currentText().strip()
        if value and value.casefold() not in {item.casefold() for item in self.selected}:
            self.selected.append(value)
            self._refresh_chips()
            self.changed.emit()
        self.search.setCurrentText("")

    def _refresh_chips(self):
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, value in enumerate(self.selected):
            chip = QPushButton(f"{value} [x]")
            chip.setToolTip(f"Remove {value}")
            chip.setMaximumWidth(150)
            chip.clicked.connect(lambda checked=False, item=value: self.remove_value(item))
            self.chips.addWidget(chip, index, 0)

    def remove_value(self, value):
        self.selected = [item for item in self.selected if item != value]
        self._refresh_chips()
        self.changed.emit()
