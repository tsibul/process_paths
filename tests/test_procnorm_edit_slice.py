# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of adding and changing named slices: a slice made by an edit equals the same slice read
from a file, the refusals are the refusals of the read."""

import copy
import json

from measure_twice import edit
from measure_twice.project import read_project

# Made-up project: an order with a status and a flag, a variant parameter with two executors.
BASE = json.loads("""
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed", "sent"]},
      {"name": "weighed", "values": ["no", "yes"]}
    ]}
  ],
  "kinds": [
    {"name": "Pack", "entity": "Order", "axis": "status", "from": "new", "to": "packed"},
    {"name": "Send", "entity": "Order", "axis": "status", "from": "packed", "to": "sent"}
  ],
  "executors": ["Clerk", "Robot"],
  "instruments": ["Hands"],
  "scopes": ["Each", "Batch"],
  "batch_scope": "Batch",
  "variant_params": ["carrier"],
  "named_slices": {
    "packed": {"any": [{"states": [["Order", "status", "packed"]]}]}
  },
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {"carrier": "Clerk"},
     "calls": [["Pack", "Clerk", "Hands", "Each"], ["Send", "Clerk", "Hands", "Each"]]}
  ],
  "normalization": {
    "kind_costs": {"Pack": 3, "Send": 2},
    "executor_coefficients": {"Clerk": 1, "Robot": 0},
    "scope_coefficients": {"Each": 1, "Batch": 1},
    "axis_skip_prices": {}
  }
}
""")

TWO_GROUPS = [
    [("Order", "status", "sent"), ("Order", "weighed", "yes")],
    [("carrier", "Robot")],
]

TWO_GROUPS_IN_FILE = {"any": [
    {"states": [["Order", "status", "sent"], ["Order", "weighed", "yes"]]},
    {"params": [["carrier", "Robot"]]},
]}


def _refused(result):
    new, remarks = result
    assert new is None
    assert remarks
    return remarks[0].text


def test_add_slice_equals_slice_from_file():
    from_file = copy.deepcopy(BASE)
    from_file["named_slices"]["shipped"] = TWO_GROUPS_IN_FILE
    before = copy.deepcopy(BASE)
    new, remarks = edit.add_slice(BASE, "shipped", TWO_GROUPS)
    assert remarks == []
    assert BASE == before
    assert new["named_slices"] == from_file["named_slices"]
    assert list(new["named_slices"]) == ["packed", "shipped"]
    assert read_project(new, strict=False)[0] is not None


def test_add_slice_to_project_without_slices():
    data = copy.deepcopy(BASE)
    del data["named_slices"]
    new, remarks = edit.add_slice(data, "sent", [[("Order", "status", "sent")]])
    assert remarks == []
    assert new["named_slices"] == {
        "sent": {"any": [{"states": [["Order", "status", "sent"]]}]}}


def test_add_slice_accepts_group_as_dictionary_and_lists():
    group = {"states": [["Order", "status", "sent"]], "params": [["carrier", "Robot"]]}
    new, remarks = edit.add_slice(BASE, "both", [group])
    assert remarks == []
    assert new["named_slices"]["both"] == {"any": [group]}


def test_add_slice_trims_the_name():
    new, remarks = edit.add_slice(BASE, "  shipped ", TWO_GROUPS)
    assert remarks == []
    assert "shipped" in new["named_slices"]


def test_set_slice_replaces_groups_and_keeps_place():
    data = copy.deepcopy(BASE)
    data["named_slices"]["shipped"] = TWO_GROUPS_IN_FILE
    before = copy.deepcopy(data)
    new, remarks = edit.set_slice(data, "packed", [[("Order", "weighed", "yes")]])
    assert remarks == []
    assert data == before
    assert list(new["named_slices"]) == ["packed", "shipped"]
    assert new["named_slices"]["packed"] == {
        "any": [{"states": [["Order", "weighed", "yes"]]}]}
    assert new["named_slices"]["shipped"] == TWO_GROUPS_IN_FILE


def test_refuse_final():
    assert "final" in _refused(edit.add_slice(BASE, "final", TWO_GROUPS))


def test_refuse_repeat():
    assert "taken" in _refused(edit.add_slice(BASE, "packed", TWO_GROUPS))


def test_refuse_empty_name():
    assert _refused(edit.add_slice(BASE, "  ", TWO_GROUPS))
    assert _refused(edit.add_slice(BASE, 5, TWO_GROUPS))


def test_refuse_empty_group():
    assert "empty" in _refused(edit.add_slice(BASE, "x", [[("Order", "status", "sent")], []]))
    assert "empty" in _refused(edit.add_slice(BASE, "x", [{"states": [], "params": []}]))


def test_refuse_no_groups():
    assert "group" in _refused(edit.add_slice(BASE, "x", []))
    assert _refused(edit.add_slice(BASE, "x", None))


def test_refuse_bad_rows():
    assert _refused(edit.add_slice(BASE, "x", [[("Order", "status", "sent", "extra")]]))
    assert _refused(edit.add_slice(BASE, "x", [[("Order", "status", 5)]]))
    assert _refused(edit.add_slice(BASE, "x", ["Order"]))


def test_refuse_unknown_names():
    assert "unknown" in _refused(edit.add_slice(BASE, "x", [[("Box", "status", "sent")]]))
    assert "unknown" in _refused(edit.add_slice(BASE, "x", [[("Order", "status", "lost")]]))
    assert "unknown" in _refused(edit.add_slice(BASE, "x", [[("size", "Robot")]]))
    assert "unknown" in _refused(edit.add_slice(BASE, "x", [[("carrier", "Nobody")]]))


def test_set_slice_refusals():
    assert "no such" in _refused(edit.set_slice(BASE, "absent", TWO_GROUPS))
    assert "final" in _refused(edit.set_slice(BASE, "final", TWO_GROUPS))
    assert "empty" in _refused(edit.set_slice(BASE, "packed", [[]]))
    assert "group" in _refused(edit.set_slice(BASE, "packed", []))
    assert "unknown" in _refused(edit.set_slice(BASE, "packed", [[("Order", "status", "no")]]))
