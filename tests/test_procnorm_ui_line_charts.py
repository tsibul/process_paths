# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the two line charts of the comparison: labour and checks done by step."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from procnorm.calc import compare, series, start_point
from procnorm.project import read_project
from procnorm.ui.line_charts import LineCharts

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def project_of(d):
    p, remarks = read_project(d)
    assert remarks == []
    return p


@pytest.fixture
def project():
    return project_of(json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal))


@pytest.fixture
def charts(app):
    w = LineCharts()
    yield w
    w.close()


def rows(project):
    return compare(project).rows


def points(s):
    return [(p.x(), p.y()) for p in s.points()]


def test_titles(charts):
    assert charts.labour.chart().title() == "Labour by step"
    assert charts.checks.chart().title() == "Checks done by step"
    assert charts.labour.chart().axes(Qt.Vertical)[0].titleText() == "Labour"
    assert charts.checks.chart().axes(Qt.Vertical)[0].titleText() == "Price of checks done"
    assert charts.labour.chart().axes(Qt.Horizontal)[0].titleText() == "Step"


def test_one_line_per_variant_named_by_code(charts, project):
    rs = rows(project)
    charts.set_rows(project, rs)
    for view in (charts.labour, charts.checks):
        assert [s.name() for s in view.chart().series()] == [r.code for r in rs]


def test_labour_points(charts, project):
    charts.set_rows(project, rows(project))
    for s in charts.labour.chart().series():
        want = [(0.0, 0.0)] + [(float(p.number), float(p.labour)) for p in series(project, s.name())]
        assert points(s) == want


def test_checks_points(charts, project):
    charts.set_rows(project, rows(project))
    for s in charts.checks.chart().series():
        start = start_point(project, s.name())
        want = [(0.0, float(start.done_total))]
        want += [(float(p.number), float(p.done_total)) for p in series(project, s.name())]
        assert points(s) == want


def test_last_x_is_path_length(charts, project):
    charts.set_rows(project, rows(project))
    for view in (charts.labour, charts.checks):
        for s in view.chart().series():
            assert points(s)[-1][0] == len(series(project, s.name()))


def test_given_rows_only_in_given_order(charts, project):
    rs = rows(project)[::-1][:2]
    charts.set_rows(project, rs)
    assert [s.name() for s in charts.labour.chart().series()] == [r.code for r in rs]


def test_own_solid_other_dashed(charts, project):
    rs = rows(project)
    charts.set_rows(project, rs)
    for view in (charts.labour, charts.checks):
        styles = {s.name(): s.pen().style() for s in view.chart().series()}
        for r in rs:
            want = Qt.SolidLine if r.side == "own" else Qt.DashLine
            assert styles[r.code] == want


def test_variant_without_checks_lies_on_zero(charts):
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    d = copy.deepcopy(d)
    d["normalization"]["axis_skip_prices"] = {}
    for k in d["kinds"]:
        k.pop("check", None)
    p = project_of(d)
    charts.set_rows(p, rows(p))
    for s in charts.checks.chart().series():
        assert {y for _, y in points(s)} == {0.0}


def test_empty_list_no_lines(charts, project):
    charts.set_rows(project, rows(project))
    charts.set_rows(project, [])
    assert charts.labour.chart().series() == []
    assert charts.checks.chart().series() == []
    charts.grab()


def test_draws(charts, project):
    charts.set_rows(project, rows(project))
    charts.resize(700, 600)
    assert not charts.grab().isNull()
