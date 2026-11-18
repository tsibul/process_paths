# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of ``edit.set_number``: a number of the normalization set, changed or cleared."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from procnorm.edit import set_number
from procnorm.project import read_project

TEXT = (Path(__file__).parent / "data" / "laundry.json").read_text(encoding="utf-8")


def base() -> dict:
    return json.loads(TEXT, parse_float=Decimal)


def from_file(table: str, key, number: str) -> dict:
    """The same number written into the file text and read back."""
    d = base()
    n = d["normalization"]
    if table == "axis_skip_prices":
        n[table][key[0]][key[1]] = json.loads(number, parse_float=Decimal)
    else:
        n[table][key] = json.loads(number, parse_float=Decimal)
    return d


@pytest.mark.parametrize("table,key,text,number", [
    ("kind_costs", "Постирать", "5", "5"),
    ("kind_costs", "Постирать", "2.5", "2.5"),
    ("executor_coefficients", "Человек", "0", "0"),
    ("executor_coefficients", "Машина", "0.25", "0.25"),
    ("scope_coefficients", "вся загрузка", "3", "3"),
    ("axis_skip_prices", ("Бельё", "цвета"), "7.5", "7.5"),
])
def test_number_equals_number_in_file(table, key, text, number):
    data, remarks = set_number(base(), table, key, text)
    assert remarks == []
    assert data == from_file(table, key, number)
    assert json.dumps(data, default=str) == json.dumps(from_file(table, key, number), default=str)


def test_comma_and_point_both_accepted():
    a, ra = set_number(base(), "kind_costs", "Постирать", "2,5")
    b, rb = set_number(base(), "kind_costs", "Постирать", "2.5")
    assert ra == rb == [] and a == b == from_file("kind_costs", "Постирать", "2.5")


def test_spaces_around_are_ignored():
    data, remarks = set_number(base(), "kind_costs", "Постирать", "  4 ")
    assert remarks == [] and data == from_file("kind_costs", "Постирать", "4")


def test_input_is_not_changed_and_result_is_a_read_project():
    d = base()
    before = copy.deepcopy(d)
    data, remarks = set_number(d, "kind_costs", "Постирать", "9")
    assert d == before and data is not d
    project, rem = read_project(data, strict=False)
    assert project is not None and rem == []


@pytest.mark.parametrize("table,key", [
    ("kind_costs", "Постирать"),
    ("executor_coefficients", "Машина"),
    ("scope_coefficients", "вся загрузка"),
    ("axis_skip_prices", ("Бельё", "цвета")),
])
def test_empty_text_removes_the_key(table, key):
    data, remarks = set_number(base(), table, key, "  ")
    assert remarks == []
    n = data["normalization"][table]
    if table == "axis_skip_prices":
        assert "цвета" not in n.get("Бельё", {})
    else:
        assert key not in n
    project, rem = read_project(data, strict=False)
    assert project is not None and rem == []
    assert read_project(data)[0] is None


def test_empty_text_on_absent_key_is_fine():
    data, _ = set_number(base(), "kind_costs", "Постирать", "")
    again, remarks = set_number(data, "kind_costs", "Постирать", "")
    assert remarks == [] and again == data


@pytest.mark.parametrize("text", ["abc", "1.2.3", "1,2,3", "nan", "inf", "-inf", "1e400000000", "--1", "5 kg"])
def test_not_a_number_refused(text):
    d = base()
    data, remarks = set_number(d, "kind_costs", "Постирать", text)
    assert data is None and remarks and "number" in str(remarks[0])
    assert d == base()


@pytest.mark.parametrize("table,key", [
    ("kind_costs", "Постирать"),
    ("executor_coefficients", "Машина"),
    ("scope_coefficients", "вся загрузка"),
])
def test_below_zero_refused(table, key):
    data, remarks = set_number(base(), table, key, "-1")
    assert data is None and "below zero" in str(remarks[0])


@pytest.mark.parametrize("text", ["0", "-2", "0,0"])
def test_price_zero_or_less_refused(text):
    data, remarks = set_number(base(), "axis_skip_prices", ("Бельё", "цвета"), text)
    assert data is None and "above zero" in str(remarks[0])


def test_zero_weight_kind_refused():
    kind = next(k["name"] for k in base()["kinds"] if k.get("zero_weight"))
    for text in ("0", "3", ""):
        data, remarks = set_number(base(), "kind_costs", kind, text)
        assert data is None and "zero weight" in str(remarks[0])


@pytest.mark.parametrize("table,key", [
    ("kind_costs", "Нет такого"),
    ("executor_coefficients", "Нет такого"),
    ("scope_coefficients", "нет такого"),
    ("axis_skip_prices", ("Бельё", "состояние")),
    ("axis_skip_prices", ("Нет", "цвета")),
    ("no_such_table", "x"),
])
def test_unknown_place_refused(table, key):
    data, remarks = set_number(base(), table, key, "1")
    assert data is None and remarks
