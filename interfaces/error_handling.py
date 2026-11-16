"""Shared logging and user-facing exception reporting for the GUI."""

import logging
import sys
import traceback
from pathlib import Path


_LOG_HANDLER_ATTRIBUTE = "_pact_error_log_handler"


def configure_logging(log_path):
    """Write application warnings and errors to the given stable file path."""
    root_logger = logging.getLogger()
    resolved_path = Path(log_path).resolve()
    for handler in root_logger.handlers:
        if getattr(handler, _LOG_HANDLER_ATTRIBUTE, None) == str(resolved_path):
            return

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(resolved_path, encoding="utf-8")
    setattr(handler, _LOG_HANDLER_ATTRIBUTE, str(resolved_path))
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(min(root_logger.level, logging.WARNING))


def exception_details(error):
    """Format an exception and its traceback for expandable GUI diagnostics."""
    return "".join(traceback.format_exception(type(error), error, error.__traceback__)).strip()


def log_exception(context, error):
    """Record an exception with its operation context and full traceback."""
    logging.getLogger("pact").error("%s: %s", context, error, exc_info=(type(error), error, error.__traceback__))
    return f"{type(error).__name__}: {error}"


def show_error(parent, title, context, error):
    """Log an exception and present context with expandable traceback details."""
    log_exception(context, error)
    from PySide6.QtWidgets import QMessageBox

    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Critical)
    dialog.setStandardButtons(QMessageBox.Ok)
    dialog.setWindowTitle(title)
    dialog.setText(context)
    dialog.setInformativeText(f"{type(error).__name__}: {error}")
    dialog.setDetailedText(exception_details(error))
    dialog.exec()


def install_exception_hook(parent_getter):
    """Log otherwise-unhandled main-thread exceptions and show their details."""
    original_hook = sys.excepthook

    def handle_exception(exception_type, exception, tb):
        context = "An unexpected application error occurred"
        logging.getLogger("pact").error(context, exc_info=(exception_type, exception, tb))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            if app is None or app.closingDown():
                original_hook(exception_type, exception, tb)
                return
            dialog = QMessageBox(parent_getter())
            dialog.setIcon(QMessageBox.Critical)
            dialog.setStandardButtons(QMessageBox.Ok)
            dialog.setWindowTitle("Unexpected application error")
            dialog.setText(f"{context}: {exception}")
            dialog.setDetailedText("".join(
                traceback.format_exception(exception_type, exception, tb)
            ).strip())
            dialog.exec()
        except Exception:
            original_hook(exception_type, exception, tb)

    sys.excepthook = handle_exception
