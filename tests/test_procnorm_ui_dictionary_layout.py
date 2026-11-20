"""The row buttons of the dictionary tables keep to their column: the entity name stays seen.

A table refilled before its first layout (the window shown, then the project refreshed) left the
replaced row widgets on the viewport at its top left corner, over the first name. A long name is
cut with an ellipsis, its tooltip holds the full name.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QWidget

from measure_twice import edit
from measure_twice.example import add_example
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.pages import CELL_PAD, WORD, WordTable

LONG = "Kitchen tap with a ceramic cartridge and a long swivel spout over the double sink"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    yield s
    s.close()


def _window(store, long_name: bool = False) -> MainWindow:
    """The example on the Dictionary tab, refreshed after ``show`` before any layout."""
    pid = add_example(store, "en")
    if long_name:
        data = store.get(pid).data
        first = data["entities"][0]["name"]
        data, remarks = edit.rename(data, "entity", first, LONG)
        assert data is not None, remarks
        store.save(pid, data)
    w = MainWindow(store)
    w.resize(1100, 780)
    w.show()
    w.refresh(pid)
    QApplication.processEvents()
    w.tabs.setCurrentWidget(w.dictionary)
    QApplication.processEvents()
    return w


def _text_rect(t, r: int, c: int) -> QRect:
    """The part of a cell its text is drawn in: the cell less its padding, no wider than the
    text."""
    cell = t.visualRect(t.model().index(r, c))
    room = cell.adjusted(CELL_PAD, 0, -CELL_PAD, 0)
    width = t.fontMetrics().horizontalAdvance(t.item(r, c).text())
    room.setWidth(min(room.width(), width))
    return room


def _shown(t) -> list[QWidget]:
    return [w for w in t.viewport().children()
            if isinstance(w, QWidget) and w.isVisible()]


def test_first_row_buttons_keep_to_their_column(app, store):
    w = _window(store)
    try:
        t = w.dictionary.entities
        last = t.columnCount() - 1
        own = {t.cellWidget(r, last) for r in range(t.rowCount())} - {None}
        name = _text_rect(t, 0, 0)
        assert t.item(0, 0).text().endswith(t.item(0, 0).data(WORD)[1])
        box = t.cellWidget(0, last)
        assert box.geometry().left() >= t.columnViewportPosition(last)
        for widget in _shown(t):
            assert widget in own, widget.geometry()
            assert not widget.geometry().intersects(name), widget.geometry()
    finally:
        w.close()


def test_word_tables_hold_only_their_row_widgets(app, store):
    w = _window(store)
    try:
        for t in w.dictionary.findChildren(WordTable):
            own = {t.cellWidget(r, c)
                   for r in range(t.rowCount()) for c in range(t.columnCount())} - {None}
            for widget in _shown(t):
                assert widget in own, (t.horizontalHeaderItem(0).text(), widget.geometry())
    finally:
        w.close()


def test_long_name_is_elided_with_full_tooltip(app, store):
    w = _window(store, long_name=True)
    try:
        t = w.dictionary.entities
        it = w.dictionary.word_item("entity", LONG)
        assert it is not None
        r = it.row()
        assert t.textElideMode() == Qt.TextElideMode.ElideRight
        assert t.columnWidth(0) < t.fontMetrics().horizontalAdvance(it.text())
        assert LONG in it.toolTip()
        name = _text_rect(t, r, 0)
        last = t.columnCount() - 1
        buttons = [b for b in t.cellWidget(r, last).findChildren(QWidget) if b.isVisible()]
        assert buttons
        for b in buttons:
            rect = QRect(b.mapTo(t.viewport(), b.rect().topLeft()), b.size())
            assert not rect.intersects(name), (rect, name)
    finally:
        w.close()


def test_short_name_keeps_the_rename_tooltip(app, store):
    w = _window(store)
    try:
        it = w.dictionary.entities.item(0, 0)
        assert it.toolTip() == "Double-click to rename"
    finally:
        w.close()
