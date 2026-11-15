"""Reusable draggable rows and containers for ordered editor fields."""

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QDrag
from PySide6.QtWidgets import QFrame, QPushButton, QSizePolicy, QVBoxLayout, QWidget


class DraggableRow(QFrame):
    """Base row that supports custom drag-and-drop reordering."""

    removeRequested = Signal()
    changed = Signal()

    def __init__(self, parent=None):
        """Initialize row styling, drag state, and the shared row contract."""
        super().__init__(parent)
        self._drag_start = QPoint()
        self.setObjectName("editorRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.OpenHandCursor))
        self.setToolTip("Drag this row to reorder it. Use X to remove it.")
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
        self.drop_marker.setStyleSheet("#dropMarker {background: #3f78c5; border: 1px solid #245a9f; border-radius: 2px; }")
        self.setStyleSheet("RowContainer { border: 1px solid #dce2ec; border-radius: 4px; }")

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
        """Place a visible insertion target before the row under the cursor."""
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
