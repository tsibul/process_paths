# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the kinds allowed at a place of a variant and of the slice there."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from process_paths.engine import initial_slice, run_variant
from procnorm.calc import allowed_kinds, slice_at
from procnorm.edit import add_call
from procnorm.project import read_project

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
CODES = ["А", "Б", "В"]


def base() -> dict:
    return json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)


def project_of(data: dict):
    project, remarks = read_project(data, strict=False)
    assert remarks == []
    return project


def variant_of(project, code: str):
    return next(v for v in project.model.variants if v.code == code)


def broken() -> dict:
    """The example whose variant А fails at transition 4 (the machine is started twice)."""
    data = base()
    variant = next(v for v in data["variants"] if v["code"] == "А")
    variant["calls"][3] = list(variant["calls"][2])
    return data


def add_result(data: dict, code: str, after: int, kind: str):
    """What ``add_call`` says to adding ``kind``: ``(error at the new transition, reason)``."""
    variant = next(v for v in data["variants"] if v["code"] == code)
    template = variant["calls"][0]
    new, remarks = add_call(data, code, after, [kind, *template[1:]])
    assert remarks == [] and new is not None
    errors = project_of(new).errors.get(code)
    if errors is not None and errors[0] == after + 1:
        return errors
    return None


@pytest.mark.parametrize("code", CODES)
def test_allowed_kinds_agree_with_add_call_at_every_place(code):
    data = base()
    project = project_of(data)
    count = len(variant_of(project, code).calls)
    names = [k.name for k in project.model.kinds]
    for after in range(count + 1):
        result = allowed_kinds(project, code, after)
        assert list(result) == names
        for kind in names:
            error = add_result(data, code, after, kind)
            if error is None:
                assert result[kind] is None, (after, kind)
            else:
                assert result[kind] == error[1], (after, kind)


@pytest.mark.parametrize("code", CODES)
def test_some_kinds_are_allowed_and_some_are_not(code):
    project = project_of(base())
    count = len(variant_of(project, code).calls)
    reasons = [allowed_kinds(project, code, after) for after in range(count + 1)]
    assert any(None in r.values() for r in reasons)
    assert any(any(x is not None for x in r.values()) for r in reasons)


def test_reasons_are_the_words_of_the_run():
    project = project_of(base())
    reasons = allowed_kinds(project, "А", 0)
    run = add_result(base(), "А", 0, "Постирать")
    assert run is not None
    assert reasons["Постирать"] == run[1]
    assert "expected" in run[1] or "condition" in run[1]
    assert reasons["Проверить карманы"] is None


def test_place_after_an_erroneous_transition_allows_all_kinds():
    project = project_of(broken())
    assert project.errors["А"][0] == 4
    names = [k.name for k in project.model.kinds]
    for after in (4, 5, 7):
        assert allowed_kinds(project, "А", after) == {name: None for name in names}
        assert slice_at(project, "А", after) is None
    assert slice_at(project, "А", 3) is not None
    assert allowed_kinds(project, "А", 3)["Запустить машину"] is not None


@pytest.mark.parametrize("code", CODES)
def test_slice_at_equals_the_run(code):
    project = project_of(base())
    v = variant_of(project, code)
    slices = run_variant(project.model, v)
    for after, expected in enumerate(slices):
        assert slice_at(project, code, after) == expected


def test_slice_at_zero_is_the_initial_slice_with_deviations():
    data = base()
    variant = next(v for v in data["variants"] if v["code"] == "Б")
    variant["initial"] = {"Бельё": {"состояние": "постирано"}}
    project = project_of(data)
    v = variant_of(project, "Б")
    result = slice_at(project, "Б", 0)
    assert result == initial_slice(project.model, v)
    assert result[("Бельё", "состояние")] == "постирано"
    plain = slice_at(project_of(base()), "Б", 0)
    assert plain[("Бельё", "состояние")] == "грязное"


def test_unknown_variant_or_place_is_refused():
    project = project_of(base())
    count = len(variant_of(project, "А").calls)
    with pytest.raises(KeyError):
        allowed_kinds(project, "нет", 0)
    with pytest.raises(IndexError):
        allowed_kinds(project, "А", count + 1)
    with pytest.raises(IndexError):
        slice_at(project, "А", -1)
