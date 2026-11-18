"""Tests of editing the normalization numbers on the second tab and of the recalculation after it."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csv
import io
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from measure_twice.cli import main as cli
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.comparison import SIDES

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
WASH = "Постирать"  # cost 1, every variant uses it
NOTE = "Changes are saved at once. To keep the old numbers, copy the project."


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
def win(app, store):
    w = MainWindow(store)
    assert w.load_path(LAUNDRY)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.norm)
    QApplication.processEvents()
    yield w
    w.close()


def _type(w, table: str, key, text: str, key_press=Qt.Key.Key_Return) -> None:
    """Open the editor of a number cell, type, then Enter (or another key that leaves the cell)."""
    t = w.norm.number_table(table)
    it = w.norm.number_item(table, key)
    t.setCurrentItem(it)
    t.editItem(it)
    QApplication.processEvents()
    editor = t.viewport().findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    editor.setText(text)
    QTest.keyClick(editor, key_press)
    for _ in range(3):
        QApplication.processEvents()


def _stored_cost(store, pid, kind):
    return store.get(pid).norm.kind_costs.get(kind)


# ---------- the tab ----------

def test_only_number_column_is_editable(win):
    n = win.norm
    for table in ("kind_costs", "executor_coefficients", "scope_coefficients", "axis_skip_prices"):
        t = n.number_table(table)
        col = t.columnCount() - 1
        assert t.rowCount() > 0
        for r in range(t.rowCount()):
            for c in range(t.columnCount()):
                editable = bool(t.item(r, c).flags() & Qt.ItemFlag.ItemIsEditable)
                zero = table == "kind_costs" and t.item(r, 0).text() == "Дождаться высыхания"
                assert editable == (c == col and not zero), (table, r, c)


def test_zero_weight_kind_shows_zero_without_input(win):
    it = win.norm.number_item("kind_costs", "Дождаться высыхания")
    assert it.text() == "0"
    assert not it.flags() & Qt.ItemFlag.ItemIsEditable


def test_batch_and_uncounted_errors_not_editable(win):
    t = win.norm.errors
    assert all(not t.item(r, c).flags() & Qt.ItemFlag.ItemIsEditable
               for r in range(t.rowCount()) for c in range(t.columnCount()))


def test_saved_at_once_note(win):
    assert win.norm.saved_note.text() == NOTE
    assert not win.norm.saved_note.isHidden()


# ---------- accepted edit ----------

def test_typed_number_changes_database(win, store):
    pid = win.current_id
    _type(win, "kind_costs", WASH, "2,5")
    assert str(_stored_cost(store, pid, WASH)) == "2.5"
    assert win.norm.number_item("kind_costs", WASH).text() == "2.5"


def test_comparison_equals_cli_table_of_saved_file(win, tmp_path, capsys):
    _type(win, "kind_costs", WASH, "2,5")
    _type(win, "scope_coefficients", "вся загрузка", "0.2")
    f = tmp_path / "out.json"
    win.save_path(f)
    capsys.readouterr()
    assert cli(["table", str(f), "--csv"]) == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    got = {r[1]: dict(zip(rows[0], r)) for r in rows[1:]}
    c = win.comparison
    assert c.cell("А", "Labour · total") != "8.40"  # recalculated
    for code in c.codes():
        for h in c.headers()[3:]:
            assert got[code][h] == c.cell(code, h), (code, h)


def test_leaving_cell_commits(win, store):
    _type(win, "executor_coefficients", "Человек", "2", key_press=Qt.Key.Key_Tab)
    assert str(store.get(win.current_id).norm.executor_coefficients["Человек"]) == "2"


def test_number_kept_after_restart(app, win, db):
    _type(win, "axis_skip_prices", ("Бельё", "цвета"), "7.5")
    win.close()
    with Store(db) as again:
        w = MainWindow(again)
        try:
            assert w.norm.number_item("axis_skip_prices", ("Бельё", "цвета")).text() == "7.5"
        finally:
            w.close()


def test_accepted_edit_shows_no_offer(win):
    win.offer_later_button.click()  # the bar after Load
    win.tabs.setCurrentWidget(win.chains)  # takes the dot away
    win.tabs.setCurrentWidget(win.norm)
    _type(win, "kind_costs", WASH, "3")
    assert not win.offer_visible() and not win.chains_dot()


# ---------- refused edit ----------

@pytest.mark.parametrize("table,key,text", [
    ("kind_costs", WASH, "-1"),
    ("kind_costs", WASH, "abc"),
    ("axis_skip_prices", ("Бельё", "цвета"), "0"),
])
def test_refusal_keeps_cell_and_database(win, store, table, key, text):
    pid = win.current_id
    before = store.text(pid)
    old = win.norm.number_item(table, key).text()
    _type(win, table, key, text)
    assert store.text(pid) == before
    assert win.norm.number_item(table, key).text() == old
    line = win.norm.refusal(table)
    assert not line.isHidden() and line.text()
    for other in ("kind_costs", "executor_coefficients", "scope_coefficients", "axis_skip_prices"):
        if other != table:
            assert win.norm.refusal(other).isHidden()


def test_refusal_line_goes_on_next_accepted_edit(win):
    _type(win, "kind_costs", WASH, "-1")
    assert not win.norm.refusal("kind_costs").isHidden()
    _type(win, "scope_coefficients", "каждая вещь", "1.5")
    assert win.norm.refusal("kind_costs").isHidden()


# ---------- empty cell ----------

def test_empty_cell_marked_and_counted(win, store):
    pid = win.current_id
    assert win.norm.missing_label.isHidden()
    _type(win, "kind_costs", WASH, "")
    assert WASH not in store.get(pid).norm.kind_costs
    it = win.norm.number_item("kind_costs", WASH)
    assert it.text() == "not set"
    assert win.norm.is_missing("kind_costs", WASH)
    assert not win.norm.is_missing("kind_costs", "Развесить")
    assert win.norm.missing_label.text() == "1 number not set"
    assert not win.norm.missing_label.isHidden()
    assert win.comparison.cell("А", "Labour · total") == "not set"


def test_two_empty_cells_counted(win):
    _type(win, "kind_costs", WASH, "")
    _type(win, "executor_coefficients", "Машина", "")
    assert win.norm.missing_label.text() == "2 numbers not set"
    assert win.norm.is_missing("executor_coefficients", "Машина")


def test_editor_of_empty_cell_starts_empty(win):
    _type(win, "kind_costs", WASH, "")
    t = win.norm.number_table("kind_costs")
    it = win.norm.number_item("kind_costs", WASH)
    t.editItem(it)
    QApplication.processEvents()
    assert t.viewport().findChild(QLineEdit).text() == ""


def test_filling_empty_cell_clears_mark(win):
    _type(win, "kind_costs", WASH, "")
    _type(win, "kind_costs", WASH, "1")
    assert not win.norm.is_missing("kind_costs", WASH)
    assert win.norm.missing_label.isHidden()


# ---------- view kept ----------

def test_side_sort_and_path_kept(win):
    c = win.comparison
    c.set_side("other")
    c.sort("Labour · total", Qt.SortOrder.DescendingOrder)
    assert c.codes() == ["В", "Б"]
    c.toggle("Б")
    win.chains.select_path("Б")
    win.norm.select_variant("В")
    _type(win, "kind_costs", "Развесить", "10")  # only В hangs out: it stays the larger
    _type(win, "kind_costs", "Убрать в шкаф", "0")
    assert c.codes() == ["В", "Б"]
    col = c.headers().index("Labour · total")
    assert c.tree.header().sortIndicatorSection() == col
    assert c.tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert c.open_codes() == ["Б"]
    assert [k for b, (k, _) in zip(c.side_buttons.buttons(), SIDES) if b.isChecked()] == ["other"]
    assert win.chains.current_code() == "Б"
    rows = win.norm.variants.selectionModel().selectedRows()
    assert rows and win.norm.variants.item(rows[0].row(), 0).text() == "В"


def test_sort_follows_new_numbers(win):
    c = win.comparison
    c.sort("Labour · total", Qt.SortOrder.AscendingOrder)
    assert c.codes() == ["А", "Б", "В"]  # ours above theirs
    _type(win, "kind_costs", "Запустить машину", "40")  # 4 → 40 on the whole load: +3.60 for every one
    assert [c.cell(x, "Labour · total") for x in c.codes()] == ["12.00", "7.00", "9.00"]
    assert c.tree.header().sortIndicatorSection() == c.headers().index("Labour · total")
