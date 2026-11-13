"""Tabbed graphical editor shell for the PACT formatter."""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
)


class EditorWindow(QMainWindow):
    """Own the main window, editor tabs, and application-level actions."""

    TAB_DEFINITIONS = (
        ("Export Panel", None),
        ("Card Editor", None),
        ("Sigil/Trait Editor", None),
        ("Template Editor", None),
    )

    def __init__(self):
        """Set up the window shell and its initial status message."""
        super().__init__()
        self.setWindowTitle("PACT Formatter")
        self.setMinimumSize(960, 640)
        self.resize(1180, 760)
        self._build_tabs()
        self.statusBar().showMessage("Ready")

    def _build_tabs(self):
        """Create each editor page and install it in the central tab widget."""
        from .card_editor import CardEditor
        from .export_panel import ExportPanel
        from .sigil_trait_editor import SigilTraitEditor
        from .template_editor import TemplateEditor

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        for name, page_factory in self.TAB_DEFINITIONS:
            if page_factory is None:
                page_factory = {
                    "Export Panel": ExportPanel,
                    "Card Editor": CardEditor,
                    "Sigil/Trait Editor": SigilTraitEditor,
                    "Template Editor": TemplateEditor,
                }[name]
            self.tabs.addTab(page_factory(), name)
        self.tabs.setCurrentIndex(0)

    def _tab_changed(self, index):
        """Reflect the active tab in the window status bar."""
        tab_name = self.tabs.tabText(index)
        self.statusBar().showMessage(f"{tab_name} selected")


def _apply_style(app):
    """Apply the shared application font, widget style, and color palette."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(
        """
        /* Window surfaces and tab navigation */
        QMainWindow, QWidget { background: #f5f7fb; color: #202938; }
        QTabWidget::pane { border: 1px solid #dce2ec; background: #ffffff; }
        QTabWidget::tab-bar { alignment: left; }
        QTabBar::tab {
            background: #e5eaf2; border: 1px solid #cbd5e1;
            border-bottom: 2px solid #cbd5e1;
            border-top-left-radius: 6px; border-top-right-radius: 6px;
            padding: 12px 18px 10px; margin: 3px 2px 0 0;
        }
        QTabBar::tab:selected {
            background: #ffffff; border-bottom-color: #ffffff;
            margin-top: 0;
        }

        /* Shared input and action-control styling */
        QLineEdit, QComboBox, QSpinBox, QPushButton {
            min-height: 28px;
        }
        QLineEdit, QComboBox {
            background: #ffffff; border: 1px solid #b8c4d4;
            border-radius: 4px; padding: 4px 8px; color: #202938;
        }
        QComboBox::drop-down { border-left: 1px solid #d5dce6; width: 24px; }
        QComboBox QAbstractItemView {
            background: #ffffff; color: #202938; selection-background-color: #dce9fa;
            selection-color: #17365d; border: 1px solid #b8c4d4;
        }
        QCheckBox { spacing: 8px; color: #202938; }
        QCheckBox::indicator {
            width: 18px; height: 18px; border: 1px solid #8b9bb0;
            border-radius: 4px; background: #ffffff;
        }
        QCheckBox::indicator:hover { border-color: #3978c5; background: #eef5ff; }
        QCheckBox::indicator:checked { border-color: #2868b2; background: #3978c5; }
        QCheckBox::indicator:checked:hover { background: #2868b2; }
        QPushButton#primaryButton {
            background: #3978c5; border: 1px solid #2868b2; border-radius: 4px;
            color: #ffffff; font-weight: 600; padding: 6px 10px;
        }
        QPushButton#primaryButton:hover { background: #2868b2; }
        QPushButton#primaryButton:disabled { background: #a8bad0; border-color: #a8bad0; }

        /* Expandable template section navigation */
        #templateSectionButton, #templateSubsectionButton {
            background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
            color: #334155; padding: 7px 10px; text-align: left;
        }
        #templateSectionButton { font-weight: 600; }
        #templateSectionButton:hover, #templateSubsectionButton:hover {
            background: #edf4fd; border-color: #8eafd6;
        }
        #templateSectionButton:checked, #templateSubsectionButton:checked {
            background: #dce9fa; border-color: #3978c5; color: #17365d;
        }

        /* Page hierarchy, panels, and status feedback */
        #pageTitle { font-size: 26px; font-weight: 600; }
        #pageDescription { color: #586579; font-size: 13px; }
        #sectionTitle { font-size: 18px; font-weight: 600; }
        QGroupBox {
            background: #ffffff; border: 1px solid #dce2ec;
            border-radius: 6px; margin-top: 10px; padding-top: 18px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; }
        #emptyState { color: #334155; font-size: 16px; }
        #mutedText { color: #68758a; }
        QStatusBar { background: #edf1f7; color: #586579; }
        """
    )


def run():
    """Create and display the GUI, then enter Qt's event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    _apply_style(app)
    window = EditorWindow()
    window.show()
    return app.exec()
