# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the charts in the PDF report (piece 22): charts on the answer page, then the file."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from measure_twice import report
from measure_twice.calc import compare, groups, series, start_point
from measure_twice.project import read_project

from tests.test_procnorm_report import _big_data

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
LINES = ["labour", "checks"]
LINES_WAITING = ["labour", "labour_waiting", "checks"]
SCALE = "scale"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _project(data: dict):
    p, remarks = read_project(data)
    assert p is not None, remarks
    return p


def _laundry_data() -> dict:
    return json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)


@pytest.fixture
def laundry():
    return _project(_laundry_data())


@pytest.fixture
def laundry_waiting():
    data = _laundry_data()
    data["normalization"]["labour_per_waiting_hour"] = 2
    return _project(data)


@pytest.fixture
def big():
    return _project(_big_data())


def _charts(pages):
    return [c for p in pages if p.kind == report.ANSWER for c in p.charts]


def _task_codes(project) -> list[str]:
    """Codes of the ways of the task groups, in the order of the table."""
    return [r.code for g in groups(compare(project)) if g.kind == "task" for r in g.rows]


def test_answer_page_has_all_charts_of_the_tab(app, laundry):
    charts = _charts(report.pages(laundry))
    assert [c.kind for c in charts] == LINES + [SCALE]
    for c in charts:
        assert c.task == "Постирать бельё"


def test_waiting_chart_when_weight_is_set(app, laundry_waiting):
    charts = _charts(report.pages(laundry_waiting))
    assert [c.kind for c in charts] == LINES_WAITING + [SCALE]


def test_chart_data_is_series_of_chosen_ways(app, laundry):
    ways = ["А", "В"]
    for c in _charts(report.pages(laundry, ways=ways)):
        assert list(c.points) == ways
        assert [r.code for r in c.rows] == ways
        for code in ways:
            assert c.points[code] == [start_point(laundry, code)] + series(laundry, code)


def test_unchosen_way_is_absent_from_charts(app, laundry):
    for c in _charts(report.pages(laundry, ways=["А", "Б"])):
        assert "В" not in c.points
        assert "В" not in [r.code for r in c.rows]


def test_no_charts_without_chosen_task_ways(app, laundry):
    pages = report.pages(laundry, ways=[])
    assert _charts(pages) == []


def test_charts_only_on_answer_pages(app, laundry):
    pages = report.pages(laundry)
    assert all(not p.charts for p in pages if p.kind != report.ANSWER)
    assert _charts(report.pages(laundry, chosen=["steps", "assumptions"])) == []


def _overlap(a, b) -> bool:
    return (a.x < b.x + b.width and b.x < a.x + a.width
            and a.y < b.y + b.height and b.y < a.y + a.height)


@pytest.mark.parametrize("which", ["laundry", "big"])
def test_charts_fit_page_and_do_not_overlap(app, laundry, big, which):
    project = laundry if which == "laundry" else big
    for page in report.pages(project):
        for c in page.charts:
            assert c.x >= report.MARGIN - 0.01
            assert c.x + c.width <= report.PAGE_WIDTH - report.MARGIN + 0.01
            assert c.y >= report.MARGIN - 0.01
            assert c.y + c.height <= report.PAGE_HEIGHT - report.MARGIN + 0.01
            assert not any(_overlap(c, t) for t in page.texts)
            assert not any(_overlap(c, d) for d in page.charts if d is not c)


def test_big_charts_go_on_following_pages(app, big):
    pages = report.pages(big, chosen=["answer"])
    assert len(pages) > 1
    assert all(p.kind == report.ANSWER for p in pages)
    charts = _charts(pages)
    assert [c.kind for c in charts] == LINES + [SCALE]
    for c in charts:
        assert list(c.points) == _task_codes(big)


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def _media_boxes(data: bytes) -> list[tuple[float, float]]:
    found = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    return [(float(x2) - float(x1), float(y2) - float(y1)) for x1, y1, x2, y2 in found]


@pytest.mark.parametrize("which", ["laundry", "big"])
def test_file_with_charts(app, laundry, big, which, tmp_path):
    project = laundry if which == "laundry" else big
    laid = report.pages(project)
    assert _charts(laid)
    path = tmp_path / "report.pdf"
    report.write(project, path)
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert _pdf_pages(data) == len(laid)
    boxes = _media_boxes(data)
    assert boxes
    for w, h in boxes:
        assert round(w) == 842 and round(h) == 595


def test_line_chart_grows_to_show_every_legend_entry(app, laundry, big):
    from measure_twice.ui import line_charts

    small = [c for c in _charts(report.pages(laundry)) if c.kind != SCALE]
    large = [c for c in _charts(report.pages(big)) if c.kind != SCALE]
    assert all(c.size[1] == line_charts.HEIGHT for c in small)
    assert all(c.size[1] > line_charts.HEIGHT for c in large)
