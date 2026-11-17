"""Tests of renaming and deleting dictionary words on the Dictionary tab."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from procnorm import edit
from procnorm.store import Store
from procnorm.ui.app import MainWindow
from tests.test_procnorm_edit_delete import with_spares

NOTE = "To add words, load a new file."

# Every sort of word, by a name the made-up project has (see tests.test_procnorm_edit_rename).
WORDS = [
    ("entity", "Box"),
    ("axis", ("Order", "label")),
    ("value", ("Order", "status", "packed")),
    ("kind", "Pack"),
    ("executor", "Clerk"),
    ("instrument", "Tape"),
    ("scope", "Each"),
    ("variant_param", "Packer"),
    ("named_slice", "Ready"),
]


def _project() -> dict:
    """The made-up project with spare words and two more copies of V3, so that the scope
    ``Each`` is used in more than ten places."""
    d = with_spares()
    for _ in range(2):
        d, _r = edit.copy_variant(d, d["variants"][-1]["code"])
    return d


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    return tmp_path / "t.db"


@pytest.fixture
def store(db):
    s = Store(db)
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    f = tmp_path / "shipping.json"
    f.write_text(json.dumps(_project(), default=float, ensure_ascii=False), encoding="utf-8")
    w = MainWindow(store)
    assert w.load_path(f)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.dictionary)
    QApplication.processEvents()
    yield w
    w.close()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


def _rename(w, what, old, text):
    """Double-click editor of a word's cell: type, then Enter."""
    page = w.dictionary
    it = page.word_item(what, old)
    t = it.tableWidget()
    t.setCurrentItem(it)
    t.editItem(it)
    QApplication.processEvents()
    editor = t.viewport().findChild(QLineEdit)
    assert editor is not None
    assert editor.text() == it.text()
    editor.selectAll()
    editor.setText(text)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    _settle()


def _remove(w, what, old):
    b = w.dictionary.remove_button(what, old)
    assert b.isEnabled() and b.text() == "✕"
    b.click()
    _settle()


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _numbers(w):
    """Comparison cells by code and column position (column names hold executor names)."""
    c = w.comparison
    return {code: [c.cell(code, h) for h in c.headers()[3:]] for code in c.codes()}


@pytest.fixture
def no_confirm(win, monkeypatch):
    def fail(text):
        raise AssertionError(f"asked: {text}")
    monkeypatch.setattr(win, "confirm", fail)


# ---------- the tab ----------

def test_grey_line_about_adding_words(win):
    note = win.dictionary.add_note
    assert note.text() == NOTE and not note.isHidden()
    assert note.objectName() == "note"


@pytest.mark.parametrize("what, old", WORDS)
def test_every_word_has_editable_cell_and_remove_button(win, what, old):
    page = win.dictionary
    it = page.word_item(what, old)
    assert it.text() == (old[-1] if isinstance(old, tuple) else old)
    assert it.flags() & Qt.ItemFlag.ItemIsEditable
    assert page.remove_button(what, old).text() == "✕"


def test_other_cells_not_editable(win):
    t = win.dictionary.kinds
    for r in range(t.rowCount()):
        for c in range(1, t.columnCount()):
            it = t.item(r, c)
            assert it is None or not it.flags() & Qt.ItemFlag.ItemIsEditable


# ---------- rename ----------

@pytest.mark.parametrize("what, old", WORDS)
def test_rename_every_sort_changes_database(win, store, what, old):
    pid = win.current_id
    before = _data(store, pid)
    _rename(win, what, old, "Zed")
    expected, _ = edit.rename(before, what, old, "Zed")
    assert _data(store, pid) == expected
    new = old[:-1] + ("Zed",) if isinstance(old, tuple) else "Zed"
    assert win.dictionary.word_item(what, new).text() == "Zed"


def test_renamed_kind_shown_on_all_tabs_numbers_unchanged(win):
    before = _numbers(win)
    _rename(win, "kind", "Pack", "Put in")
    assert "Put in" in win.dictionary.all_text()
    assert "Put in" in win.norm.all_text()
    win.chains.select_path("V1")
    assert "Put in" in win.chains.all_text()
    for page in (win.dictionary, win.norm, win.chains):
        assert "Pack" not in page.all_text().split("\n")
    assert _numbers(win) == before


def test_renamed_executor_in_comparison_headers_numbers_unchanged(win):
    before = _numbers(win)
    _rename(win, "executor", "Clerk", "Worker")
    heads = win.comparison.headers()
    assert "Labour · Worker" in heads and "Labour · Clerk" not in heads
    assert _numbers(win) == before


def test_rename_refused_shows_red_line_and_keeps_database(win, store):
    pid = win.current_id
    before = _data(store, pid)
    _rename(win, "executor", "Clerk", "Robot")
    assert _data(store, pid) == before
    line = win.dictionary.refusal_text()
    assert line and "Robot" in line
    assert win.dictionary.word_item("executor", "Clerk").text() == "Clerk"


def test_unchanged_name_writes_nothing(win, store, monkeypatch):
    called = []
    monkeypatch.setattr(store, "save", lambda *a: called.append(a))
    _rename(win, "kind", "Pack", "Pack")
    assert called == []


def test_renamed_name_kept_after_restart(app, win, db):
    _rename(win, "instrument", "Tape", "Glue")
    win.close()
    with Store(db) as again:
        w2 = MainWindow(again)
        assert w2.dictionary.word_item("instrument", "Glue").text() == "Glue"
        assert w2.dictionary.word_item("instrument", "Tape") is None
        w2.close()


# ---------- delete ----------

def test_unused_word_deleted_without_confirmation(win, store, no_confirm):
    pid = win.current_id
    before = _data(store, pid)
    _remove(win, "executor", "Spare executor")
    expected, _ = edit.delete(before, "executor", "Spare executor")
    assert _data(store, pid) == expected
    assert win.dictionary.word_item("executor", "Spare executor") is None
    assert win.dictionary.refusal_text() == ""


@pytest.mark.parametrize("what, old", [("entity", "Spare entity"), ("axis", ("Order", "Spare axis")),
                                       ("value", ("Order", "status", "Spare value")),
                                       ("named_slice", "Spare slice"), ("kind", "Spare kind")])
def test_unused_structure_words_deleted(win, store, no_confirm, what, old):
    pid = win.current_id
    before = _data(store, pid)
    _remove(win, what, old)
    assert _data(store, pid) == edit.delete(before, what, old)[0]
    assert win.dictionary.word_item(what, old) is None


def test_used_word_refused_with_every_place(win, store, no_confirm):
    pid = win.current_id
    before = _data(store, pid)
    _remove(win, "kind", "Wrap")
    assert _data(store, pid) == before
    page = win.dictionary
    assert page.refusal_line() == "Wrap is used and cannot be deleted:"
    assert page.refusal_places() == ["variant V1, call 1"]
    assert page.word_item("kind", "Wrap") is not None


def test_long_list_of_places_cut_at_ten(win, store, no_confirm):
    data = _data(store, win.current_id)
    places = edit.usages(data, "scope", "Each")
    assert len(places) > 10
    _remove(win, "scope", "Each")
    page = win.dictionary
    assert page.refusal_line() == "Each is used and cannot be deleted:"
    assert page.refusal_places() == places[:10] + [f"and {len(places) - 10} more"]


def test_refusal_goes_after_next_edit(win, no_confirm):
    _remove(win, "kind", "Wrap")
    assert win.dictionary.refusal_text()
    _rename(win, "instrument", "Tape", "Glue")
    assert win.dictionary.refusal_text() == ""
