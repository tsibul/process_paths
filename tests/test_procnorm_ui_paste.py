"""Tests of the `Paste AI answer` window opened from the `+ New ▾` menu."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton

from measure_twice.store import Store
from measure_twice.ui import app as app_module
from measure_twice.ui.app import MainWindow
from tests.test_procnorm_ai import _example_text


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
def opened(monkeypatch):
    """Replace the modal exec by a stub that records the window and runs a given action."""
    log = {"dialogs": [], "act": None}

    def exec_(dialog):
        log["dialogs"].append(dialog)
        if log["act"] is not None:
            log["act"](dialog)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", exec_)
    return log


def _button(dialog, text) -> QPushButton:
    return next(b for b in dialog.findChildren(QPushButton) if b.text() == text)


def _good() -> str:
    return "Done:\n```json\n" + _example_text() + "\n```\n"


def _bad_data() -> str:
    data = json.loads(_example_text())
    data["paths"] = "broken"
    return json.dumps(data)


def test_item_enabled(win):
    assert win.paste_action.isEnabled()


def test_window_has_one_field_load_cancel(win, opened):
    win.paste_action.trigger()
    dialog = opened["dialogs"][0]
    assert len(dialog.findChildren(QPlainTextEdit)) == 1
    assert sorted(b.text() for b in dialog.findChildren(QPushButton)) == ["Cancel", "Load"]


def test_text_without_json_shows_remark_and_adds_nothing(win, store, opened):
    def act(dialog):
        dialog.answer.setPlainText("no data here")
        _button(dialog, "Load").click()

    opened["act"] = act
    win.paste_action.trigger()
    dialog = opened["dialogs"][0]
    assert dialog.error.text() == app_module.NO_JSON
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert win.project_names() == []
    assert store.list() == []


def test_bad_answer_shows_remarks_under_field(win, store, opened):
    def act(dialog):
        dialog.answer.setPlainText(_bad_data())
        _button(dialog, "Load").click()

    opened["act"] = act
    win.paste_action.trigger()
    dialog = opened["dialogs"][0]
    assert dialog.error.text().strip()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert store.list() == []


def test_good_answer_adds_and_opens_project(win, store, opened):
    def act(dialog):
        dialog.answer.setPlainText(_good())
        _button(dialog, "Load").click()

    opened["act"] = act
    win.paste_action.trigger()
    assert opened["dialogs"][0].result() == QDialog.DialogCode.Accepted
    assert win.project_names() == ["Change a bike tyre"]
    assert win.projects.currentText() == "Change a bike tyre"


def test_cancel_adds_nothing(win, store, opened):
    def act(dialog):
        dialog.answer.setPlainText(_good())
        _button(dialog, "Cancel").click()

    opened["act"] = act
    win.paste_action.trigger()
    assert opened["dialogs"][0].result() != QDialog.DialogCode.Accepted
    assert store.list() == []


def test_field_empty_on_each_open(win, opened):
    def act(dialog):
        dialog.answer.setPlainText("some answer")
        _button(dialog, "Cancel").click()

    opened["act"] = act
    win.paste_action.trigger()
    win.paste_action.trigger()
    opened["act"] = None
    win.paste_action.trigger()
    assert opened["dialogs"][-1].answer.toPlainText() == ""
    assert opened["dialogs"][-1].error.text() == ""
