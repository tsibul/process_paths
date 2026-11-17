# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of adding dictionary words: the word goes to the end of its list and the data equals
the data of the same word written in a file."""

import copy
import json

import pytest

from procnorm import edit
from procnorm.project import read_project

# Made-up project with one variant parameter and two variants.
BASE = json.loads("""
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed"]}
    ]},
    {"name": "Box", "axes": [
      {"name": "presence", "values": ["none", "present"]}
    ]}
  ],
  "kinds": [
    {"name": "Pack", "entity": "Order", "axis": "status", "from": "new", "to": "packed"}
  ],
  "executors": ["Clerk", "Robot"],
  "instruments": ["Hands"],
  "scopes": ["Each", "Batch"],
  "batch_scope": "Batch",
  "variant_params": ["Packer"],
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {"Packer": "Clerk"},
     "calls": [["Pack", "Clerk", "Hands", "Each"]]},
    {"code": "V2", "title": "Second", "side": "own", "task": "Ship",
     "params": {"Packer": "Robot"},
     "calls": [["Pack", "Robot", "Hands", "Batch"]]}
  ],
  "normalization": {
    "kind_costs": {},
    "executor_coefficients": {},
    "scope_coefficients": {},
    "axis_skip_prices": {}
  }
}
""")


def _no_variants(data):
    data = copy.deepcopy(data)
    data["variants"] = []
    return data


def _edited(what, name, **kwargs):
    new, remarks = edit.add_word(BASE, what, name, **kwargs)
    assert remarks == []
    assert new is not None
    return new


def _same_as_file(new, expected):
    assert new == expected
    project, remarks = read_project(expected, strict=False)
    assert remarks == []
    assert project is not None


def test_entity_equals_file():
    expected = copy.deepcopy(BASE)
    expected["entities"].append({"name": "Parcel", "axes": []})
    _same_as_file(_edited("entity", "Parcel"), expected)


def test_axis_with_first_value_equals_file():
    expected = copy.deepcopy(BASE)
    expected["entities"][0]["axes"].append({"name": "label", "values": ["unchecked"]})
    _same_as_file(_edited("axis", ("Order", "label"), first_value="unchecked"), expected)


def test_value_equals_file():
    expected = copy.deepcopy(BASE)
    expected["entities"][0]["axes"][0]["values"].append("sent")
    _same_as_file(_edited("value", ("Order", "status", "sent")), expected)


@pytest.mark.parametrize("what, key", [
    ("executor", "executors"),
    ("instrument", "instruments"),
    ("scope", "scopes"),
])
def test_simple_words_equal_file(what, key):
    expected = copy.deepcopy(BASE)
    expected[key].append("Newcomer")
    _same_as_file(_edited(what, "Newcomer"), expected)


def test_words_go_to_the_end():
    assert _edited("executor", "Newcomer")["executors"] == ["Clerk", "Robot", "Newcomer"]
    assert _edited("scope", "Newcomer")["scopes"][-1] == "Newcomer"
    assert _edited("entity", "Parcel")["entities"][-1]["name"] == "Parcel"
    axes = _edited("axis", ("Order", "label"), first_value="x")["entities"][0]["axes"]
    assert [a["name"] for a in axes] == ["status", "label"]
    values = _edited("value", ("Order", "status", "sent"))["entities"][0]["axes"][0]["values"]
    assert values == ["new", "packed", "sent"]


def test_name_is_trimmed():
    assert _edited("executor", "  Newcomer ")["executors"][-1] == "Newcomer"


@pytest.mark.parametrize("what, name, kwargs", [
    ("entity", "Order", {}),
    ("axis", ("Order", "status"), {"first_value": "new"}),
    ("value", ("Order", "status", "new"), {}),
    ("executor", "Clerk", {}),
    ("instrument", "Hands", {}),
    ("scope", "Each", {}),
    ("variant_param", "Packer", {"executor": "Clerk"}),
])
def test_repeat_refused(what, name, kwargs):
    new, remarks = edit.add_word(BASE, what, name, **kwargs)
    assert new is None
    assert remarks


@pytest.mark.parametrize("what, name, kwargs", [
    ("entity", "", {}),
    ("entity", "   ", {}),
    ("axis", ("Order", " "), {"first_value": "x"}),
    ("axis", ("Order", "label"), {"first_value": " "}),
    ("value", ("Order", "status", ""), {}),
    ("executor", "", {}),
    ("instrument", " ", {}),
    ("scope", "", {}),
    ("variant_param", "", {"executor": "Clerk"}),
])
def test_empty_name_refused(what, name, kwargs):
    new, remarks = edit.add_word(BASE, what, name, **kwargs)
    assert new is None
    assert remarks


@pytest.mark.parametrize("first_value", [None, ""])
def test_axis_without_first_value_refused(first_value):
    new, remarks = edit.add_word(BASE, "axis", ("Order", "label"), first_value=first_value)
    assert new is None
    assert remarks


def test_unknown_owner_refused():
    assert edit.add_word(BASE, "axis", ("Nobody", "x"), first_value="y")[0] is None
    assert edit.add_word(BASE, "value", ("Order", "nothing", "y"))[0] is None
    assert edit.add_word(BASE, "value", ("Nobody", "status", "y"))[0] is None


def test_unknown_kind_and_bad_shape_refused():
    assert edit.add_word(BASE, "kind", "Ship")[0] is None
    assert edit.add_word(BASE, "axis", "label", first_value="x")[0] is None
    assert edit.add_word(BASE, "value", ("Order", "status"))[0] is None


def test_existence_axis_needs_absent_value():
    new, remarks = edit.add_word(BASE, "axis", ("Order", "presence"), first_value="present")
    assert new is None
    assert remarks
    new, remarks = edit.add_word(BASE, "axis", ("Order", "presence"), first_value="none")
    assert remarks == []
    assert new is not None


def test_param_without_variants_needs_no_executor():
    base = _no_variants(BASE)
    new, remarks = edit.add_word(base, "variant_param", "Sender")
    assert remarks == []
    assert new["variant_params"] == ["Packer", "Sender"]


def test_param_with_variants_without_executor_refused():
    new, remarks = edit.add_word(BASE, "variant_param", "Sender")
    assert new is None
    assert remarks


def test_param_with_variants_and_unknown_executor_refused():
    new, remarks = edit.add_word(BASE, "variant_param", "Sender", executor="Ghost")
    assert new is None
    assert remarks


def test_param_with_executor_set_for_all_variants():
    new = _edited("variant_param", "Sender", executor="Robot")
    assert new["variant_params"] == ["Packer", "Sender"]
    assert [v["params"] for v in new["variants"]] == [
        {"Packer": "Clerk", "Sender": "Robot"},
        {"Packer": "Robot", "Sender": "Robot"},
    ]


def test_param_with_variants_without_params_key():
    base = copy.deepcopy(BASE)
    base["variant_params"] = []
    for v in base["variants"]:
        del v["params"]
    new, remarks = edit.add_word(base, "variant_param", "Sender", executor="Clerk")
    assert remarks == []
    assert [v["params"] for v in new["variants"]] == [{"Sender": "Clerk"}] * 2


def test_param_added_to_project_without_the_list():
    base = _no_variants(BASE)
    del base["variant_params"]
    new, remarks = edit.add_word(base, "variant_param", "Sender")
    assert remarks == []
    assert new["variant_params"] == ["Sender"]


def test_argument_not_mutated():
    before = copy.deepcopy(BASE)
    edit.add_word(BASE, "variant_param", "Sender", executor="Robot")
    edit.add_word(BASE, "executor", "Newcomer")
    edit.add_word(BASE, "executor", "Clerk")
    edit.add_word(BASE, "axis", ("Order", "label"), first_value="x")
    assert BASE == before
