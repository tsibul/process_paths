"""Tests of `Copy table` and `Copy chart` on the Comparison tab (piece 24)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.line_charts import ChartView

EXAMPLE = Path(__file__).parent / "data" / "laundry.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store):
    w = MainWindow(store)
    assert w.load_path(EXAMPLE)
    w.show()
    QApplication.processEvents()
    QApplication.clipboard().clear()
    yield w
    w.close()


def _views(page):
    return [v for pair in page.chart_pairs() for v in pair.charts.findChildren(ChartView)
            if not v.isHidden()]


def test_copy_table_button_next_to_exports(win):
    b = win.comparison.copy_table_button
    assert b.text() == "Copy table"
    assert b.parent() is win.comparison.export_bar
    assert b.isEnabled()


def test_copy_table_puts_text_and_html(win):
    page = win.comparison
    page.copy_table_button.click()
    data = QApplication.clipboard().mimeData()
    assert data.hasText()
    assert data.hasHtml()
    lines = data.text().split("\n")
    rows = [line.split("\t") for line in lines]
    assert len({len(r) for r in rows}) == 1
    assert rows[0][1:5] == ["Code", "Title", "Side", "Steps"]
    assert "Labour · total" in rows[0]
    assert [r[1] for r in rows[1:]] == page.codes()
    col = rows[0].index("Labour · total")
    for r in rows[1:]:
        assert r[col] == page.cell(r[1], "Labour · total")
    html = data.html()
    assert "<table" in html
    assert "Labour · total" in html
    assert html.count("<tr") == len(rows)


def test_copy_table_follows_side_filter(win):
    page = win.comparison
    page.set_side("own")
    page.copy_table_button.click()
    rows = QApplication.clipboard().text().split("\n")
    assert [r.split("\t")[1] for r in rows[1:]] == page.codes()


def test_copy_table_says_so_in_status_bar(win):
    win.comparison.copy_table_button.click()
    assert win.statusBar().currentMessage() == "Copied table"


def test_copy_table_disabled_without_project(win):
    win.comparison.show_project(None)
    assert not win.comparison.copy_table_button.isEnabled()


def test_each_chart_has_its_button_in_the_top_right_corner(win):
    views = _views(win.comparison)
    assert len(views) >= 2
    for v in views:
        b = v.copy_button
        assert b.text() == "Copy chart"
        assert b.parent() is v
        assert b.isEnabled()
        assert b.geometry().right() <= v.width()
        assert b.geometry().top() < v.height() // 4
        assert b.geometry().center().x() > v.width() // 2


def test_copy_chart_puts_image(win):
    views = _views(win.comparison)
    views[0].copy_button.click()
    clip = QApplication.clipboard()
    assert not clip.image().isNull()
    assert clip.image().width() > 0
    assert clip.image().height() > 0
    assert win.statusBar().currentMessage() == "Copied chart"


def test_copy_chart_disabled_without_lines(win):
    page = win.comparison
    page.show_project(None)
    assert page.chart_pairs() == []
    from measure_twice.ui.line_charts import LineCharts

    empty = LineCharts()
    for v in empty.findChildren(ChartView):
        assert not v.copy_button.isEnabled()
