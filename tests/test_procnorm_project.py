# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of reading and checking a procnorm project file."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from procnorm.project import load_file, parse_text, read_project

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
TEXT = LAUNDRY.read_text(encoding="utf-8")


def base() -> dict:
    return copy.deepcopy(json.loads(TEXT, parse_float=Decimal))


def remarks_of(d: dict):
    project, remarks = read_project(d)
    assert project is None
    return remarks


def has(remarks, fragment: str, where: str | None = None) -> bool:
    return any(fragment in r.text and (where is None or where in r.where) for r in remarks)


def kind(d, name):
    return next(k for k in d["kinds"] if k["name"] == name)


def variant(d, code):
    return next(v for v in d["variants"] if v["code"] == code)


def test_laundry_loads():
    project, remarks = load_file(LAUNDRY)
    assert remarks == []
    assert project.name == "Стирка белья"
    assert project.sides == {"А": "own", "Б": "other", "В": "other"}
    assert project.norm.batch_size == Decimal(10)
    assert set(project.norm.skip_prices) == {("Бельё", "карманы"), ("Бельё", "цвета")}


def test_base_is_valid():
    project, remarks = read_project(base())
    assert remarks == [] and project is not None


# ---------- stage 1 ----------

def _del(path, key):
    def f(d):
        t = d
        for p in path:
            t = t[p]
        del t[key]
    return f


def _set(path, key, value):
    def f(d):
        t = d
        for p in path:
            t = t[p]
        t[key] = value
    return f


STAGE1 = [
    (lambda d: d.update(extra=1), "unknown field 'extra'", "file"),
    (_del([], "name"), "field 'name' is missing", "file"),
    (_set([], "format", 2), "must be 1", "format"),
    (_set([], "name", " "), "text expected", "name"),
    (_set([], "description", 5), "text expected", "description"),
    (_set([], "existence_axis", ["a"]), "object expected", "existence_axis"),
    (_set(["existence_axis"], "extra", 1), "unknown field", "existence_axis"),
    (_del(["existence_axis"], "absent"), "field 'absent' is missing", "existence_axis"),
    (_set(["existence_axis"], "name", 3), "name and absent must be texts", "existence_axis"),
    (_set(["entities"], 0, "x"), "object expected", "entity 1"),
    (_set(["entities", 0], "extra", 1), "unknown field", "entity Бельё"),
    (_del(["entities", 0], "axes"), "field 'axes' is missing", "entity Бельё"),
    (_set(["entities", 0], "axes", "x"), "axes: list expected", "entity Бельё"),
    (_set(["entities", 0], "name", 5), "name must be a text", "entity 1"),
    (_set(["entities", 0, "axes"], 0, 5), "object expected", "axis 1"),
    (_set(["entities", 0, "axes", 0], "extra", 1), "unknown field", "axis состояние"),
    (_del(["entities", 0, "axes", 0], "values"), "field 'values' is missing", "axis состояние"),
    (_set(["entities", 0, "axes", 0], "name", 5), "name must be a text", "axis 1"),
    (_set(["entities", 0, "axes", 0], "values", "x"), "list of names expected", "values"),
    (_set(["entities", 0, "axes", 0], "inherit", [["a"]]), "list of [name, name] expected", "inherit"),
    (_set([], "entities", "x"), "list expected", "entities"),
    (_set([], "kinds", "x"), "list expected", "kinds"),
    (_set(["kinds"], 0, 5), "object expected", "kind 1"),
    (_set(["kinds", 0], "extra", 1), "unknown field", "kind Проверить карманы"),
    (_del(["kinds", 0], "to"), "field 'to' is missing", "kind Проверить карманы"),
    (_set(["kinds", 0], "to", 5), "to must be a text", "kind Проверить карманы"),
    (_set(["kinds", 0], "requires", [["a", "b"]]), "list of [name, name, name] expected", "requires"),
    (_set(["kinds", 0], "check", "yes"), "check must be true or false", "kind Проверить карманы"),
    (_set(["kinds", 0], "zero_weight", 1), "zero_weight must be true or false", "kind Проверить карманы"),
    (_set(["kinds", 0], "zero_weight_note", "note"), "zero_weight_note needs", "kind Проверить карманы"),
    (_set(["kinds", 5], "zero_weight_note", ""), "zero_weight_note needs", "kind Дождаться"),
    (_set([], "executors", "x"), "list of names expected", "executors"),
    (_set([], "instruments", [1]), "list of names expected", "instruments"),
    (_set([], "scopes", None), "list of names expected", "scopes"),
    (_set([], "batch_scope", 1), "text expected", "batch_scope"),
    (_set([], "variant_params", "x"), "list of names expected", "variant_params"),
    (_set([], "named_slices", []), "object expected", "named_slices"),
    (_set(["named_slices"], "постирано", 5), "object expected", "named slice постирано"),
    (_set(["named_slices", "постирано"], "extra", 1), "unknown field", "named slice постирано"),
    (_set(["named_slices", "постирано"], "any", []), "non-empty list of groups", "named slice"),
    (_set(["named_slices", "постирано"], "any", [5]), "object expected", "named slice"),
    (_set(["named_slices", "постирано", "any", 0], "extra", 1), "unknown field", "named slice"),
    (_set(["named_slices", "постирано", "any", 0], "states", [["a", "b"]]),
     "list of [name, name, name] expected", "states"),
    (_set(["named_slices", "постирано", "any", 0], "params", [["a"]]),
     "list of [name, name] expected", "params"),
    (_set(["named_slices", "постирано"], "any", [{}]), "empty group", "named slice"),
    (_set([], "variants", "x"), "list expected", "variants"),
    (_set(["variants"], 0, 5), "object expected", "variant 1"),
    (_set(["variants", 0], "extra", 1), "unknown field", "variant А"),
    (_del(["variants", 0], "calls"), "field 'calls' is missing", "variant А"),
    (_set(["variants", 0], "title", 5), "title must be a text", "variant А"),
    (_set(["variants", 0], "calls", [["a", "b"]]), "list of [name, name, name, name] expected", "calls"),
    (_set(["variants", 0], "side", "third"), "side must be", "variant А"),
    (_set(["variants", 0], "params", {"p": 1}), "{parameter: executor}", "params"),
    (_set(["variants", 0], "entities", "x"), "list of names expected", "entities"),
    (_set(["variants", 0], "initial", {"Бельё": "x"}), "{entity: {axis: value}}", "initial"),
    (_set(["variants", 0], "out_of_comparison", ""), "out_of_comparison must be a reason", "variant А"),
    (_set([], "normalization", []), "object expected", "normalization"),
    (_set(["normalization"], "extra", 1), "unknown field", "normalization"),
    (_del(["normalization"], "kind_costs"), "field 'kind_costs' is missing", "normalization"),
    (_set(["normalization", "kind_costs"], "Развесить", "2"), "number expected", "kind_costs"),
    (_set(["normalization", "kind_costs"], "Развесить", True), "number expected", "kind_costs"),
    (_set(["normalization"], "executor_coefficients", []), "object expected", "executor_coefficients"),
    (_set(["normalization", "scope_coefficients"], "вся загрузка", None), "number expected",
     "scope_coefficients"),
    (_set(["normalization"], "axis_skip_prices", []), "object expected", "axis_skip_prices"),
    (_set(["normalization", "axis_skip_prices", "Бельё"], "цвета", "3"), "number expected", "Бельё"),
    (_set(["normalization"], "batch_size", "10"), "number expected", "batch_size"),
    (_set(["normalization"], "uncounted_errors", []), "object expected", "uncounted_errors"),
    (_set(["normalization", "uncounted_errors"], "Вне модели", "x"), "list of texts expected",
     "uncounted_errors"),
]


@pytest.mark.parametrize("mutate,fragment,where", STAGE1)
def test_stage1_rules(mutate, fragment, where):
    d = base()
    mutate(d)
    assert has(remarks_of(d), fragment, where)


def test_top_level_not_object():
    assert has(remarks_of([]), "object expected", "file")


# ---------- stage 2: dictionary ----------

def _dup(path, index):
    def f(d):
        t = d
        for p in path:
            t = t[p]
        t.append(copy.deepcopy(t[index]))
    return f


def _kind_set(name, **kw):
    return lambda d: kind(d, name).update(kw)


def _inherit(d):
    d["entities"][0]["axes"][0]["inherit"] = [["Нет такой", "ось"]]


def _no_absent(d):
    d["entities"][1]["axes"][0]["values"] = ["есть"]


def _slice_group(**kw):
    def f(d):
        d["named_slices"]["постирано"]["any"] = [kw]
    return f


DICTIONARY = [
    (_dup(["entities"], 1), "entity repeats", "entities"),
    (_dup(["entities", 0, "axes"], 1), "axis repeats", "entity Бельё"),
    (lambda d: d["entities"][0]["axes"][1]["values"].append("проверены"), "value repeats", "карманы"),
    (lambda d: d["entities"][0]["axes"][1].update(values=[]), "no values", "карманы"),
    (_inherit, "unknown inherit source", "состояние"),
    (_no_absent, "existence axis lacks the value", "Цикл стирки"),
    (_dup(["kinds"], 0), "kind repeats", "kinds"),
    (lambda d: d["executors"].append("Человек"), "executor repeats", "executors"),
    (lambda d: d["instruments"].append("руки"), "instrument repeats", "instruments"),
    (lambda d: d["scopes"].append("вся загрузка"), "scope repeats", "scopes"),
    (lambda d: d.update(variant_params=["p", "p"]), "variant parameter repeats", "variant_params"),
    (lambda d: d.update(batch_scope="нигде"), "is not among the scopes", "batch_scope"),
    (_kind_set("Развесить", entity="Нет"), "unknown entity", "kind Развесить"),
    (_kind_set("Развесить", axis="нет"), "unknown axis", "kind Развесить"),
    (_kind_set("Развесить", to="нет"), "unknown value", "kind Развесить"),
    (_kind_set("Развесить", to="постирано"), "from equals to", "kind Развесить"),
    (_kind_set("Постирать", requires=[["Цикл стирки", "наличие", "возможно"]]),
     "condition: unknown", "kind Постирать"),
    (_kind_set("Постирать", requires=[["Бельё", "состояние", "грязное"]]),
     "condition on its own axis", "kind Постирать"),
    (lambda d: d["named_slices"].update(final=d["named_slices"]["постирано"]), "reserved", "named slice final"),
    (_slice_group(states=[["Бельё", "состояние", "мокрое"]]), "unknown Бельё/состояние=мокрое",
     "named slice постирано"),
    (_slice_group(params=[["p", "Человек"]]), "unknown variant parameter p", "named slice"),
    (lambda d: (d.update(variant_params=["p"]),
                variant(d, "А").update(params={"p": "Человек"}),
                variant(d, "Б").update(params={"p": "Человек"}),
                variant(d, "В").update(params={"p": "Человек"}),
                d["named_slices"]["постирано"].update(any=[{"params": [["p", "Робот"]]}])),
     "unknown executor Робот", "named slice"),
]


@pytest.mark.parametrize("mutate,fragment,where", DICTIONARY)
def test_dictionary_rules(mutate, fragment, where):
    d = base()
    mutate(d)
    assert has(remarks_of(d), fragment, where)


# ---------- stage 2: variant names ----------

def _call_set(i, pos, value):
    def f(d):
        variant(d, "Б")["calls"][i][pos] = value
    return f


VARIANT_NAMES = [
    (lambda d: d["variants"].append(copy.deepcopy(d["variants"][0])), "variant code repeats", "variants"),
    (lambda d: d.update(variant_params=["p"]), "variant parameter p not set", "variant А"),
    (lambda d: variant(d, "А").update(params={"q": "Человек"}), "unknown variant parameter q", "variant А"),
    (lambda d: (d.update(variant_params=["p"]),
                [v.update(params={"p": "Человек"}) for v in d["variants"]],
                variant(d, "А").update(params={"p": "Робот"})),
     "parameter p: unknown executor Робот", "variant А"),
    (lambda d: variant(d, "А").update(entities=["Нет"]), "unknown entity Нет", "variant А"),
    (lambda d: variant(d, "А").update(initial={"Бельё": {"состояние": "мокрое"}}),
     "unknown Бельё/состояние=мокрое", "variant А, initial"),
    (_call_set(0, 0, "Нет такого"), "unknown kind Нет такого", "variant Б, call 1"),
    (_call_set(0, 1, "Робот"), "unknown executor Робот", "variant Б, call 1"),
    (_call_set(0, 2, "лопата"), "unknown instrument лопата", "variant Б, call 1"),
    (_call_set(0, 3, "всё"), "unknown scope всё", "variant Б, call 1"),
]


@pytest.mark.parametrize("mutate,fragment,where", VARIANT_NAMES)
def test_variant_name_rules(mutate, fragment, where):
    d = base()
    mutate(d)
    assert has(remarks_of(d), fragment, where)


# ---------- stage 2: normalization ----------

def _norm(section, key, value):
    def f(d):
        d["normalization"][section][key] = value
    return f


def _norm_del(section, key):
    def f(d):
        del d["normalization"][section][key]
    return f


NORMALIZATION = [
    (_norm("kind_costs", "Дождаться высыхания", 1), "has zero_weight, its cost must be 0", "kind_costs"),
    (_norm_del("kind_costs", "Развесить"), "kind without cost: Развесить", "kind_costs"),
    (_norm("kind_costs", "Лишний", 1), "cost of unknown kind: Лишний", "kind_costs"),
    (_norm("kind_costs", "Развесить", -1), "kind Развесить: cost below zero", "kind_costs"),
    (_norm_del("executor_coefficients", "Машина"), "executor without coefficient: Машина",
     "executor_coefficients"),
    (_norm("executor_coefficients", "Робот", 1), "coefficient of unknown executor: Робот",
     "executor_coefficients"),
    (_norm("executor_coefficients", "Человек", -1), "executor Человек: coefficient below zero",
     "executor_coefficients"),
    (_norm_del("scope_coefficients", "вся загрузка"), "scope without coefficient: вся загрузка",
     "scope_coefficients"),
    (_norm("scope_coefficients", "всё", 1), "coefficient of unknown scope: всё", "scope_coefficients"),
    (_norm("scope_coefficients", "вся загрузка", -1), "scope вся загрузка: coefficient below zero",
     "scope_coefficients"),
    (lambda d: d["normalization"]["axis_skip_prices"]["Бельё"].pop("цвета"),
     "check axis without skip price: Бельё/цвета", "axis_skip_prices"),
    (lambda d: d["normalization"]["axis_skip_prices"]["Бельё"].update({"состояние": 1}),
     "Бельё/состояние is not a check axis", "axis_skip_prices"),
    (lambda d: d["normalization"]["axis_skip_prices"]["Бельё"].update({"цвета": 0}),
     "Бельё/цвета: price must be above zero", "axis_skip_prices"),
    (lambda d: d["normalization"].update(batch_size=0), "must be above zero", "batch_size"),
]


@pytest.mark.parametrize("mutate,fragment,where", NORMALIZATION)
def test_normalization_rules(mutate, fragment, where):
    d = base()
    mutate(d)
    assert has(remarks_of(d), fragment, where)


# ---------- stage 3 ----------

def _add_kind(d, name, src, dst, cost=1, **kw):
    k = {"name": name, "entity": "Бельё", "axis": "состояние", "from": src, "to": dst}
    k.update(kw)
    d["kinds"].append(k)
    d["normalization"]["kind_costs"][name] = cost


def test_variant_run_failure():
    d = base()
    del variant(d, "Б")["calls"][0]  # no wash cycle: the washing has no required condition
    r = remarks_of(d)
    assert r and all(x.where == "" for x in r)


def test_duplicate_kinds():
    d = base()
    _add_kind(d, "Повесить", "постирано", "развешано")
    assert has(remarks_of(d), "same change of state", "kinds")


def test_decomposable_kinds():
    d = base()
    _add_kind(d, "Постирать и развесить", "грязное", "развешано")
    assert has(remarks_of(d), "repeats the chain", "kinds")


# ---------- all remarks, stage order ----------

def test_several_remarks_in_one_stage():
    d = base()
    del d["normalization"]["kind_costs"]["Развесить"]
    del d["normalization"]["kind_costs"]["Убрать в шкаф"]
    r = remarks_of(d)
    assert len([x for x in r if "kind without cost" in x.text]) == 2


def test_structure_mistake_stops_before_stage2():
    d = base()
    d["name"] = 5
    kind(d, "Развесить")["entity"] = "Нет"  # stage 2 mistake
    r = remarks_of(d)
    assert len(r) == 1 and r[0].where == "name"
    assert not has(r, "unknown entity")


def test_dictionary_mistake_stops_norm_and_runs():
    d = base()
    kind(d, "Развесить")["entity"] = "Нет"
    del d["normalization"]["kind_costs"]["Убрать в шкаф"]
    r = remarks_of(d)
    assert has(r, "unknown entity")
    assert not has(r, "kind without cost")


# ---------- text and file ----------

def test_invalid_json_one_remark():
    project, remarks = parse_text("{\n  \"a\": ,\n}")
    assert project is None and len(remarks) == 1
    assert "line 2" in remarks[0].text and "column" in remarks[0].text


def test_missing_file(tmp_path):
    project, remarks = load_file(tmp_path / "none.json")
    assert project is None and len(remarks) == 1
    assert "cannot read" in remarks[0].text


# ---------- zero_weight ----------

def test_zero_weight_cost_absent_ok():
    d = base()
    del d["normalization"]["kind_costs"]["Дождаться высыхания"]
    project, remarks = read_project(d)
    assert remarks == [] and project is not None


def test_zero_weight_cost_zero_ok():
    d = base()
    d["normalization"]["kind_costs"]["Дождаться высыхания"] = 0
    project, remarks = read_project(d)
    assert remarks == []


def test_zero_weight_cost_one_is_remark():
    d = base()
    d["normalization"]["kind_costs"]["Дождаться высыхания"] = 1
    assert has(remarks_of(d), "zero_weight")


# ---------- task ----------

def test_laundry_has_one_task():
    project, remarks = load_file(LAUNDRY)
    assert remarks == []
    assert project.tasks == {"А": "Постирать бельё", "Б": "Постирать бельё", "В": "Постирать бельё"}


def test_task_reaches_project():
    d = base()
    variant(d, "А")["task"] = "Постирать бельё"
    variant(d, "Б")["task"] = " Постирать бельё "
    project, remarks = read_project(d)
    assert remarks == []
    assert project.tasks == {"А": "Постирать бельё", "Б": " Постирать бельё ", "В": "Постирать бельё"}


@pytest.mark.parametrize("value", ["", "   ", "\t\n", 5, True, None, ["x"], {"a": "b"}])
def test_task_must_be_a_text(value):
    d = base()
    variant(d, "Б")["task"] = value
    assert has(remarks_of(d), "task must be a text", "variant Б")
