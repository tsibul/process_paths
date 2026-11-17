# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of adding and changing transition kinds: a kind made by an edit equals the same kind
read from a file, a number that is no longer needed goes away, the refusals are the refusals of
the read."""

import copy
import json

import pytest

from procnorm import edit
from procnorm.project import read_project

# Made-up project: an order with a status and a check axis, a box with the existence axis.
BASE = json.loads("""
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed", "sent", "lost"]},
      {"name": "weighed", "values": ["no", "yes"]},
      {"name": "labelled", "values": ["no", "yes"]}
    ]},
    {"name": "Box", "axes": [
      {"name": "presence", "values": ["none", "present"]}
    ]}
  ],
  "kinds": [
    {"name": "Pack", "entity": "Order", "axis": "status", "from": "new", "to": "packed"},
    {"name": "Send", "entity": "Order", "axis": "status", "from": "packed", "to": "sent"},
    {"name": "Weigh", "entity": "Order", "axis": "weighed", "from": "no", "to": "yes",
     "check": true}
  ],
  "executors": ["Clerk", "Robot"],
  "instruments": ["Hands"],
  "scopes": ["Each", "Batch"],
  "batch_scope": "Batch",
  "variant_params": [],
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {},
     "calls": [["Pack", "Clerk", "Hands", "Each"], ["Send", "Clerk", "Hands", "Each"]]}
  ],
  "normalization": {
    "kind_costs": {"Pack": 3, "Send": 2, "Weigh": 1},
    "executor_coefficients": {"Clerk": 1, "Robot": 0},
    "scope_coefficients": {"Each": 1, "Batch": 1},
    "axis_skip_prices": {"Order": {"weighed": 5}}
  }
}
""")


def _structure(**changes):
    structure = {"entity": "Order", "axis": "labelled", "from": "no", "to": "yes"}
    structure.update(changes)
    return structure


def _kind(data, name):
    return next(k for k in data["kinds"] if k["name"] == name)


def _refused(result):
    new, remarks = result
    assert new is None
    assert remarks
    return remarks[0].text


def test_add_kind_equals_kind_from_file():
    from_file = copy.deepcopy(BASE)
    from_file["kinds"].append({
        "name": "Label", "entity": "Order", "axis": "labelled", "from": "no", "to": "yes",
        "requires": [["Order", "status", "packed"]], "check": True,
    })
    from_file["normalization"]["kind_costs"]["Label"] = 4
    from_file["normalization"]["axis_skip_prices"]["Order"]["labelled"] = 2
    from_file = json.loads(json.dumps(from_file))

    structure = _structure(requires=[["Order", "status", "packed"]], check=True)
    new, remarks = edit.add_kind(BASE, "Label", structure)
    assert remarks == []
    new["normalization"]["kind_costs"]["Label"] = 4
    new["normalization"]["axis_skip_prices"]["Order"]["labelled"] = 2
    assert json.loads(json.dumps(new)) == from_file
    assert list(_kind(new, "Label")) == list(_kind(from_file, "Label"))
    assert read_project(new, strict=True)[0] is not None


def test_add_kind_goes_to_the_end_and_does_not_change_argument():
    before = copy.deepcopy(BASE)
    new, remarks = edit.add_kind(BASE, "Label", _structure())
    assert remarks == []
    assert [k["name"] for k in new["kinds"]] == ["Pack", "Send", "Weigh", "Label"]
    assert _kind(new, "Label") == {
        "name": "Label", "entity": "Order", "axis": "labelled", "from": "no", "to": "yes"}
    assert BASE == before


def test_add_kind_trims_name():
    new, remarks = edit.add_kind(BASE, "  Label ", _structure())
    assert remarks == []
    assert _kind(new, "Label")["name"] == "Label"


def test_add_kind_zero_weight_with_note():
    structure = _structure(zero_weight=True, zero_weight_note="just waiting")
    new, remarks = edit.add_kind(BASE, "Wait", structure)
    assert remarks == []
    kind = _kind(new, "Wait")
    assert kind["zero_weight"] is True
    assert kind["zero_weight_note"] == "just waiting"
    assert "Wait" not in new["normalization"]["kind_costs"]
    assert read_project(new, strict=True)[0] is not None


def test_add_kind_false_flags_are_not_written():
    structure = _structure(requires=[], check=False, zero_weight=False, zero_weight_note="")
    new, remarks = edit.add_kind(BASE, "Label", structure)
    assert remarks == []
    assert set(_kind(new, "Label")) == {"name", "entity", "axis", "from", "to"}


def test_add_kind_refuses_taken_and_empty_name():
    assert "taken" in _refused(edit.add_kind(BASE, "Pack", _structure()))
    assert _refused(edit.add_kind(BASE, "  ", _structure()))
    assert _refused(edit.add_kind(BASE, None, _structure()))


@pytest.mark.parametrize("changes", [
    {"entity": "Parcel"},
    {"axis": "colour"},
    {"from": "gone"},
    {"to": "gone"},
    {"requires": [["Parcel", "status", "new"]]},
    {"requires": [["Order", "status", "gone"]]},
])
def test_add_kind_refuses_unknown_names(changes):
    assert _refused(edit.add_kind(BASE, "Label", _structure(**changes)))


def test_add_kind_refuses_from_equal_to():
    assert _refused(edit.add_kind(BASE, "Label", _structure(to="no")))


def test_add_kind_refuses_condition_on_own_axis():
    structure = _structure(requires=[["Order", "labelled", "no"]])
    assert _refused(edit.add_kind(BASE, "Label", structure))


def test_add_kind_refuses_identical_quadruple():
    structure = _structure(axis="status", **{"from": "new", "to": "packed"})
    assert _refused(edit.add_kind(BASE, "Pack again", structure))


def test_add_kind_refuses_chain_repeat():
    structure = _structure(axis="status", **{"from": "new", "to": "sent"})
    assert _refused(edit.add_kind(BASE, "Rush", structure))


@pytest.mark.parametrize("structure", [
    None,
    "text",
    {"entity": "Order", "axis": "labelled", "from": "no"},
    {"entity": 1, "axis": "labelled", "from": "no", "to": "yes"},
    {"entity": "Order", "axis": "labelled", "from": "no", "to": "yes", "colour": "red"},
    {"entity": "Order", "axis": "labelled", "from": "no", "to": "yes", "check": "yes"},
    {"entity": "Order", "axis": "labelled", "from": "no", "to": "yes", "requires": "x"},
    {"entity": "Order", "axis": "labelled", "from": "no", "to": "yes", "zero_weight_note": "x"},
])
def test_add_kind_refuses_bad_shape(structure):
    assert _refused(edit.add_kind(BASE, "Label", structure))


def test_set_kind_changes_structure_in_place():
    structure = _structure(axis="status", **{"from": "new", "to": "lost"})
    new, remarks = edit.set_kind(BASE, "Weigh", structure)
    assert remarks == []
    assert [k["name"] for k in new["kinds"]] == ["Pack", "Send", "Weigh"]
    assert _kind(new, "Weigh") == {
        "name": "Weigh", "entity": "Order", "axis": "status", "from": "new", "to": "lost"}


def test_set_kind_equals_kind_from_file():
    from_file = copy.deepcopy(BASE)
    kind = _kind(from_file, "Send")
    kind["to"] = "lost"
    kind["requires"] = [["Box", "presence", "present"]]
    new, remarks = edit.set_kind(BASE, "Send", _structure(
        axis="status", **{"from": "packed", "to": "lost"},
        requires=[["Box", "presence", "present"]]))
    assert remarks == []
    assert new == from_file


def test_set_kind_refuses_unknown_kind():
    assert "no such kind" in _refused(edit.set_kind(BASE, "Nothing", _structure()))


def test_set_kind_refusals_leave_argument_unchanged():
    before = copy.deepcopy(BASE)
    assert _refused(edit.set_kind(BASE, "Send", _structure(axis="status", to="new")))
    assert _refused(edit.set_kind(BASE, "Send", _structure(axis="status", **{
        "from": "new", "to": "packed"})))
    assert _refused(edit.set_kind(BASE, "Pack", _structure(
        axis="status", **{"from": "new", "to": "packed"},
        requires=[["Order", "status", "new"]])))
    assert BASE == before


def test_set_kind_refuses_chain_repeat_and_own_axis_condition():
    # Pack new -> packed and Send packed -> sent exist; a new -> sent kind repeats them.
    structure = _structure(axis="status", **{"from": "new", "to": "sent"})
    assert _refused(edit.set_kind(BASE, "Weigh", structure))
    structure = _structure(axis="weighed", **{"from": "no", "to": "yes"},
                           requires=[["Order", "weighed", "no"]])
    assert _refused(edit.set_kind(BASE, "Weigh", structure))


def test_set_kind_keeps_own_old_shape_when_unchanged():
    structure = {"entity": "Order", "axis": "status", "from": "new", "to": "packed"}
    new, remarks = edit.set_kind(BASE, "Pack", structure)
    assert remarks == []
    assert new == BASE


def test_zero_weight_removes_the_cost():
    structure = {"entity": "Order", "axis": "status", "from": "new", "to": "packed",
                 "zero_weight": True, "zero_weight_note": "waiting"}
    new, remarks = edit.set_kind(BASE, "Pack", structure)
    assert remarks == []
    assert "Pack" not in new["normalization"]["kind_costs"]
    assert new["normalization"]["kind_costs"] == {"Send": 2, "Weigh": 1}
    assert read_project(new, strict=True)[0] is not None


def test_zero_weight_off_does_not_invent_a_cost():
    structure = {"entity": "Order", "axis": "status", "from": "new", "to": "packed",
                 "zero_weight": True, "zero_weight_note": "waiting"}
    waiting, _ = edit.set_kind(BASE, "Pack", structure)
    again, remarks = edit.set_kind(waiting, "Pack", {
        "entity": "Order", "axis": "status", "from": "new", "to": "packed"})
    assert remarks == []
    assert "Pack" not in again["normalization"]["kind_costs"]
    assert read_project(again, strict=False)[0] is not None
    assert read_project(again, strict=True)[0] is None


def test_unchecking_removes_axis_price_when_no_check_kind_is_left():
    structure = {"entity": "Order", "axis": "weighed", "from": "no", "to": "yes"}
    new, remarks = edit.set_kind(BASE, "Weigh", structure)
    assert remarks == []
    assert "check" not in _kind(new, "Weigh")
    assert new["normalization"]["axis_skip_prices"] == {}
    assert read_project(new, strict=True)[0] is not None


def test_unchecking_keeps_axis_price_when_another_kind_checks_the_axis():
    base = copy.deepcopy(BASE)
    base["kinds"].append({"name": "Weigh back", "entity": "Order", "axis": "weighed",
                          "from": "yes", "to": "no", "check": True})
    base["normalization"]["kind_costs"]["Weigh back"] = 1
    structure = {"entity": "Order", "axis": "weighed", "from": "no", "to": "yes"}
    new, remarks = edit.set_kind(base, "Weigh", structure)
    assert remarks == []
    assert new["normalization"]["axis_skip_prices"] == {"Order": {"weighed": 5}}


def test_moving_a_check_kind_to_another_axis_drops_the_old_price_only():
    structure = _structure(check=True)
    new, remarks = edit.set_kind(BASE, "Weigh", structure)
    assert remarks == []
    assert new["normalization"]["axis_skip_prices"] == {}
    assert _kind(new, "Weigh")["check"] is True
    assert new["normalization"]["kind_costs"]["Weigh"] == 1


def test_other_entities_prices_stay_when_one_price_goes():
    base = copy.deepcopy(BASE)
    base["entities"][1]["axes"].append({"name": "sealed", "values": ["no", "yes"]})
    base["kinds"].append({"name": "Seal", "entity": "Box", "axis": "sealed",
                          "from": "no", "to": "yes", "check": True})
    base["normalization"]["kind_costs"]["Seal"] = 1
    base["normalization"]["axis_skip_prices"]["Box"] = {"sealed": 7}
    structure = {"entity": "Order", "axis": "weighed", "from": "no", "to": "yes"}
    new, remarks = edit.set_kind(base, "Weigh", structure)
    assert remarks == []
    assert new["normalization"]["axis_skip_prices"] == {"Box": {"sealed": 7}}


def test_new_check_kind_needs_its_price_only_for_strict_read():
    new, remarks = edit.add_kind(BASE, "Label", _structure(check=True))
    assert remarks == []
    assert read_project(new, strict=False)[0] is not None
    assert read_project(new, strict=True)[0] is None


def test_changing_from_of_a_kind_in_a_variant_puts_variant_to_errors():
    structure = {"entity": "Order", "axis": "status", "from": "sent", "to": "packed"}
    new, remarks = edit.set_kind(BASE, "Pack", structure)
    assert remarks == []
    project, _ = read_project(new, strict=False)
    assert "V1" in project.errors
    number, reason = project.errors["V1"]
    assert number == 1
    assert reason
    assert read_project(BASE, strict=False)[0].errors == {}
