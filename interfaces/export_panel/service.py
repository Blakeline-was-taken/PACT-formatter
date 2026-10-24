"""Parallel image rendering and file output for the export panel."""

import os
import re
import tempfile
import threading
import traceback
from pathlib import Path
from logging import Handler, WARNING, getLogger

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from model import DEFAULT_CONFIG, GENERAL_ASSETS_DIR, cards, sigils
from model.text import strip_rich_text_tags

_COLOR_MAP_LOCK = threading.Lock()
_DEFAULT_COLOR_MAP = None
_LOGGING_LOCK = threading.Lock()
_LOG_CAPTURE_COUNT = 0
_ORIGINAL_LOG_LEVEL = None


class _TaskLogHandler(Handler):
    def __init__(self, thread_id, item_name, message_callback):
        super().__init__(WARNING)
        self.thread_id = thread_id
        self.item_name = item_name
        self.message_callback = message_callback

    def emit(self, record):
        if record.thread == self.thread_id:
            self.message_callback(self.item_name, record.levelname, record.getMessage())


def _attach_task_log_handler(handler):
    global _LOG_CAPTURE_COUNT, _ORIGINAL_LOG_LEVEL
    root_logger = getLogger()
    with _LOGGING_LOCK:
        if _LOG_CAPTURE_COUNT == 0:
            _ORIGINAL_LOG_LEVEL = root_logger.level
            root_logger.setLevel(min(root_logger.level, WARNING))
        _LOG_CAPTURE_COUNT += 1
        root_logger.addHandler(handler)


def _detach_task_log_handler(handler):
    global _LOG_CAPTURE_COUNT, _ORIGINAL_LOG_LEVEL
    root_logger = getLogger()
    with _LOGGING_LOCK:
        root_logger.removeHandler(handler)
        _LOG_CAPTURE_COUNT -= 1
        if _LOG_CAPTURE_COUNT == 0 and _ORIGINAL_LOG_LEVEL is not None:
            root_logger.setLevel(_ORIGINAL_LOG_LEVEL)
            _ORIGINAL_LOG_LEVEL = None


def _safe_name(name):
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return safe or "export"


def _default_color_map():
    global _DEFAULT_COLOR_MAP
    if _DEFAULT_COLOR_MAP is None:
        with _COLOR_MAP_LOCK:
            if _DEFAULT_COLOR_MAP is None:
                _DEFAULT_COLOR_MAP = sigils.get_color_mapping("default")
    return _DEFAULT_COLOR_MAP


def _known_card_effect(effect, known_names):
    if effect in known_names:
        return True
    if effect.casefold() in ("rainbow", "tribal"):
        return True
    parts = effect.split("_")
    if len(parts) > 1 and parts[0].casefold() in ("cell", "latch", "hint"):
        return "_".join(parts[1:]) in known_names
    if len(parts) > 1 and set(part.casefold() for part in parts[:-1]).issubset({"green", "blue", "orange", "prism"}):
        return parts[-1] in known_names
    return False


def _validate_card_effects(row):
    issues = []
    for field, known_names in (("Sigils", sigils.SIGILS), ("Traits", sigils.TRAITS)):
        for effect in row.get(field, "").split(","):
            effect = effect.strip()
            if effect and effect.casefold() != "none" and not _known_card_effect(effect, known_names):
                issues.append(f"Unknown {field.lower()[:-1]}: {effect}")
    if issues:
        raise ValueError("; ".join(issues))


def _save_image(image, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.stem}.", suffix=".tmp.png", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        image.save(temporary_path, format="PNG")
        with Image.open(temporary_path) as saved_image:
            saved_image.verify()
        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    if not destination.is_file() or destination.stat().st_size == 0:
        raise OSError(f"Export output was not created correctly: {destination}")
    return destination


def _export_card(row, options, output_dir):
    _validate_card_effects(row)
    image = cards.create_card(row)
    name = strip_rich_text_tags(row.get("Card Name", row.get("Name", ""))).strip()
    filename = _safe_name(Path(row.get("Art File") or f"{name}.png").name)
    if options["sorted"]:
        destination = output_dir / "cards" / _safe_name(row.get("Temple", "")) / _safe_name(row.get("Tier", "")) / filename
    else:
        destination = output_dir / "cards" / filename
    _save_image(image, destination)
    return [destination]


def _export_sigil(row, options, output_dir):
    item = sigils.SIGILS[row["Name"]].copy()
    color = options["color"]
    color_map = _default_color_map()
    if not options["formats"]:
        raise ValueError("At least one sigil export format must be selected.")
    destinations = []
    for format_name in options["formats"]:
        if format_name == "Standard":
            image = item.getImage(color=color, config=DEFAULT_CONFIG, color_map=color_map)
            folder = "sigils"
        elif format_name == "Shortened":
            image = item.getImage(shortened_format=True, color=color, config=DEFAULT_CONFIG, color_map=color_map)
            folder = "short sigils"
        elif format_name == "Base game":
            image = item.getImage(base_game=True, color=color, config=DEFAULT_CONFIG, color_map=color_map)
            folder = "base game sigils"
        elif format_name == "Patch":
            patch_path = GENERAL_ASSETS_DIR / "patch.png"
            with Image.open(patch_path) as patch_source:
                patch = patch_source.convert("RGBA")
            icon = item.sigilImage(color=color)
            position = ((patch.width - icon.width) // 2, (patch.height - icon.height) // 2)
            image = cards.paste_sigil(patch, icon, position)
            folder = "sigil patches"
        else:
            raise ValueError(f"Unsupported sigil export format: {format_name}")
        suffix = "_patch" if format_name == "Patch" else ""
        destination = output_dir / folder / f"{_safe_name(item.name)}{suffix}.png"
        destinations.append(_save_image(image, destination))
    return destinations


def _export_trait(row, options, output_dir):
    item = sigils.TRAITS[row["Name"]].copy()
    color_map = _default_color_map()
    image = item.getImage(color=options["color"], config=DEFAULT_CONFIG, color_map=color_map)
    destination = output_dir / "traits" / f"{_safe_name(row['Name'])}.png"
    _save_image(image, destination)
    return [destination]


def _export_row(row, item_type, options, output_dir):
    if item_type == "Cards":
        return _export_card(row, options, output_dir)
    elif item_type == "Sigils":
        return _export_sigil(row, options, output_dir)
    elif item_type == "Traits":
        return _export_trait(row, options, output_dir)
    raise ValueError(f"Unsupported export type: {item_type}")


class _TaskSignals(QObject):
    completed = Signal(str, bool, str, str)
    message = Signal(str, str, str)


class _ExportTask(QRunnable):
    def __init__(self, row, item_type, options, output_dir):
        super().__init__()
        self.row = row
        self.item_type = item_type
        self.options = options
        self.output_dir = output_dir
        self.signals = _TaskSignals()

    @Slot()
    def run(self):
        item_name = self.row.get("Card Name", self.row.get("Name", "Item"))
        warnings = []
        errors = []

        def collect_log(name, level, message):
            if level == "WARNING":
                warnings.append(message)
            elif level == "ERROR" or level == "CRITICAL":
                errors.append(message)
            self.signals.message.emit(name, level, message)

        log_handler = _TaskLogHandler(threading.get_ident(), item_name, collect_log)
        _attach_task_log_handler(log_handler)
        try:
            output_paths = _export_row(self.row, self.item_type, self.options, self.output_dir)
            for output_path in output_paths:
                if not output_path.is_file() or output_path.stat().st_size == 0:
                    raise OSError(f"Export output was not created: {output_path}")
                with Image.open(output_path) as saved_image:
                    saved_image.verify()
            self.signals.completed.emit(item_name, not errors, "\n".join(errors), "\n".join(warnings))
        except Exception as exception:
            error = traceback.format_exc()
            errors.append(error)
            self.signals.message.emit(item_name, "ERROR", str(exception) or type(exception).__name__)
            self.signals.completed.emit(item_name, False, "\n".join(errors), "\n".join(warnings))
        finally:
            _detach_task_log_handler(log_handler)


class ExportJob(QObject):
    """Run independent selected-item exports in a bounded worker pool."""

    progress = Signal(int, int, str)
    message = Signal(str, str, str)
    finished = Signal(int, int, int, str, str)

    def __init__(self, rows, item_type, options, output_dir, parent=None):
        super().__init__(parent)
        self.rows = list(rows)
        self.item_type = item_type
        self.options = dict(options)
        self.output_dir = Path(output_dir)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(1, os.cpu_count() or 1))
        self.total = len(self.rows)
        self.completed = 0
        self.succeeded = 0
        self.failed = 0
        self.warnings = []
        self.errors = []
        self.done = False
        self._tasks = []

    def start(self):
        if not self.rows:
            self.done = True
            self.finished.emit(0, 0, 0, "", "")
            return
        for row in self.rows:
            task = _ExportTask(row, self.item_type, self.options, self.output_dir)
            task.signals.completed.connect(self._item_completed)
            task.signals.message.connect(self.message)
            self._tasks.append(task)
            self.pool.start(task)

    def is_running(self):
        return not self.done

    def wait_for_done(self):
        self.pool.waitForDone()

    @Slot(str, bool, str, str)
    def _item_completed(self, item_name, succeeded, error, warnings):
        self.completed += 1
        if succeeded:
            self.succeeded += 1
        else:
            self.failed += 1
        if error:
            self.errors.append(f"{item_name}:\n{error}")
        if warnings:
            self.warnings.append(f"{item_name}:\n{warnings}")
        self.progress.emit(self.completed, self.total, item_name)
        if self.completed == self.total:
            self.done = True
            self.finished.emit(self.succeeded, self.failed, self.total, "\n\n".join(self.warnings), "\n\n".join(self.errors))
