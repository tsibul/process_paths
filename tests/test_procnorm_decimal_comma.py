"""Test of the decimal separator of the window language (procnorm-118).

Russian and Greek show a decimal comma: the comparison table, the cells of the normalization,
the charts, the labour scale, the steps of a way and the PDF report. English keeps the point.
The CSV keeps the point under every language; a typed number takes a point or a comma.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csv
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QGraphicsTextItem

from measure_twice import edit, export, i18n, report
from measure_twice.calc import compare, groups
from measure_twice.project import read_project
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.labour_scale import LabourScale
from measure_twice.ui.line_charts import LineCharts

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
COMMA = re.compile(r"-?\d+,\d+")
POINT = re.compile(r"-?\d+\.\d+")


def laundry() -> dict:
    return json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)


def project(change=None):
    d = laundry()
    if change is not None:
        change(d)
    found, remarks = read_project(d)
    assert found is not None, remarks
    return found


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=["ru", "el", "en"])
def lang(request, app, tmp_path):
    """The window language; without `.qm` the strings stay English, the locale is that language."""
    i18n.apply_language(app, request.param, tmp_path)
    yield request.param
    i18n.apply_language(app, "en", tmp_path)


def decimal(lang: str) -> re.Pattern:
    return POINT if lang == "en" else COMMA


def other(lang: str) -> re.Pattern:
    return COMMA if lang == "en" else POINT


@pytest.fixture
def win(lang, tmp_path):
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    w = MainWindow(store, settings)
    assert w.load_path(LAUNDRY)
    yield w
    w.close()
    store.close()


def check(texts: list[str], lang: str) -> None:
    """Some text has a decimal number, every one with the separator of the language."""
    assert any(decimal(lang).search(t) for t in texts), texts
    assert not any(other(lang).search(t) for t in texts), texts


def test_comparison_table(win, lang):
    c = win.comparison
    check([c.cell(code, h) for code in c.codes() for h in c.headers()], lang)


def test_copied_table(win, lang):
    win.comparison.copy_table()
    check([QApplication.clipboard().text()], lang)


def test_norm_cells(win, lang):
    item = win.norm.number_item("scope_coefficients", "вся загрузка")
    shown = "0.1" if lang == "en" else "0,1"
    assert item.text() == shown
    assert item.data(edit_role()) == shown  # the editor starts from the number as shown


def edit_role():
    from measure_twice.ui.pages import RAW
    return RAW


def test_steps_of_a_way(win, lang):
    c = win.comparison
    for code in c.codes():
        c.toggle(code)
    texts = [t for code in c.codes() for t in c.steps(code).texts()]
    check(texts, lang)


def test_compare_steps_view(win, lang):
    c = win.comparison
    group = next(g for g in groups(compare(c._project)) if g.kind == "task")
    c.open_steps(group)
    view = c.steps_view
    texts = [view.cell(n, code).labour.text() for code in view.codes()
             for n in range(1, view.step_count() + 1) if view.cell(n, code) is not None]
    check(texts, lang)


def small(d: dict) -> None:
    """Labour below 1 on every way: the ticks of the labour scale are fractions."""
    d["normalization"]["executor_coefficients"]["Человек"] = Decimal("0.05")
    d["normalization"]["executor_coefficients"]["Машина"] = Decimal("0.05")


def test_labour_scale(lang):
    p = project(small)
    rows = next(g for g in groups(compare(p)) if g.kind == "task").rows
    w = LabourScale(p, rows)
    try:
        texts = list(w.tick_texts())
        for r in w.rows():
            texts += list(r.end_text())
            texts += [s.text for s in r.segments] + [s.tip for s in r.segments]
        check(texts, lang)
    finally:
        w.close()


def test_chart_axis_labels(lang):
    p = project(small)
    rows = next(g for g in groups(compare(p)) if g.kind == "task").rows
    charts = LineCharts()
    try:
        charts.set_rows(p, rows)
        view = charts.labour
        view.resize(700, 400)
        view.grab()
        texts = [i.toPlainText() for i in view.scene().items() if isinstance(i, QGraphicsTextItem)]
        check(texts, lang)
        assert {"1", "2"} <= set(texts)  # the step axis keeps whole numbers
    finally:
        charts.close()


def test_report(lang):
    texts = [t.text for page in report.pages(project()) for t in page.texts]
    check(texts, lang)


def test_report_from_window(win, lang, tmp_path):
    path = tmp_path / "r.pdf"
    report.write(win.comparison._project, path)
    assert path.stat().st_size > 0


def test_markdown_follows_window(lang):
    check([export.markdown(project(), i18n.shown)], lang)


def test_csv_keeps_point(lang):
    rows = list(csv.reader(io.StringIO(export.csv_text(project(), i18n.shown))))
    cells = [c for r in rows[1:] for c in r]
    assert any(POINT.fullmatch(c) for c in cells)
    assert not any(COMMA.search(c) for c in cells), cells


def test_window_csv_keeps_point(win, tmp_path):
    win.comparison.export_path(tmp_path / "out.csv")
    text = (tmp_path / "out.csv").read_text(encoding="utf-8")
    cells = [c for r in list(csv.reader(io.StringIO(text)))[1:] for c in r]
    assert any(POINT.fullmatch(c) for c in cells)
    assert not any(COMMA.search(c) for c in cells), cells


def test_csv_waiting_keeps_point(lang):
    def waiting(d):
        kind = next(k for k in d["kinds"] if k["name"] == "Дождаться высыхания")
        kind["waiting"] = Decimal("1.5")
        kind["waiting_unit"] = "hours"
        d["normalization"]["kind_costs"].pop(kind["name"])
    rows = list(csv.reader(io.StringIO(export.csv_text(project(waiting), i18n.shown))))
    cells = [c for r in rows[1:] for c in r]
    assert any("1.5" in c for c in cells), cells
    assert not any(COMMA.search(c) for c in cells), cells


@pytest.mark.parametrize("typed", ["8,4", "8.4", " 8,4 "])
def test_typed_number(lang, typed):
    data, remarks = edit.set_number(laundry(), "kind_costs", "Постирать", typed)
    assert remarks == []
    assert data["normalization"]["kind_costs"]["Постирать"] == Decimal("8.4")


@pytest.mark.parametrize("typed", ["8,4", "8.4"])
def test_typed_number_in_window(win, typed):
    assert win.edit_number("kind_costs", "Постирать", typed)
    data = win.store.get(win.current_id).data
    assert data["normalization"]["kind_costs"]["Постирать"] == Decimal("8.4")


@pytest.mark.parametrize("typed", ["0,5", "0.5"])
def test_typed_waiting_weight(win, typed):
    assert win.edit_number("labour_per_waiting_hour", None, typed)
    data = win.store.get(win.current_id).data
    assert data["normalization"]["labour_per_waiting_hour"] == Decimal("0.5")
    shown = "0.5" if i18n.current() == "en" else "0,5"
    assert win.norm.waiting_weight.text() == shown
