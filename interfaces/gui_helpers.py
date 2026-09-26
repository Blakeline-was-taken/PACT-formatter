"""Shared widgets and value helpers used by GUI editor pages."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget
)

ROOT = Path(__file__).resolve().parent.parent


def _split(value):
    """Split a comma-delimited CSV field, treating empty and None as empty."""
    return [] if not value or value == "None" else [part.strip() for part in value.split(",") if part.strip()]


def _join(values):
    """Join list-style CSV values using the repository's standard delimiter."""
    return ", ".join(values)


class NoWheelComboBox(QComboBox):
    """Editable selector that lets the parent scroll area consume mouse wheels."""

    def wheelEvent(self, event):
        event.ignore()


class Gemification(QWidget):
    """Reusable gem toggle group for stats, costs, and sigil conditionals."""

    changed = Signal()

    def __init__(self, with_text):
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
        """Enforce Prism's exclusive priority over individual gem colors."""
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
