"""Test of two layout faults: the side filter under the load banner, a checked button's width.

The banner of a load sits between the tab bar and the pages and pushes the pages down; the tab
widget lays its pages out again on its own (a new tab icon, a style change), and the pages must
stay under the banner. A checked button is drawn in bold; it must be wide enough for that text.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication

from measure_twice.calc import compare, groups
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
PADDING = 2 * 10 + 2  # QPushButton#small: 10px padding and a 1px border on each side


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    store = Store(tmp_path / "t.db")
    w = MainWindow(store)
    w.show()
    assert w.load_path(LAUNDRY)
    yield w
    w.close()
    store.close()


def settle(app) -> None:
    for _ in range(3):
        app.sendPostedEvents()
        app.processEvents()


def top_in_window(widget, win) -> int:
    return widget.mapTo(win, QPoint(0, 0)).y()


def check_under_banner(win) -> None:
    strip = win.tabs.strip
    assert win.offer_visible()
    banner_bottom = top_in_window(strip, win) + strip.height()
    page = win.comparison
    assert top_in_window(page.viewport(), win) >= banner_bottom
    for b in page.side_buttons.buttons():
        assert b.isVisible()
        assert top_in_window(b, win) >= banner_bottom


def test_side_filter_under_banner(app, win):
    settle(app)
    check_under_banner(win)


def test_side_filter_under_banner_after_relayout(app, win):
    win.tabs.setTabIcon(0, win.tabs.tabIcon(3))
    settle(app)
    check_under_banner(win)
    QApplication.sendEvent(win.tabs, QEvent(QEvent.Type.StyleChange))
    settle(app)
    check_under_banner(win)


def test_checked_compare_button_fits_bold_text(app, win):
    c = win.comparison
    group = next(g for g in groups(compare(c._project)) if g.kind == "task")
    c.open_steps(group)
    settle(app)
    button = next(b for b in c.steps_view.findChildren(type(c.steps_view.back))
                  if b.isCheckable())
    assert button.isChecked()
    bold = QFont(button.font())
    bold.setWeight(QFont.Weight.DemiBold)
    need = QFontMetrics(bold).horizontalAdvance(button.text()) + PADDING
    assert button.sizeHint().width() >= need
    assert button.width() >= need


def test_side_buttons_fit_bold_text(app, win):
    settle(app)
    for b in win.comparison.side_buttons.buttons():
        bold = QFont(b.font())
        bold.setWeight(QFont.Weight.DemiBold)
        assert b.sizeHint().width() >= QFontMetrics(bold).horizontalAdvance(b.text())
