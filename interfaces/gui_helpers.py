"""Shared widgets and value helpers used by GUI editor pages."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from model.cards import create_card

ROOT = Path(__file__).resolve().parent.parent


def create_card_preview(
    card_name="",
    art_file="",
    temple="",
    tier="",
    cost="",
    power="",
    health="",
    sigils="",
    token="",
    traits="",
    tribes="",
    flavor_text="",
    credit="",
    tags="",
    config=None,
):
    """Render a preview card from editor field values.

    The keyword arguments mirror the card CSV columns so previews use the same
    renderer interface as saved cards.
    """
    card_data = {
        "Card Name": card_name,
        "Art File": art_file,
        "Temple": temple,
        "Tier": tier,
        "Cost": cost,
        "Power": power,
        "Health": health,
        "Sigils": sigils,
        "Token": token,
        "Traits": traits,
        "Tribes": tribes,
        "Flavor Text": flavor_text,
        "Credit": credit,
        "Tags": tags,
    }
    return create_card(card_data, config)


def _split(value):
    """Split a comma-delimited CSV field, treating empty and None as empty."""
    if not value or value == "None":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _join(values):
    """Join list-style CSV values using the repository's standard delimiter."""
    return ", ".join(values)


class NoWheelComboBox(QComboBox):
    """Editable selector that lets the parent scroll area consume mouse wheels."""

    def wheelEvent(self, event):
        """Leave wheel scrolling to the enclosing scroll area."""
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """Numeric selector that leaves wheel scrolling to the parent widget."""

    def wheelEvent(self, event):
        """Leave wheel scrolling to the enclosing scroll area."""
        event.ignore()


class ColorPickerButton(QPushButton):
    """RGB color chooser button with a live swatch and shared dialog behavior."""

    colorPicked = Signal(object)
    colorPreviewed = Signal(object)

    def __init__(self, color=(0, 0, 0), label="Color", parent=None):
        super().__init__(parent)
        self.label = label
        self._color = (0, 0, 0)
        self.clicked.connect(self._choose_color)
        self.set_color(color)

    @property
    def color(self):
        """Return the selected RGB channels."""
        return self._color

    def set_color(self, color):
        """Set an RGB tuple and refresh the button label and icon swatch."""
        self._color = tuple(color)
        selected = QColor(*self._color)
        self.setText(f"{self.label}: {selected.name()}")
        swatch = QPixmap(14, 14)
        swatch.fill(selected)
        self.setIcon(QIcon(swatch))
        self.setStyleSheet("")

    def _choose_color(self):
        initial_color = self._color
        dialog_color = (255, 255, 255) if initial_color == (0, 0, 0) else initial_color
        dialog = QColorDialog(QColor(*dialog_color), self)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setWindowTitle("Choose color")
        dialog.currentColorChanged.connect(self._preview_color)
        if dialog.exec() != QDialog.Accepted:
            self.set_color(initial_color)
            self.colorPreviewed.emit(initial_color)
            return
        selected = dialog.selectedColor()
        if selected.isValid():
            color = (selected.red(), selected.green(), selected.blue())
            self.set_color(color)
            self.colorPreviewed.emit(color)
            self.colorPicked.emit(color)

    def _preview_color(self, selected):
        color = (selected.red(), selected.green(), selected.blue())
        self.set_color(color)
        self.colorPreviewed.emit(color)


class Gemification(QWidget):
    """Reusable gem toggle group for stats, costs, and sigil conditionals."""

    changed = Signal()

    def __init__(self, with_text):
        """Build gem toggles and optionally include an effect-text input."""
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if with_text:
            self.effect = QLineEdit()
            self.effect.setPlaceholderText("Gemification text")
            self.effect.textChanged.connect(self.changed)
            layout.addWidget(self.effect, 1)
        else:
            self.effect = None

        # Prism replaces individual colors, the other gems can be combined.
        toggles = QHBoxLayout()
        self.checks = {}
        for gem in ("green", "blue", "orange", "prism"):
            check = QPushButton(gem.title())
            check.setCheckable(True)
            check.toggled.connect(self._toggle)
            toggles.addWidget(check)
            self.checks[gem] = check
        layout.addLayout(toggles, 1)

    def _toggle(self, checked):
        """Keep Prism exclusive while allowing combinations of other gems."""
        if checked and self.sender() is self.checks["prism"]:
            for name, check in self.checks.items():
                if name != "prism":
                    check.setChecked(False)
        elif checked:
            self.checks["prism"].setChecked(False)
        self.changed.emit()

    def set_value(self, value):
        """Decode a stored gemified value into text and selected gem buttons."""
        parts = value.split("_")
        if self.effect:
            # The base value is last, text sits between gems and base.
            gem_names = {"green", "blue", "orange", "prism"}
            text_parts = [part for part in parts[:-1] if part.lower() not in gem_names]
            self.effect.setText("_".join(text_parts))
        for gem, check in self.checks.items():
            check.setChecked(gem in [part.lower() for part in parts[:-1]])

    def set_gems(self, gems):
        """Select gem buttons from a list of gem names."""
        for gem, check in self.checks.items():
            check.setChecked(gem in [value.lower() for value in gems])

    def value(self, base):
        """Encode the selected gems and optional text around a base value."""
        gems = [name for name, check in self.checks.items() if check.isChecked()]
        if not gems:
            return base
        text = self.effect.text().strip() if self.effect else ""
        return "_".join(gems + ([text] if text else []) + [base])
