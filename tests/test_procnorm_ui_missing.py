"""Tests of the window and the export for numbers not set and variants with a run error."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import csv
import io
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from procnorm import export
from procnorm.calc import compare
from procnorm.project import read_project
from procnorm.store import Store
from procnorm.ui import style
from procnorm.ui.app import MainWindow
from procnorm.ui.labour_scale import LabourScale
from procnorm.ui.line_charts import LineCharts

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
TASK = "Постирать бельё"
NOT_SET = "not set"
DASH = "—"
REASON_A = "Not set: cost of Разобрать по цветам"
REASON_E = "Error at transition 4: Бельё/состояние is 'постирано', expected 'развешано'"


def _data() -> dict:
    """Invented data: laundry.json without the cost of sorting (only А uses it) and a copy of В,
    code Е, without hanging out: its call 4 (drying) finds the linen washed, not hung."""
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    v = copy.deepcopy(next(x for x in d["variants"] if x["code"] == "В"))
    v["code"], v["title"] = "Е", "Без развешивания"
    del v["calls"][3]
    v["steps"][2]["calls"] -= 1
    d["variants"].append(v)
    del d["normalization"]["kind_costs"]["Разобрать по цветам"]
    return d


def _no_price() -> dict:
    """laundry.json without the skip price of Бельё/цвета: every variant lacks it."""
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    del d["normalization"]["axis_skip_prices"]["Бельё"]["цвета"]
    return d


def lenient(d):
    p, remarks = read_project(d, strict=False)
    assert p is not None and remarks == []
    return p


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def _window(store, data):
    """A window on a project stored as laundry.json, then saved over by an edit with ``data``."""
    w = MainWindow(store)
    assert w.load_path(LAUNDRY)
    store.save(w.current_id, data)
    w.refresh(w.current_id)
    return w


@pytest.fixture
def win(app, store):
    w = _window(store, _data())
    yield w
    w.close()


@pytest.fixture
def price_win(app, store):
    w = _window(store, _no_price())
    yield w
    w.close()


def _csv(project):
    rows = list(csv.reader(io.StringIO(export.csv_text(project))))
    return {r[1]: dict(zip(rows[0], r)) for r in rows[1:]}


# ---------- Comparison table ----------

def test_groups_put_both_out(win):
    c = win.comparison
    assert c.codes() == ["Б", "В", "А", "Е"]
    assert [h.title.text() for h in c.group_headers()] == [f"Task: {TASK}", "Out of comparison"]


def test_missing_cells_not_set(win):
    c = win.comparison
    assert c.cell("А", "Labour · Человек") == NOT_SET
    assert c.cell("А", "Labour · total") == NOT_SET
    assert c.cell("А", "Skipped checks, end") == "0.00"  # prices are all set
    assert c.cell("А", "Title").endswith(f"\nReason: {REASON_A}")
    assert not c.is_bold("А", "Labour · total") and not c.is_bold("Е", "Labour · total")


def test_error_cells_dash(win):
    c = win.comparison
    for h in c.headers()[4:]:
        assert c.cell("Е", h) == DASH
    assert c.cell("Е", "Steps") == "5"
    assert c.cell("Е", "Title").endswith(f"\nReason: {REASON_E}")


def test_compared_rows_as_before(win):
    c = win.comparison
    assert c.cell("Б", "Labour · total") == "3.40" and c.cell("В", "Labour · total") == "5.40"
    assert c.is_bold("Б", "Labour · total")


def test_missing_price_sum_not_set(price_win):
    c = price_win.comparison
    assert c.codes() == ["А", "Б", "В"]
    assert c.cell("Б", "Labour · total") == "3.40"
    assert c.cell("Б", "Skipped checks, end") == NOT_SET
    assert c.cell("А", "Skipped checks, end") == "0.00"
    assert c.cell("Б", "Title").endswith("\nReason: Not set: skip price of Бельё/цвета")
    c.toggle("Б")
    assert [w.text() for w in c.skipped_labels("Б")] == [
        "Skipped checks, постирано: Бельё/карманы (5), Бельё/цвета (not set)",
        "Skipped checks, end: Бельё/карманы (5), Бельё/цвета (not set)"]


def test_sort_with_numbers_not_set(win):
    c = win.comparison
    for h in c.headers()[3:]:
        c.sort(h, c.tree.header().sortIndicatorOrder())
        assert set(c.codes()) == {"А", "Б", "В", "Е"}


def test_steps_of_missing_variant(win):
    c = win.comparison
    c.toggle("А")
    t = c.steps("А")
    assert t.rowCount() == 7
    assert [t.item(1, i).text() for i in (5, 8)] == [NOT_SET, NOT_SET]
    assert [t.item(0, i).text() for i in (5, 8)] == ["2", "2"]


def test_steps_of_error_variant_show_all_transitions(win):
    c = win.comparison
    c.toggle("Е")
    t = c.steps("Е")
    assert t.rowCount() == 5
    assert [t.item(r, 1).text() for r in range(5)] == [x[0] for x in _data()["variants"][-1]["calls"]]
    for r in range(5):
        assert [t.item(r, i).text() for i in (5, 6, 7, 8, 9)] == [DASH] * 5
    assert t.item(0, 10).text() and t.item(4, 10).text() == ""


# ---------- Compare steps, line charts, labour scale ----------

def test_compare_steps_without_such_variants(win):
    c = win.comparison
    [pair] = c.chart_pairs()
    assert [s.name().split(" · ")[0] for s in pair.charts.labour.chart().series()] == ["Б", "В"]
    c.open_steps(c._groups[0])
    v = c.steps_view
    assert v.codes() == ["Б", "В"]
    assert [r.code for r in v.scale.rows()] == ["Б", "В"]


def test_no_line_and_no_bar(app):
    p = lenient(_data())
    cmp = compare(p)
    rows = cmp.rows + cmp.excluded_rows
    charts = LineCharts()
    charts.set_rows(p, rows)
    for view in (charts.labour, charts.checks):
        assert [s.name().split(" · ")[0] for s in view.chart().series()] == ["Б", "В"]
    scale = LabourScale(p, rows)
    assert [r.code for r in scale.rows()] == ["Б", "В"]


def test_no_line_without_a_price(app):
    p = lenient(_no_price())
    cmp = compare(p)
    charts = LineCharts()
    charts.set_rows(p, cmp.excluded_rows)
    assert charts.labour.chart().series() == [] and charts.checks.chart().series() == []
    assert LabourScale(p, cmp.excluded_rows).rows() == []


# ---------- Step chains ----------

def test_chains_list_has_both(win):
    page = win.chains
    assert page.groups() == [(f"Task: {TASK}", False, ["Б", "В"]), ("Out of comparison", True, ["А", "Е"])]


def test_chain_of_error_variant_marks_transition(win):
    page = win.chains
    page.select_path("Е")
    rows = page.rows()
    calls = [r for r in rows if r[0] == "call"]
    assert [r[1] for r in calls] == ["1", "2", "3", "4", "5"]
    at = rows.index(next(r for r in calls if r[1] == "4"))
    assert rows[at + 1] == ("error", REASON_E)
    assert page.table.failed_rows() == [at]
    it = page.table.item(at, 2)
    assert it.foreground().color().name().upper() == style.ERR.upper() and it.font().bold()
    before = rows.index(next(r for r in calls if r[1] == "3"))
    assert page.table.item(before, 2).font().bold() is False


def test_chain_of_good_variant_has_no_mark(win):
    page = win.chains
    for code in ("А", "Б", "В"):
        page.select_path(code)
        assert page.table.failed_rows() == []
        assert all(r[0] != "error" for r in page.rows())


# ---------- export equals what is shown ----------

def test_csv_equals_table(win):
    p = lenient(_data())
    got = _csv(p)
    c = win.comparison
    for code in c.codes():
        for h in c.headers():
            if h not in ("Title", "Side"):
                assert got[code][h] == c.cell(code, h), (code, h)
    assert got["А"]["Reason"] == REASON_A and got["Е"]["Reason"] == REASON_E
    assert got["А"]["Group"] == got["Е"]["Group"] == "Out of comparison"
    assert got["Б"]["Reason"] == ""


def test_csv_equals_table_without_a_price(price_win):
    got = _csv(lenient(_no_price()))
    c = price_win.comparison
    for code in c.codes():
        for h in c.headers()[3:]:
            assert got[code][h] == c.cell(code, h), (code, h)


def test_markdown_out_table_and_details(win):
    md = export.markdown(lenient(_data()))
    out = md[md.index("## Out of comparison"):md.index("## Uncounted errors")]
    assert f"| А | Аккуратная стирка | Ours | 7 | {NOT_SET} | {NOT_SET} | 0.00 | 0.00 | {REASON_A} |" in out
    assert (f"| Е | Без развешивания | Theirs | 5 | {DASH} | {DASH} | {DASH} | {DASH} | "
            f"{REASON_E.replace('|', chr(92) + '|')} |") in out
    c = win.comparison
    for code in ("А", "Е"):
        c.toggle(code)
        t = c.steps(code)
        part = md[md.index(f"### {code}: "):]
        lines = [ln for ln in part.splitlines()[4:] if ln.startswith("| ")][:t.rowCount()]
        for r, ln in enumerate(lines):
            cells = [x.strip() for x in ln.strip("|").split(" | ")]
            assert cells[5:9] == [t.item(r, i).text() for i in (5, 6, 7, 8)], (code, r)
