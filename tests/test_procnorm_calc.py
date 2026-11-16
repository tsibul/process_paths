# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the comparison and step details of procnorm."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from procnorm.calc import compare, details, fmt
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
