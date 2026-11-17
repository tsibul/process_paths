# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the edits of transitions and variants: add, remove, move, copy, delete, rename."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from procnorm.edit import (add_call, copy_variant, delete_variant, move_call, remove_call,
                           rename_variant)
from procnorm.project import read_project

TEXT = (Path(__file__).parent / "data" / "laundry.json").read_text(encoding="utf-8")
A, B = "А", "Б"
# variant А: 7 calls; steps hold 0, 1, 1, 2, 1, 1, 1 of them
STEPS_A = [0, 1, 1, 2, 1, 1, 1]


def base() -> dict:
    return json.loads(TEXT, parse_float=Decimal)


def variant(d: dict, code: str = A) -> dict:
    return next(v for v in d["variants"] if v["code"] == code)


def counts(d: dict, code: str = A) -> list[int]:
    return [s["calls"] for s in variant(d, code)["steps"]]


def reload(d: dict) -> dict:
    """The data as a file with the same text would be read."""
    return json.loads(json.dumps(d, ensure_ascii=False, default=str), parse_float=Decimal)


def ok(result):
    new, remarks = result
    assert remarks == [] and new is not None
    return new


def test_laundry_steps_are_as_assumed():
    assert counts(base()) == STEPS_A


# ---------- add_call ----------

def test_add_call_equals_file_and_joins_step_of_row_above():
    d = base()
    before = copy.deepcopy(d)
    call = list(variant(d)["calls"][1])          # a copy of call 2, harmless in the run
    new = ok(add_call(d, A, 2, call))
    assert d == before                           # the argument is not changed
    expected = base()
    variant(expected)["calls"].insert(2, call)
    variant(expected)["steps"][2]["calls"] += 1  # step of call 2
    assert new == expected
    assert counts(new) == [0, 1, 2, 2, 1, 1, 1]
    project, remarks = read_project(new, strict=False)
    assert remarks == [] and project is not None


def test_add_call_to_empty_step_by_index():
    new = ok(add_call(base(), A, 0, list(variant(base())["calls"][0]), step=0))
    assert counts(new) == [1, 1, 1, 2, 1, 1, 1]
    assert variant(new)["calls"][0] == variant(base())["calls"][0]


def test_add_call_at_start_without_step_goes_to_first_step():
    new = ok(add_call(base(), A, 0, list(variant(base())["calls"][0])))
    assert counts(new)[0] == 1 and sum(counts(new)) == 8


def test_add_call_step_must_contain_the_place():
    new, remarks = add_call(base(), A, 3, list(variant(base())["calls"][0]), step=5)
    assert new is None and remarks


def test_add_call_to_variant_without_steps_changes_only_calls():
    d = base()
    del variant(d, B)["steps"]
    call = list(variant(d, B)["calls"][0])
    new = ok(add_call(d, B, 1, call))
    assert "steps" not in variant(new, B)
    assert len(variant(new, B)["calls"]) == 6


@pytest.mark.parametrize("after", [-1, 8])
def test_add_call_bad_place_refused(after):
    new, remarks = add_call(base(), A, after, list(variant(base())["calls"][0]))
    assert new is None and remarks


def test_add_call_unknown_variant_refused():
    new, remarks = add_call(base(), "нет", 1, list(variant(base())["calls"][0]))
    assert new is None and remarks


def test_add_call_unknown_kind_refused():
    new, remarks = add_call(base(), A, 1, ["Нет такого", "Человек", "руки", "каждая вещь"])
    assert new is None and remarks


def test_add_call_that_breaks_the_run_is_accepted_with_error_number():
    new = ok(add_call(base(), A, 2, list(variant(base())["calls"][3])))   # wash before the machine
    project, _ = read_project(new, strict=False)
    assert list(project.errors) == [A] and project.errors[A][0] == 3


# ---------- remove_call ----------

def test_remove_call_equals_file_and_shrinks_its_step():
    d = base()
    new = ok(remove_call(d, A, 2))
    expected = base()
    del variant(expected)["calls"][1]
    variant(expected)["steps"][2]["calls"] -= 1
    assert new == expected
    assert counts(new) == [0, 1, 0, 2, 1, 1, 1]      # the step stays, empty


def test_remove_call_from_two_call_step():
    new = ok(remove_call(base(), A, 4))
    assert counts(new) == [0, 1, 1, 1, 1, 1, 1]


@pytest.mark.parametrize("number", [0, 8])
def test_remove_call_bad_number_refused(number):
    new, remarks = remove_call(base(), A, number)
    assert new is None and remarks


def test_remove_middle_gives_errors_with_number():
    new = ok(remove_call(base(), A, 3))
    project, remarks = read_project(new, strict=False)
    assert remarks == [] and project is not None
    assert list(project.errors) == [A] and project.errors[A][0] == 3


# ---------- move_call ----------

def test_move_within_step_swaps_calls_keeps_counts():
    new = ok(move_call(base(), A, 3, +1))            # calls 3, 4 are the one step of two
    expected = base()
    c = variant(expected)["calls"]
    c[2], c[3] = c[3], c[2]
    assert new == expected
    assert counts(new) == STEPS_A


def test_move_up_first_call_of_step_goes_to_previous_step():
    new = ok(move_call(base(), A, 2, -1))            # first and only call of step 2
    assert variant(new)["calls"] == variant(base())["calls"]       # the order is the same
    assert counts(new) == [0, 2, 0, 2, 1, 1, 1]


def test_move_up_into_empty_previous_step_is_the_same_rule():
    new = ok(move_call(base(), A, 1, -1))            # call 1 is in step 1, step 0 is empty
    assert counts(new) == [1, 0, 1, 2, 1, 1, 1]


def test_move_down_last_call_of_step_goes_to_next_step():
    new = ok(move_call(base(), A, 2, +1))
    assert variant(new)["calls"] == variant(base())["calls"]
    assert counts(new) == [0, 1, 0, 3, 1, 1, 1]


def test_move_down_last_call_of_two_call_step_leaves_one():
    new = ok(move_call(base(), A, 4, +1))
    assert counts(new) == [0, 1, 1, 1, 2, 1, 1]
    assert variant(new)["calls"] == variant(base())["calls"]


def test_move_up_first_of_two_call_step():
    new = ok(move_call(base(), A, 3, -1))
    assert counts(new) == [0, 1, 2, 1, 1, 1, 1]
    assert variant(new)["calls"] == variant(base())["calls"]


@pytest.mark.parametrize("number,delta", [(1, -1), (7, +1)])
def test_move_at_the_ends_refused_when_no_step_to_go(number, delta):
    d = base()
    variant(d)["steps"] = [{"text": "всё", "calls": 7}]
    new, remarks = move_call(d, A, number, delta)
    assert new is None and remarks


def test_move_last_call_down_into_nothing_refused():
    new, remarks = move_call(base(), A, 7, +1)
    assert new is None and remarks


def test_move_bad_arguments_refused():
    assert move_call(base(), A, 0, 1)[0] is None
    assert move_call(base(), A, 2, 2)[0] is None
    assert move_call(base(), "нет", 2, 1)[0] is None


def test_move_equals_file_and_may_break_run():
    new = ok(move_call(base(), A, 4, -1))            # wash before the machine start
    project, remarks = read_project(new, strict=False)
    assert remarks == [] and project.errors[A][0] == 3


def test_move_in_variant_without_steps_swaps_only():
    d = base()
    del variant(d, B)["steps"]
    new = ok(move_call(d, B, 1, +1))
    expected = copy.deepcopy(d)
    c = variant(expected, B)["calls"]
    c[0], c[1] = c[1], c[0]
    assert new == expected


# ---------- copy_variant ----------

def test_copy_gets_new_code_same_task_and_side():
    d = base()
    new = ok(copy_variant(d, B))
    codes = [v["code"] for v in new["variants"]]
    assert codes == [A, B, "Б (copy)", "В"]          # next to the original
    c, o = variant(new, "Б (copy)"), variant(new, B)
    assert c["task"] == o["task"] and c["side"] == o["side"]
    assert c["title"] == o["title"] and c["calls"] == o["calls"] and c["steps"] == o["steps"]
    assert c is not o and c["calls"] is not o["calls"]
    project, remarks = read_project(new, strict=False)
    assert remarks == [] and project.tasks["Б (copy)"] == project.tasks[B]
    assert project.sides["Б (copy)"] == "other"


def test_copy_twice_refused_as_duplicate():
    new = ok(copy_variant(base(), A))
    again, remarks = copy_variant(new, A)
    assert again is None and remarks


def test_copy_unknown_refused():
    assert copy_variant(base(), "нет")[0] is None


# ---------- delete_variant ----------

def test_delete_variant_equals_file():
    new = ok(delete_variant(base(), B))
    expected = base()
    expected["variants"] = [v for v in expected["variants"] if v["code"] != B]
    assert new == expected


def test_delete_unknown_refused():
    assert delete_variant(base(), "нет")[0] is None


# ---------- rename_variant ----------

def test_rename_code_and_title():
    new = ok(rename_variant(base(), B, "Б2", "Новое название"))
    v = variant(new, "Б2")
    assert v["title"] == "Новое название"
    assert [x["code"] for x in new["variants"]] == [A, "Б2", "В"]
    assert v["calls"] == variant(base(), B)["calls"]


def test_rename_title_only_keeps_code():
    new = ok(rename_variant(base(), B, B, "Другое"))
    assert variant(new, B)["title"] == "Другое"


def test_rename_to_duplicate_code_refused():
    new, remarks = rename_variant(base(), B, A, "x")
    assert new is None and remarks


@pytest.mark.parametrize("code,title", [("", "x"), ("  ", "x"), ("Б", ""), ("Б", "  ")])
def test_rename_empty_refused(code, title):
    new, remarks = rename_variant(base(), B, code, title)
    assert new is None and remarks


def test_rename_unknown_refused():
    assert rename_variant(base(), "нет", "н", "x")[0] is None


def test_edits_do_not_change_argument():
    d = base()
    before = copy.deepcopy(d)
    for f in (lambda: remove_call(d, A, 3), lambda: move_call(d, A, 2, -1),
              lambda: copy_variant(d, A), lambda: delete_variant(d, A),
              lambda: rename_variant(d, A, "Я", "я")):
        f()
    assert d == before
