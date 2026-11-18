"""Tests of the block «Entities and initial state» on the Step chains tab: a tick per entity of
the dictionary and a list per axis to deviate the initial value; each change goes to the
database, and a path that lost the entity of a transition shows the error on that row."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtWidgets import QApplication

from procnorm import edit
from procnorm.store import Store
from procnorm.ui.app import MainWindow

# Made-up project: three entities; G1 has no entities of its own, G2 lists them.
GARDEN = {
    "format": 1,
    "name": "Garden",
    "existence_axis": {"name": "exists", "absent": "no"},
    "entities": [
        {"name": "Bed", "axes": [{"name": "soil", "values": ["dry", "wet"]}]},
        {"name": "Can", "axes": [{"name": "water", "values": ["empty", "full"]}]},
        {"name": "Shed", "axes": [{"name": "door", "values": ["shut", "open"]}]},
    ],
    "kinds": [
        {"name": "Fill", "entity": "Can", "axis": "water", "from": "empty", "to": "full"},
        {"name": "Water", "entity": "Bed", "axis": "soil", "from": "dry", "to": "wet"},
    ],
    "executors": ["Gardener"],
    "instruments": ["Hose"],
    "scopes": ["Bed", "Plot"],
    "batch_scope": "Plot",
    "variants": [
        {
            "code": "G1",
            "title": "Plain watering",
            "side": "own",
            "task": "Water the bed",
            "calls": [["Fill", "Gardener", "Hose", "Plot"], ["Water", "Gardener", "Hose", "Bed"]],
        },
        {
            "code": "G2",
            "title": "Watering with the shed",
            "side": "other",
            "task": "Water the bed",
            "entities": ["Bed", "Can", "Shed"],
            "initial": {"Shed": {"door": "open"}},
            "calls": [["Fill", "Gardener", "Hose", "Plot"], ["Water", "Gardener", "Hose", "Bed"]],
        },
    ],
    "normalization": {
        "kind_costs": {"Fill": 1, "Water": 2},
        "executor_coefficients": {"Gardener": 1},
        "scope_coefficients": {"Bed": 1, "Plot": 1},
        "axis_skip_prices": {},
    },
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "g.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    path = tmp_path / "garden.json"
    path.write_text(json.dumps(GARDEN), "utf-8")
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


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _variant(store, pid, code):
    return next(v for v in store.get(pid).data["variants"] if v["code"] == code)


def _ticked(page):
    return [name for name, box in page.entity_checks.items() if box.isChecked()]


def _items(box):
    return [box.itemText(i) for i in range(box.count())]


def _choose(box, text):
    box.setCurrentIndex(box.findText(text))
    box.activated.emit(box.currentIndex())
    QApplication.processEvents()


def _open(page):
    if page.entities_body.isHidden():
        _click(page.fold_button)


def test_block_is_folded_until_opened(win):
    page = win.chains
    page.select_path("G1")
    assert "Entities and initial state" in page.fold_button.text()
    assert page.entities_body.isHidden()
    _click(page.fold_button)
    assert not page.entities_body.isHidden()
    page.select_path("G2")
    assert not page.entities_body.isHidden()  # stays open for another path
    _click(page.fold_button)
    assert page.entities_body.isHidden()


def test_path_without_entities_shows_axes_of_transitions(win):
    page = win.chains
    page.select_path("G1")
    _open(page)
    assert list(page.entity_checks) == ["Bed", "Can", "Shed"]
    assert _ticked(page) == []
    assert list(page.initial_boxes) == [("Bed", "soil"), ("Can", "water")]
    box = page.initial_boxes[("Can", "water")]
    assert _items(box) == ["as in dictionary: empty", "empty", "full"]
    assert box.currentText() == "as in dictionary: empty"


def test_path_with_entities_and_deviation(win):
    page = win.chains
    page.select_path("G2")
    _open(page)
    assert _ticked(page) == ["Bed", "Can", "Shed"]
    assert list(page.initial_boxes) == [("Bed", "soil"), ("Can", "water"), ("Shed", "door")]
    assert page.initial_boxes[("Shed", "door")].currentText() == "open"
    assert page.initial_boxes[("Bed", "soil")].currentText() == "as in dictionary: dry"


def test_tick_adds_entity_in_dictionary_order(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G1")
    _open(page)
    _click(page.entity_checks["Can"])
    _click(page.entity_checks["Bed"])
    old = _data(store, pid)
    _click(page.entity_checks["Shed"])
    expected, _ = edit.set_variant(old, "G1", entities=["Bed", "Can", "Shed"])
    assert store.get(pid).data == expected
    assert page.current_code() == "G1"
    assert _ticked(page) == ["Bed", "Can", "Shed"]
    assert ("Shed", "door") in page.initial_boxes
    assert not page.entities_body.isHidden()


def test_untick_all_removes_entities(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    for name in ("Shed", "Can", "Bed"):
        _click(page.entity_checks[name])
    v = _variant(store, pid, "G2")
    assert "entities" not in v
    assert _ticked(page) == []
    assert page.path("G2").error_text() is None
    assert list(page.initial_boxes) == [("Bed", "soil"), ("Can", "water")]


def test_lost_entity_gives_error_on_its_transition(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    old = _data(store, pid)
    _click(page.entity_checks["Bed"])
    expected, _ = edit.set_variant(old, "G2", entities=["Can", "Shed"])
    assert store.get(pid).data == expected
    assert page.current_code() == "G2"
    assert page.path("G2").error_text() == "error"
    kinds = page.row_kinds()
    second = page.table.call_row(2)
    assert page.table.failed_rows() == [second]
    assert kinds[second + 1] == "error"
    assert kinds.count("error") == 1
    _click(page.entity_checks["Bed"])
    assert page.path("G2").error_text() is None
    assert "error" not in page.row_kinds()


def test_deviation_written_and_removed(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G1")
    _open(page)
    old = _data(store, pid)
    _choose(page.initial_boxes[("Can", "water")], "full")
    expected, _ = edit.set_variant(old, "G1", initial={"Can": {"water": "full"}})
    assert store.get(pid).data == expected
    assert page.current_code() == "G1"
    assert page.initial_boxes[("Can", "water")].currentText() == "full"
    first = page.table.call_row(1)
    assert page.table.failed_rows() == [first]  # Fill needs an empty can
    _choose(page.initial_boxes[("Can", "water")], "as in dictionary: empty")
    assert "initial" not in _variant(store, pid, "G1")
    assert page.table.failed_rows() == []


def test_deviation_to_first_value_is_kept(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G1")
    _open(page)
    _choose(page.initial_boxes[("Bed", "soil")], "dry")
    assert _variant(store, pid, "G1")["initial"] == {"Bed": {"soil": "dry"}}
    assert page.initial_boxes[("Bed", "soil")].currentText() == "dry"


def test_deviation_keeps_other_deviations(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    _choose(page.initial_boxes[("Bed", "soil")], "wet")
    initial = _variant(store, pid, "G2")["initial"]
    assert initial == {"Shed": {"door": "open"}, "Bed": {"soil": "wet"}}
    _choose(page.initial_boxes[("Shed", "door")], "as in dictionary: shut")
    assert _variant(store, pid, "G2")["initial"] == {"Bed": {"soil": "wet"}}


def test_refusal_gives_stored_ticks_back(win):
    page = win.chains
    page.select_path("G2")
    _open(page)
    page.entity_checks["Bed"].setChecked(False)
    page.initial_boxes[("Shed", "door")].setCurrentIndex(0)
    page.show_refusal("refused")
    assert _ticked(page) == ["Bed", "Can", "Shed"]
    assert page.initial_boxes[("Shed", "door")].currentText() == "open"
    assert not page.refusal.isHidden()


def _cleared(page):
    return page.cleared_note.text() if not page.cleared_note.isHidden() else None


def test_untick_clears_its_deviations_and_says_so(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    old = _data(store, pid)
    assert _cleared(page) is None
    _click(page.entity_checks["Shed"])
    expected, _ = edit.set_variant(old, "G2", entities=["Bed", "Can"], initial={})
    assert store.get(pid).data == expected
    assert "initial" not in _variant(store, pid, "G2")
    assert _cleared(page) == "Initial-state changes of Shed were cleared."


def test_retick_starts_from_dictionary(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    _click(page.entity_checks["Shed"])
    _click(page.entity_checks["Shed"])
    assert _variant(store, pid, "G2")["entities"] == ["Bed", "Can", "Shed"]
    assert "initial" not in _variant(store, pid, "G2")
    assert page.initial_boxes[("Shed", "door")].currentText() == "as in dictionary: shut"


def test_untick_without_deviations_shows_no_line(win, store):
    page = win.chains
    page.select_path("G2")
    _open(page)
    _click(page.entity_checks["Bed"])
    assert _cleared(page) is None
    assert _variant(store, win.current_id, "G2")["initial"] == {"Shed": {"door": "open"}}


def test_untick_keeps_deviations_of_other_entities(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("G2")
    _open(page)
    _choose(page.initial_boxes[("Bed", "soil")], "wet")
    _click(page.entity_checks["Bed"])
    assert _variant(store, pid, "G2")["initial"] == {"Shed": {"door": "open"}}
    assert _cleared(page) == "Initial-state changes of Bed were cleared."


def test_cleared_line_goes_with_next_edit_or_other_path(win, store):
    page = win.chains
    page.select_path("G2")
    _open(page)
    _click(page.entity_checks["Shed"])
    assert _cleared(page) is not None
    _choose(page.initial_boxes[("Bed", "soil")], "wet")
    assert _cleared(page) is None
    _click(page.entity_checks["Bed"])
    _click(page.entity_checks["Bed"])
    _click(page.entity_checks["Can"])
    page.select_path("G2")
    page.select_path("G1")
    assert _cleared(page) is None
    page.select_path("G2")
    assert _cleared(page) is None
