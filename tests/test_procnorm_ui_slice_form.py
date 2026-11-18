"""Tests of the named slice form on the Dictionary tab: groups "or", rows "and", a row is a state
(entity, axis, value) or a parameter (variant parameter, executor)."""

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

# Made-up project: a chair is primed, painted and its legs fixed; a table is sanded.
WORKSHOP = json.loads("""
{
  "format": 1,
  "name": "Workshop",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Chair", "axes": [
      {"name": "paint", "values": ["bare", "primed", "painted"]},
      {"name": "legs", "values": ["loose", "fixed"]}
    ]},
    {"name": "Table", "axes": [
      {"name": "surface", "values": ["rough", "smooth"]}
    ]}
  ],
  "kinds": [
    {"name": "Prime", "entity": "Chair", "axis": "paint", "from": "bare", "to": "primed"},
    {"name": "Paint", "entity": "Chair", "axis": "paint", "from": "primed", "to": "painted"},
    {"name": "Fix legs", "entity": "Chair", "axis": "legs", "from": "loose", "to": "fixed"},
    {"name": "Sand", "entity": "Table", "axis": "surface", "from": "rough", "to": "smooth"}
  ],
  "executors": ["Joiner", "Painter"],
  "instruments": ["Brush"],
  "scopes": ["Each", "Lot"],
  "batch_scope": "Lot",
  "variant_params": ["finisher"],
  "named_slices": {
    "ready": {"any": [
      {"states": [["Chair", "paint", "painted"], ["Chair", "legs", "fixed"]]},
      {"params": [["finisher", "Painter"]]}
    ]},
    "smooth": {"any": [{"states": [["Table", "surface", "smooth"]]}]}
  },
  "variants": [
    {"code": "W1", "title": "Chair first", "side": "own", "task": "Furnish",
     "params": {"finisher": "Joiner"},
     "calls": [["Prime", "Joiner", "Brush", "Each"], ["Paint", "Joiner", "Brush", "Each"],
               ["Fix legs", "Joiner", "Brush", "Each"]]}
  ],
  "normalization": {
    "kind_costs": {"Prime": 2, "Paint": 3, "Fix legs": 2, "Sand": 4},
    "executor_coefficients": {"Joiner": 1, "Painter": 1},
    "scope_coefficients": {"Each": 1, "Lot": 1},
    "axis_skip_prices": {}
  }
}
""")

ROW_NOTE = "A row is either a state (entity, axis, value) or a parameter (parameter, executor)."


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
    f = tmp_path / "workshop.json"
    f.write_text(json.dumps(WORKSHOP, ensure_ascii=False), encoding="utf-8")
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
    w.new_button.click()
    QApplication.processEvents()
    yield w
    w.close()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _click_add_slice(w):
    """Click the ``+ Add slice`` row; return the open form."""
    page = w.dictionary
    it = page.add_item("named_slice")
    assert it is not None
    t = it.tableWidget()
    rect = t.visualItemRect(it)
    QTest.mouseClick(t.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    _settle()
    form = page.slice_form()
    assert form is not None
    return form


def _click_edit(w, name):
    """Click ``✎`` of a slice row; return the open form."""
    page = w.dictionary
    b = page.edit_button("named_slice", name)
    assert b is not None
    b.click()
    _settle()
    form = page.slice_form()
    assert form is not None
    return form


def _items(combo):
    return [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i)]


def _form_row(w):
    """The table row the open form takes."""
    t = w.dictionary.slices
    for r in range(t.rowCount()):
        if t.cellWidget(r, 0) is not None:
            return r
    return -1


def _values(form):
    return [[row.values() for row in box.rows()] for box in form.group_boxes()]


def _fill_pair(row, param, executor):
    row.first.setCurrentText(param)
    row.value.setCurrentText(executor)


def _fill_triple(row, entity, axis, value):
    row.first.setCurrentText(entity)
    row.axis.setCurrentText(axis)
    row.value.setCurrentText(value)


# ---------- opening ----------

def test_add_slice_row_ends_slices(win):
    page = win.dictionary
    it = page.add_item("named_slice")
    assert it is not None
    assert it.text() == "+ Add slice"
    t = it.tableWidget()
    assert t is page.slices
    assert it.row() == t.rowCount() - 1


def test_empty_project_has_only_add_slice_row(empty):
    t = empty.dictionary.slices
    assert t.rowCount() == 1
    assert t.item(0, 0).text() == "+ Add slice"


def test_edit_button_on_every_slice_row(win):
    page = win.dictionary
    for name in WORKSHOP["named_slices"]:
        b = page.edit_button("named_slice", name)
        assert b is not None
        assert b.text() == "✎"
        assert b.toolTip() == "Edit"


def test_add_row_opens_add_form_with_one_group_under_it(win):
    form = _click_add_slice(win)
    assert form.name.text() == ""
    assert not form.name.isReadOnly()
    assert form.submit_button.text() == "Add"
    assert form.cancel_button.text() == "Cancel"
    boxes = form.group_boxes()
    assert len(boxes) == 1
    assert len(boxes[0].rows()) == 1
    assert _values(form) == [[("Chair", "paint", "bare")]]
    assert form.row_note.text() == ROW_NOTE
    add_row = win.dictionary.add_item("named_slice").row()
    assert _form_row(win) == add_row + 1


def test_edit_button_opens_filled_form_under_its_row(win):
    form = _click_edit(win, "ready")
    assert form.name.text() == "ready"
    assert form.name.isReadOnly()
    assert form.submit_button.text() == "Apply"
    assert _values(form) == [
        [("Chair", "paint", "painted"), ("Chair", "legs", "fixed")],
        [("finisher", "Painter")],
    ]
    pair = form.group_boxes()[1].rows()[0]
    assert pair.is_pair()
    assert pair.axis.isHidden()
    assert not form.group_boxes()[0].rows()[0].is_pair()
    row = win.dictionary.word_item("named_slice", "ready").row()
    assert _form_row(win) == row + 1


def test_group_titles_and_or_line(win):
    form = _click_edit(win, "ready")
    boxes = form.group_boxes()
    assert [box.title.text() for box in boxes] == ["Group 1", "Group 2"]
    assert boxes[0].or_line.isHidden()
    assert not boxes[1].or_line.isHidden()
    assert boxes[1].or_line.text() == "or"
    assert boxes[0].hint.text() == "all rows must hold"


def test_one_form_at_a_time(win):
    _click_edit(win, "ready")
    _click_edit(win, "smooth")
    t = win.dictionary.slices
    widgets = [r for r in range(t.rowCount()) if t.cellWidget(r, 0) is not None]
    assert len(widgets) == 1
    assert win.dictionary.slice_form().name.text() == "smooth"


def test_slice_form_closes_kind_form(win):
    win.dictionary.edit_button("kind", "Paint").click()
    _settle()
    assert win.dictionary.kind_form() is not None
    _click_edit(win, "ready")
    assert win.dictionary.kind_form() is None
    assert win.dictionary.slice_form() is not None


def test_cancel_closes_form_without_change(win, store):
    before = _data(store, win.current_id)
    rows = win.dictionary.slices.rowCount()
    form = _click_edit(win, "ready")
    form.group_boxes()[0].remove_button.click()
    _settle()
    form.cancel_button.click()
    _settle()
    assert win.dictionary.slice_form() is None
    assert win.dictionary.slices.rowCount() == rows
    assert _data(store, win.current_id) == before


def test_esc_closes_form(win, store):
    before = _data(store, win.current_id)
    form = _click_add_slice(win)
    QTest.keyClick(form.name, Qt.Key.Key_Escape)
    _settle()
    assert win.dictionary.slice_form() is None
    assert _data(store, win.current_id) == before


# ---------- lists follow the choice ----------

def test_first_list_has_entities_then_parameters(win):
    form = _click_add_slice(win)
    row = form.group_boxes()[0].rows()[0]
    assert _items(row.first) == ["Chair", "Table", "finisher"]


def test_axis_and_value_follow_entity(win):
    form = _click_add_slice(win)
    row = form.group_boxes()[0].rows()[0]
    row.first.setCurrentText("Table")
    assert _items(row.axis) == ["surface"]
    assert _items(row.value) == ["rough", "smooth"]
    row.first.setCurrentText("Chair")
    row.axis.setCurrentText("legs")
    assert _items(row.value) == ["loose", "fixed"]


def test_parameter_makes_a_pair_row(win):
    form = _click_add_slice(win)
    row = form.group_boxes()[0].rows()[0]
    row.first.setCurrentText("finisher")
    assert row.is_pair()
    assert row.axis.isHidden()
    assert _items(row.value) == ["Joiner", "Painter"]
    assert row.values() == ("finisher", "Joiner")
    row.first.setCurrentText("Chair")
    assert not row.is_pair()
    assert not row.axis.isHidden()
    assert row.values() == ("Chair", "paint", "bare")


# ---------- rows and groups ----------

def test_rows_added_and_removed(win):
    form = _click_add_slice(win)
    box = form.group_boxes()[0]
    assert box.add_row.text() == "+ Add row"
    box.add_row.click()
    box.add_row.click()
    _settle()
    rows = box.rows()
    assert len(rows) == 3
    _fill_pair(rows[1], "finisher", "Painter")
    assert rows[2].remove_button.text() == "✕"
    rows[2].remove_button.click()
    rows[0].remove_button.click()
    _settle()
    assert _values(form) == [[("finisher", "Painter")]]


def test_groups_added_and_removed(win):
    form = _click_add_slice(win)
    assert form.add_group.text() == "+ Add group"
    form.add_group.click()
    form.add_group.click()
    _settle()
    boxes = form.group_boxes()
    assert len(boxes) == 3
    assert len(boxes[1].rows()) == 1
    _fill_triple(boxes[1].rows()[0], "Table", "surface", "smooth")
    boxes[0].remove_button.click()
    _settle()
    boxes = form.group_boxes()
    assert [box.title.text() for box in boxes] == ["Group 1", "Group 2"]
    assert boxes[0].or_line.isHidden()
    assert _values(form)[0] == [("Table", "surface", "smooth")]


def test_form_row_grows_with_groups(win):
    form = _click_add_slice(win)
    t = win.dictionary.slices
    r = _form_row(win)
    before = t.rowHeight(r)
    form.add_group.click()
    form.group_boxes()[0].add_row.click()
    _settle()
    assert t.rowHeight(r) > before


# ---------- add and apply ----------

def test_add_writes_slice_and_table(win, store):
    form = _click_add_slice(win)
    QTest.keyClicks(form.name, "finished")
    first = form.group_boxes()[0]
    _fill_triple(first.rows()[0], "Chair", "paint", "painted")
    first.add_row.click()
    _settle()
    _fill_pair(first.rows()[1], "finisher", "Painter")
    form.add_group.click()
    _settle()
    _fill_triple(form.group_boxes()[1].rows()[0], "Table", "surface", "smooth")
    form.submit_button.click()
    _settle()
    data = _data(store, win.current_id)
    assert list(data["named_slices"]) == ["ready", "smooth", "finished"]
    assert data["named_slices"]["finished"] == {"any": [
        {"states": [["Chair", "paint", "painted"]], "params": [["finisher", "Painter"]]},
        {"states": [["Table", "surface", "smooth"]]},
    ]}
    assert win.dictionary.slice_form() is None
    assert win.dictionary.word_item("named_slice", "finished") is not None
    assert win.dictionary.refusal_line() == ""
    cells = win.dictionary.slices.texts()
    assert "Chair/paint = painted and finisher = Painter or Table/surface = smooth" in cells


def test_enter_in_name_adds(win, store):
    form = _click_add_slice(win)
    QTest.keyClicks(form.name, "primed")
    _fill_triple(form.group_boxes()[0].rows()[0], "Chair", "paint", "primed")
    QTest.keyClick(form.name, Qt.Key.Key_Return)
    _settle()
    data = _data(store, win.current_id)
    assert data["named_slices"]["primed"] == {"any": [{"states": [["Chair", "paint", "primed"]]}]}


def test_apply_changes_slice_keeps_place(win, store):
    form = _click_edit(win, "ready")
    boxes = form.group_boxes()
    boxes[0].rows()[1].remove_button.click()
    _settle()
    _fill_pair(boxes[1].rows()[0], "finisher", "Joiner")
    form.submit_button.click()
    _settle()
    data = _data(store, win.current_id)
    assert list(data["named_slices"]) == ["ready", "smooth"]
    assert data["named_slices"]["ready"] == {"any": [
        {"states": [["Chair", "paint", "painted"]]},
        {"params": [["finisher", "Joiner"]]},
    ]}
    assert win.dictionary.slice_form() is None


# ---------- refusal ----------

def test_refusal_of_empty_group_keeps_form_open_with_contents(win, store):
    before = _data(store, win.current_id)
    form = _click_add_slice(win)
    QTest.keyClicks(form.name, "half")
    _fill_triple(form.group_boxes()[0].rows()[0], "Chair", "legs", "fixed")
    form.add_group.click()
    _settle()
    form.group_boxes()[1].rows()[0].remove_button.click()
    _settle()
    form.submit_button.click()
    _settle()
    assert _data(store, win.current_id) == before
    assert win.dictionary.refusal_line() == "empty group"
    assert win.dictionary.slice_form() is form
    assert form.name.text() == "half"
    assert _values(form) == [[("Chair", "legs", "fixed")], []]


def test_refusal_of_taken_name(win):
    form = _click_add_slice(win)
    QTest.keyClicks(form.name, "smooth")
    form.submit_button.click()
    _settle()
    assert win.dictionary.refusal_line() == "named slice name is taken: smooth"
    assert win.dictionary.slice_form() is form


def test_refusal_of_final(win):
    form = _click_add_slice(win)
    QTest.keyClicks(form.name, "final")
    form.submit_button.click()
    _settle()
    assert win.dictionary.refusal_line() == "the name 'final' is reserved for the final slice"


def test_refusal_of_apply_without_groups(win, store):
    before = _data(store, win.current_id)
    form = _click_edit(win, "smooth")
    form.group_boxes()[0].remove_button.click()
    _settle()
    form.submit_button.click()
    _settle()
    assert _data(store, win.current_id) == before
    assert win.dictionary.refusal_line() == "a slice needs at least one group"
    assert win.dictionary.slice_form() is form
    assert form.group_boxes() == []


def test_cancel_clears_refusal(win):
    form = _click_add_slice(win)
    form.submit_button.click()
    _settle()
    assert win.dictionary.refusal_line() != ""
    form.cancel_button.click()
    _settle()
    assert win.dictionary.refusal_line() == ""
