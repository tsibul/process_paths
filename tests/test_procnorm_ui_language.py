"""Tests of the language switch at the end of the panel row (procnorm-117)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from measure_twice import i18n
from measure_twice.example import add_example
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

TEST_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ru_RU">
<context>
    <name>MainWindow</name>
    <message>
        <source>+ New ▾</source>
        <translation>[ru] + New ▾</translation>
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
    """Choose a language in the list; the window shown after it."""
    for a in w.language_menu.actions():
        if a.text().startswith(code.upper() + " "):
            return w.choose_language(code)
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


def test_no_restart_controls(win):
    assert not hasattr(win, "restart_row")
    assert not hasattr(win, "restart_button")
    texts = [b.text() for b in win.findChildren(QPushButton)]
    assert "Restart now" not in texts


@pytest.fixture
def qm(tmp_path, monkeypatch):
    """A test translation into Russian in the folder the window takes translations from."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "measure_twice_ru.ts").write_text(TEST_TS, encoding="utf-8")
    out = tmp_path / "out"
    i18n.build_qm(src, out)
    monkeypatch.setattr(i18n, "BUILD", out)
    return out


def test_choosing_changes_the_language_at_once(win, settings, qm, restarts):
    new = _choose(win, "ru")
    assert settings.value(i18n.KEY) == "ru"
    assert i18n.current() == "ru"
    assert new.new_menu_button.text() == "[ru] + New ▾"
    assert new.language_button.text() == "RU ▾"
    assert restarts == []
    new.close()


def test_new_window_keeps_the_store_project_and_tab(win, store, settings, qm):
    first = add_example(store, "en")
    second = store.copy(first)
    win.refresh(second)
    win.tabs.setCurrentWidget(win.norm)
    new = _choose(win, "ru")
    assert new is not win
    assert new.store is store
    assert new.current_id == second != first
    assert new.tabs.currentIndex() == win.tabs.indexOf(win.norm)
    new.close()


def test_shown_window_is_replaced_by_the_new_one(win, qm):
    win.show()
    new = _choose(win, "ru")
    assert new.isVisible()
    assert not win.isVisible()
    new.close()


def test_list_row_changes_the_language(win, settings, qm):
    next(a for a in win.language_menu.actions() if a.data() == "ru").trigger()
    assert settings.value(i18n.KEY) == "ru"
    assert i18n.current() == "ru"


def test_choosing_the_running_language_keeps_the_window(win, settings):
    assert _choose(win, "en") is win
    assert settings.value(i18n.KEY) == "en"


def test_window_without_settings_changes_language(app, store, qm):
    w = MainWindow(store)
    new = _choose(w, "ru")
    assert new.language_button.text() == "RU ▾"
    assert new.new_menu_button.text() == "[ru] + New ▾"
    new.close()


def test_right_to_left_language_turns_the_window(app, store, settings, restarts, tmp_path):
    i18n.apply_language(app, "he", tmp_path)
    w = MainWindow(store, settings)
    assert w.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert w.language_button.layoutDirection() == Qt.LayoutDirection.RightToLeft
    w.close()
