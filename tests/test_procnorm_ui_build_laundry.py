"""End-to-end test of piece 13 in the window: the dictionary of the example file
tests/data/laundry.json is typed into a new empty project only by actions of the window, and the
exported project text has the same dictionary."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from procnorm.store import Store
from procnorm.ui.app import MainWindow

LAUNDRY = json.loads(
    (Path(__file__).parent / "data" / "laundry.json").read_text(encoding="utf-8"))

DICTIONARY_PARTS = ("existence_axis", "entities", "kinds", "executors", "instruments", "scopes",
                    "batch_scope", "variant_params", "named_slices")

LISTS = (("executor", "executors"), ("instrument", "instruments"), ("scope", "scopes"))


def _dictionary(data):
    return {part: data.get(part) for part in DICTIONARY_PARTS}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, monkeypatch):
    w = MainWindow(store)
    w.resize(1200, 900)
    w.show()
    monkeypatch.setattr(w, "ask_name", lambda text: LAUNDRY["name"])
    monkeypatch.setattr(w, "confirm", lambda text: True)
    yield w
    w.close()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _click(item):
    t = item.tableWidget()
    rect = t.visualItemRect(item)
    QTest.mouseClick(t.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    _settle()


def _type(field, text):
    """Put text into a field as a paste does: QTest types only Latin keys."""
    field.setFocus()
    field.insert(text)


def _no_refusal(w):
    assert w.dictionary.refusal_text() == ""


def _add_word(w, what, owner, name, first=None):
    """Click the add row of a list, type the name (and the first value), press Enter."""
    page = w.dictionary
    it = page.add_item(what, owner)
    assert it is not None, (what, owner)
    _click(it)
    editor = page.open_editor()
    assert editor is not None
    _type(editor.name, name)
    if first is not None:
        _type(editor.first, first)
    QTest.keyClick(editor.name, Qt.Key.Key_Return)
    _settle()
    _no_refusal(w)


def _type_over(field, text):
    field.setFocus()
    field.selectAll()
    _type(field, text)
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle()


def _set_existence_axis(w):
    page = w.dictionary
    axis = LAUNDRY["existence_axis"]
    _type_over(page.existence_name, axis["name"])
    _no_refusal(w)
    _type_over(page.absent_value, axis["absent"])
    _no_refusal(w)


def _set_batch_scope(w):
    box = w.dictionary.batch_box
    box.setCurrentText(LAUNDRY["batch_scope"])
    box.activated.emit(box.currentIndex())
    _settle()
    _no_refusal(w)


def _add_kind(w, kind):
    page = w.dictionary
    _click(page.add_item("kind"))
    form = page.kind_form()
    assert form is not None
    _type(form.name, kind["name"])
    form.entity.setCurrentText(kind["entity"])
    form.axis.setCurrentText(kind["axis"])
    form.source.setCurrentText(kind["from"])
    form.target.setCurrentText(kind["to"])
    for entity, axis, value in kind.get("requires", []):
        form.add_condition.click()
        _settle()
        row = form.conditions()[-1]
        row.entity.setCurrentText(entity)
        row.axis.setCurrentText(axis)
        row.value.setCurrentText(value)
    form.check.setChecked(bool(kind.get("check")))
    form.zero_weight.setChecked(bool(kind.get("zero_weight")))
    if kind.get("zero_weight_note"):
        _type(form.note, kind["zero_weight_note"])
    form.submit_button.click()
    _settle()
    _no_refusal(w)
    assert page.kind_form() is None


def _add_slice(w, name, spec):
    page = w.dictionary
    _click(page.add_item("named_slice"))
    form = page.slice_form()
    assert form is not None
    _type(form.name, name)
    for g, group in enumerate(spec["any"]):
        if g > 0:
            form.add_group.click()
            _settle()
        box = form.group_boxes()[g]
        rows = group.get("states", []) + group.get("params", [])
        for r, cells in enumerate(rows):
            if r > 0:
                box.add_row.click()
                _settle()
            row = box.rows()[r]
            row.first.setCurrentText(cells[0])
            if len(cells) == 3:
                row.axis.setCurrentText(cells[1])
            row.value.setCurrentText(cells[-1])
    form.submit_button.click()
    _settle()
    _no_refusal(w)
    assert page.slice_form() is None


def test_dictionary_typed_in_window_equals_file(win, store):
    win.new_button.click()
    _settle()
    assert win.tabs.currentWidget() is win.dictionary
    _set_existence_axis(win)
    for entity in LAUNDRY["entities"]:
        _add_word(win, "entity", (), entity["name"])
        for axis in entity["axes"]:
            first, *others = axis["values"]
            _add_word(win, "axis", (entity["name"],), axis["name"], first)
            for value in others:
                _add_word(win, "value", (entity["name"], axis["name"]), value)
    for what, key in LISTS:
        for name in LAUNDRY[key]:
            _add_word(win, what, (), name)
    _set_batch_scope(win)
    # The empty project has the scope "batch"; the file has only its own scopes.
    win.dictionary.remove_button("scope", "batch").click()
    _settle()
    _no_refusal(win)
    for kind in LAUNDRY["kinds"]:
        _add_kind(win, kind)
    for name, spec in LAUNDRY["named_slices"].items():
        _add_slice(win, name, spec)
    exported = json.loads(store.text(win.current_id))
    assert _dictionary(exported) == _dictionary(LAUNDRY)
