"""The `✦ Create with AI` button of the top row: before `+ New`, bright, short in a cramped window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QPushButton,
                               QStyleOptionComboBox)

from measure_twice import i18n
from measure_twice.store import Store
from measure_twice.ui import app as app_module
from measure_twice.ui.app import MainWindow

FULL = {"en": "✦ Add with AI", "ru": "✦ Создать с AI", "el": "✦ Δημιουργία με AI"}
SHORT = "✦ AI"
LEAST = 220  # the projects list at the window of 1100 px, px
LONG = {
    "en": "Fix a leaking kitchen tap in the flat on the fourth floor before the guests come",
    "ru": "Починить подтекающий кран на кухне в квартире на четвёртом этаже до прихода гостей",
    "el": "Επισκευή σταγόνας βρύσης κουζίνας στο διαμέρισμα του τέταρτου ορόφου πριν τους καλεσμένους",
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lang(app, tmp_path, request):
    """The language of the test, its `.qm` built from the sources; English again after."""
    i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, request.param, tmp_path)
    yield request.param
    i18n.apply_language(app, "en", tmp_path)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    yield s
    s.close()


def _window(store, tmp_path, width: int, name: str | None = None) -> MainWindow:
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    if name is not None:
        w.new_project(name)
    w.resize(width, 700)
    w.show()
    QApplication.processEvents()
    return w


def _bar(win) -> QHBoxLayout:
    return next(lay for lay in win.findChildren(QHBoxLayout) if lay.indexOf(win.projects) >= 0)


# ---------- place and look ----------

def test_button_right_before_new(app, store, tmp_path):
    w = _window(store, tmp_path, 1100)
    try:
        bar = _bar(w)
        widgets = [bar.itemAt(i).widget() for i in range(bar.count())]
        controls = [x for x in widgets if isinstance(x, (QComboBox, QPushButton))]
        assert controls == [w.projects, w.ai_button, w.new_menu_button, w.more_menu_button,
                            w.language_button]
        assert w.ai_button.text() == FULL["en"]
        assert w.ai_button.menu() is None
        assert w.ai_button.property("primary") is True
        assert not w.new_menu_button.property("primary")
    finally:
        w.close()


def test_ai_item_left_the_new_menu(app, store, tmp_path):
    w = _window(store, tmp_path, 1100)
    try:
        texts = [a.text() for a in w.new_menu.actions() if a.text()]
        assert texts == ["Paste AI answer…", "From file…", "Empty", "Example"]
        assert not hasattr(w, "ai_action")
    finally:
        w.close()


def test_button_opens_scenario(app, store, tmp_path, monkeypatch):
    w = _window(store, tmp_path, 1100)
    shown = []

    def exec_(dialog):
        shown.append(dialog)
        return app_module.AiScenarioDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module.AiScenarioDialog, "exec", exec_)
    try:
        w.ai_button.click()
        assert shown == [w.ai_scenario()]
    finally:
        w.close()


# ---------- the row in three languages and three widths ----------

def _row_whole(w: MainWindow) -> None:
    """Every button of the row whole and inside the window."""
    for b in (w.ai_button, w.new_menu_button, w.more_menu_button, w.language_button):
        assert b.width() >= b.sizeHint().width(), b.text()
        assert b.mapTo(w, b.rect().topRight()).x() < w.width(), b.text()


@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_full_label_at_1100_with_long_name(app, lang, store, tmp_path):
    w = _window(store, tmp_path, 1100, LONG[lang])
    try:
        assert w.projects.currentText() == LONG[lang]
        assert w.ai_button.text() == FULL[lang]
        assert w.projects.width() >= LEAST
        _row_whole(w)
    finally:
        w.close()


@pytest.mark.parametrize("width", [760, 900])
@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_short_label_only_when_cramped(app, lang, store, tmp_path, width):
    w = _window(store, tmp_path, width, LONG[lang])
    try:
        _row_whole(w)
        assert w.ai_button.text() in (FULL[lang], SHORT)
        assert w.projects.width() >= LEAST
        if w.ai_button.text() == SHORT:
            assert w.ai_button.toolTip() == FULL[lang]
            wider = w.ai_button.fontMetrics().horizontalAdvance(FULL[lang]) \
                - w.ai_button.fontMetrics().horizontalAdvance(SHORT)
            assert w.projects.width() - wider < LEAST  # the full one would not fit
    finally:
        w.close()


def test_greek_narrow_window_takes_short_label(app, store, tmp_path, request):
    i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, "el", tmp_path)
    request.addfinalizer(lambda: i18n.apply_language(app, "en", tmp_path))
    w = _window(store, tmp_path, 760, LONG["el"])
    try:
        assert w.ai_button.text() == SHORT
    finally:
        w.close()


def test_label_comes_back_when_wider(app, store, tmp_path):
    w = _window(store, tmp_path, 640, LONG["en"])
    try:
        assert w.ai_button.text() == SHORT
        w.resize(1100, 700)
        QApplication.processEvents()
        assert w.ai_button.text() == FULL["en"]
    finally:
        w.close()


# ---------- a long project name ----------

def test_long_name_cut_whole_in_tooltip_and_open_list(app, store, tmp_path):
    w = _window(store, tmp_path, 760, LONG["en"])
    try:
        box = w.projects
        option = QStyleOptionComboBox()
        box.initStyleOption(option)
        assert option.currentText.endswith("…")
        assert LONG["en"].startswith(option.currentText[:-1])
        assert box.toolTip() == LONG["en"]
        box.showPopup()
        QApplication.processEvents()
        assert box.view().width() >= box.view().sizeHintForColumn(0)
        box.hidePopup()
    finally:
        w.close()
