# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of moving dictionary words, the batch scope and the existence axis words."""

import copy
import json

import pytest

from procnorm import edit
from procnorm.calc import compare
from procnorm.project import read_project

# Made-up project: two entities with the existence axis, two kinds, two variants.
BASE = json.loads("""
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed", "sent"]},
      {"name": "priority", "values": ["low", "high"]}
    ]},
    {"name": "Box", "axes": [
      {"name": "presence", "values": ["none", "present"]}
    ]},
    {"name": "Label", "axes": [
      {"name": "presence", "values": ["none", "present"]}
    ]}
  ],
  "kinds": [
    {"name": "Pack", "entity": "Order", "axis": "status", "from": "new", "to": "packed"},
    {"name": "Take box", "entity": "Box", "axis": "presence", "from": "none", "to": "present"}
  ],
  "executors": ["Clerk", "Robot"],
  "instruments": ["Hands", "Tape"],
  "scopes": ["Each", "Batch"],
  "batch_scope": "Batch",
  "variant_params": ["Packer", "Checker"],
  "named_slices": {
    "boxed": {"any": [{"states": [["Box", "presence", "present"]]}]},
    "packed": {"any": [{"states": [["Order", "status", "packed"]]}]}
  },
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {"Packer": "Clerk", "Checker": "Robot"},
     "calls": [["Take box", "Clerk", "Hands", "Each"], ["Pack", "Clerk", "Hands", "Each"]]},
    {"code": "V2", "title": "Second", "side": "own", "task": "Ship",
     "params": {"Packer": "Robot", "Checker": "Clerk"},
     "calls": [["Take box", "Robot", "Hands", "Batch"], ["Pack", "Robot", "Hands", "Batch"]]}
  ],
  "normalization": {
    "kind_costs": {"Pack": 3},
    "executor_coefficients": {},
    "scope_coefficients": {},
    "axis_skip_prices": {}
  }
}
""")


def _moved(what, name, delta):
    new, remarks = edit.move_word(BASE, what, name, delta)
    assert remarks == []
    assert new is not None
    return new


def _names(items):
    return [x["name"] for x in items]


def test_move_entity_down():
    new = _moved("entity", "Order", 1)
    assert _names(new["entities"]) == ["Box", "Order", "Label"]


def test_move_axis_up():
    new = _moved("axis", ("Order", "priority"), -1)
    assert _names(new["entities"][0]["axes"]) == ["priority", "status"]


def test_move_value_down():
    new = _moved("value", ("Order", "status", "packed"), 1)
    assert new["entities"][0]["axes"][0]["values"] == ["new", "sent", "packed"]


def test_move_kind():
    new = _moved("kind", "Take box", -1)
    assert _names(new["kinds"]) == ["Take box", "Pack"]


@pytest.mark.parametrize("what, name, key", [
    ("executor", "Robot", "executors"),
    ("instrument", "Tape", "instruments"),
    ("scope", "Batch", "scopes"),
    ("variant_param", "Checker", "variant_params"),
])
def test_move_simple_lists_up(what, name, key):
    new = _moved(what, name, -1)
    assert new[key] == [name] + [x for x in BASE[key] if x != name]


def test_move_named_slice():
    new = _moved("named_slice", "boxed", 1)
    assert list(new["named_slices"]) == ["packed", "boxed"]
    assert new["named_slices"]["boxed"] == BASE["named_slices"]["boxed"]


def test_move_keeps_the_argument():
    before = copy.deepcopy(BASE)
    edit.move_word(BASE, "entity", "Order", 1)
    assert BASE == before


@pytest.mark.parametrize("what, name, delta", [
    ("entity", "Order", -1),
    ("entity", "Label", 1),
    ("axis", ("Order", "status"), -1),
    ("axis", ("Order", "priority"), 1),
    ("value", ("Order", "status", "sent"), 1),
    ("kind", "Pack", -1),
    ("scope", "Batch", 1),
])
def test_move_past_the_edge_is_refused(what, name, delta):
    new, remarks = edit.move_word(BASE, what, name, delta)
    assert new is None
    assert remarks


@pytest.mark.parametrize("what, name, delta", [
    ("entity", "Nobody", 1),
    ("axis", ("Order", "none"), 1),
    ("value", ("Order", "status", "gone"), 1),
    ("axis", "Order", 1),
    ("kind", ("a",), 1),
    ("colour", "Red", 1),
    ("entity", "Order", 0),
    ("entity", "Order", 2),
    ("entity", "Order", "up"),
])
def test_bad_move_is_refused(what, name, delta):
    new, remarks = edit.move_word(BASE, what, name, delta)
    assert new is None
    assert remarks


def test_move_first_value_keeps_project_readable_and_variant_gets_error():
    new = _moved("value", ("Order", "status", "new"), 1)
    assert new["entities"][0]["axes"][0]["values"] == ["packed", "new", "sent"]
    project, remarks = read_project(new, strict=False)
    assert remarks == []
    assert project is not None
    assert set(project.errors) == {"V1", "V2"}
    assert [code for code, _, _ in compare(project).excluded] == ["V1", "V2"]


def test_set_batch_scope():
    new, remarks = edit.set_batch_scope(BASE, "Each")
    assert remarks == []
    assert new["batch_scope"] == "Each"
    assert new["scopes"] == BASE["scopes"]
    assert BASE["batch_scope"] == "Batch"


def test_unknown_batch_scope_is_refused():
    new, remarks = edit.set_batch_scope(BASE, "Pallet")
    assert new is None
    assert remarks


def test_non_text_batch_scope_is_refused():
    new, remarks = edit.set_batch_scope(BASE, None)
    assert new is None
    assert remarks


def test_existence_axis_changes_everywhere_and_compare_is_the_same():
    new, remarks = edit.set_existence_axis(BASE, "exists", "gone")
    assert remarks == []
    assert new["existence_axis"] == {"name": "exists", "absent": "gone"}
    for entity in new["entities"][1:]:
        assert entity["axes"] == [{"name": "exists", "values": ["gone", "present"]}]
    assert new["kinds"][1]["axis"] == "exists"
    assert new["kinds"][1]["from"] == "gone"
    assert new["named_slices"]["boxed"]["any"][0]["states"] == [["Box", "exists", "present"]]
    before, _ = read_project(BASE, strict=False)
    after, remarks = read_project(new, strict=False)
    assert remarks == []
    assert compare(after) == compare(before)


def test_existence_axis_value_only():
    new, remarks = edit.set_existence_axis(BASE, "presence", "gone")
    assert remarks == []
    assert new["existence_axis"] == {"name": "presence", "absent": "gone"}
    assert new["kinds"][1]["from"] == "gone"


def test_existence_axis_taken_name_is_refused():
    new, remarks = edit.set_existence_axis(BASE, "status", "none")
    assert new is None
    assert remarks


@pytest.mark.parametrize("name, value", [("", "none"), ("presence", "  "), (None, "none"),
                                         ("presence", 5)])
def test_existence_axis_empty_or_not_text_is_refused(name, value):
    new, remarks = edit.set_existence_axis(BASE, name, value)
    assert new is None
    assert remarks
