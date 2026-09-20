"""Tabbed graphical editor shell for the PACT formatter.

The editor pages intentionally contain only their navigation and empty states for
now. Keeping each page as a normal QWidget gives later editors a stable place to
add controls without changing the application shell.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class EditorPage(QWidget):
    """Base page with a consistent heading, description, and empty-state panel."""

    def __init__(self, title, description, next_step):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        summary = QLabel(description)
        summary.setObjectName("pageDescription")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        panel = QGroupBox("Workspace")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)
        panel_layout.setSpacing(10)

        status = QLabel(next_step)
        status.setObjectName("emptyState")
        status.setWordWrap(True)
        panel_layout.addWidget(status)

        hint = QLabel("This area is ready for the editor controls.")
        hint.setObjectName("mutedText")
        panel_layout.addWidget(hint)
        panel_layout.addStretch()
        layout.addWidget(panel, 1)


class WelcomePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("PACT formatter")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        description = QLabel(
            "Use the tabs above to edit card data, configure layouts, manage "
            "assets, and prepare exports."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        overview = QGroupBox("Editor workspace")
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(24, 24, 24, 24)
        overview_layout.setSpacing(12)
        for text in (
            "Card Editor - Change, Preview and Export individual cards with live updates",
            "Sigil & Trait Editor - Change, Preview and Export sigils and traits with live updates",
            "Template Editor - Tweak positioning and assets for all the different card templates",
            "Config Editor - Edit global formatter options and printing formats",
            "Export - Render cards, sigils, and traits in bulk",
        ):
            label = QLabel(text)
            label.setObjectName("overviewItem")
            overview_layout.addWidget(label)
        layout.addWidget(overview)
        layout.addStretch()


class EditorWindow(QMainWindow):
    TAB_DEFINITIONS = (
        ("Overview", WelcomePage),
        (
            "Card Editor",
            None,
        ),
        (
            "Sigil/Trait Editor",
            None,
        ),
        (
            "Template Editor",
            lambda: EditorPage(
                "Template Editor",
                "Tweak positioning and assets for all the different card templates.",
                "Temple and tier layout controls will appear here.",
            ),
        ),
        (
            "Config Editor",
            lambda: EditorPage(
                "Config Editor",
                "Edit global formatter options and printing formats.",
                "Configuration fields and save actions will appear here.",
            ),
        ),
        (
            "Export",
            lambda: EditorPage(
                "Export",
                "Render cards, sigils, and traits in bulk using the current settings.",
                "Export selection, progress, and output controls will appear here.",
            ),
        ),
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PACT Formatter")
        self.setMinimumSize(960, 640)
        self.resize(1180, 760)
        self._build_actions()
        self._build_tabs()
        self.statusBar().showMessage("Ready")

    def _build_actions(self):
        close_action = QAction("Close", self)
        close_action.setShortcut("Ctrl+Q")
        close_action.triggered.connect(self.close)
        self.menuBar().addMenu("File").addAction(close_action)

    def _build_tabs(self):
        from .card_editor import CardEditor
        from .sigil_trait_editor import SigilTraitEditor

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        for name, page_factory in self.TAB_DEFINITIONS:
            if page_factory is None:
                page_factory = CardEditor if name == "Card Editor" else SigilTraitEditor
            self.tabs.addTab(page_factory(), name)

    def _tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        self.statusBar().showMessage(f"{tab_name} selected")


def _apply_style(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(
        """
        QMainWindow, QWidget { background: #f5f7fb; color: #202938; }
        QMenuBar, QMenu { background: #ffffff; color: #202938; }
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
        QLineEdit, QComboBox, QSpinBox, QPushButton {
            min-height: 28px;
        }
        #pageTitle { font-size: 26px; font-weight: 600; }
        #pageDescription { color: #586579; font-size: 13px; }
        #sectionTitle { font-size: 18px; font-weight: 600; }
        QGroupBox {
            background: #ffffff; border: 1px solid #dce2ec;
            border-radius: 6px; margin-top: 10px; padding-top: 18px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; }
        #emptyState { color: #334155; font-size: 16px; }
        #mutedText, #overviewItem { color: #68758a; }
        QStatusBar { background: #edf1f7; color: #586579; }
        """
    )


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    _apply_style(app)
    window = EditorWindow()
    window.show()
    return app.exec()
