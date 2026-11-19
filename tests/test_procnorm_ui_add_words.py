"""Tests of adding and reordering dictionary words on the Dictionary tab, and of the row with the
existence axis and the batch scope above its tables."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from measure_twice import edit
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from tests.test_procnorm_edit_delete import with_spares


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
    f = tmp_path / "shipping.json"
    text = json.dumps(with_spares(), default=float, ensure_ascii=False)
    f.write_text(text, encoding="utf-8")
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


def _open(w, what, owner=()):
    """Click the add row of a list; return its open editor."""
    page = w.dictionary
    it = page.add_item(what, owner)
    assert it is not None
    t = it.tableWidget()
    rect = t.visualItemRect(it)
    QTest.mouseClick(t.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    _settle()
    editor = page.open_editor()
    assert editor is not None
    return editor


def _type_enter(editor, name, first=None):
    QTest.keyClicks(editor.name, name)
    if first is not None:
        QTest.keyClicks(editor.first, first)
    QTest.keyClick(editor.name, Qt.Key.Key_Return)
    _settle()


# what, owner of the add row, typed name, first value, name as add_word takes it
ADDS = [
    ("entity", (), "Pallet", None, "Pallet"),
    ("axis", ("Order",), "seal", "open", ("Order", "seal")),
    ("value", ("Order", "label"), "torn", None, ("Order", "label", "torn")),
    ("executor", (), "Porter", None, "Porter"),
    ("instrument", (), "Knife", None, "Knife"),
    ("scope", (), "Per pallet", None, "Per pallet"),
]

ADD_TEXTS = {
    "entity": "+ Add entity",
    "axis": "+ Add axis",
    "value": "+ Add value",
    "executor": "+ Add executor",
    "instrument": "+ Add instrument",
    "scope": "+ Add scope",
    "variant_param": "+ Add parameter",
}


# ---------- add rows ----------

def test_add_row_ends_every_list(win):
    page = win.dictionary
    for what in ("entity", "executor", "instrument", "scope", "variant_param"):
        it = page.add_item(what)
        t = it.tableWidget()
        assert it.text() == ADD_TEXTS[what]
        assert it.row() == t.rowCount() - 1


def test_add_row_under_every_entity_and_axis(win):
    page = win.dictionary
    t = page.entities
    order_axes = ["status", "label", "wrap", "Spare axis"]
    for axis in order_axes:
        it = page.add_item("value", ("Order", axis))
        assert it.text() == ADD_TEXTS["value"]
        last_value = page.word_item("value", ("Order", axis, _values(win, "Order", axis)[-1]))
        assert it.row() == last_value.row() + 1
    axis_row = page.add_item("axis", ("Order",))
    assert axis_row.text() == ADD_TEXTS["axis"]
    assert axis_row.row() == page.add_item("value", ("Order", "Spare axis")).row() + 1
    assert t.item(axis_row.row() + 1, 0).data(Qt.ItemDataRole.UserRole + 2) == ("entity", "Box")


def _values(win, entity, axis):
    data = win.store.get(win.current_id).data
    owner = next(e for e in data["entities"] if e["name"] == entity)
    return next(a for a in owner["axes"] if a["name"] == axis)["values"]


def test_line_about_loading_a_file_gone(win):
    assert "To add words, load a new file." not in win.dictionary.all_text()


def test_click_opens_input_with_focus(win):
    editor = _open(win, "executor")
    assert editor.name.text() == ""
    assert editor.first is None
    assert editor.executor is None
    assert QApplication.focusWidget() is editor.name


def test_axis_input_has_first_value(win):
    editor = _open(win, "axis", ("Order",))
    assert editor.first is not None
    assert editor.first.placeholderText() == "first value"


@pytest.mark.parametrize("what, owner, typed, first, name", ADDS)
def test_enter_adds_word(win, store, what, owner, typed, first, name):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, what, owner)
    _type_enter(editor, typed, first)
    expected, remarks = edit.add_word(before, what, name, first_value=first)
    assert remarks == []
    assert _data(store, pid) == expected
    assert win.dictionary.word_item(what, name) is not None
    assert win.dictionary.open_editor() is None
    assert win.dictionary.refusal_line() == ""


def test_add_button_adds_like_enter(win, store):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, "instrument")
    QTest.keyClicks(editor.name, "Knife")
    editor.add_button.click()
    _settle()
    assert _data(store, pid) == edit.add_word(before, "instrument", "Knife")[0]


def test_esc_cancels(win, store):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, "executor")
    QTest.keyClicks(editor.name, "Porter")
    QTest.keyClick(editor.name, Qt.Key.Key_Escape)
    _settle()
    assert _data(store, pid) == before
    assert win.dictionary.open_editor() is None
    assert win.dictionary.add_item("executor").text() == "+ Add executor"


def test_refusal_red_line_input_stays_open(win, store):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, "executor")
    _type_enter(editor, "Clerk")
    page = win.dictionary
    assert _data(store, pid) == before
    assert "Clerk" in page.refusal_line()
    assert not page._refusals[page.executors][0].isHidden()
    assert page.open_editor() is editor
    assert editor.name.text() == "Clerk"


def test_axis_without_first_value_refused(win, store):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, "axis", ("Order",))
    _type_enter(editor, "seal")
    assert _data(store, pid) == before
    assert "first value" in win.dictionary.refusal_line()
    assert win.dictionary.open_editor() is editor


def test_parameter_input_lists_executors_when_variants_exist(win, store):
    pid = win.current_id
    before = _data(store, pid)
    editor = _open(win, "variant_param")
    items = [editor.executor.itemText(i) for i in range(editor.executor.count())]
    assert items == before["executors"]
    editor.executor.setCurrentText("Robot")
    _type_enter(editor, "Checker")
    expected = edit.add_word(before, "variant_param", "Checker", executor="Robot")[0]
    assert _data(store, pid) == expected


def test_new_word_on_second_tab_not_set(win):
    _type_enter(_open(win, "executor"), "Porter")
    _type_enter(_open(win, "scope"), "Per pallet")
    assert win.norm.is_missing("executor_coefficients", "Porter")
    assert win.norm.is_missing("scope_coefficients", "Per pallet")
    t = win.norm.number_table("executor_coefficients")
    assert t.item(t.row_of("Porter"), 1).text() == "not set"


def test_scroll_place_kept_after_add(win):
    page = win.dictionary
    bar = page.verticalScrollBar()
    assert bar.maximum() > 0
    place = bar.maximum() // 2
    bar.setValue(place)
    _settle()
    _type_enter(_open(win, "instrument"), "Knife")
    _settle()
    assert bar.value() == place


def test_add_entity_row_shown_when_last_entity_collapsed(win):
    page = win.dictionary
    page.toggle_entity("Spare entity")
    it = page.add_item("entity")
    assert not page.entities.isRowHidden(it.row())
    assert page.entities.isRowHidden(page.add_item("axis", ("Spare entity",)).row())


# ---------- order ----------

ORDERED = [
    ("entity", ["Order", "Box", "Spare entity"], lambda n: n),
    ("axis", ["status", "label", "wrap", "Spare axis"], lambda n: ("Order", n)),
    ("value", ["new", "packed", "sent", "Spare value"], lambda n: ("Order", "status", n)),
    ("kind", ["Make box", "Pack", "Send", "Check label", "Wrap", "Inspect", "Spare kind"],
     lambda n: n),
    ("executor", ["Clerk", "Robot", "Spare executor"], lambda n: n),
    ("instrument", ["Hands", "Tape", "Spare instrument"], lambda n: n),
    ("scope", ["Each", "Batch", "Spare scope"], lambda n: n),
    ("variant_param", ["Packer", "Sender"], lambda n: n),
    ("named_slice", ["Ready", "Done", "Spare slice"], lambda n: n),
]


@pytest.mark.parametrize("what, names, key", ORDERED)
def test_edge_arrows_disabled_not_hidden(win, what, names, key):
    page = win.dictionary
    for i, n in enumerate(names):
        up = page.move_button(what, key(n), -1)
        down = page.move_button(what, key(n), 1)
        assert up.text() == "↑" and down.text() == "↓"
        assert up.toolTip() == "Move up" and down.toolTip() == "Move down"
        assert not up.isHidden() and not down.isHidden()
        assert up.isEnabled() == (i > 0)
        assert down.isEnabled() == (i < len(names) - 1)


@pytest.mark.parametrize("what, names, key", ORDERED)
def test_arrow_moves_word(win, store, what, names, key):
    pid = win.current_id
    before = _data(store, pid)
    page = win.dictionary
    page.move_button(what, key(names[0]), 1).click()
    _settle()
    expected, remarks = edit.move_word(before, what, key(names[0]), 1)
    assert remarks == []
    assert _data(store, pid) == expected
    assert not page.move_button(what, key(names[1]), -1).isEnabled()
    assert page.move_button(what, key(names[0]), -1).isEnabled()


def test_scroll_place_kept_after_move(win):
    page = win.dictionary
    bar = page.verticalScrollBar()
    place = bar.maximum() // 2
    bar.setValue(place)
    _settle()
    page.move_button("scope", "Each", 1).click()
    _settle()
    assert bar.value() == place


# ---------- existence axis and batch scope ----------

def test_row_above_tables(win):
    page = win.dictionary
    texts = [w.text() for w in page.special.findChildren(QLabel)]
    assert texts == ["Existence axis:", "absent value:", "Batch scope:"]
    assert page.existence_name.text() == "presence"
    assert page.absent_value.text() == "none"
    items = [page.batch_box.itemText(i) for i in range(page.batch_box.count())]
    assert items == ["Each", "Batch", "Spare scope"]
    assert page.batch_box.currentText() == "Batch"
    assert page.special.geometry().bottom() < page.entities.geometry().top()


def test_batch_scope_row_tagged_without_remove(win):
    page = win.dictionary
    assert page.remove_button("scope", "Batch") is None
    assert page.remove_button("scope", "Each") is not None
    assert page.scope_tag("Batch") == "batch scope"
    assert page.scope_tag("Each") == ""


def test_choose_batch_scope(win, store):
    pid = win.current_id
    before = _data(store, pid)
    page = win.dictionary
    page.batch_box.setCurrentText("Each")
    page.batch_box.activated.emit(page.batch_box.currentIndex())
    _settle()
    assert _data(store, pid) == edit.set_batch_scope(before, "Each")[0]
    assert page.scope_tag("Each") == "batch scope"
    assert page.remove_button("scope", "Each") is None
    assert page.remove_button("scope", "Batch") is not None


def test_set_existence_axis_by_enter(win, store):
    pid = win.current_id
    before = _data(store, pid)
    page = win.dictionary
    page.existence_name.setFocus()
    page.existence_name.selectAll()
    QTest.keyClicks(page.existence_name, "exists")
    QTest.keyClick(page.existence_name, Qt.Key.Key_Return)
    _settle()
    assert _data(store, pid) == edit.set_existence_axis(before, "exists", "none")[0]
    assert page.word_item("axis", ("Box", "exists")) is not None


def test_set_absent_value_by_enter(win, store):
    pid = win.current_id
    before = _data(store, pid)
    page = win.dictionary
    page.absent_value.setFocus()
    page.absent_value.selectAll()
    QTest.keyClicks(page.absent_value, "gone")
    QTest.keyClick(page.absent_value, Qt.Key.Key_Return)
    _settle()
    assert _data(store, pid) == edit.set_existence_axis(before, "presence", "gone")[0]


def test_existence_refusal_red_line(win, store):
    pid = win.current_id
    before = _data(store, pid)
    page = win.dictionary
    page.existence_name.setFocus()
    page.existence_name.selectAll()
    QTest.keyClick(page.existence_name, Qt.Key.Key_Delete)
    QTest.keyClick(page.existence_name, Qt.Key.Key_Return)
    _settle()
    assert _data(store, pid) == before
    assert "not empty" in page.refusal_line()
    assert page.existence_name.text() == ""


# ---------- new empty project ----------

def test_empty_project_shows_add_rows_only(empty):
    page = empty.dictionary
    for what in ("entity", "executor", "instrument", "variant_param"):
        t = page.add_item(what).tableWidget()
        assert t.rowCount() == 1
    assert page.existence_name.text() == "exists"
    assert page.absent_value.text() == "no"
    assert page.batch_box.currentText() == "batch"


def test_empty_project_single_scope(empty):
    page = empty.dictionary
    assert page.remove_button("scope", "batch") is None
    assert page.scope_tag("batch") == "batch scope"
    assert not page.move_button("scope", "batch", -1).isEnabled()
    assert not page.move_button("scope", "batch", 1).isEnabled()


def test_empty_project_add_entity_then_axis(empty, store):
    pid = empty.current_id
    _type_enter(_open(empty, "entity"), "Shed")
    _type_enter(_open(empty, "axis", ("Shed",)), "door", "shut")
    data = _data(store, pid)
    assert data["entities"] == [{"name": "Shed", "axes": [{"name": "door", "values": ["shut"]}]}]
    assert empty.dictionary.add_item("value", ("Shed", "door")) is not None
