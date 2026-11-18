# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the renaming of dictionary words: every place of the old name changes, the result
does not."""

import copy
import json
from decimal import Decimal

import pytest

from procnorm.calc import compare
from procnorm import edit
from procnorm.project import read_project

# Made-up project; every word is written once in the dictionary and spelled unlike any other
# string of the file, so "the old name is nowhere" is a plain search. The value "wrapped" is one
# word of two axes: Box/cover takes it from Order/wrap by name (inherit).
TEXT = """
{
  "format": 1,
  "name": "Shipping",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Order", "axes": [
      {"name": "status", "values": ["new", "packed", "sent"]},
      {"name": "label", "values": ["unchecked", "checked"]},
      {"name": "wrap", "values": ["bare", "wrapped"]}
    ]},
    {"name": "Box", "axes": [
      {"name": "presence", "values": ["none", "present"]},
      {"name": "cover", "values": ["plain", "wrapped"], "inherit": [["Order", "wrap"]]}
    ]}
  ],
  "kinds": [
    {"name": "Make box", "entity": "Box", "axis": "presence", "from": "none", "to": "present"},
    {"name": "Pack", "entity": "Order", "axis": "status", "from": "new", "to": "packed",
     "requires": [["Box", "presence", "present"]]},
    {"name": "Send", "entity": "Order", "axis": "status", "from": "packed", "to": "sent"},
    {"name": "Check label", "entity": "Order", "axis": "label", "from": "unchecked",
     "to": "checked", "check": true},
    {"name": "Wrap", "entity": "Order", "axis": "wrap", "from": "bare", "to": "wrapped"},
    {"name": "Inspect", "entity": "Box", "axis": "cover", "from": "plain", "to": "wrapped",
     "check": true}
  ],
  "executors": ["Clerk", "Robot"],
  "instruments": ["Hands", "Tape"],
  "scopes": ["Each", "Batch"],
  "batch_scope": "Batch",
  "variant_params": ["Packer", "Sender"],
  "named_slices": {
    "Ready": {"any": [
      {"states": [["Order", "status", "packed"]], "params": [["Packer", "Clerk"]]},
      {"states": [["Box", "presence", "present"], ["Order", "label", "checked"]]}
    ]},
    "Done": {"any": [{"states": [["Order", "status", "sent"]]}]}
  },
  "variants": [
    {"code": "V1", "title": "First", "side": "own", "task": "Ship",
     "params": {"Packer": "Clerk", "Sender": "Robot"},
     "entities": ["Order", "Box"],
     "calls": [
       ["Wrap", "Clerk", "Tape", "Each"],
       ["Make box", "Robot", "Hands", "Batch"],
       ["Pack", "Clerk", "Hands", "Each"],
       ["Check label", "Clerk", "Hands", "Each"],
       ["Send", "Clerk", "Hands", "Batch"]
     ],
     "steps": [{"text": "step one", "calls": 2}, {"text": "step two", "calls": 3}]},
    {"code": "V2", "title": "Second", "side": "other", "task": "Ship",
     "params": {"Packer": "Robot", "Sender": "Clerk"},
     "initial": {"Order": {"wrap": "wrapped"}},
     "calls": [
       ["Make box", "Robot", "Hands", "Batch"],
       ["Pack", "Robot", "Tape", "Each"],
       ["Send", "Clerk", "Hands", "Each"]
     ]},
    {"code": "V3", "title": "Third", "side": "other", "task": "Receive",
     "params": {"Packer": "Clerk", "Sender": "Clerk"},
     "calls": [
       ["Make box", "Clerk", "Hands", "Batch"],
       ["Inspect", "Clerk", "Hands", "Each"],
       ["Pack", "Clerk", "Tape", "Each"],
       ["Send", "Robot", "Hands", "Each"]
     ]}
  ],
  "normalization": {
    "batch_size": 10,
    "kind_costs": {"Make box": 4, "Pack": 2, "Send": 1, "Check label": 3, "Wrap": 5,
                   "Inspect": 1.5},
    "executor_coefficients": {"Clerk": 1, "Robot": 0.5},
    "scope_coefficients": {"Each": 1, "Batch": 0.1},
    "axis_skip_prices": {"Order": {"label": 4}, "Box": {"cover": 2}},
    "uncounted_errors": {"Other": ["courier late"]}
  }
}
"""


def base() -> dict:
    return json.loads(TEXT, parse_float=Decimal)


def ok(result):
    new, remarks = result
    assert remarks == [] and new is not None
    return new


def refused(result):
    new, remarks = result
    assert new is None and remarks
    return remarks


def strings(obj) -> list[str]:
    """Every string of the data, dictionary keys included."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in strings(k) + strings(v)]
    if isinstance(obj, list):
        return [s for x in obj for s in strings(x)]
    return []


def numbers(d: dict) -> list:
    """The comparison without names: per variant labour by column, total, slices."""
    project, remarks = read_project(d)
    assert remarks == [] and project is not None
    c = compare(project)
    return [(r.code, r.reason, r.total, [r.labour[x] for x in c.executors],
             [(s.index, s.reached, s.total, len(s.skips)) for s in r.slices])
            for r in c.rows + c.excluded_rows]


def test_base_is_complete_and_uses_inheritance():
    c = compare(read_project(base())[0])
    assert c.excluded == [] and len(c.rows) == 3
    v1 = c.rows[0]
    # V1 wraps the order, so the new box inherits "wrapped" and its cover is no skip
    assert [(e, a) for e, a, _ in v1.slices[-1].skips] == []


# what, old name, new name, words that must vanish
CASES = [
    ("entity", "Order", "Parcel", ["Order"]),
    ("entity", "Box", "Crate", ["Box"]),
    ("axis", ("Order", "label"), "tag", ["label"]),
    ("axis", ("Order", "wrap"), "film", ["wrap"]),
    ("axis", ("Box", "presence"), "exists", ["presence"]),   # the existence axis
    ("value", ("Order", "wrap", "wrapped"), "covered", ["wrapped"]),  # inherited by Box/cover
    ("value", ("Order", "status", "packed"), "boxed", ["packed"]),
    ("value", ("Box", "presence", "none"), "missing", ["none"]),  # "does not exist"
    ("kind", "Pack", "Put in", ["Pack"]),
    ("kind", "Make box", "Fold box", ["Make box"]),
    ("executor", "Clerk", "Worker", ["Clerk"]),
    ("instrument", "Tape", "Glue", ["Tape"]),
    ("scope", "Batch", "Whole lot", ["Batch"]),
    ("scope", "Each", "Per item", ["Each"]),
    ("variant_param", "Packer", "Boxer", ["Packer"]),
    ("named_slice", "Ready", "Packed up", ["Ready"]),
]


@pytest.mark.parametrize("what, old, new_name, gone", CASES)
def test_rename_changes_every_place_and_keeps_the_result(what, old, new_name, gone):
    d = base()
    before = copy.deepcopy(d)
    new = ok(edit.rename(d, what, old, new_name))
    assert d == before                               # the argument is not changed
    words = strings(new)
    for w in gone:
        assert w not in words
    assert new_name in words
    assert numbers(new) == numbers(before)


def test_nine_kinds_are_covered():
    assert {c[0] for c in CASES} == {"entity", "axis", "value", "kind", "executor", "instrument",
                                     "scope", "variant_param", "named_slice"}


def test_rename_keeps_order_of_dictionary_and_normalization():
    new = ok(edit.rename(base(), "kind", "Pack", "Put in"))
    assert list(new["normalization"]["kind_costs"]) == [
        "Make box", "Put in", "Send", "Check label", "Wrap", "Inspect"]
    new = ok(edit.rename(base(), "named_slice", "Ready", "Packed up"))
    assert list(new["named_slices"]) == ["Packed up", "Done"]
    new = ok(edit.rename(base(), "entity", "Order", "Parcel"))
    assert list(new["normalization"]["axis_skip_prices"]) == ["Parcel", "Box"]


def test_rename_keeps_human_texts():
    new = ok(edit.rename(base(), "kind", "Pack", "Put in"))
    v1 = new["variants"][0]
    assert v1["steps"] == base()["variants"][0]["steps"]
    assert v1["title"] == "First" and v1["task"] == "Ship"


def test_rename_trims_spaces():
    new = ok(edit.rename(base(), "executor", "Clerk", "  Worker "))
    assert new["executors"] == ["Worker", "Robot"]


TAKEN = [
    ("entity", "Order", "Box"),
    ("axis", ("Order", "label"), "status"),
    ("axis", ("Order", "label"), "presence"),     # the existence axis name is taken
    ("axis", ("Box", "presence"), "label"),       # an axis of another entity would turn existence
    ("value", ("Order", "status", "new"), "sent"),
    ("value", ("Order", "wrap", "wrapped"), "plain"),  # taken in the inheriting axis
    ("kind", "Pack", "Send"),
    ("executor", "Clerk", "Robot"),
    ("instrument", "Hands", "Tape"),
    ("scope", "Each", "Batch"),
    ("variant_param", "Packer", "Sender"),
    ("named_slice", "Ready", "Done"),
    ("named_slice", "Ready", "final"),
]


@pytest.mark.parametrize("what, old, new_name", TAKEN)
def test_taken_name_is_refused(what, old, new_name):
    d = base()
    before = copy.deepcopy(d)
    refused(edit.rename(d, what, old, new_name))
    assert d == before


EMPTY = [(what, old) for what, old, _, _ in CASES]


@pytest.mark.parametrize("what, old", EMPTY)
@pytest.mark.parametrize("empty", ["", "   "])
def test_empty_name_is_refused(what, old, empty):
    refused(edit.rename(base(), what, old, empty))


@pytest.mark.parametrize("what, old", [
    ("entity", "Nobody"), ("axis", ("Order", "colour")), ("value", ("Order", "status", "lost")),
    ("kind", "Fly"), ("executor", "Nobody"), ("instrument", "Saw"), ("scope", "Half"),
    ("variant_param", "Owner"), ("named_slice", "Never"), ("word", "Order"),
])
def test_unknown_word_is_refused(what, old):
    refused(edit.rename(base(), what, old, "Anything"))


def test_same_name_changes_nothing():
    assert ok(edit.rename(base(), "kind", "Pack", "Pack")) == base()
