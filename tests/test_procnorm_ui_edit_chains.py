"""Tests of editing the transitions of a path in the Step chains tab."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from procnorm import edit
from procnorm.store import Store
from procnorm.ui.app import MainWindow
from procnorm.ui.comparison import OUT

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
A, B, V = "А", "Б", "В"  # А: 7 calls, its first step has none; В: 6 calls
ICONS = ["↑", "↓", "✕", "+"]
TIPS = ["Move up", "Move down", "Remove", "Add transition below"]


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


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _page(win, code):
    win.chains.select_path(code)
    return win.chains


def _calls(page):
    return [r for r in page.rows() if r[0] == "call"]


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _variant(data, code):
    return next(v for v in data["variants"] if v["code"] == code)


def _click(button):
    assert button.isEnabled()
    button.click()
    _settle()


# ---------- buttons ----------

def test_buttons_in_column_right_of_scope(win):
    t = _page(win, A).table
    last = t.columnCount() - 1
    assert t.horizontalHeaderItem(last - 1).text() == "Scope"
    for r, kind in enumerate(t.kinds):
        b = t.buttons_at(r)
        if kind == "call":
            assert b is not None and t.cellWidget(r, last) is b
            assert b.texts() == ICONS
            assert b.tips() == TIPS
        elif kind == "none":
            assert b is not None and b.texts() == ["+"]
            assert b.tips() == ["Add transition below"]
        else:
            assert b is None


def test_up_off_on_first_down_off_on_last(win):
    t = _page(win, A).table
    states = [(t.buttons_at(t.call_row(n)).up.isEnabled(), t.buttons_at(t.call_row(n)).down.isEnabled())
              for n in range(1, 8)]
    assert states[0] == (False, True)
    assert states[-1] == (True, False)
    assert all(s == (True, True) for s in states[1:-1])


def test_path_with_empty_steps_only_has_plus(win, store):
    pid = win.current_id
    data = _data(store, pid)
    for _ in range(5):
        data, _ = edit.remove_call(data, B, 1)
    store.save(pid, data)
    win.refresh(pid)
    t = _page(win, B).table
    nones = [r for r, k in enumerate(t.kinds) if k == "none"]
    assert len(nones) == 4 and "call" not in t.kinds
    assert all(t.buttons_at(r).texts() == ["+"] for r in nones)


# ---------- input row ----------

def test_plus_opens_input_row_with_defaults_of_row_above(win, store):
    page = _page(win, A)
    t = page.table
    r = t.call_row(3)
    _click(t.buttons_at(r).add)
    assert t.kinds[r + 1] == "input"
    inp = t.input
    above = _calls(page)[2][2:]
    assert inp.values() == list(above)
    kinds = [k["name"] for k in store.get(win.current_id).data["kinds"]]
    assert inp.choices("kind") == kinds  # every kind of the dictionary
    assert inp.add_button.text() == "Add" and inp.cancel_button.text() == "Cancel"


def test_one_input_row_at_a_time(win):
    t = _page(win, A).table
    _click(t.buttons_at(t.call_row(2)).add)
    _click(t.buttons_at(t.call_row(5)).add)
    assert t.kinds.count("input") == 1
    assert t.kinds.index("input") == t.call_row(5) + 1


def test_cancel_closes_input_row(win, store):
    pid = win.current_id
    before = store.text(pid)
    t = _page(win, A).table
    _click(t.buttons_at(t.call_row(2)).add)
    _click(t.input.cancel_button)
    assert "input" not in t.kinds and t.input is None
    assert store.text(pid) == before


def test_add_changes_database_and_chain(win, store):
    pid = win.current_id
    old = _data(store, pid)
    page = _page(win, V)
    t = page.table
    _click(t.buttons_at(t.call_row(6)).add)
    t.input.set_value("kind", "Проверить карманы")
    _click(t.input.add_button)
    call = ["Проверить карманы", "Человек", "руки", "каждая вещь"]
    expected, _ = edit.add_call(old, V, 6, call)
    assert store.get(pid).data == expected
    calls = _calls(page)
    assert len(calls) == 7 and list(calls[6][1:]) == ["7"] + call
    assert page.current_code() == V
    assert "input" not in page.table.kinds


def test_add_into_empty_step(win, store):
    pid = win.current_id
    old = _data(store, pid)
    t = _page(win, A).table
    r = t.kinds.index("none")
    _click(t.buttons_at(r).add)
    assert t.kinds[r + 1] == "input"
    values = t.input.values()
    _click(t.input.add_button)
    expected, _ = edit.add_call(old, A, 0, values, step=0)
    assert store.get(pid).data == expected
    assert [s["calls"] for s in _variant(expected, A)["steps"]][:2] == [1, 1]


# ---------- move and remove ----------

def test_down_moves_and_crosses_step(win, store):
    pid = win.current_id
    old = _data(store, pid)
    t = _page(win, V).table
    _click(t.buttons_at(t.call_row(1)).down)
    expected, _ = edit.move_call(old, V, 1, 1)
    assert store.get(pid).data == expected


def test_remove_changes_database_and_chain(win, store):
    pid = win.current_id
    old = _data(store, pid)
    page = _page(win, V)
    _click(page.table.buttons_at(page.table.call_row(6)).remove)
    expected, _ = edit.remove_call(old, V, 6)
    assert store.get(pid).data == expected
    assert len(_calls(page)) == 5


# ---------- broken run, kept view, refusal ----------

def test_breaking_edit_marks_row_and_moves_path_out(win):
    page = _page(win, A)
    t = page.table
    _click(t.buttons_at(t.call_row(4)).up)  # wash before the machine start
    assert page.current_code() == A
    rows = page.rows()
    at = t.call_row(3)
    assert t.failed_rows() == [at]
    assert rows[at + 1][0] == "error" and rows[at + 1][1].startswith("Error at transition 3")
    out = [codes for title, _, codes in page.groups() if title == OUT]
    assert out and A in out[0]


def test_selected_path_stays_selected(win):
    page = _page(win, V)
    t = page.table
    _click(t.buttons_at(t.call_row(2)).down)
    assert page.current_code() == V
    assert page.path(V).selected


def test_refused_edit_shows_red_line_and_keeps_database(win, store):
    pid = win.current_id
    before = store.text(pid)
    page = _page(win, V)
    assert page.refusal.isHidden()
    assert win.edit_chain("move", (V, 1, -1)) is False  # the first transition of the first step
    assert store.text(pid) == before
    assert not page.refusal.isHidden() and "cannot move up" in page.refusal.text()
    assert page.current_code() == V
    _click(page.table.buttons_at(page.table.call_row(2)).down)
    assert page.refusal.isHidden()
