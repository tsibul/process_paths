# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the places where a dictionary word is used and of the deletion of unused words."""

import copy

import pytest

from procnorm import edit
from tests.test_procnorm_edit_rename import base, numbers, ok, refused, strings

# Every place where a word of the base project is used (a set: the order is not part of the rule).
USED = [
    ("kind", "Pack", {"variant V1, call 3", "variant V2, call 2", "variant V3, call 3"}),
    ("kind", "Wrap", {"variant V1, call 1"}),
    ("executor", "Robot", {"variant V1, call 2", "variant V1, parameter Sender",
                           "variant V2, call 1", "variant V2, call 2",
                           "variant V2, parameter Packer", "variant V3, call 4"}),
    ("instrument", "Tape", {"variant V1, call 1", "variant V2, call 2", "variant V3, call 3"}),
    ("scope", "Batch", {"variant V1, call 2", "variant V1, call 5", "variant V2, call 1",
                        "variant V3, call 1", "batch scope"}),
    ("variant_param", "Packer", {"variant V1, parameter Packer", "variant V2, parameter Packer",
                                 "variant V3, parameter Packer", "slice Ready"}),
    ("entity", "Box", {"kind Make box", "kind Inspect", "kind Pack, condition", "slice Ready",
                       "variant V1, entities"}),
    ("axis", ("Order", "wrap"), {"kind Wrap", "axis Box/cover, inherit", "variant V2, initial"}),
    ("value", ("Order", "wrap", "wrapped"),
     {"kind Wrap, to", "kind Inspect, to", "variant V2, initial"}),
    ("value", ("Order", "status", "packed"), {"kind Pack, to", "kind Send, from", "slice Ready"}),
    ("value", ("Order", "status", "new"), {"kind Pack, from", "initial value of Order/status"}),
]


def with_spares() -> dict:
    """The base project plus one unused word of every sort, each with its normalization number."""
    d = base()
    d["executors"].append("Spare executor")
    d["instruments"].append("Spare instrument")
    d["scopes"].append("Spare scope")
    d["named_slices"]["Spare slice"] = {"any": [{"states": [["Order", "status", "sent"]]}]}
    d["kinds"].append({"name": "Spare kind", "entity": "Order", "axis": "status",
                       "from": "sent", "to": "packed"})
    order = next(e for e in d["entities"] if e["name"] == "Order")
    order["axes"][0]["values"].append("Spare value")
    order["axes"].append({"name": "Spare axis", "values": ["on", "off"]})
    d["entities"].append({"name": "Spare entity", "axes": [{"name": "mode", "values": ["a", "b"]}]})
    n = d["normalization"]
    n["kind_costs"]["Spare kind"] = 7
    n["executor_coefficients"]["Spare executor"] = 3
    n["scope_coefficients"]["Spare scope"] = 2
    return d


UNUSED = [
    ("kind", "Spare kind", ["Spare kind"]),
    ("executor", "Spare executor", ["Spare executor"]),
    ("instrument", "Spare instrument", ["Spare instrument"]),
    ("scope", "Spare scope", ["Spare scope"]),
    ("named_slice", "Spare slice", ["Spare slice"]),
    ("entity", "Spare entity", ["Spare entity", "mode"]),
    ("axis", ("Order", "Spare axis"), ["Spare axis"]),
    ("value", ("Order", "status", "Spare value"), ["Spare value"]),
]


@pytest.mark.parametrize("what, old, places", USED)
def test_usages_name_every_place(what, old, places):
    found = edit.usages(base(), what, old)
    assert set(found) == places
    assert len(found) == len(places)                 # no place twice


@pytest.mark.parametrize("what, old, places", USED)
def test_used_word_is_refused_with_all_places(what, old, places):
    d = base()
    before = copy.deepcopy(d)
    remarks = refused(edit.delete(d, what, old))
    assert d == before
    label = "/".join(old) if isinstance(old, tuple) else old
    text = remarks[0].text
    assert text.startswith(f"{old[-1] if isinstance(old, tuple) else old} is used and cannot be deleted:\n")
    assert set(text.split("\n")[1:]) == places
    assert label in remarks[0].where


def without_slice(d: dict) -> dict:
    d = copy.deepcopy(d)
    d["named_slices"].pop("Spare slice", None)
    return d


@pytest.mark.parametrize("what, old, gone", UNUSED)
def test_unused_word_is_deleted_and_result_is_the_same(what, old, gone):
    d = with_spares()
    before = copy.deepcopy(d)
    assert edit.usages(d, what, old) == []           # the number of normalization is no use
    new = ok(edit.delete(d, what, old))
    assert d == before
    words = strings(new)
    for w in gone:
        assert w not in words                        # also not as a key of normalization
    # the other spares change no number; a named slice is one more row of the comparison
    assert numbers(without_slice(new)) == numbers(base())


def test_deleting_a_word_deletes_only_it():
    d = with_spares()
    new = ok(edit.delete(d, "executor", "Spare executor"))
    expected = copy.deepcopy(d)
    expected["executors"].remove("Spare executor")
    del expected["normalization"]["executor_coefficients"]["Spare executor"]
    assert new == expected


def test_normalization_number_is_not_a_use():
    d = base()
    assert "Robot" in d["normalization"]["executor_coefficients"]
    assert edit.usages(d, "kind", "Wrap") == ["variant V1, call 1"]
    d["variants"] = []                               # no variant uses anything
    d["named_slices"] = {}
    assert edit.usages(d, "executor", "Robot") == []
    assert edit.usages(d, "kind", "Wrap") == []
    new = ok(edit.delete(d, "kind", "Wrap"))
    assert "Wrap" not in new["normalization"]["kind_costs"]


def test_variant_param_without_variants_is_deleted():
    d = base()
    assert len(edit.usages(d, "variant_param", "Packer")) == 4
    d["variants"], d["named_slices"] = [], {}
    new = ok(edit.delete(d, "variant_param", "Packer"))
    assert "Packer" not in strings(new)


def test_existence_absent_value_is_used():
    places = edit.usages(base(), "value", ("Box", "presence", "none"))
    assert "existence axis" in places


def test_unknown_word_is_refused():
    d = base()
    refused(edit.delete(d, "executor", "Nobody"))
    refused(edit.delete(d, "axis", ("Order", "nothing")))
    refused(edit.delete(d, "value", ("Order", "status", "nothing")))
    refused(edit.delete(d, "whatever", "Robot"))
    refused(edit.delete(d, "axis", "Order"))         # not a pair
    assert edit.usages(d, "executor", "Nobody") == []


@pytest.mark.parametrize("what, old", [
    ("kind", "Pack"), ("executor", "Clerk"), ("instrument", "Hands"), ("scope", "Each"),
    ("variant_param", "Sender"), ("entity", "Order"), ("axis", ("Order", "label")),
    ("value", ("Order", "wrap", "wrapped")), ("named_slice", "Ready"),
])
def test_rename_keeps_the_number_of_places(what, old):
    """Rename and usages agree on the places: a renamed word has as many places as before."""
    d = base()
    n = len(edit.usages(d, what, old))
    assert n >= 0
    new_name = "Renamed"
    new = ok(edit.rename(d, what, old, new_name))
    new_old = (*old[:-1], new_name) if isinstance(old, tuple) else new_name
    assert len(edit.usages(new, what, new_old)) == n
