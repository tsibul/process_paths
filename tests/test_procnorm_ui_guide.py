"""Tests of the user guide: the `More` menu item, the window, the files, the names in the text."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from measure_twice import i18n
from measure_twice.store import Store
from measure_twice.ui import guide
from measure_twice.ui.app import MainWindow

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "measure_twice" / "data"
ITEM = {"en": "User guide", "ru": "Руководство", "el": "Οδηγός χρήσης"}
HEADING = {"en": "user guide", "ru": "руководство"}
# The names of buttons, tabs and menu items the guide mentions, as the program has them.
NAMES = (
    "✦ Add with AI",
    "+ New ▾",
    "More ▾",
    "Paste AI answer…",
    "From file…",
    "Empty",
    "Example",
    "Export to file…",
    "Duplicate",
    "Replace from file…",
    "Delete…",
    "Dictionary",
    "Normalization && variants",
    "Comparison",
    "Step chains",
    "Copy prompt",
    "Next step",
    "Load file",
    "Load",
    "Compare steps",
    "Export table (Markdown)",
    "Export table (CSV)",
    "Copy table",
    "Report (PDF)…",
    "Side:",
    "All",
    "Back to table",
    "Add a process with AI",
    "Paste the AI’s answer",
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lang(app, tmp_path, request):
    i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, request.param, tmp_path)
    yield request.param
    i18n.apply_language(app, "en", tmp_path)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    yield s
    s.close()


def _window(store, tmp_path) -> MainWindow:
    return MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))


def _translations(code: str) -> dict[str, set[str]]:
    """Source text to its shown texts: the source itself for English, else the `.ts` ones."""
    if code == "en":
        return {}
    out: dict[str, set[str]] = {}
    root = ET.parse(ROOT / "measure_twice" / "i18n" / f"measure_twice_{code}.ts").getroot()
    for message in root.iter("message"):
        text = message.find("translation").text
        if text:
            out.setdefault(message.find("source").text, set()).add(text)
    return out


def _shown(code: str, source: str) -> set[str]:
    texts = {source} if code == "en" else _translations(code).get(source, set())
    return {t.replace("&&", "&") for t in texts}


@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_menu_item(lang, store, tmp_path):
    w = _window(store, tmp_path)
    assert w.guide_action.text() == ITEM[lang]
    assert w.guide_action in w.more_menu.actions()
    assert w.guide_action.isEnabled()  # also with no project open
    w.close()


@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_window_text(lang, store, tmp_path):
    w = _window(store, tmp_path)
    w.guide_action.trigger()
    dialog = w.guide_dialog
    assert dialog.isVisible()
    shown = lang if lang != "el" else "en"  # no Greek guide yet
    text = dialog.browser.toMarkdown()
    assert HEADING[shown] in text.lower()
    assert len(text) > 2000  # the whole guide, not a part
    assert dialog.windowTitle() == ITEM[lang]
    dialog.close()
    w.close()


def test_greek_takes_english():
    assert guide.guide_file("el") == DATA / "user_guide_en.md"
    assert guide.guide_file("ru") == DATA / "user_guide_ru.md"
    assert guide.guide_file("en") == DATA / "user_guide_en.md"


def test_files_in_build():
    for lang in ("en", "ru"):
        assert (DATA / f"user_guide_{lang}.md").is_file()
    assert not list((ROOT / "docs").glob("user_guide_*"))  # one copy, in the data folder
    spec = (ROOT / "packaging" / "measure_twice.spec").read_text(encoding="utf-8")
    assert '(PACKAGE / "data").iterdir()' in spec  # every file of the data folder goes in


@pytest.mark.parametrize("code", ["en", "ru"])
def test_names_match_program(code):
    text = (DATA / f"user_guide_{code}.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        assert len(line) <= 100, line
    mentioned = set(re.findall(r"\*\*(.+?)\*\*", text, flags=re.S))
    mentioned = {" ".join(m.split()) for m in mentioned}
    known = set()
    for source in NAMES:
        known |= _shown(code, source)
    known |= {code.upper() + " ▾" for code in ("en", "ru", "el")}
    known |= {ITEM[code], "Новый" if code == "ru" else "New"}
    assert mentioned - known == set()
    for source in NAMES:
        assert _shown(code, source) & mentioned, source

