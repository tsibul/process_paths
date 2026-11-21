"""Test of the width of the title column of the comparison table under every language.

The title column takes its width from the titles, the header being the least; the wider labels
of another language never squeeze it below its content. A spare width of the window still
goes to the titles.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from measure_twice import i18n
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.comparison import PAD_X, _head_font

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
LONG_TITLE = "Стирка с проверкой карманов и сушкой на балконе"  # made up, longer than the others
WIDTH = 1000  # a window narrow enough to squeeze the column under the Greek labels


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=["en", "ru", "el"])
def lang(request, app, tmp_path):
    """The window language, from `.qm` files built into a temporary folder."""
    if request.param != "en":
        if i18n._lrelease() is None:
            pytest.skip("pyside6-lrelease is not installed")
        assert i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, request.param, tmp_path)
    yield request.param
    i18n.apply_language(app, i18n.SOURCE, tmp_path)


@pytest.fixture
def win(lang, app, tmp_path):
    data = json.loads(LAUNDRY.read_text(encoding="utf-8"))
    data["variants"][2]["title"] = LONG_TITLE
    path = tmp_path / "long_title.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    w = MainWindow(store, settings)
    w.resize(WIDTH, 800)
    assert w.load_path(path)
    w.show()
    w.tabs.setCurrentWidget(w.comparison)
    app.processEvents()
    yield w
    w.close()
    store.close()


def _titles(tree) -> list[str]:
    return [line for it in tree.visible_items() for line in it.text(1).split("\n") if line]


def test_title_column_fits_the_titles(win, lang):
    tree = win.comparison.tree
    fm = QFontMetrics(tree.font())
    titles = _titles(tree)
    assert LONG_TITLE in titles
    widest = max(fm.horizontalAdvance(t) for t in titles)
    assert tree.columnWidth(1) >= widest + 2 * PAD_X, (lang, tree.columnWidth(1), widest)


def test_title_column_fits_its_header(win, lang):
    tree = win.comparison.tree
    head = QFontMetrics(_head_font()).horizontalAdvance(tree.headerItem().text(1))
    assert tree.columnWidth(1) >= head + 2 * PAD_X


def test_spare_width_goes_to_the_titles(win, lang, app):
    tree = win.comparison.tree
    win.resize(WIDTH + 600, 800)
    app.processEvents()
    total = sum(tree.columnWidth(c) for c in range(tree.columnCount()))
    assert total >= tree.viewport().width()


@pytest.fixture
def greek_win(app, tmp_path):
    """The window in Greek, 1000 px wide: the columns are wider than the viewport."""
    if i18n._lrelease() is None:
        pytest.skip("pyside6-lrelease is not installed")
    assert i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, "el", tmp_path)
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    w = MainWindow(store, settings)
    w.resize(WIDTH, 800)
    assert w.load_path(LAUNDRY)
    w.show()
    w.tabs.setCurrentWidget(w.comparison)
    app.processEvents()
    yield w
    w.close()
    store.close()
    i18n.apply_language(app, i18n.SOURCE, tmp_path)


def test_compare_button_stays_in_view_when_scrolled(greek_win, app):
    tree = greek_win.comparison.tree
    bar = tree.horizontalScrollBar()
    assert bar.maximum() > 0  # the case of the side effect: the table scrolls sideways
    heads = [h for h in greek_win.comparison.group_headers() if h.compare is not None]
    assert heads
    view = tree.viewport()
    for value in (0, bar.maximum() // 2, bar.maximum()):
        bar.setValue(value)
        app.processEvents()
        for head in heads:
            button = head.compare
            rect = QRect(button.mapTo(view, QPoint(0, 0)), button.size())
            assert view.rect().contains(rect), (value, rect, view.rect())
            assert button.isVisible() and button.isEnabled()
            assert view.childAt(rect.center()) is button
            clicks = []
            button.clicked.connect(lambda _=False: clicks.append(1))
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            app.processEvents()
            assert clicks, value
            assert greek_win.comparison.steps_view is not None  # the click opened the steps
            greek_win.comparison.close_steps()
            app.processEvents()


LONG_TASK = (  # made up, wider than a narrow window
    "Постирать, высушить, погладить и разложить по полкам бельё всей большой семьи за неделю"
)


@pytest.fixture(params=[(900, False), (760, False), (760, True)])
def narrow_win(request, lang, app, tmp_path):
    """The window at a narrow width, in each language; with a long task name too."""
    width, long_task = request.param
    path = LAUNDRY
    if long_task:
        data = json.loads(LAUNDRY.read_text(encoding="utf-8"))
        for v in data["variants"]:
            v["task"] = LONG_TASK
        path = tmp_path / "long_task.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    w = MainWindow(store, settings)
    w.resize(width, 800)
    assert w.load_path(path)
    w.show()
    w.tabs.setCurrentWidget(w.comparison)
    app.processEvents()
    yield w, width
    w.close()
    store.close()


def test_compare_button_fits_a_narrow_window(narrow_win, lang):
    win, width = narrow_win
    tree = win.comparison.tree
    view = tree.viewport()
    heads = [h for h in win.comparison.group_headers() if h.compare is not None]
    assert heads
    for head in heads:
        button = head.compare
        rect = QRect(button.mapTo(view, QPoint(0, 0)), button.size())
        assert view.rect().contains(rect), (lang, width, rect, view.rect())
        shown = QRect(button.mapTo(win, QPoint(0, 0)), button.size())
        assert win.rect().contains(shown), (lang, width, shown, win.rect())
        assert button.width() >= button.sizeHint().width(), (lang, width, button.width())
        if LONG_TASK in head.title.text():
            assert head.title.toolTip() == head.title.text()  # cut, the whole name on hover
