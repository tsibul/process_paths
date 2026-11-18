# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the labour scale of the Compare steps view: what it draws, checked against series()."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from measure_twice.calc import compare, groups, money, series, start_point
from measure_twice.project import read_project
from measure_twice.ui import style
from measure_twice.ui.labour_scale import LabourScale

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
D = Decimal


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def project():
    """The example with a working machine: its steps get labour, so two executors colour the bars."""
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    d["normalization"]["executor_coefficients"]["Машина"] = D("0.5")
    p, remarks = read_project(d)
    assert remarks == []
    return p


@pytest.fixture(scope="module")
def rows(project):
    return next(g for g in groups(compare(project)) if g.kind == "task").rows


@pytest.fixture
def scale(app, project, rows):
    w = LabourScale(project, rows)
    w.resize(1100, w.heightForWidth(1100))
    yield w
    w.close()


def points(project, code):
    return [start_point(project, code)] + series(project, code)


def executor_color(project, executor):
    i = [e.name for e in project.model.executors].index(executor)
    return style.SCALE_STEPS[i % len(style.SCALE_STEPS)][0]


def test_axis_ends_at_largest_total(scale, rows):
    assert scale.axis_end() == max(r.total for r in rows)
    ticks = scale.ticks()
    assert ticks[0] == 0 and ticks[-1] >= scale.axis_end()
    step = ticks[1] - ticks[0]
    assert all(b - a == step for a, b in zip(ticks, ticks[1:]))
    assert ticks[-2] < scale.axis_end()


def test_rows_in_given_order(app, project, rows):
    back = list(reversed(rows))
    w = LabourScale(project, back)
    assert [r.code for r in w.rows()] == [r.code for r in back]
    assert [(r.title, r.side) for r in w.rows()] == [(r.title, "● Ours" if r.side == "own" else "○ Theirs")
                                                     for r in back]


def test_accent_bar_only_for_own(scale, rows):
    assert [r.own for r in scale.rows()] == [r.side == "own" for r in rows]
    assert any(r.own for r in scale.rows()) and not all(r.own for r in scale.rows())


def test_segments_end_at_running_labour(scale, project):
    for r in scale.rows():
        pts = points(project, r.code)
        want = [(b.number, a.labour, b.labour) for a, b in zip(pts, pts[1:]) if b.labour != a.labour]
        assert [(s.number, s.start, s.end) for s in r.segments] == want


def test_segment_colour_by_executor(scale, project):
    for r in scale.rows():
        by_number = {p.number: p for p in series(project, r.code)}
        for s in r.segments:
            assert s.executor == by_number[s.number].executor
            assert s.color == executor_color(project, s.executor)
    used = {s.executor for r in scale.rows() for s in r.segments}
    assert len({executor_color(project, e) for e in used}) == len(used) > 1


def test_segment_tip(scale, project):
    r = scale.rows()[0]
    s = r.segments[0]
    p = series(project, r.code)[s.number - 1]
    assert s.tip == f"{p.kind}, {p.executor}: {money(s.end - s.start)}"
    assert s.text == money(s.end - s.start)


def test_zero_step_is_a_line_not_a_segment(scale, project):
    found = False
    for r in scale.rows():
        pts = points(project, r.code)
        want = [(b.number, b.labour) for a, b in zip(pts, pts[1:]) if b.labour == a.labour]
        assert [(z.number, z.at) for z in r.zeros] == want
        assert not {z.number for z in r.zeros} & {s.number for s in r.segments}
        assert len(r.zeros) + len(r.segments) == len(pts) - 1
        found = found or bool(want)
        for z in r.zeros:
            p = pts[z.number]
            assert z.tip == f"{p.kind}, {p.executor}: {money(D(0))}"
    assert found


def test_check_where_done_total_grew(scale, project):
    seen = []
    for r in scale.rows():
        pts = points(project, r.code)
        want = [(b.number, b.labour) for a, b in zip(pts, pts[1:]) if b.done_total > a.done_total]
        assert [(c.number, c.at) for c in r.checks] == want
        seen.append(bool(want))
    assert any(seen) and not all(seen)


def test_slice_dash_where_slices(scale, project):
    for r in scale.rows():
        want = [(p.number, p.labour, ", ".join(p.slices)) for p in series(project, r.code) if p.slices]
        assert [(m.number, m.at, m.name) for m in r.slices] == want
        assert want


def test_strip_colours_by_skips(scale, project):
    colours = set()
    for r in scale.rows():
        pts = points(project, r.code)
        want = [(a.labour, b.labour, style.SCALE_OPEN if a.skips_count else style.SCALE_DONE)
                for a, b in zip(pts, pts[1:])]
        assert [(s.start, s.end, s.color) for s in r.strip] == want
        assert r.strip[0].color == (style.SCALE_OPEN if pts[0].skips_count else style.SCALE_DONE)
        colours |= {s.color for s in r.strip}
    assert colours == {style.SCALE_OPEN, style.SCALE_DONE}


def test_end_label_is_total_and_skips(scale, project, rows):
    for r, row in zip(scale.rows(), rows):
        last = points(project, r.code)[-1]
        assert r.total == last.labour == row.total
        assert r.skips_total == last.skips_total
        assert r.end_text() == (money(last.labour), money(last.skips_total))
        assert r.skips_color == (style.OK if last.skips_total == 0 else style.ERR)


def test_legend_lists_used_executors(scale, project):
    names = [t for t, _ in scale.legend()]
    used = [e.name for e in project.model.executors
            if any(s.executor == e.name for r in scale.rows() for s in r.segments)]
    assert names[:len(used)] == [f"{e} step" for e in used]
    assert [c for _, c in scale.legend()][:len(used)] == [executor_color(project, e) for e in used]
    assert "zero-labour step" in " ".join(names)


def test_tip_at_segment_middle(scale):
    r = scale.rows()[0]
    s = r.segments[0]
    pos = scale.point_at(0, (s.start + s.end) / 2)
    assert scale.tip_at(pos) == s.tip
    assert scale.tip_at(scale.point_at(0, scale.ticks()[-1])) is None


def test_paints(scale):
    assert not scale.grab().isNull()


def test_paints_empty(app, project):
    w = LabourScale(project, [])
    w.resize(600, 200)
    assert w.rows() == [] and not w.grab().isNull()
