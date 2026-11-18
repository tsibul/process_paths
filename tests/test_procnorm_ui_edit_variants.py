"""Tests of copying, deleting and renaming variants in the Step chains tab."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from measure_twice import edit
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.comparison import OUT

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
A, B, V = "А", "Б", "В"  # one group "Постирать бельё"; А is ours


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
    assert w.load_path(LAUNDRY)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.chains)
    QApplication.processEvents()
    yield w
    w.close()


def _click(button):
    assert button.isEnabled()
    button.click()
    QApplication.processEvents()


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _group_of(page, code):
    return next(codes for _, _, codes in page.groups() if code in codes)


def _rename(page, code, title):
    page.code_edit.setText(code)
    page.title_edit.setText(title)
    page.title_edit.editingFinished.emit()
    QApplication.processEvents()


def test_header_has_copy_and_delete(win):
    page = win.chains
    page.select_path(B)
    assert page.copy_button.text() == "Copy" and page.delete_button.text() == "Delete"
    assert page.code_edit.text() == B and page.title_edit.text() == "Быстрая стирка"


def test_copy_lands_in_same_group_and_is_selected(win, store):
    pid = win.current_id
    old = _data(store, pid)
    page = win.chains
    page.select_path(B)
    _click(page.copy_button)
    expected, _ = edit.copy_variant(old, B)
    assert store.get(pid).data == expected
    twin = "Б (copy)"
    assert page.current_code() == twin and page.path(twin).selected
    assert twin in _group_of(page, B)
    assert page.code_edit.text() == twin  # editable at once


def test_second_copy_refused_with_red_line(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path(B)
    _click(page.copy_button)
    page.select_path(B)
    before = store.text(pid)
    _click(page.copy_button)
    assert store.text(pid) == before
    assert not page.refusal.isHidden() and "variant code is taken" in page.refusal.text()
    assert page.current_code() == B


def test_delete_after_confirmation_selects_neighbour(win, store, monkeypatch):
    pid = win.current_id
    page = win.chains
    codes = _group_of(page, B)
    i = codes.index(B)
    neighbour = codes[i + 1] if i + 1 < len(codes) else codes[i - 1]
    asked = []
    monkeypatch.setattr(win, "confirm", lambda text: asked.append(text) or True)
    page.select_path(B)
    _click(page.delete_button)
    assert asked == [f"Delete {B}?"]
    assert B not in [v["code"] for v in store.get(pid).data["variants"]]
    assert B not in page.codes() and page.current_code() == neighbour


def test_delete_declined_changes_nothing(win, store, monkeypatch):
    pid = win.current_id
    before = store.text(pid)
    monkeypatch.setattr(win, "confirm", lambda text: False)
    win.chains.select_path(B)
    _click(win.chains.delete_button)
    assert store.text(pid) == before and win.chains.current_code() == B


def test_rename_code_and_title(win, store):
    pid = win.current_id
    old = _data(store, pid)
    page = win.chains
    page.select_path(B)
    _rename(page, "Б2", "Новое название")
    expected, _ = edit.rename_variant(old, B, "Б2", "Новое название")
    assert store.get(pid).data == expected
    assert page.current_code() == "Б2" and page.head_title() == "Б2 Новое название"


def test_rename_to_taken_code_refused(win, store):
    pid = win.current_id
    before = store.text(pid)
    page = win.chains
    page.select_path(B)
    _rename(page, V, "Быстрая стирка")
    assert store.text(pid) == before
    assert not page.refusal.isHidden() and "taken" in page.refusal.text()
    assert page.code_edit.text() == B and page.current_code() == B


def test_error_mark_in_path_list(win):
    page = win.chains
    assert page.path(A).error_text() is None
    t = page.table
    _click(t.buttons_at(t.call_row(4)).up)  # breaks the run of А
    assert page.path(A).error_text() == "error"
    assert page.path(B).error_text() is None
    assert A in next(c for title, _, c in page.groups() if title == OUT)
