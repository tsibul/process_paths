# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of ``missing`` and ``error`` in the calculation of a leniently read project."""

from decimal import Decimal as D

from measure_twice import calc
from measure_twice.project import read_project
from tests.test_procnorm_project import base, variant


def lenient(d):
    project, remarks = read_project(d, strict=False)
    assert remarks == [] and project is not None
    return project


def row(cmp, code):
    return next(r for r in cmp.rows + cmp.excluded_rows if r.code == code)


def numbers(project, code):
    """Every number of one variant the calculation gives."""
    r = row(calc.compare(project), code)
    return (r.labour, r.total, [(s.name, s.index, s.reached, s.skips, s.total) for s in r.slices],
            [(p.labour, p.skips, p.skips_total, p.done_total, p.slices) for p in calc.series(project, code)],
            calc.start_point(project, code),
            [(s.cost, s.scope_coefficient, s.executor_coefficient, s.labour, s.changes)
             for s in calc.details(project, code)])


# ---------- a complete project: numbers as before ----------

def test_complete_project_numbers_as_before():
    p = lenient(base())
    cmp = calc.compare(p)
    assert cmp.executors == ["Человек"]
    assert [(r.code, r.total) for r in cmp.rows] == [("А", D("8.4")), ("Б", D("3.4")), ("В", D("5.4"))]
    assert all(r.missing == [] and r.error is None and r.reason is None for r in cmp.rows)
    assert cmp.excluded_rows == [] and cmp.excluded == []
    assert [(g.kind, [r.code for r in g.rows]) for g in calc.groups(cmp)] == [("task", ["А", "Б", "В"])]
    b = row(cmp, "Б")
    assert [(s.name, s.total) for s in b.slices] == [("постирано", D(8)), ("final", D(8))]
    assert [(x.labour, x.skips_total, x.done_total) for x in calc.series(p, "В")][-1] == (D("5.4"), D(3), D(5))
    assert calc.start_point(p, "В").skips_total == D(8)
    assert [s.labour for s in calc.details(p, "В")] == [D(2), D("0.4"), D("0.0"), D(2), D("0.0"), D(1)]


def test_complete_project_lenient_equals_strict():
    strict, _ = read_project(base())
    p = lenient(base())
    for code in ("А", "Б", "В"):
        assert numbers(p, code) == numbers(strict, code)


# ---------- a kind cost removed ----------

def no_sort_cost():
    d = base()
    del d["normalization"]["kind_costs"]["Разобрать по цветам"]  # only variant А uses it
    return d


def test_missing_cost_marks_only_variants_with_the_kind():
    cmp = calc.compare(lenient(no_sort_cost()))
    a = row(cmp, "А")
    assert a.missing == ["cost of Разобрать по цветам"]
    assert a.error is None
    assert a.reason == "Not set: cost of Разобрать по цветам"
    assert a.total is None and a.labour == {"Человек": None}
    assert row(cmp, "Б").missing == [] and row(cmp, "В").missing == []


def test_missing_cost_goes_out_of_comparison():
    cmp = calc.compare(lenient(no_sort_cost()))
    assert [r.code for r in cmp.rows] == ["Б", "В"]
    assert [r.code for r in cmp.excluded_rows] == ["А"]
    assert cmp.excluded == [("А", variant(base(), "А")["title"], "Not set: cost of Разобрать по цветам")]
    gs = calc.groups(cmp)
    assert [(g.kind, [r.code for r in g.rows]) for g in gs] == [("task", ["Б", "В"]), ("out", ["А"])]


def test_missing_cost_others_compute_as_before():
    strict, _ = read_project(base())
    p = lenient(no_sort_cost())
    for code in ("Б", "В"):
        assert numbers(p, code) == numbers(strict, code)


def test_missing_cost_skips_still_computed():
    p = lenient(no_sort_cost())
    a = row(calc.compare(p), "А")
    assert [(s.name, s.skips, s.total) for s in a.slices] == [("постирано", [], D(0)), ("final", [], D(0))]


def test_missing_cost_details_and_series():
    p = lenient(no_sort_cost())
    steps = calc.details(p, "А")
    assert len(steps) == 7
    assert steps[1].cost is None and steps[1].labour is None
    assert steps[0].cost == D(2) and steps[0].labour == D(2)
    pts = calc.series(p, "А")
    assert [x.labour for x in pts][:2] == [D(2), None]
    assert all(x.labour is None for x in pts[1:])
    assert pts[-1].skips_total == D(0)


def test_zero_weight_kind_without_cost_is_not_missing():
    d = base()
    del d["normalization"]["kind_costs"]["Дождаться высыхания"]
    cmp = calc.compare(lenient(d))
    assert [r.code for r in cmp.rows] == ["А", "Б", "В"]
    assert all(r.missing == [] for r in cmp.rows)


def test_missing_coefficients_named():
    d = base()
    del d["normalization"]["executor_coefficients"]["Машина"]
    del d["normalization"]["scope_coefficients"]["вся загрузка"]
    cmp = calc.compare(lenient(d))
    assert cmp.rows == []
    for code in ("А", "Б", "В"):
        r = row(cmp, code)
        assert r.missing == ["coefficient of executor Машина", "coefficient of scope вся загрузка"]
        assert r.reason == "Not set: coefficient of executor Машина, coefficient of scope вся загрузка"
        assert r.total is None


# ---------- a check axis price removed ----------

def no_colour_price():
    d = base()
    del d["normalization"]["axis_skip_prices"]["Бельё"]["цвета"]
    return d


def test_missing_price_labour_present_sum_not_set_list_present():
    cmp = calc.compare(lenient(no_colour_price()))
    b = row(cmp, "Б")
    assert b.missing == ["skip price of Бельё/цвета"]
    assert b.reason == "Not set: skip price of Бельё/цвета"
    assert b.total == D("3.4") and b.labour == {"Человек": D("3.4")}
    fin = b.slices[-1]
    assert fin.skips == [("Бельё", "карманы", D(5)), ("Бельё", "цвета", None)]
    assert fin.total is None


def test_missing_price_all_variants_out():
    cmp = calc.compare(lenient(no_colour_price()))
    assert cmp.rows == []
    assert [(g.kind, [r.code for r in g.rows]) for g in calc.groups(cmp)] == [("out", ["А", "Б", "В"])]


def test_missing_price_series_and_start():
    p = lenient(no_colour_price())
    s0 = calc.start_point(p, "Б")
    assert s0.skips == [("Бельё", "карманы"), ("Бельё", "цвета")] and s0.skips_count == 2
    assert s0.skips_total is None and s0.done_total == D(0)
    pts = calc.series(p, "А")
    assert pts[0].skips == [("Бельё", "цвета")] and pts[0].skips_total is None
    assert pts[0].done_total == D(5)
    assert pts[-1].skips == [] and pts[-1].skips_total == D(0) and pts[-1].done_total is None
    assert pts[-1].labour == D("8.4")


# ---------- a variant with a run error ----------

def broken():
    d = base()
    del variant(d, "А")["calls"][4]  # call 5 (drying) finds the linen washed, not hung
    return d


def test_error_row_has_no_numbers():
    p = lenient(broken())
    cmp = calc.compare(p)
    a = row(cmp, "А")
    number, reason = p.errors["А"]
    assert a.error == (5, reason)
    assert a.reason == f"Error at transition 5: {reason}"
    assert a.total is None and a.labour == {"Человек": None} and a.slices == []
    assert a.steps == 6


def test_error_goes_out_others_as_before():
    strict, _ = read_project(base())
    p = lenient(broken())
    cmp = calc.compare(p)
    assert [(g.kind, [r.code for r in g.rows]) for g in calc.groups(cmp)] == [("task", ["Б", "В"]),
                                                                            ("out", ["А"])]
    for code in ("Б", "В"):
        assert numbers(p, code) == numbers(strict, code)


def test_error_chain_gives_all_transitions_without_numbers():
    p = lenient(broken())
    links = calc.chain(p, "А")
    calls = [s for link in links for s in link.calls]
    assert [s.number for s in calls] == [1, 2, 3, 4, 5, 6]
    assert [s.kind for s in calls] == [c[0] for c in variant(broken(), "А")["calls"]]
    assert all(s.cost is None and s.scope_coefficient is None and s.executor_coefficient is None
               and s.labour is None for s in calls)
    assert all(link.slices == [] for link in links)


def test_error_details_changes_up_to_the_failed_call():
    p = lenient(broken())
    steps = calc.details(p, "А")
    assert all(s.changes for s in steps[:4])
    assert all(s.changes == [] for s in steps[4:])


def test_error_series_empty_start_point_present():
    p = lenient(broken())
    assert calc.series(p, "А") == []
    s0 = calc.start_point(p, "А")
    assert s0.number == 0 and s0.labour == D(0) and s0.skips_total == D(8)


def test_error_and_missing_reason_is_error():
    d = broken()
    del d["normalization"]["kind_costs"]["Разобрать по цветам"]
    a = row(calc.compare(lenient(d)), "А")
    assert a.error is not None and a.missing == ["cost of Разобрать по цветам"]
    assert a.reason.startswith("Error at transition 5: ")
