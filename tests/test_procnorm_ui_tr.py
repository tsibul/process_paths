"""Test of the strings of the window (piece 26): every visible English text goes through `tr()`.

A test translation puts every source string of ``measure_twice/ui`` in guillemets. The window
is opened on invented projects, every tab, panel and window is built, and every text a person can
see is collected; a text with English letters and no mark is a string the code did not wrap.
Names from the project are not translated and are not counted.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import html
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCharts import QChartView
from PySide6.QtCore import QLocale, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialog, QFileDialog,
                               QGroupBox, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QTabWidget, QTableWidget,
                               QTextEdit, QTreeWidget, QWidget)

from measure_twice import ai, i18n, report
from measure_twice.store import Store
from measure_twice.ui import app as app_module
from measure_twice.ui.app import MainWindow
from measure_twice.ui.paste import PasteDialog
from measure_twice.ui.report_dialog import ReportDialog

ROOT = Path(__file__).parent.parent
SOURCES = sorted((ROOT / "measure_twice" / "ui").glob("*.py"))
LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
MARK = "«"
LETTERS = re.compile("[A-Za-z]")

# The invented English project: the laundry one, renamed word by word.
ENGLISH = {
    "Стирка с проверкой карманов": "Washing with a pocket check",
    "Три способа постирать одну загрузку белья.": "Three ways to wash one load of linen.",
    "Стирка белья": "Washing linen",
    "Аккуратная стирка": "Careful washing",
    "Быстрая стирка": "Quick washing",
    "Постирать бельё": "Wash the linen",
    "Достать порошок": "Get the powder",
    "Загрузить бельё и включить машину": "Load the linen and start the machine",
    "Развесить бельё": "Hang the linen",
    "Дождаться, пока высохнет": "Wait until it dries",
    "Убрать в шкаф": "Put into the wardrobe",
    "Проверить карманы": "Check pockets",
    "Разобрать по цветам": "Sort by colour",
    "Запустить машину": "Start the machine",
    "Дождаться высыхания": "Wait for drying",
    "ожидание, труда нет": "waiting, no labour",
    "порошок закончился": "powder ran out",
    "Вне модели": "Outside the model",
    "не проверены": "unchecked",
    "не разобраны": "unsorted",
    "стиральная машина": "washing machine",
    "Цикл стирки": "Wash cycle",
    "каждая вещь": "each item",
    "вся загрузка": "whole load",
    "Постирать": "Wash",
    "Развесить": "Hang",
    "постирано": "washed",
    "развешано": "hung",
    "высохло": "dried",
    "убрано": "put away",
    "грязное": "dirty",
    "проверены": "checked",
    "разобраны": "sorted",
    "состояние": "state",
    "карманы": "pockets",
    "наличие": "presence",
    "сушилка": "dryer",
    "цвета": "colours",
    "Бельё": "Linen",
    "Человек": "Person",
    "Машина": "Machine",
    "руки": "hands",
    "есть": "present",
    "нет": "absent",
}


def english_project() -> dict:
    """The invented project in English names."""
    text = LAUNDRY.read_text(encoding="utf-8")
    pattern = re.compile("|".join(re.escape(k) for k in sorted(ENGLISH, key=len, reverse=True)))
    data = json.loads(pattern.sub(lambda m: ENGLISH[m.group(0)], text))
    data["variants"] = [dict(v, code=code) for v, code in zip(data["variants"], "ABC")]
    return data


def leaves(value) -> list[str]:
    """Every string of the project data."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in leaves(k) + leaves(v)]
    if isinstance(value, list):
        return [s for v in value for s in leaves(v)]
    return []


# What is not translated although it is Latin: the name of the program, the language switch.
FIXED = ["Measure Twice", "English", *i18n.LANGUAGES, *[c.upper() for c in i18n.LANGUAGES]]


def lupdate() -> str | None:
    near = Path(sys.executable).parent / "pyside6-lupdate"
    return str(near) if near.exists() else shutil.which("pyside6-lupdate")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def marked(tmp_path_factory) -> Path:
    """The folder with the `.qm` where every source string is translated to «string»."""
    tool = lupdate()
    if tool is None or i18n._lrelease() is None:
        pytest.skip("pyside6-lupdate and pyside6-lrelease are needed")
    folder = tmp_path_factory.mktemp("marked")
    ts = folder / "measure_twice_ru.ts"
    done = subprocess.run(
        [tool, *map(str, SOURCES), "-ts", str(ts), "-target-language", "ru_RU"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
    tree = ET.parse(ts)
    for message in tree.iter("message"):
        source = message.find("source").text or ""
        translation = message.find("translation")
        translation.attrib.pop("type", None)
        if message.get("numerus") == "yes":
            for form in list(translation):
                translation.remove(form)
            for _ in range(3):
                ET.SubElement(translation, "numerusform").text = MARK + source + "»"
        else:
            translation.text = MARK + source + "»"
    tree.write(ts, encoding="utf-8", xml_declaration=True)
    i18n.build_qm(folder, folder)
    return folder


@pytest.fixture
def russian(app, marked):
    old = QLocale()
    i18n.apply_language(app, "ru", marked)
    yield
    i18n.apply_language(app, "en", marked)
    QLocale.setDefault(old)


@pytest.fixture
def shown(monkeypatch):
    """Windows of the system and modal loops are stubbed; what they were asked is recorded."""
    texts: list[str] = []
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    def question(parent, title, text, *args, **kwargs):
        texts.extend([title, text])
        return QMessageBox.StandardButton.Yes

    def warning(parent, title, text, *args, **kwargs):
        texts.extend([title, text])
        return QMessageBox.StandardButton.Ok

    def get_text(parent, title, label, *args, **kwargs):
        texts.extend([title, label])
        return "", False

    def get_file(parent, title, directory="", filter="", *args, **kwargs):
        texts.extend([title, filter])
        return "", ""

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QInputDialog, "getText", get_text)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", get_file)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", get_file)
    return texts


@pytest.fixture
def win(app, russian, shown, tmp_path):
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue(i18n.KEY, "ru")
    w = MainWindow(store, settings)
    assert w.load_path(LAUNDRY)
    w.refresh(store.add(app_module.parse_text(json.dumps(english_project()))[0]))
    w.show()
    QApplication.processEvents()
    yield w
    w.close()
    store.close()


def plain(text: str) -> str:
    """A text without markup, mnemonics and doubled ampersands."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).replace("&&", "&")


def outside_the_window() -> set[str]:
    """Whole texts that come from files outside ``ui``: the report headings (piece 27) and the
    step names and notes of the prompts file."""
    texts = set(report.HEADINGS.values())
    for prompt in ai.prompts():
        texts |= {prompt.name, f"{prompt.number}. {prompt.name}", prompt.note}
    return texts


def untranslated(text: str, data: list[str]) -> bool:
    """Whether the text has English letters outside the project names and has no mark."""
    if MARK in text or text in outside_the_window():
        return False
    text = text.replace("\xa0", " ")  # the state lines bind names with no-break spaces
    for word in sorted(data + FIXED, key=len, reverse=True):
        text = text.replace(word, " ")
    return bool(LETTERS.search(text))


def menu_actions(menu: QMenu) -> list[QAction]:
    out = []
    for action in menu.actions():
        out.append(action)
        if action.menu() is not None:
            out.extend(menu_actions(action.menu()))
    return out


def widget_texts(root: QWidget) -> list[tuple[str, str]]:
    """Every text a person can see in the widget and below it: ``(where, text)``."""
    found: list[tuple[str, str]] = []

    def add(widget, kind, text):
        if text:
            found.append((f"{type(widget).__name__}.{widget.objectName()} {kind}", plain(text)))

    for w in [root, *root.findChildren(QWidget)]:
        add(w, "window title", w.windowTitle() if w.isWindow() else "")
        add(w, "tooltip", w.toolTip())
        add(w, "status tip", w.statusTip())
        if isinstance(w, QLabel):
            add(w, "label", w.text())
        if isinstance(w, QAbstractButton):
            add(w, "button", w.text())
        if isinstance(w, QGroupBox):
            add(w, "group", w.title())
        if isinstance(w, QLineEdit | QPlainTextEdit | QTextEdit):
            add(w, "placeholder", w.placeholderText())
        if isinstance(w, QTabWidget):
            for i in range(w.count()):
                add(w, "tab", w.tabText(i))
                add(w, "tab tip", w.tabToolTip(i))
        if isinstance(w, QTableWidget):
            for i in range(w.columnCount()):
                item = w.horizontalHeaderItem(i)
                add(w, "column", item.text() if item else "")
            for i in range(w.rowCount()):
                item = w.verticalHeaderItem(i)
                add(w, "row head", item.text() if item else "")
            for r in range(w.rowCount()):
                for c in range(w.columnCount()):
                    item = w.item(r, c)
                    if item is not None:
                        add(w, "cell", item.text())
                        add(w, "cell tip", item.toolTip())
        if isinstance(w, QTreeWidget):
            for i in range(w.columnCount()):
                add(w, "tree column", w.headerItem().text(i))
        if isinstance(w, QListWidget):
            for i in range(w.count()):
                add(w, "list item", w.item(i).text())
        if isinstance(w, QComboBox):
            for i in range(w.count()):
                add(w, "combo item", w.itemText(i))
        if isinstance(w, QMenu):
            for a in menu_actions(w):
                add(w, "menu item", a.text())
                add(w, "menu tip", a.toolTip() if a.text() != a.toolTip() else "")
        if isinstance(w, QChartView):
            chart = w.chart()
            add(w, "chart title", chart.title())
            for axis in chart.axes():
                add(w, "axis", axis.titleText())
            for series in chart.series():
                add(w, "series", series.name())
    if isinstance(root, QMainWindow):
        add(root, "status bar", root.statusBar().currentMessage())
    return found


def data_words(win: MainWindow) -> list[str]:
    words = leaves(english_project())
    for info in win.store.list():
        words += leaves(win.store.get(info.id).data)
    words = [w for w in words if w not in ("own", "other")]  # stored side values, not names
    words += [win.projects.itemText(i) for i in range(win.projects.count())]
    return words


def visit(win: MainWindow, shown: list[str]) -> list[tuple[str, str]]:
    """Open every tab, panel and window of the program and gather the texts."""
    found: list[tuple[str, str]] = []
    found += [("system dialog", t) for t in shown]
    for index in range(win.tabs.count()):
        win.tabs.setCurrentIndex(index)
        QApplication.processEvents()
        found += widget_texts(win)
    return found


def open_inputs(win: MainWindow) -> list[tuple[str, str]]:
    """Open the add rows, the forms of kinds and slices and the input and state rows of the chain
    of the current project, and gather the texts of each."""
    found: list[tuple[str, str]] = []
    page = win.dictionary
    for table in page.tables():
        for what, owner in list(table._adds):
            if what in ("kind", "named_slice"):
                continue  # these open a form, not the one-line input
            table.open_add(what, owner)
            QApplication.processEvents()
            found += widget_texts(table)
        table.cancel_add()
    for table, what in ((page.kinds, "kind"), (page.slices, "named_slice")):
        names = [None] + [
            table.item(r, c).text()
            for r in range(table.rowCount())
            for c in range(table.columnCount())
            if table.item(r, c) is not None and table.word_item(what, table.item(r, c).text())
        ][:2]
        for old in names:
            page._open_form(table, what, old)
            QApplication.processEvents()
            found += widget_texts(table)
            table.cancel_add()
    win.tabs.setCurrentWidget(win.chains)
    table = win.chains.table
    for adding in (("none", 0), ("none", 1), ("call", 1), ("call", 2)):
        table.open_input(adding)
        QApplication.processEvents()
        found += widget_texts(win.chains)
    table.open_input(None)
    return found


def test_every_visible_string_is_marked(win, shown):
    # Windows and dialogs of the program, built without modal loops.
    win.on_new()
    win.on_load()
    win.on_load_over()
    win.on_save()
    win.on_export(".md")
    win.on_export(".csv")
    win.on_report()
    win.on_ai()
    win.on_paste()
    win.confirm(MARK)
    win.warn(MARK)
    win.delete_project()
    # Statuses and panels.
    win.load_text("no json here")
    win.new_project("")
    win.show_example()
    win.show_example()
    win.new_project("A tea")
    win.save_path(win.settings.fileName() + ".json")
    win.load_path(Path("/nonexistent/file.json"))
    extra = []
    dialogs = [win.ai_scenario(), ReportDialog(win.comparison._project, lambda p, w: True, win)]
    dialogs.append(PasteDialog(win.load_text, win))
    for dialog in dialogs:
        extra += widget_texts(dialog)
    for menu in win.findChildren(QMenu):
        extra += widget_texts(menu)
    for i in range(win.projects.count()):
        win.projects.setCurrentIndex(i)
        extra += visit(win, shown)
        extra += open_inputs(win)
    extra += visit(win, shown)
    data = data_words(win)
    bad = sorted({f"{where}: {text!r}" for where, text in extra if untranslated(text, data)})
    assert not bad, f"{len(bad)} unmarked strings:\n" + "\n".join(bad)
