"""Tests of the kind form on the Dictionary tab, of the amber line about variants that got errors
after a dictionary edit, and of the start hint of a project without variants."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

# Made-up project: dough is kneaded, rested and baked in an oven that is heated first.
BAKERY = json.loads("""
{
  "format": 1,
  "name": "Bakery",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Dough", "axes": [
      {"name": "state", "values": ["raw", "kneaded", "baked"]},
      {"name": "rested", "values": ["no", "yes"]},
      {"name": "probed", "values": ["no", "yes"]}
    ]},
    {"name": "Oven", "axes": [
      {"name": "heat", "values": ["cold", "warm", "hot"]}
    ]}
  ],
  "kinds": [
    {"name": "Knead", "entity": "Dough", "axis": "state", "from": "raw", "to": "kneaded"},
    {"name": "Rest", "entity": "Dough", "axis": "rested", "from": "no", "to": "yes",
     "zero_weight": true, "zero_weight_note": "Only waiting"},
    {"name": "Heat", "entity": "Oven", "axis": "heat", "from": "cold", "to": "hot"},
    {"name": "Bake", "entity": "Dough", "axis": "state", "from": "kneaded", "to": "baked",
     "requires": [["Oven", "heat", "hot"]]},
    {"name": "Probe", "entity": "Dough", "axis": "probed", "from": "no", "to": "yes",
     "check": true}
  ],
  "executors": ["Baker", "Helper"],
  "instruments": ["Hands"],
  "scopes": ["Each", "Tray"],
  "batch_scope": "Tray",
  "variant_params": [],
  "variants": [
    {"code": "B1", "title": "Plain", "side": "own", "task": "Bread",
     "params": {},
     "calls": [["Knead", "Baker", "Hands", "Each"], ["Heat", "Baker", "Hands", "Each"],
               ["Bake", "Baker", "Hands", "Each"]]},
    {"code": "B2", "title": "Rested", "side": "other", "task": "Bread",
     "params": {},
     "calls": [["Knead", "Baker", "Hands", "Each"], ["Rest", "Baker", "Hands", "Each"],
               ["Heat", "Baker", "Hands", "Each"], ["Bake", "Baker", "Hands", "Each"]]},
    {"code": "B3", "title": "Warm oven", "side": "own", "task": "Oven",
     "params": {},
     "calls": [["Heat", "Helper", "Hands", "Each"]]}
  ],
  "normalization": {
    "kind_costs": {"Knead": 3, "Heat": 1, "Bake": 4, "Probe": 1},
    "executor_coefficients": {"Baker": 1, "Helper": 1},
    "scope_coefficients": {"Each": 1, "Tray": 1},
    "axis_skip_prices": {"Dough": {"probed": 2}}
  }
}
""")

ZERO_NOTE = "Zero weight clears the cost of this kind."
START_HINT = ("Start with entities, their axes and values. Then add kinds, executors, instruments "
              "and scopes. Add variants on the Step chains tab.")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    f = tmp_path / "bakery.json"
    f.write_text(json.dumps(BAKERY, ensure_ascii=False), encoding="utf-8")
    w = MainWindow(store)
    assert w.load_path(f)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.dictionary)
    QApplication.processEvents()
    yield w
    w.close()


@pytest.fixture
def empty(app, store, monkeypatch):
    """A window with a new empty project."""
    w = MainWindow(store)
    w.resize(1200, 900)
    w.show()
    monkeypatch.setattr(w, "ask_name", lambda text: "Garden shed")
    w.new_action.trigger()
    QApplication.processEvents()
    yield w
    w.close()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _kind(data, name):
    return next(k for k in data["kinds"] if k["name"] == name)


def _click_add_kind(w):
    """Click the ``+ Add kind`` row; return the open form."""
    page = w.dictionary
    it = page.add_item("kind")
    assert it is not None
    t = it.tableWidget()
    rect = t.visualItemRect(it)
    QTest.mouseClick(t.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    _settle()
    form = page.kind_form()
    assert form is not None
    return form


def _click_edit(w, name):
    """Click ``✎`` of a kind row; return the open form."""
    page = w.dictionary
    b = page.edit_button("kind", name)
    assert b is not None
    b.click()
    _settle()
    form = page.kind_form()
    assert form is not None
    return form


def _items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def _form_row(w):
    """The table row the open form takes."""
    t = w.dictionary.kinds
    for r in range(t.rowCount()):
        if t.cellWidget(r, 0) is not None:
            return r
    return -1


def _kind_row(w, name):
    it = w.dictionary.word_item("kind", name)
    return it.row()


# ---------- opening ----------

def test_add_kind_row_ends_kinds(win):
    page = win.dictionary
    it = page.add_item("kind")
    assert it is not None
    assert it.text() == "+ Add kind"
    t = it.tableWidget()
    assert t is page.kinds
    assert it.row() == t.rowCount() - 1


def test_empty_project_has_add_kind_row(empty):
    it = empty.dictionary.add_item("kind")
    assert it is not None
    assert it.text() == "+ Add kind"


def test_edit_button_on_every_kind_row(win):
    page = win.dictionary
    for k in BAKERY["kinds"]:
        b = page.edit_button("kind", k["name"])
        assert b is not None
        assert b.text() == "✎"
        assert b.toolTip() == "Edit"


def test_add_row_opens_empty_add_form_under_it(win):
    form = _click_add_kind(win)
    assert form.name.text() == ""
    assert not form.name.isReadOnly()
    assert form.submit_button.text() == "Add"
    assert form.cancel_button.text() == "Cancel"
    assert form.conditions() == []
    assert not form.check.isChecked()
    assert not form.zero_weight.isChecked()
    add_row = win.dictionary.add_item("kind").row()
    assert _form_row(win) == add_row + 1


def test_edit_button_opens_filled_form_under_its_row(win):
    form = _click_edit(win, "Bake")
    assert form.name.text() == "Bake"
    assert form.submit_button.text() == "Apply"
    assert form.entity.currentText() == "Dough"
    assert form.axis.currentText() == "state"
    assert form.source.currentText() == "kneaded"
    assert form.target.currentText() == "baked"
    assert [row.values() for row in form.conditions()] == [("Oven", "heat", "hot")]
    assert _form_row(win) == _kind_row(win, "Bake") + 1


def test_edit_form_shows_flags_and_note(win):
    form = _click_edit(win, "Rest")
    assert form.zero_weight.isChecked()
    assert form.note.text() == "Only waiting"
    assert not form.check.isChecked()
    form = _click_edit(win, "Probe")
    assert form.check.isChecked()
    assert not form.zero_weight.isChecked()


def test_zero_weight_line_under_checkbox(win):
    form = _click_add_kind(win)
    assert form.zero_line.text() == ZERO_NOTE
    assert form.zero_line.objectName() == "note"


def test_note_field_follows_zero_weight(win):
    form = _click_add_kind(win)
    assert not form.note.isEnabled()
    form.zero_weight.setChecked(True)
    assert form.note.isEnabled()


def test_one_form_at_a_time(win):
    _click_edit(win, "Bake")
    _click_edit(win, "Knead")
    t = win.dictionary.kinds
    widgets = [r for r in range(t.rowCount()) if t.cellWidget(r, 0) is not None]
    assert len(widgets) == 1
    assert win.dictionary.kind_form().name.text() == "Knead"


def test_cancel_closes_form_without_change(win, store):
    before = _data(store, win.current_id)
    rows = win.dictionary.kinds.rowCount()
    form = _click_edit(win, "Bake")
    form.target.setCurrentText("raw")
    form.cancel_button.click()
    _settle()
    assert win.dictionary.kind_form() is None
    assert win.dictionary.kinds.rowCount() == rows
    assert _data(store, win.current_id) == before


def test_esc_closes_form(win, store):
    before = _data(store, win.current_id)
    form = _click_add_kind(win)
    QTest.keyClick(form.name, Qt.Key.Key_Escape)
    _settle()
    assert win.dictionary.kind_form() is None
    assert _data(store, win.current_id) == before


# ---------- lists follow the choice ----------

def test_axis_list_follows_entity(win):
    form = _click_add_kind(win)
    assert _items(form.entity) == ["Dough", "Oven"]
    form.entity.setCurrentText("Oven")
    assert _items(form.axis) == ["heat"]
    form.entity.setCurrentText("Dough")
    assert _items(form.axis) == ["state", "rested", "probed"]


def test_from_to_follow_axis(win):
    form = _click_add_kind(win)
    form.entity.setCurrentText("Dough")
    form.axis.setCurrentText("rested")
    assert _items(form.source) == ["no", "yes"]
    assert _items(form.target) == ["no", "yes"]
    form.entity.setCurrentText("Oven")
    assert _items(form.source) == ["cold", "warm", "hot"]
    assert _items(form.target) == ["cold", "warm", "hot"]


def test_condition_rows_added_and_removed(win):
    form = _click_add_kind(win)
    assert form.add_condition.text() == "+ Add condition"
    form.add_condition.click()
    form.add_condition.click()
    _settle()
    rows = form.conditions()
    assert len(rows) == 2
    rows[0].entity.setCurrentText("Oven")
    assert _items(rows[0].axis) == ["heat"]
    assert _items(rows[0].value) == ["cold", "warm", "hot"]
    rows[0].value.setCurrentText("warm")
    assert rows[1].remove_button.text() == "✕"
    rows[1].remove_button.click()
    _settle()
    assert [row.values() for row in form.conditions()] == [("Oven", "heat", "warm")]


def test_form_row_grows_with_conditions(win):
    form = _click_add_kind(win)
    t = win.dictionary.kinds
    r = _form_row(win)
    before = t.rowHeight(r)
    form.add_condition.click()
    form.add_condition.click()
    _settle()
    assert t.rowHeight(r) > before


# ---------- add and apply ----------

def test_add_writes_kind_and_table(win, store):
    form = _click_add_kind(win)
    QTest.keyClicks(form.name, "Cool")
    form.entity.setCurrentText("Oven")
    form.source.setCurrentText("hot")
    form.target.setCurrentText("warm")
    form.add_condition.click()
    _settle()
    row = form.conditions()[0]
    row.entity.setCurrentText("Dough")
    row.axis.setCurrentText("state")
    row.value.setCurrentText("baked")
    form.zero_weight.setChecked(True)
    QTest.keyClicks(form.note, "Oven cools alone")
    form.submit_button.click()
    _settle()
    data = _data(store, win.current_id)
    assert data["kinds"][-1] == {
        "name": "Cool", "entity": "Oven", "axis": "heat", "from": "hot", "to": "warm",
        "requires": [["Dough", "state", "baked"]], "zero_weight": True,
        "zero_weight_note": "Oven cools alone",
    }
    assert win.dictionary.kind_form() is None
    it = win.dictionary.word_item("kind", "Cool")
    assert it is not None
    assert win.dictionary.refusal_line() == ""


def test_add_plain_kind_writes_no_empty_parts(win, store):
    form = _click_add_kind(win)
    QTest.keyClicks(form.name, "Warm up")
    form.entity.setCurrentText("Oven")
    form.source.setCurrentText("cold")
    form.target.setCurrentText("warm")
    form.check.setChecked(True)
    QTest.keyClick(form.name, Qt.Key.Key_Return)
    _settle()
    data = _data(store, win.current_id)
    assert data["kinds"][-1] == {
        "name": "Warm up", "entity": "Oven", "axis": "heat", "from": "cold", "to": "warm",
        "check": True,
    }


def test_note_not_written_without_zero_weight(win, store):
    form = _click_add_kind(win)
    QTest.keyClicks(form.name, "Warm up")
    form.entity.setCurrentText("Oven")
    form.target.setCurrentText("warm")
    form.zero_weight.setChecked(True)
    QTest.keyClicks(form.note, "typed then dropped")
    form.zero_weight.setChecked(False)
    form.submit_button.click()
    _settle()
    kind = _data(store, win.current_id)["kinds"][-1]
    assert "zero_weight_note" not in kind
    assert "zero_weight" not in kind


def test_apply_changes_kind_keeps_place(win, store):
    names = [k["name"] for k in BAKERY["kinds"]]
    form = _click_edit(win, "Bake")
    form.conditions()[0].value.setCurrentText("warm")
    form.add_condition.click()
    _settle()
    row = form.conditions()[1]
    row.entity.setCurrentText("Dough")
    row.axis.setCurrentText("rested")
    row.value.setCurrentText("yes")
    form.submit_button.click()
    _settle()
    data = _data(store, win.current_id)
    assert [k["name"] for k in data["kinds"]] == names
    assert _kind(data, "Bake")["requires"] == [["Oven", "heat", "warm"], ["Dough", "rested", "yes"]]
    assert win.dictionary.kind_form() is None
    cells = win.dictionary.kinds.texts()
    assert "Oven/heat = warm; Dough/rested = yes" in cells


def test_apply_zero_weight_drops_cost(win, store):
    form = _click_edit(win, "Knead")
    form.zero_weight.setChecked(True)
    form.submit_button.click()
    _settle()
    data = _data(store, win.current_id)
    assert _kind(data, "Knead")["zero_weight"] is True
    assert "Knead" not in data["normalization"]["kind_costs"]


def test_apply_removing_condition(win, store):
    form = _click_edit(win, "Bake")
    form.conditions()[0].remove_button.click()
    _settle()
    form.submit_button.click()
    _settle()
    assert "requires" not in _kind(_data(store, win.current_id), "Bake")


def test_name_read_only_when_applying(win):
    form = _click_edit(win, "Bake")
    assert form.name.isReadOnly()


# ---------- refusal ----------

def test_refusal_keeps_form_open_with_contents(win, store):
    before = _data(store, win.current_id)
    form = _click_add_kind(win)
    QTest.keyClicks(form.name, "Idle")
    form.entity.setCurrentText("Oven")
    form.source.setCurrentText("warm")
    form.target.setCurrentText("warm")
    form.add_condition.click()
    _settle()
    form.submit_button.click()
    _settle()
    assert _data(store, win.current_id) == before
    assert win.dictionary.refusal_line() == "from equals to"
    still = win.dictionary.kind_form()
    assert still is form
    assert form.name.text() == "Idle"
    assert form.entity.currentText() == "Oven"
    assert form.source.currentText() == "warm"
    assert form.target.currentText() == "warm"
    assert len(form.conditions()) == 1


def test_refusal_of_taken_name(win, store):
    form = _click_add_kind(win)
    QTest.keyClicks(form.name, "Knead")
    form.entity.setCurrentText("Oven")
    form.target.setCurrentText("warm")
    form.submit_button.click()
    _settle()
    assert win.dictionary.refusal_line() == "kind name is taken: Knead"
    assert win.dictionary.kind_form() is form


def test_refusal_of_apply_keeps_form(win, store):
    before = _data(store, win.current_id)
    form = _click_edit(win, "Bake")
    form.target.setCurrentText("kneaded")
    form.submit_button.click()
    _settle()
    assert _data(store, win.current_id) == before
    assert win.dictionary.refusal_line() == "from equals to"
    assert win.dictionary.kind_form() is form
    assert form.target.currentText() == "kneaded"


def test_cancel_clears_refusal(win):
    form = _click_add_kind(win)
    form.entity.setCurrentText("Oven")
    form.submit_button.click()
    _settle()
    assert win.dictionary.refusal_line() != ""
    form.cancel_button.click()
    _settle()
    assert win.dictionary.refusal_line() == ""


# ---------- amber line ----------

AMBER = "2 paths have errors after this change: B1, B2. Fix them on the Step chains tab."


def _break_bake(w):
    form = _click_edit(w, "Bake")
    form.conditions()[0].value.setCurrentText("cold")
    form.submit_button.click()
    _settle()


def test_no_amber_line_at_start(win):
    assert win.dictionary.amber_text() == ""
    assert win.dictionary.amber.isHidden()


def test_amber_line_names_variants_that_got_errors(win, store):
    _break_bake(win)
    assert set(store.get(win.current_id).errors) == {"B1", "B2"}
    assert win.dictionary.amber_text() == AMBER
    assert not win.dictionary.amber.isHidden()


def test_amber_line_stays_after_unrelated_edit(win):
    _break_bake(win)
    assert win.add_word("executor", "Apprentice")
    _settle()
    assert win.dictionary.amber_text() == AMBER


def test_amber_line_goes_when_errors_fixed(win):
    _break_bake(win)
    form = _click_edit(win, "Bake")
    form.conditions()[0].value.setCurrentText("hot")
    form.submit_button.click()
    _settle()
    assert win.dictionary.amber_text() == ""
    assert win.dictionary.amber.isHidden()


def test_amber_line_one_path(win):
    form = _click_edit(win, "Rest")
    form.source.setCurrentText("yes")
    form.target.setCurrentText("no")
    form.submit_button.click()
    _settle()
    assert win.dictionary.amber_text() == (
        "1 path has errors after this change: B2. Fix them on the Step chains tab.")


def test_amber_line_after_moving_first_value(win, store):
    assert win.move_word("value", ("Oven", "heat", "cold"), 1)
    _settle()
    assert set(store.get(win.current_id).errors) == {"B1", "B2", "B3"}
    assert win.dictionary.amber_text() == (
        "3 paths have errors after this change: B1, B2, B3. Fix them on the Step chains tab.")


def test_no_amber_line_after_edit_without_errors(win):
    assert win.edit_word("rename", "executor", "Helper", "Assistant")
    _settle()
    assert win.dictionary.amber_text() == ""


def test_amber_line_gone_on_other_project(win, store, tmp_path):
    _break_bake(win)
    other = copy.deepcopy(BAKERY)
    other["name"] = "Second bakery"
    f = tmp_path / "second.json"
    f.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
    assert win.load_path(f)
    _settle()
    assert win.dictionary.amber_text() == ""


# ---------- start hint ----------

def test_start_hint_in_project_without_variants(empty):
    hint = empty.dictionary.start_hint
    assert hint.text() == START_HINT
    assert not hint.isHidden()
    assert hint.objectName() == "note"


def test_no_start_hint_with_variants(win):
    assert win.dictionary.start_hint.isHidden()
