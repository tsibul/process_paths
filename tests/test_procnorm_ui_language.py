"""Tests of the language switch at the end of the panel row (procnorm-117)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtWidgets import QApplication

from measure_twice import i18n
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

TEST_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ru_RU">
<context>
    <name>MainWindow</name>
    <message>
        <source>Restart now</source>
        <translation>[ru] Restart now</translation>
    </message>
    <message>
        <source>The language changes at the next start.</source>
        <translation>[ru] The language changes at the next start.</translation>
    </message>
</context>
</TS>
"""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english_after(app, tmp_path):
    old = QLocale()
    yield
    i18n.apply_language(app, "en", tmp_path)
    QLocale.setDefault(old)


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def restarts(monkeypatch):
    """Restarting only counts; the process stays."""
    calls = []
    monkeypatch.setattr(i18n, "restart", lambda: calls.append(1))
    return calls


@pytest.fixture
def win(app, store, settings, restarts):
    settings.setValue(i18n.KEY, "en")
    w = MainWindow(store, settings)
    yield w
    w.close()


def _rows(w):
    return [a.text() for a in w.language_menu.actions()]


def _choose(w, code):
    for a in w.language_menu.actions():
        if a.text().startswith(code.upper() + " "):
            a.trigger()
            return
    raise AssertionError(code)


def test_button_shows_only_the_code(win):
    assert win.language_button.text() == "EN ▾"


def test_button_at_the_end_of_the_panel_row(win):
    row = win.panel_bar
    assert row.indexOf(win.language_button) == row.count() - 1
    assert row.indexOf(win.more_menu_button) == row.count() - 2


def test_list_has_three_rows_without_flags(win):
    assert _rows(win) == ["EN English", "RU Русский", "EL Ελληνικά"]
    assert all(a.icon().isNull() for a in win.language_menu.actions())


def test_current_row_is_checked(win):
    checked = [a.text() for a in win.language_menu.actions() if a.isChecked()]
    assert checked == ["EN English"]


def test_no_restart_line_at_start(win):
    assert not win.restart_row.isVisibleTo(win)


def test_choosing_writes_language_and_offers_restart(win, settings):
    _choose(win, "ru")
    assert settings.value(i18n.KEY) == "ru"
    assert win.restart_row.isVisibleTo(win)
    assert win.restart_button.text() == "Restart now"
    assert win.restart_note.text() == "The language changes at the next start."
    assert win.language_button.text() == "RU ▾"


def test_without_restart_window_language_stays(win, restarts):
    title = win.windowTitle()
    _choose(win, "el")
    assert i18n.current() == "en"
    assert win.windowTitle() == title
    assert win.new_menu_button.text() == "+ New ▾"
    assert i18n.locale().language() == QLocale.Language.English
    assert restarts == []


def test_restart_button_restarts(win, restarts):
    _choose(win, "ru")
    win.restart_button.click()
    assert restarts == [1]


def test_choosing_running_language_again_hides_restart(win, settings):
    _choose(win, "ru")
    _choose(win, "en")
    assert settings.value(i18n.KEY) == "en"
    assert not win.restart_row.isVisibleTo(win)


def test_window_without_settings_has_switch(app, store, restarts):
    w = MainWindow(store)
    assert w.language_button.text() == "EN ▾"
    _choose(w, "ru")
    assert w.restart_row.isVisibleTo(w)
    w.close()


def test_test_translation_changes_switch_labels(app, store, settings, restarts, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "measure_twice_ru.ts").write_text(TEST_TS, encoding="utf-8")
    out = tmp_path / "out"
    i18n.build_qm(src, out)
    settings.setValue(i18n.KEY, "ru")
    i18n.apply_language(app, "ru", out)
    w = MainWindow(store, settings)
    assert w.language_button.text() == "RU ▾"
    assert w.restart_button.text() == "[ru] Restart now"
    assert w.restart_note.text() == "[ru] The language changes at the next start."
    w.close()


def test_right_to_left_language_turns_the_window(app, store, settings, restarts, tmp_path):
    i18n.apply_language(app, "he", tmp_path)
    w = MainWindow(store, settings)
    assert w.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert w.language_button.layoutDirection() == Qt.LayoutDirection.RightToLeft
    w.close()
