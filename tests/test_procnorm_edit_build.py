# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end test: a chain of edits from an empty project gives the dictionary of the example
file tests/data/laundry.json."""

import json
from pathlib import Path

from measure_twice import edit

LAUNDRY = json.loads(
    (Path(__file__).parent / "data" / "laundry.json").read_text(encoding="utf-8"))

DICTIONARY_PARTS = ("existence_axis", "entities", "kinds", "executors", "instruments", "scopes",
                    "batch_scope", "variant_params", "named_slices")


def _dictionary(data):
    return {part: data.get(part) for part in DICTIONARY_PARTS}


class _Chain:
    """Apply the edits one by one; every edit must be accepted."""

    def __init__(self, data):
        self.data = data

    def do(self, function, *args, **kwargs):
        new, remarks = function(self.data, *args, **kwargs)
        assert new is not None, remarks
        assert remarks == []
        self.data = new


def _build():
    data, remarks = edit.empty_project(LAUNDRY["name"])
    assert remarks == []
    chain = _Chain(data)
    axis = LAUNDRY["existence_axis"]
    chain.do(edit.set_existence_axis, axis["name"], axis["absent"])
    for entity in LAUNDRY["entities"]:
        chain.do(edit.add_word, "entity", entity["name"])
        for ax in entity["axes"]:
            first, *others = ax["values"]
            chain.do(edit.add_word, "axis", (entity["name"], ax["name"]), first_value=first)
            for value in others:
                chain.do(edit.add_word, "value", (entity["name"], ax["name"], value))
    for what, key in (("executor", "executors"), ("instrument", "instruments"),
                      ("scope", "scopes")):
        for name in LAUNDRY[key]:
            chain.do(edit.add_word, what, name)
    # The empty project already has the scope "batch"; the file has its own scopes.
    return chain


def test_chain_of_edits_gives_the_dictionary_of_laundry():
    chain = _build()
    chain.do(edit.set_batch_scope, LAUNDRY["batch_scope"])
    chain.do(edit.delete, "scope", "batch")
    for kind in LAUNDRY["kinds"]:
        structure = {key: value for key, value in kind.items() if key != "name"}
        chain.do(edit.add_kind, kind["name"], structure)
    for name, spec in LAUNDRY["named_slices"].items():
        groups = [group.get("states", []) + group.get("params", []) for group in spec["any"]]
        chain.do(edit.add_slice, name, groups)
    assert _dictionary(chain.data) == _dictionary(LAUNDRY)
