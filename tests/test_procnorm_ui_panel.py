"""Tests of the panel: the project list, the `+ New ▾` menu and the `More ▾` menu."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QPushButton,
                               QWidgetAction)

from measure_twice.example import EXAMPLE_NAME
from measure_twice.store import Store
from measure_twice.ui import app as app_module
from measure_twice.ui.app import MainWindow
from tests.test_procnorm_edit_delete import with_spares

NEW_ITEMS = ["With AI…", "Paste AI answer…", "From file…", "Empty", "Example"]
MORE_ITEMS = ["Export to file…", "Duplicate", "Replace from file…", "Delete…"]
HINT = "The program keeps your projects by itself. This makes a file to send or archive."
OLD_TEXTS = {"New", "Load", "Load over", "Save file", "Copy", "Delete",
             "Add a process with AI", "Example"}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store):
    w = MainWindow(store)
    w.show()
    QApplication.processEvents()
    yield w
    w.close()


@pytest.fixture
def project_file(tmp_path):
    f = tmp_path / "shipping.json"
    f.write_text(json.dumps(with_spares(), default=float, ensure_ascii=False), encoding="utf-8")
    return f


def _items(menu) -> list[str]:
    """Texts of the clickable items of a menu, in order."""
    return [a.text() for a in menu.actions()
            if not a.isSeparator() and not isinstance(a, QWidgetAction)]


def _bar(win) -> QHBoxLayout:
    return next(lay for lay in win.findChildren(QHBoxLayout)
                if lay.indexOf(win.projects) >= 0)


def test_row_has_exactly_three_elements(win):
    bar = _bar(win)
    widgets = [bar.itemAt(i).widget() for i in range(bar.count())]
    controls = [w for w in widgets if isinstance(w, (QComboBox, QPushButton))]
    assert controls == [win.projects, win.new_menu_button, win.more_menu_button]
    assert win.new_menu_button.text() == "+ New ▾"
    assert win.more_menu_button.text() == "More ▾"
    assert win.new_menu_button.menu() is win.new_menu
    assert win.more_menu_button.menu() is win.more_menu


def test_new_menu_items_in_order(win):
    assert _items(win.new_menu) == NEW_ITEMS


def test_more_menu_items_in_order(win):
    assert _items(win.more_menu) == MORE_ITEMS


def test_hint_right_under_export(win):
    actions = win.more_menu.actions()
    assert actions[0] is win.save_action
    hint = actions[1]
    assert isinstance(hint, QWidgetAction)
    assert hint.defaultWidget().text() == HINT
    assert not hint.isEnabled()


def test_no_old_buttons_visible(win):
    texts = {b.text() for b in win.findChildren(QPushButton) if b.isVisible()}
    assert not texts & OLD_TEXTS
    for name in ("new_button", "load_button", "load_over_button", "save_button",
                 "copy_button", "delete_button", "ai_button", "example_button"):
        assert not hasattr(win, name)


def test_more_items_grey_without_project(win):
    assert win.current_id is None
    for a in (win.save_action, win.copy_action, win.load_over_action, win.delete_action):
        assert not a.isEnabled()
    for a in (win.ai_action, win.load_action, win.new_action, win.example_action):
        assert a.isEnabled()


def test_more_items_on_with_project(win):
    win.example_action.trigger()
    for a in (win.save_action, win.copy_action, win.load_over_action, win.delete_action):
        assert a.isEnabled()


def test_paste_item_present_and_enabled(win):
    assert win.paste_action.text() == "Paste AI answer…"
    assert win.paste_action.isEnabled()


def test_with_ai_opens_scenario(win, monkeypatch):
    shown = []

    def exec_(dialog):
        shown.append(dialog)
        return app_module.AiScenarioDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module.AiScenarioDialog, "exec", exec_)
    win.ai_action.trigger()
    assert shown == [win.ai_scenario()]


def test_from_file_loads(win, monkeypatch, project_file):
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(project_file), ""))
    win.load_action.trigger()
    assert len(win.project_names()) == 1
    assert win.current_id is not None


def test_empty_makes_project(win, monkeypatch):
    monkeypatch.setattr(win, "ask_name", lambda text: "Garden shed")
    win.new_action.trigger()
    assert win.project_names() == ["Garden shed"]
    assert win.tabs.currentWidget() is win.dictionary


def test_example_adds_example(win):
    win.example_action.trigger()
    assert win.project_names() == [EXAMPLE_NAME]
    assert win.tabs.currentWidget() is win.comparison
    assert win.example_action.toolTip() == f"Add the {EXAMPLE_NAME} example"


def test_export_writes_file(win, monkeypatch, tmp_path):
    win.example_action.trigger()
    out = tmp_path / "out.json"
    monkeypatch.setattr(app_module.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), ""))
    win.save_action.trigger()
    assert out.read_text(encoding="utf-8") == win.store.text(win.current_id)


def test_duplicate_copies(win):
    win.example_action.trigger()
    win.copy_action.trigger()
    assert len(win.project_names()) == 2


def test_replace_from_file_loads_over(win, monkeypatch, project_file):
    win.example_action.trigger()
    pid = win.current_id
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(project_file), ""))
    win.load_over_action.trigger()
    assert win.current_id == pid
    assert len(win.project_names()) == 1
    assert win.projects.currentText() != EXAMPLE_NAME


def test_delete_after_yes(win, monkeypatch):
    win.example_action.trigger()
    asked = []

    def confirm(text):
        asked.append(text)
        return True

    monkeypatch.setattr(win, "confirm", confirm)
    win.delete_action.trigger()
    assert asked and "cannot be undone" in asked[0]
    assert win.project_names() == []


def test_delete_after_no_keeps(win, monkeypatch):
    win.example_action.trigger()
    monkeypatch.setattr(win, "confirm", lambda text: False)
    win.delete_action.trigger()
    assert win.project_names() == [EXAMPLE_NAME]


def test_default_width_shows_whole_labels(win):
    win.example_action.trigger()
    QApplication.processEvents()
    assert win.width() == 1100
    for b in (win.new_menu_button, win.more_menu_button):
        right = b.mapTo(win, b.rect().topRight()).x()
        assert right < win.width()
        assert b.width() >= b.sizeHint().width()
    hint = win.more_menu.actions()[1].defaultWidget()
    for menu in (win.new_menu, win.more_menu):
        menu.ensurePolished()
        widest = max(menu.fontMetrics().horizontalAdvance(t) for t in _items(menu))
        assert menu.sizeHint().width() > widest
    assert win.more_menu.sizeHint().width() >= hint.sizeHint().width()
