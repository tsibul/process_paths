# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of adding a variant and changing its header: a variant made by edits equals the same
variant read from a file without steps, the refusals are the refusals of the read."""

import copy
import json
from decimal import Decimal
from pathlib import Path

from procnorm import edit
from procnorm.project import read_project

LAUNDRY = json.loads(
    (Path(__file__).parent / "data" / "laundry.json").read_text("utf-8"), parse_float=Decimal)

# Made-up project: two entities, a variant parameter, two executors.
BASE = json.loads("""
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed", "sent"]}
    ]},
    {"name": "Box", "axes": [
      {"name": "lid", "values": ["open", "closed"]}
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
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {"carrier": "Robot"},
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


def _refused(result):
    new, remarks = result
    assert new is None
    assert remarks
    return remarks[0].text


def _find(data, code):
    return next(v for v in data["variants"] if v["code"] == code)


def test_variant_from_edits_equals_variant_from_file():
    full = _find(LAUNDRY, "Б")
    expected = {k: v for k, v in full.items() if k != "steps"}
    data = copy.deepcopy(LAUNDRY)
    data["variants"].remove(_find(data, "Б"))
    before = copy.deepcopy(data)
    new, remarks = edit.add_variant(
        data, "Б", "Быстрая стирка", side="other", task="Постирать бельё")
    assert remarks == []
    assert data == before
    for number, call in enumerate(full["calls"]):
        new, remarks = edit.add_call(new, "Б", number, call)
        assert remarks == []
    assert _find(new, "Б") == expected
    assert new["variants"][-1]["code"] == "Б"
    assert read_project(new, strict=False)[0] is not None


def test_add_variant_gives_params_the_first_executor():
    new, remarks = edit.add_variant(BASE, "V2", "Second")
    assert remarks == []
    assert _find(new, "V2") == {
        "code": "V2", "title": "Second", "side": "own", "params": {"carrier": "Clerk"},
        "calls": []}


def test_add_variant_keeps_given_params_and_header_fields():
    new, remarks = edit.add_variant(
        BASE, " V2 ", " Second ", side="other", task="Ship", params={"carrier": "Robot"},
        entities=["Order", "Box"], initial={"Box": {"lid": "closed"}},
        out_of_comparison="Draft")
    assert remarks == []
    assert _find(new, "V2") == {
        "code": "V2", "title": "Second", "side": "other", "task": "Ship",
        "params": {"carrier": "Robot"}, "entities": ["Order", "Box"],
        "initial": {"Box": {"lid": "closed"}}, "out_of_comparison": "Draft", "calls": []}


def test_add_variant_drops_empty_optional_fields():
    new, remarks = edit.add_variant(
        BASE, "V2", "Second", task="  ", entities=[], initial={}, out_of_comparison="")
    assert remarks == []
    v = _find(new, "V2")
    for key in ("task", "entities", "initial", "out_of_comparison"):
        assert key not in v


def test_add_variant_refuses_duplicate_and_empty_code_and_title():
    assert "taken" in _refused(edit.add_variant(BASE, "V1", "Again"))
    assert "empty" in _refused(edit.add_variant(BASE, "  ", "Second"))
    assert "empty" in _refused(edit.add_variant(BASE, "V2", ""))


def test_add_variant_refuses_unknown_things():
    assert _refused(edit.add_variant(BASE, "V2", "S", side="mine"))
    assert _refused(edit.add_variant(BASE, "V2", "S", params={"carrier": "Ghost"}))
    assert _refused(edit.add_variant(BASE, "V2", "S", params={"speed": "Clerk"}))
    assert _refused(edit.add_variant(BASE, "V2", "S", entities=["Ghost"]))
    assert _refused(edit.add_variant(BASE, "V2", "S", initial={"Ghost": {"lid": "open"}}))
    assert _refused(edit.add_variant(BASE, "V2", "S", initial={"Box": {"ghost": "open"}}))
    assert _refused(edit.add_variant(BASE, "V2", "S", initial={"Box": {"lid": "ajar"}}))


def test_set_variant_changes_header_and_keeps_the_rest():
    before = copy.deepcopy(BASE)
    new, remarks = edit.set_variant(
        BASE, "V1", side="other", task="Deliver", params={"carrier": "Clerk"},
        entities=["Order", "Box"], initial={"Box": {"lid": "closed"}},
        out_of_comparison="Draft")
    assert remarks == []
    assert BASE == before
    v = _find(new, "V1")
    assert v["side"] == "other"
    assert v["task"] == "Deliver"
    assert v["params"] == {"carrier": "Clerk"}
    assert v["entities"] == ["Order", "Box"]
    assert v["initial"] == {"Box": {"lid": "closed"}}
    assert v["out_of_comparison"] == "Draft"
    assert v["title"] == "First"
    assert v["calls"] == _find(BASE, "V1")["calls"]


def test_set_variant_leaves_fields_not_given():
    new, remarks = edit.set_variant(BASE, "V1", side="other")
    assert remarks == []
    v = _find(new, "V1")
    assert v["side"] == "other"
    assert v["task"] == "Ship"
    assert v["params"] == {"carrier": "Robot"}


def test_set_variant_empty_task_and_reason_remove_the_key():
    data, _ = edit.set_variant(BASE, "V1", out_of_comparison="Draft", entities=["Order"])
    new, remarks = edit.set_variant(
        data, "V1", task="", out_of_comparison=" ", entities=[], initial={})
    assert remarks == []
    v = _find(new, "V1")
    for key in ("task", "out_of_comparison", "entities", "initial"):
        assert key not in v
    new, remarks = edit.set_variant(data, "V1", task=None, out_of_comparison=None)
    assert remarks == []
    assert "task" not in _find(new, "V1")
    assert "out_of_comparison" not in _find(new, "V1")


def test_set_variant_refuses():
    assert "no such variant" in _refused(edit.set_variant(BASE, "X", side="own"))
    assert _refused(edit.set_variant(BASE, "V1", side="mine"))
    assert _refused(edit.set_variant(BASE, "V1", params={"carrier": "Ghost"}))
    assert _refused(edit.set_variant(BASE, "V1", entities=["Ghost"]))
    assert _refused(edit.set_variant(BASE, "V1", initial={"Box": {"lid": "ajar"}}))
    assert _refused(edit.set_variant(BASE, "V1", initial={"Ghost": {"lid": "open"}}))
