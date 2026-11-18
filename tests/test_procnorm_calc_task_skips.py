# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Skipped checks of a path count the check axes of every entity its task touches."""

import json
from decimal import Decimal
from pathlib import Path

from measure_twice.calc import compare, series, start_point
from measure_twice.project import read_project

PROMPTS = Path(__file__).parent.parent / "docs" / "ai_prompts_en.md"
D = Decimal


def example() -> dict:
    """The file of the example of prompt 5 (the plunger and the plumber)."""
    text = PROMPTS.read_text(encoding="utf-8")
    part = text.split("## Prompt 5", 1)[1]
    block = part.split("```text\n", 1)[1].split("\n```", 1)[0]
    body = block.split("EXAMPLE\n", 1)[1]
    return json.loads(body, parse_float=Decimal)


def project_of(d, strict=True):
    p, remarks = read_project(d, strict=strict)
    assert remarks == []
    return p


def finals(project) -> dict:
    c = compare(project)
    return {r.code: r.slices[-1].total for r in c.rows + c.excluded_rows}


def test_prompt_5_variant_b_skips_the_drain_test():
    p = project_of(example())
    row = next(r for r in compare(p).rows if r.code == "B")
    assert row.slices[-1].skips == [("Sink", "drain test", D(5))]
    assert row.slices[-1].total == D(5)
    assert finals(p)["A"] == D(0)


def test_path_without_the_check_agrees_in_table_series_and_start():
    p = project_of(example())
    start = start_point(p, "B")
    assert start.skips == [("Sink", "drain test")]
    assert start.skips_total == D(5)
    assert start.done_total == D(0)
    for point in series(p, "B"):
        assert point.skips == [("Sink", "drain test")]
        assert point.skips_count == 1
        assert point.skips_total == D(5)
        assert point.done_total == D(0)


def test_other_task_check_is_not_counted():
    d = example()
    d["variants"].append({
        "code": "C",
        "title": "Plunge only",
        "side": "other",
        "task": "Clear the pipe",
        "calls": [["Plunge", "Owner", "plunger", "job"]],
    })
    p = project_of(d)
    assert finals(p) == {"A": D(0), "B": D(5), "C": D(0)}
    assert series(p, "C")[-1].skips == []


def test_variant_without_task_counts_its_own_entities_only():
    d = example()
    for v in d["variants"]:
        v.pop("task")
    p = project_of(d, strict=False)
    assert finals(p) == {"A": D(0), "B": D(0)}


def absent_project() -> dict:
    """A part that one path checks and another throws away; a spare that only one path fits."""
    return {
        "format": 1,
        "name": "Absent parts",
        "existence_axis": {"name": "exists", "absent": "no"},
        "entities": [
            {
                "name": "Part",
                "axes": [
                    {"name": "exists", "values": ["yes", "no"]},
                    {"name": "check", "values": ["not checked", "checked"]},
                ],
            },
            {
                "name": "Spare",
                "axes": [
                    {"name": "exists", "values": ["no", "yes"]},
                    {"name": "check", "values": ["not checked", "checked"]},
                ],
            },
        ],
        "kinds": [
            {"name": "Check part", "entity": "Part", "axis": "check",
             "from": "not checked", "to": "checked", "check": True},
            {"name": "Throw part away", "entity": "Part", "axis": "exists",
             "from": "yes", "to": "no"},
            {"name": "Fit spare", "entity": "Spare", "axis": "exists",
             "from": "no", "to": "yes"},
            {"name": "Check spare", "entity": "Spare", "axis": "check",
             "from": "not checked", "to": "checked", "check": True},
        ],
        "executors": ["Owner"],
        "instruments": ["hands"],
        "scopes": ["job"],
        "batch_scope": "job",
        "variants": [
            {"code": "A", "title": "Check the part", "side": "own", "task": "Fix",
             "calls": [["Check part", "Owner", "hands", "job"]]},
            {"code": "B", "title": "Throw the part away", "side": "own", "task": "Fix",
             "calls": [["Throw part away", "Owner", "hands", "job"]]},
            {"code": "C", "title": "Throw away, fit and check a spare", "side": "other",
             "task": "Fix",
             "calls": [["Throw part away", "Owner", "hands", "job"],
                       ["Fit spare", "Owner", "hands", "job"],
                       ["Check spare", "Owner", "hands", "job"]]},
        ],
        "normalization": {
            "batch_size": 1,
            "kind_costs": {"Check part": 1, "Throw part away": 1, "Fit spare": 1,
                           "Check spare": 1},
            "executor_coefficients": {"Owner": 1},
            "scope_coefficients": {"job": 1},
            "axis_skip_prices": {"Part": {"check": 3}, "Spare": {"check": 5}},
        },
    }


def test_check_axis_of_absent_entity_is_not_skipped():
    p = project_of(absent_project())
    assert finals(p) == {"A": D(0), "B": D(0), "C": D(0)}
    assert start_point(p, "B").skips == [("Part", "check")]
    assert [point.skips for point in series(p, "B")] == [[]]
    assert [point.skips for point in series(p, "C")] == [[], [("Spare", "check")], []]
