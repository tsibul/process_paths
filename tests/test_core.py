"""Tests of the core: loading, transitions, checks, cost, Markdown."""

import copy
import json
from decimal import Decimal

import pytest

from process_paths import analysis
from process_paths.cli import main
from process_paths.engine import TransitionError, initial_slice, run_variant
from process_paths.model import ModelError, load_model, parse_model
from process_paths.render import render_markdown

BASE = {
    "texts": {"title": "T", "definitions": "- **A** — a.", "split_semantic": "ok."},
    "existence_axis": {"name": "exists", "absent": "no"},
    "entities": [
        {"name": "Paper", "axes": [{"name": "place", "values": ["supplier", "client", "office"]}]},
        {"name": "Image", "axes": [
            {"name": "exists", "values": ["no", "yes"]},
            {"name": "place", "values": ["client", "office"], "inherit": [["Paper", "place"]]},
        ]},
        {"name": "Doc", "axes": [{"name": "checked", "values": ["unchecked", "checked"]}]},
    ],
    "kinds": [
        {"name": "receive", "entity": "Paper", "axis": "place", "from": "supplier", "to": "client"},
        {"name": "hand over", "entity": "Paper", "axis": "place", "from": "client", "to": "office"},
        {"name": "shoot", "entity": "Image", "axis": "exists", "from": "no", "to": "yes"},
        {"name": "send", "entity": "Image", "axis": "place", "from": "client", "to": "office"},
        {"name": "check", "entity": "Doc", "axis": "checked", "from": "unchecked", "to": "checked"},
    ],
    "executors": [{"name": "client"}, {"name": "program"}],
    "instruments": ["hand", "pc"],
    "scopes": ["per doc", "per batch"],
    "batch_scope": "per batch",
    "variants": [
        {"code": "V1", "title": "one", "calls": [
            ["receive", "client", "hand", "per doc"], ["shoot", "client", "hand", "per doc"],
            ["send", "client", "pc", "per batch"], ["check", "program", "pc", "per doc"]]},
        {"code": "V2", "title": "two", "calls": [
            ["receive", "client", "hand", "per doc"], ["hand over", "client", "hand", "per batch"],
            ["check", "program", "pc", "per doc"]]},
    ],
    "forbidden_words": ["bad"],
    "forbidden_exceptions": ["not bad at all"],
}


def model(**changes):
    """Build a model from BASE with top-level changes."""
    data = copy.deepcopy(BASE)
    data.update(changes)
    return parse_model(json.loads(json.dumps(data), parse_float=Decimal))


def test_python_version():
    import sys
    assert sys.version_info >= (3, 14)


def test_counts():
    n = analysis.dictionary_counts(model())
    assert (n["entities"], n["axes"], n["values"], n["kinds"]) == (3, 4, 9, 5)
    assert (n["executors"], n["instruments"], n["scopes"]) == (2, 2, 2)


def test_initial_slice_hides_absent_axes():
    m = model()
    s = initial_slice(m, m.variants[0])
    assert s[("Image", "exists")] == "no" and s[("Image", "place")] is None
    assert s[("Paper", "place")] == "supplier"


def test_creation_inherits_place_and_one_change_per_call():
    m = model()
    slices = run_variant(m, m.variants[0])
    assert len(slices) == 5
    assert slices[2][("Image", "place")] == "client"
    for a, b in zip(slices, slices[1:]):
        changed = [k for k in b if b[k] != a[k] and a[k] is not None]
        assert len(changed) == 1


def test_wrong_from_value_names_variant_and_call():
    data = copy.deepcopy(BASE)
    data["variants"][0]["calls"].insert(0, ["hand over", "client", "hand", "per doc"])
    m = parse_model(data)
    with pytest.raises(TransitionError, match=r"variant V1, call 1"):
        run_variant(m, m.variants[0])


def test_unknown_name_names_variant_and_call():
    data = copy.deepcopy(BASE)
    data["variants"][1]["calls"][2][1] = "nobody"
    with pytest.raises(ModelError, match=r"variant V2, call 3: unknown executor"):
        parse_model(data)


def test_unknown_scope():
    data = copy.deepcopy(BASE)
    data["variants"][0]["calls"][0][3] = "per year"
    with pytest.raises(ModelError, match="unknown scope"):
        parse_model(data)


def test_initial_deviation():
    data = copy.deepcopy(BASE)
    data["variants"][1]["initial"] = {"Paper": {"place": "client"}}
    data["variants"][1]["calls"].pop(0)
    m = parse_model(data)
    assert run_variant(m, m.variants[1])[-1][("Paper", "place")] == "office"


def test_decomposition_and_duplicates():
    data = copy.deepcopy(BASE)
    data["kinds"].append({"name": "direct", "entity": "Paper", "axis": "place", "from": "supplier", "to": "office"})
    data["kinds"].append({"name": "twin", "entity": "Doc", "axis": "checked", "from": "unchecked", "to": "checked"})
    m = parse_model(data)
    assert analysis.decomposable_kinds(m) == [("direct", ["receive", "hand over"])]
    assert analysis.duplicate_kinds(m) == [("check", "twin")]
    assert analysis.decomposable_kinds(model()) == [] and analysis.duplicate_kinds(model()) == []


def test_variant_counts_and_unused():
    m = model()
    assert analysis.variant_counts(m) == [("V1", "one", 4, 4), ("V2", "two", 3, 3)]
    data = copy.deepcopy(BASE)
    data["variants"].pop(1)
    assert analysis.unused_kinds(parse_model(data)) == ["hand over"]


def test_identical_slices():
    rows = analysis.identical_slices(model())
    r = rows[0]
    assert r["full"] == [] and (0, 0) in r["common"] and (1, 1) in r["common"]


def test_cost_not_set_without_numbers():
    m = model()
    assert analysis.path_cost(m, m.variants[0]) is None
    assert analysis.path_safety(m, m.variants[0]) is None
    assert analysis.cost_ranking(m) is None
    assert not analysis.has_numbers(m)


def test_cost_per_document_with_batch():
    data = copy.deepcopy(BASE)
    for k in data["kinds"]:
        k["cost"] = 1
        k["check"] = k["name"] == "check"
    data["kinds"][3]["instrument_costs"] = {"pc": 10}
    data["executors"] = [{"name": "client", "factor": 2}, {"name": "program", "factor": Decimal("0.5")}]
    m = parse_model(data)
    # V1: receive 2 + shoot 2 + send 10*2/batch + check 0.5
    assert analysis.path_cost(m, m.variants[0], 10) == Decimal("6.5")
    assert analysis.path_cost(m, m.variants[0], 1) == Decimal("24.5")
    assert analysis.path_safety(m, m.variants[0]) == 1
    ranking = analysis.cost_ranking(m)
    assert set(ranking) == {1, 10, 100, 1000} and ranking[1] == ["V2", "V1"]
    assert "2.4." in render_markdown(m)


def test_forbidden_words():
    m = model()
    assert analysis.forbidden_hits(m, "it is not bad at all") == []
    assert analysis.forbidden_hits(m, "a bad name") == ["bad"]


def test_markdown_structure():
    text = render_markdown(model())
    for head in ("## 1. Определения", "### 2.1.", "### 3.3. Виды переходов", "### 3.6. Охваты",
                 "### V1. one", "## 5. Сводная таблица"):
        assert head in text
    assert "↓ send (client; pc; per batch)" in text
    assert "Image: **yes**; client" in text
    assert "Image: no" in text
    assert "2.4." not in text


def test_cli_check_and_markdown(tmp_path, capsys):
    src = tmp_path / "m.json"
    src.write_text(json.dumps(BASE, ensure_ascii=False), encoding="utf-8")
    assert main(["check", str(src)]) == 0
    assert "OK" in capsys.readouterr().out
    out = tmp_path / "m.md"
    assert main(["markdown", str(src), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# T")
    assert load_model(src).variants[0].calls[2].scope == "per batch"
