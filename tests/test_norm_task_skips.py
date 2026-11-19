# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Skips in the norm report count the check axes of every entity the task of a path touches."""

import json
from decimal import Decimal
from pathlib import Path

from process_paths import norm
from process_paths.model import parse_model

TAP = Path(__file__).parent.parent / "docs" / "example_tap.json"
D = Decimal


def tap():
    """:return: the model and the normalization of the tap example, in the norm file format.

    The skip prices go by axis name; a zero-weight or waiting kind without a cost costs 0, as in the app.
    """
    data = json.loads(TAP.read_text(encoding="utf-8"), parse_float=Decimal)
    n = data["normalization"]
    costs = dict(n["kind_costs"])
    for k in data["kinds"]:
        if (k.get("zero_weight") or k.get("waiting")) and k["name"] not in costs:
            costs[k["name"]] = 0
    prices = {a: p for axes in n["axis_skip_prices"].values() for a, p in axes.items()}
    nrm = norm.parse_normalization({**n, "kind_costs": costs, "axis_skip_prices": prices})
    return parse_model(data), nrm


def finals(model, nrm) -> dict:
    out = norm.to_json(model, nrm, norm.norm_all(model, nrm))
    return {v["code"]: v["slices"][-1]["total"] for v in out["variants"]}


def test_tap_example_final_skips_match_the_app():
    assert finals(*tap()) == {"T1": 0, "T2": 0, "T3": 11, "T4": 0}


def tea() -> dict:
    """A kettle and a cup that the paths of one task check, and a teabag with no check."""
    return {
        "existence_axis": {"name": "exists", "absent": "no"},
        "entities": [
            {"name": "Kettle", "axes": [
                {"name": "water", "values": ["empty", "filled"]},
                {"name": "boil check", "values": ["not checked", "checked"]},
            ]},
            {"name": "Cup", "axes": [
                {"name": "exists", "values": ["yes", "no"]},
                {"name": "crack check", "values": ["not checked", "checked"]},
            ]},
            {"name": "Teabag", "axes": [{"name": "state", "values": ["dry", "brewed"]}]},
        ],
        "kinds": [
            {"name": "Fill kettle", "entity": "Kettle", "axis": "water",
             "from": "empty", "to": "filled"},
            {"name": "Check boil", "entity": "Kettle", "axis": "boil check",
             "from": "not checked", "to": "checked", "check": True},
            {"name": "Check crack", "entity": "Cup", "axis": "crack check",
             "from": "not checked", "to": "checked", "check": True},
            {"name": "Break cup", "entity": "Cup", "axis": "exists", "from": "yes", "to": "no"},
            {"name": "Brew", "entity": "Teabag", "axis": "state", "from": "dry", "to": "brewed"},
        ],
        "executors": [{"name": "Host"}],
        "instruments": ["hands"],
        "scopes": ["pot"],
        "batch_scope": "pot",
        "variants": [
            {"code": "A", "title": "Kettle only", "task": "Make tea", "calls": [
                ["Fill kettle", "Host", "hands", "pot"],
                ["Check boil", "Host", "hands", "pot"]]},
            {"code": "B", "title": "Cup and teabag", "task": "Make tea", "calls": [
                ["Check crack", "Host", "hands", "pot"],
                ["Brew", "Host", "hands", "pot"]]},
            {"code": "C", "title": "Break the cup", "task": "Make tea", "calls": [
                ["Break cup", "Host", "hands", "pot"],
                ["Check boil", "Host", "hands", "pot"]]},
            {"code": "D", "title": "Brew, no task", "calls": [
                ["Brew", "Host", "hands", "pot"]]},
            {"code": "E", "title": "Check the cup", "task": "Wash up", "calls": [
                ["Check crack", "Host", "hands", "pot"]]},
        ],
    }


TEA_NORM = {
    "kind_costs": {"Fill kettle": 1, "Check boil": 1, "Check crack": 1, "Break cup": 1, "Brew": 1},
    "executor_coefficients": {"Host": 1},
    "scope_coefficients": {"pot": 1},
    "axis_skip_prices": {"boil check": 5, "crack check": 2},
}


def test_task_entities_count_and_absent_entity_does_not():
    model = parse_model(json.loads(json.dumps(tea()), parse_float=Decimal))
    nrm = norm.parse_normalization(TEA_NORM)
    by = {r.variant.code: r.slices[-1] for r in norm.norm_all(model, nrm)}
    # A leaves the cup of its task untouched; B leaves the kettle.
    assert by["A"].skips == [("Cup", "crack check", D(2))]
    assert by["B"].skips == [("Kettle", "boil check", D(5))]
    # C breaks the cup: an absent cup has no check to skip.
    assert by["C"].skips == []
    # D has no task: only its own teabag counts. E's task has no kettle.
    assert by["D"].skips == []
    assert by["E"].skips == []
    assert finals(model, nrm) == {"A": 2, "B": 5, "C": 0, "D": 0, "E": 0}
