# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the input row of a new transition on the Step chains tab: the list ``Kind`` offers the
kinds allowed at that place first, then under ``Not allowed here`` the others in grey with their
reason; ``State here`` under the input row shows the slice at that place; after ``Add`` the input
row moves under the new transition with the list and the state of the next place."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from procnorm.calc import allowed_kinds, slice_at
from procnorm.project import read_project
from procnorm.store import Store
from procnorm.ui.app import MainWindow
from procnorm.ui.tables import mono

# Made-up project: K1 and K2 run, K3 has no transitions; a test breaks K2 at its first transition.
KITCHEN = {
    "format": 1,
    "name": "Kitchen",
    "existence_axis": {"name": "exists", "absent": "no"},
    "entities": [
        {"name": "Cup", "axes": [{"name": "state", "values": ["dirty", "clean", "dry"]}]},
        {"name": "Pot", "axes": [{"name": "water", "values": ["cold", "hot"]}]},
    ],
    "kinds": [
        {"name": "Wash", "entity": "Cup", "axis": "state", "from": "dirty", "to": "clean"},
        {"name": "Dry", "entity": "Cup", "axis": "state", "from": "clean", "to": "dry"},
        {"name": "Boil", "entity": "Pot", "axis": "water", "from": "cold", "to": "hot"},
    ],
    "executors": ["Cook", "Helper"],
    "instruments": ["Hands", "Towel"],
    "scopes": ["Cup", "All"],
    "batch_scope": "All",
    "variants": [
        {
            "code": "K1",
            "title": "Wash and boil",
            "side": "own",
            "task": "Tea",
            "calls": [["Wash", "Cook", "Hands", "Cup"], ["Boil", "Helper", "Hands", "All"]],
        },
        {
            "code": "K2",
            "title": "Wash and dry",
            "side": "other",
            "task": "Tea",
            "calls": [["Wash", "Cook", "Hands", "Cup"], ["Dry", "Cook", "Towel", "Cup"]],
        },
        {"code": "K3", "title": "Nothing yet", "side": "own", "task": "Task K3", "calls": []},
    ],
    "normalization": {
        "kind_costs": {"Wash": 1, "Dry": 1, "Boil": 2},
        "executor_coefficients": {"Cook": 1, "Helper": 1},
        "scope_coefficients": {"Cup": 1, "All": 1},
        "axis_skip_prices": {},
    },
}

KINDS = ["Wash", "Dry", "Boil"]
NOT_ALLOWED = "Not allowed here"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "k.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    path = tmp_path / "kitchen.json"
    path.write_text(json.dumps(KITCHEN), "utf-8")
    w = MainWindow(store)
    assert w.load_path(path)
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


def _project(store, pid):
    project, _ = read_project(store.get(pid).data, strict=False)
    return project


def _page(win, code):
    page = win.chains
    page.select_path(code)
    QApplication.processEvents()
    return page


def _open_under_call(win, code, number):
    t = _page(win, code).table
    _click(t.buttons_at(t.call_row(number)).add)
    return t


def _open_in_empty(win, code):
    t = _page(win, code).table
    _click(t.buttons_at(t.kinds.index("none")).add)
    return t


def _expected_lines(project, code, after):
    s = slice_at(project, code, after)
    lines = []
    for (entity, axis), value in s.items():
        lines.append(f"{entity} / {axis} = {'—' if value is None else value}")
    return lines


def _check_place(win, store, t, code, after):
    allowed = allowed_kinds(_project(store, win.current_id), code, after)
    inp = t.input
    free = [k for k, why in allowed.items() if why is None]
    grey = {k: why for k, why in allowed.items() if why is not None}
    assert inp.allowed() == free
    assert inp.reasons() == grey
    assert inp.choices("kind") == free + list(grey)


# ---------- the list Kind ----------

@pytest.mark.parametrize("number", [1, 2])
def test_kind_list_equals_allowed_kinds_under_a_call(win, store, number):
    t = _open_under_call(win, "K1", number)
    _check_place(win, store, t, "K1", number)


def test_kind_list_equals_allowed_kinds_in_an_empty_variant(win, store):
    t = _open_in_empty(win, "K3")
    _check_place(win, store, t, "K3", 0)
    assert t.input.allowed() == ["Wash", "Boil"]  # entities come with the transitions


def test_allowed_come_first_then_separator_then_grey(win):
    t = _open_under_call(win, "K1", 1)
    box = t.input.lists["kind"]
    texts = [box.itemText(i) for i in range(box.count())]
    assert texts == ["Dry", "Boil", NOT_ALLOWED, "Wash"]
    model = box.model()
    flags = [model.item(i).flags() for i in range(box.count())]
    assert all(f & Qt.ItemFlag.ItemIsEnabled for f in flags[:2])
    assert not flags[2] & Qt.ItemFlag.ItemIsEnabled
    assert not flags[3] & Qt.ItemFlag.ItemIsEnabled
    assert not flags[3] & Qt.ItemFlag.ItemIsSelectable


def test_grey_kind_shows_its_reason_and_cannot_be_chosen(win, store):
    t = _open_under_call(win, "K1", 1)
    inp = t.input
    reason = allowed_kinds(_project(store, win.current_id), "K1", 1)["Wash"]
    assert reason == "Cup/state is 'clean', expected 'dirty'"
    box = inp.lists["kind"]
    grey = box.model().item(box.findText("Wash"))
    assert grey.toolTip() == reason
    chosen = inp.values()[0]
    inp.set_value("kind", "Wash")
    assert inp.values()[0] == chosen


def test_kind_above_not_allowed_gives_the_first_allowed(win):
    t = _open_under_call(win, "K1", 1)
    assert t.input.values() == ["Dry", "Cook", "Hands", "Cup"]


def test_place_after_an_error_allows_all_kinds_without_reasons_or_state(win, store):
    pid = win.current_id
    data = copy.deepcopy(store.get(pid).data)
    variant = next(v for v in data["variants"] if v["code"] == "K2")
    variant["calls"].reverse()  # Dry before Wash fails at the first transition
    store.save(pid, data)
    win.refresh(pid)
    assert _project(store, pid).errors["K2"][0] == 1
    t = _open_under_call(win, "K2", 1)
    assert t.input.allowed() == KINDS
    assert t.input.reasons() == {}
    assert t.input.choices("kind") == KINDS
    assert "state" not in t.kinds


# ---------- State here ----------

@pytest.mark.parametrize("number", [1, 2])
def test_state_here_is_the_slice_at_the_place(win, store, number):
    t = _open_under_call(win, "K1", number)
    r = t.kinds.index("input")
    assert t.kinds[r + 1] == "state"
    project = _project(store, win.current_id)
    assert t.state_lines() == _expected_lines(project, "K1", number)
    row = dict(enumerate(t.rows()))[r + 1]
    assert row[0] == "state" and row[1] == "State here:"
    assert list(row[2:]) == _expected_lines(project, "K1", number)


def test_state_here_of_an_empty_variant_is_empty(win):
    t = _open_in_empty(win, "K3")
    assert "state" in t.kinds
    assert t.state_lines() == []


def test_state_here_only_while_the_input_row_is_open(win):
    page = _page(win, "K1")
    assert "state" not in page.table.kinds
    t = _open_under_call(win, "K1", 2)
    assert "state" in t.kinds
    _click(t.input.cancel_button)
    assert "state" not in t.kinds


def test_state_here_is_monospace_and_wraps(win):
    t = _open_under_call(win, "K1", 1)
    label = t.state_label
    assert label.wordWrap()
    assert label.font().family() == mono().family()


# ---------- after Add ----------

def test_add_moves_the_input_under_the_new_transition_and_recomputes(win, store):
    t = _open_under_call(win, "K1", 1)
    t.input.set_value("kind", "Dry")
    _click(t.input.add_button)
    page = win.chains
    t = page.table
    assert page.current_code() == "K1"
    calls = [row for row in t.rows() if row[0] == "call"]
    assert [row[2] for row in calls] == ["Wash", "Dry", "Boil"]
    r = t.kinds.index("input")
    assert t.kinds[r - 1] == "call" and t.item(r - 1, 1).text() == "2"
    _check_place(win, store, t, "K1", 2)
    project = _project(store, win.current_id)
    assert t.state_lines() == _expected_lines(project, "K1", 2)
    assert ("Cup", "state") in slice_at(project, "K1", 2)
    assert slice_at(project, "K1", 2)[("Cup", "state")] == "dry"


def test_add_into_an_empty_variant_opens_the_next_place(win, store):
    t = _open_in_empty(win, "K3")
    t.input.set_value("kind", "Boil")
    _click(t.input.add_button)
    t = win.chains.table
    assert t.kinds.count("input") == 1
    _check_place(win, store, t, "K3", 1)
    assert t.state_lines() == ["Pot / water = hot"]


def test_other_path_does_not_keep_the_input_open(win):
    t = _open_under_call(win, "K1", 1)
    _click(t.input.add_button)
    assert "input" in win.chains.table.kinds
    page = _page(win, "K2")
    assert "input" not in page.table.kinds
