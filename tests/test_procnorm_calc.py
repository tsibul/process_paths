# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the comparison and step details of procnorm."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from procnorm.calc import compare, details, fmt, groups, series
from procnorm.project import load_file, read_project

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
D = Decimal


def base() -> dict:
    return copy.deepcopy(json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal))


def project_of(d):
    p, remarks = read_project(d)
    assert remarks == []
    return p


@pytest.fixture
def project():
    p, remarks = load_file(LAUNDRY)
    assert remarks == []
    return p


def rows(project):
    return {r.code: r for r in compare(project).rows}


def test_columns_and_slice_names(project):
    c = compare(project)
    assert c.executors == ["Человек"]
    assert c.slice_names == ["постирано", "final"]
    assert c.excluded == []
    assert [r.code for r in c.rows] == ["А", "Б", "В"]


@pytest.mark.parametrize("code,steps,total,index,skips", [
    ("А", 7, "8.4", 4, "0"),
    ("Б", 5, "3.4", 2, "8"),
    ("В", 6, "5.4", 3, "3"),
])
def test_rows(project, code, steps, total, index, skips):
    r = rows(project)[code]
    assert r.steps == steps
    assert r.total == D(total)
    assert r.labour == {"Человек": D(total)}
    named, final = r.slices
    assert (named.name, named.reached, named.index) == ("постирано", True, index)
    assert named.total == D(skips)
    assert (final.name, final.reached, final.index) == ("final", True, steps)
    assert final.total == D(skips)


def test_skips_detail_b(project):
    named = rows(project)["Б"].slices[0]
    assert {(e, a): p for e, a, p in named.skips} == {("Бельё", "карманы"): D(5), ("Бельё", "цвета"): D(3)}


def test_out_of_comparison_excluded():
    d = base()
    next(v for v in d["variants"] if v["code"] == "Б")["out_of_comparison"] = "не сравнивать"
    c = compare(project_of(d))
    assert [r.code for r in c.rows] == ["А", "В"]
    assert c.excluded == [("Б", "Быстрая стирка", "не сравнивать")]


def test_unreached_named_slice():
    d = base()
    d["named_slices"]["карманы"] = {"any": [{"states": [["Бельё", "карманы", "проверены"]]}]}
    c = compare(project_of(d))
    assert c.slice_names == ["постирано", "карманы", "final"]
    b = {r.code: r for r in c.rows}["Б"]
    s = b.slices[1]
    assert s.name == "карманы" and s.reached is False and s.index == b.steps


def test_zero_coefficient_executor_not_column():
    d = base()
    d["normalization"]["executor_coefficients"]["Человек"] = 0
    c = compare(project_of(d))
    assert c.executors == []
    assert all(r.total == 0 and r.labour == {} for r in c.rows)


def test_unused_executor_not_column():
    d = base()
    d["executors"].append("Курьер")
    d["normalization"]["executor_coefficients"]["Курьер"] = 1
    assert compare(project_of(d)).executors == ["Человек"]


def test_total_counts_executors_outside_columns():
    d = base()
    d["normalization"]["executor_coefficients"]["Машина"] = 2  # used, so it is a column
    c = compare(project_of(d))
    assert c.executors == ["Человек", "Машина"]
    b = {r.code: r for r in c.rows}["Б"]
    assert b.labour["Машина"] == D("0.2") and b.total == D("3.6")


def test_total_includes_non_column_when_coefficient_zero_executor_dropped():
    d = base()
    d["normalization"]["executor_coefficients"]["Человек"] = 0
    d["normalization"]["executor_coefficients"]["Машина"] = 1
    c = compare(project_of(d))
    assert c.executors == ["Машина"]
    assert {r.code: r for r in c.rows}["Б"].total == D("0.1")


def test_details_b(project):
    steps = details(project, "Б")
    assert len(steps) == 5
    s1 = steps[0]
    assert s1.number == 1 and s1.kind == "Запустить машину"
    assert s1.cost == D(4) and s1.labour == D("0.4")
    assert ("Цикл стирки", "наличие", "нет", "есть") in s1.changes
    assert sum((s.labour for s in steps), D(0)) == rows(project)["Б"].total


def test_fmt():
    assert fmt(D("8.40")) == "8.4"
    assert fmt(D("1E+1")) == "10"
    assert fmt(D("0.000")) == "0"


# ---------- task, out of comparison with numbers, groups ----------

def clone(d, src, code, side, task=None, out=None):
    v = copy.deepcopy(next(x for x in d["variants"] if x["code"] == src))
    v["code"], v["title"], v["side"] = code, "T" + code, side
    for key, val in (("task", task), ("out_of_comparison", out)):
        if val is not None:
            v[key] = val
        else:
            v.pop(key, None)
    d["variants"].append(v)


def grouped_project():
    """А 8.4 own, Б 3.4 other, В 5.4 other (all without task); more are cloned."""
    d = base()
    for v in d["variants"]:
        v.pop("task", None)
    clone(d, "А", "а2", "own", "Мыть")       # 8.4
    clone(d, "Б", "б2", "other", "Мыть")     # 3.4
    clone(d, "В", "в2", "other", "Мыть")     # 5.4
    clone(d, "Б", "б3", "own", "Мыть")       # 3.4
    clone(d, "Б", "б0", "own", "Мыть")       # 3.4, ties with б3: by code
    clone(d, "А", "а3", "own", "Сушить")     # 8.4
    clone(d, "В", "в3", "own", "Сушить")     # 5.4
    clone(d, "Б", "б4", "own", "Одна")       # alone
    clone(d, "А", "а4", "other", "Вне", out="не сравнивать")
    clone(d, "Б", "б5", "own", "Мыть", out="ещё не готов")
    return project_of(d)


def test_row_task_and_reason(project):
    c = compare(project)
    assert all(r.task == "Постирать бельё" and r.reason is None for r in c.rows)


def test_row_task_from_file():
    d = base()
    next(v for v in d["variants"] if v["code"] == "Б")["task"] = "Мыть"
    assert rows(project_of(d))["Б"].task == "Мыть"


def test_excluded_rows_have_numbers_and_reason():
    d = base()
    next(v for v in d["variants"] if v["code"] == "Б")["out_of_comparison"] = "не сравнивать"
    c = compare(project_of(d))
    assert [r.code for r in c.rows] == ["А", "В"]
    assert c.excluded == [("Б", "Быстрая стирка", "не сравнивать")]
    assert [r.code for r in c.excluded_rows] == ["Б"]
    b = c.excluded_rows[0]
    assert b.reason == "не сравнивать" and b.side == "other"


def test_excluded_numbers_equal_unmarked():
    plain = {r.code: r for r in compare(project_of(base())).rows}["Б"]
    d = base()
    next(v for v in d["variants"] if v["code"] == "Б")["out_of_comparison"] = "x"
    marked = compare(project_of(d)).excluded_rows[0]
    assert (marked.steps, marked.labour, marked.total, marked.slices) == \
           (plain.steps, plain.labour, plain.total, plain.slices)


def test_groups_order_and_kinds():
    g = groups(compare(grouped_project()))
    assert [(x.kind, x.task) for x in g] == [
        ("task", "Мыть"), ("task", "Сушить"), ("no-pair", None), ("out", None)]


def test_groups_rows_order():
    g = groups(compare(grouped_project()))
    # own first, then other; by total, tie by code
    assert [r.code for r in g[0].rows] == ["б0", "б3", "а2", "б2", "в2"]
    assert [r.code for r in g[1].rows] == ["в3", "а3"]


def test_groups_no_pair_and_out():
    g = groups(compare(grouped_project()))
    # alone task "Одна" and the three without task: А own, Б, В other
    assert [r.code for r in g[2].rows] == ["б4", "А", "Б", "В"]
    assert g[2].task is None
    # out of comparison regardless of task; own first
    assert [r.code for r in g[3].rows] == ["б5", "а4"]
    assert [r.reason for r in g[3].rows] == ["ещё не готов", "не сравнивать"]


def test_pair_of_two_own_is_a_group():
    d = base()
    clone(d, "А", "а2", "own", "Мыть")
    clone(d, "Б", "б2", "own", "Мыть")
    g = groups(compare(project_of(d)))
    assert [(x.kind, x.task, [r.code for r in x.rows]) for x in g] == [
        ("task", "Мыть", ["б2", "а2"]),
        ("task", "Постирать бельё", ["А", "Б", "В"])]


def test_out_of_comparison_does_not_make_a_pair():
    d = base()
    clone(d, "А", "а2", "own", "Мыть")
    clone(d, "Б", "б2", "own", "Мыть", out="x")
    g = groups(compare(project_of(d)))
    assert [x.kind for x in g] == ["task", "no-pair", "out"]
    assert "а2" in [r.code for r in g[1].rows]


def test_empty_groups_absent():
    g = groups(compare(project_of(base())))
    assert [x.kind for x in g] == ["task"]
    assert g[0].task == "Постирать бельё"
    assert [r.code for r in g[0].rows] == ["А", "Б", "В"]


# ---------- series ----------

def test_series_a(project):
    pts = series(project, "А")
    assert [p.number for p in pts] == list(range(1, 8))
    assert [p.kind for p in pts][:3] == ["Проверить карманы", "Разобрать по цветам", "Запустить машину"]
    assert [p.executor for p in pts][3] == "Машина"
    assert [p.labour for p in pts][:4] == [D(2), D(5), D("5.4"), D("5.4")]
    p1, p2 = pts[0], pts[1]
    assert p1.skips == [("Бельё", "цвета")] and p1.skips_count == 1 and p1.skips_total == D(3)
    assert p1.done_total == D(5)
    assert p2.skips == [] and p2.skips_count == 0 and p2.skips_total == D(0) and p2.done_total == D(8)
    assert pts[-1].done_total == D(8)


def test_series_last_point_equals_row(project):
    for code, row in rows(project).items():
        pts = series(project, code)
        assert len(pts) == row.steps
        assert pts[-1].labour == row.total
        final = row.slices[-1]
        assert pts[-1].skips_total == final.total
        assert pts[-1].skips_count == len(final.skips)
        assert pts[-1].skips == [(e, a) for e, a, _ in final.skips]
        assert all(a.labour <= b.labour for a, b in zip(pts, pts[1:]))


def test_series_slice_marker(project):
    pts = series(project, "А")
    assert [p.slices for p in pts] == [[], [], [], ["постирано"], [], [], []]
    pts = series(project, "Б")
    assert [p.slices for p in pts] == [[], ["постирано"], [], [], []]


def test_series_unreached_slice_has_no_marker():
    d = base()
    d["named_slices"]["карманы"] = {"any": [{"states": [["Бельё", "карманы", "проверены"]]}]}
    p = project_of(d)
    assert [x.slices for x in series(p, "А")][:4] == [["карманы"], [], [], ["постирано"]]
    assert all(x.slices in ([], ["постирано"]) for x in series(p, "Б"))
    assert not any("карманы" in x.slices for x in series(p, "Б"))


def test_series_check_reverted_counts_as_skip_again():
    d = base()
    d["kinds"].append({"name": "Снять проверку", "entity": "Бельё", "axis": "карманы",
                       "from": "проверены", "to": "не проверены"})
    d["normalization"]["kind_costs"]["Снять проверку"] = 1
    v = next(x for x in d["variants"] if x["code"] == "А")
    v["calls"] = [["Проверить карманы", "Человек", "руки", "каждая вещь"],
                  ["Снять проверку", "Человек", "руки", "каждая вещь"]]
    pts = series(project_of(d), "А")
    assert pts[0].skips == [("Бельё", "цвета")] and pts[0].done_total == D(5)
    assert pts[1].skips == [("Бельё", "карманы"), ("Бельё", "цвета")]
    assert pts[1].skips_total == D(8) and pts[1].done_total == D(0)
    assert pts[1].labour == D(3)


def test_series_without_checks_is_zero():
    d = base()
    d["normalization"]["axis_skip_prices"] = {}
    for k in d["kinds"]:
        k.pop("check", None)
    d["variants"] = [v for v in d["variants"] if v["code"] == "Б"]
    pts = series(project_of(d), "Б")
    assert len(pts) == 5
    assert all(p.skips == [] and p.skips_count == 0 and p.skips_total == D(0) and p.done_total == D(0)
               for p in pts)
