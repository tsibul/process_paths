# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of labour and skips by a normalization file."""

import copy
import json
from decimal import Decimal

import pytest

from process_paths import norm
from process_paths.cli import main
from process_paths.model import ModelError, parse_model

MODEL = {
    "existence_axis": {"name": "exists", "absent": "no"},
    "entities": [
        {"name": "Paper", "axes": [{"name": "place", "values": ["supplier", "receiver", "office"]}]},
        {"name": "Doc", "axes": [
            {"name": "sum check", "values": ["unchecked", "ok", "bad"]},
            {"name": "dup check", "values": ["unchecked", "ok"]},
            {"name": "item", "values": ["none", "chosen"]},
        ]},
        {"name": "Record", "axes": [{"name": "exists", "values": ["no", "yes"]}]},
    ],
    "kinds": [
        {"name": "receive", "entity": "Paper", "axis": "place", "from": "supplier", "to": "receiver",
         "zero_weight": True},
        {"name": "hand over", "entity": "Paper", "axis": "place", "from": "receiver", "to": "office"},
        {"name": "check sums", "entity": "Doc", "axis": "sum check", "from": "unchecked", "to": "ok",
         "check": True},
        {"name": "check dup", "entity": "Doc", "axis": "dup check", "from": "unchecked", "to": "ok",
         "check": True},
        {"name": "choose item", "entity": "Doc", "axis": "item", "from": "none", "to": "chosen"},
        {"name": "post", "entity": "Record", "axis": "exists", "from": "no", "to": "yes"},
    ],
    "executors": [{"name": "client"}, {"name": "accountant"}, {"name": "program"}],
    "instruments": ["hand", "pc"],
    "scopes": ["per doc", "per batch"],
    "batch_scope": "per batch",
    "variants": [
        {"code": "V1", "title": "client hands over", "calls": [
            ["receive", "client", "hand", "per doc"],
            ["choose item", "client", "pc", "per doc"],
            ["hand over", "client", "hand", "per batch"],
            ["check sums", "accountant", "pc", "per doc"],
            ["post", "program", "pc", "per doc"]]},
        {"code": "V2", "title": "accountant receives", "calls": [
            ["receive", "accountant", "hand", "per doc"],
            ["check dup", "program", "pc", "per doc"],
            ["post", "accountant", "pc", "per batch"]]},
        {"code": "V3", "title": "client alone", "out_of_comparison": "only ours", "calls": [
            ["receive", "client", "hand", "per doc"],
            ["choose item", "client", "pc", "per doc"]]},
    ],
}

NORM = {
    "batch_size": 10,
    "kind_costs": {"receive": 0, "hand over": 3, "check sums": 2, "check dup": 5, "choose item": 1, "post": 4},
    "executor_coefficients": {"client": 1, "accountant": 2, "program": 0},
    "scope_coefficients": {"per doc": 10, "per batch": 1},
    "axis_skip_prices": {"sum check": 3, "dup check": 1},
    "uncounted_errors": {"no_state": ["wrong firm"]},
}

SLICES = {"handed": {"otherwise": "final", "any": [
    {"states": [["Paper", "place", "office"]]},
    {"states": [["Paper", "place", "receiver"]], "calls": [["receive", "accountant"]]},
    {"states": [["Record", "exists", "yes"]]},
]}}


def _load(model=None, normalization=None, slices=None):
    """:return: parsed model, normalization and named slices."""
    as_json = lambda d: json.loads(json.dumps(d), parse_float=Decimal)  # noqa: E731
    return (parse_model(as_json(model or MODEL)), norm.parse_normalization(as_json(normalization or NORM)),
            norm.parse_slices(slices or SLICES))


def _by_code(results):
    return {r.variant.code: r for r in results}


def test_labour_per_executor_and_total():
    r = _by_code(norm.norm_all(*_load()))
    # V1: choose item 1*10*1 + hand over 3*1*1 = 13 (client); check sums 2*10*2 = 40 (accountant)
    assert r["V1"].labour == {"client": Decimal(13), "accountant": Decimal(40), "program": Decimal(0)}
    assert r["V1"].total == 53
    # V2: post per batch by accountant 4*1*2 = 8; program check costs nothing
    assert (r["V2"].labour["accountant"], r["V2"].total) == (8, 8)


def test_skips_in_named_and_final_slice():
    r = _by_code(norm.norm_all(*_load()))
    handed, final = r["V1"].slices
    assert (handed.name, handed.index, handed.reached) == ("handed", 3, True)
    assert [a for _, a, _ in handed.skips] == ["sum check", "dup check"] and handed.total == 4
    assert (final.name, final.index) == (norm.FINAL, 5)
    assert [a for _, a, _ in final.skips] == ["dup check"] and final.total == 1


def test_named_slice_by_receiving_executor():
    handed, final = _by_code(norm.norm_all(*_load()))["V2"].slices
    assert handed.index == 1 and handed.total == 4
    assert final.skips == [("Doc", "sum check", Decimal(3))]


def test_named_slice_not_reached():
    handed, final = _by_code(norm.norm_all(*_load()))["V3"].slices
    assert not handed.reached and handed.index == final.index == 2 and handed.total == 4
    data = copy.deepcopy(SLICES)
    del data["handed"]["otherwise"]
    handed = _by_code(norm.norm_all(*_load(slices=data)))["V3"].slices[0]
    assert handed.index is None and handed.skips is None and handed.total is None


def test_out_of_comparison_is_counted_and_marked():
    m, n, s = _load()
    results = norm.norm_all(m, n, s)
    assert _by_code(results)["V3"].total == 10
    text = norm.render_markdown(m, n, results)
    assert "| V3 client alone | 10 | 0 | 10 | не наступает (= конечный, 2) |" in text
    assert text.count("| вне сравнения |") == 1 and "- **V3**: only ours" in text
    out = norm.to_json(m, n, results)
    assert out["variants"][2]["out_of_comparison"] == "only ours"
    assert out["variants"][0]["slices"][0]["skips"][0] == {"entity": "Doc", "axis": "sum check", "price": 3}


@pytest.mark.parametrize("section, change, message", [
    ("kind_costs", {"post": None}, "kind without cost: post"),
    ("kind_costs", {"extra": 1}, "cost of unknown kind: extra"),
    ("kind_costs", {"receive": 1}, "zero_weight but cost 1"),
    ("executor_coefficients", {"program": None}, "executor without coefficient: program"),
    ("scope_coefficients", {"per batch": None}, "scope without coefficient: per batch"),
    ("axis_skip_prices", {"dup check": None}, "check axis without skip price: Doc/dup check"),
    ("axis_skip_prices", {"item": 1}, "not a check axis: item"),
])
def test_mismatch_is_reported(section, change, message):
    data = copy.deepcopy(NORM)
    for k, v in change.items():
        if v is None:
            del data[section][k]
        else:
            data[section][k] = v
    with pytest.raises(ModelError, match=message):
        norm.norm_all(*_load(normalization=data))


def test_slice_with_unknown_value():
    data = {"s": {"any": [{"states": [["Paper", "place", "moon"]]}]}}
    with pytest.raises(ModelError, match="unknown Paper/place=moon"):
        norm.norm_all(*_load(slices=data))


def test_cli_writes_markdown_and_json(tmp_path):
    paths = {}
    for name, data in (("m", MODEL), ("n", NORM), ("s", SLICES)):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    md, js = tmp_path / "out.md", tmp_path / "out.json"
    assert main(["norm", str(paths["m"]), "--norm", str(paths["n"]), "--slices", str(paths["s"]),
                 "-o", str(md), "--json", str(js)]) == 0
    assert "| V1 client hands over | 13 | 40 | 53 | 3 |" in md.read_text(encoding="utf-8")
    out = json.loads(js.read_text(encoding="utf-8"))
    assert [v["labour_total"] for v in out["variants"]] == [53, 8, 10]
    assert main(["norm", str(paths["m"])]) == 2
