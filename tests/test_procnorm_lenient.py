# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the lenient project read (``strict=False``) and the transition number of run errors."""

import pytest

from process_paths.engine import TransitionError, run_variant
from procnorm.project import read_project
from tests.test_procnorm_project import base, has, kind, variant


def lenient(d):
    return read_project(d, strict=False)


# ---------- strict mode stays as it was ----------

def test_strict_is_default_and_has_no_errors():
    project, remarks = read_project(base())
    assert remarks == [] and project.errors == {}


def test_strict_refuses_missing_number():
    d = base()
    del d["normalization"]["kind_costs"]["Развесить"]
    project, remarks = read_project(d, strict=True)
    assert project is None and has(remarks, "kind without cost: Развесить")


def test_strict_refuses_run_error():
    d = base()
    del variant(d, "А")["calls"][4]
    project, remarks = read_project(d)
    assert project is None and remarks


# ---------- missing numbers ----------

@pytest.mark.parametrize("mutate", [
    lambda d: d["normalization"]["kind_costs"].pop("Развесить"),
    lambda d: d["normalization"]["executor_coefficients"].pop("Машина"),
    lambda d: d["normalization"]["scope_coefficients"].pop("вся загрузка"),
    lambda d: d["normalization"]["axis_skip_prices"]["Бельё"].pop("цвета"),
])
def test_lenient_missing_number_gives_project(mutate):
    d = base()
    mutate(d)
    project, remarks = lenient(d)
    assert remarks == [] and project is not None
    assert project.errors == {}


def test_lenient_missing_number_stays_missing():
    d = base()
    del d["normalization"]["kind_costs"]["Развесить"]
    project, _ = lenient(d)
    assert "Развесить" not in project.norm.kind_costs
    assert project.data is d


@pytest.mark.parametrize("mutate,fragment", [
    (lambda d: d["normalization"]["kind_costs"].update({"Развесить": -1}), "cost below zero"),
    (lambda d: d["normalization"]["kind_costs"].update({"Лишний": 1}), "cost of unknown kind"),
    (lambda d: d["normalization"]["axis_skip_prices"]["Бельё"].update({"цвета": 0}),
     "price must be above zero"),
])
def test_lenient_other_normalization_remarks_refuse(mutate, fragment):
    d = base()
    mutate(d)
    project, remarks = lenient(d)
    assert project is None and has(remarks, fragment)


# ---------- run errors ----------

def test_lenient_variant_broken_in_middle_gives_project():
    d = base()
    del variant(d, "А")["calls"][4]  # no hanging: call 5 (drying) finds the linen washed
    project, remarks = lenient(d)
    assert remarks == [] and project is not None
    assert set(project.errors) == {"А"}
    number, text = project.errors["А"]
    assert number == 5
    assert "постирано" in text and "развешано" in text
    assert [v.code for v in project.model.variants] == ["А", "Б", "В"]


def test_lenient_first_call_error_number():
    d = base()
    del variant(d, "Б")["calls"][0]
    project, _ = lenient(d)
    assert project.errors["Б"][0] == 1


def test_lenient_several_broken_variants():
    d = base()
    del variant(d, "А")["calls"][4]
    del variant(d, "В")["calls"][3]
    project, _ = lenient(d)
    assert project.errors["А"][0] == 5
    assert project.errors["В"][0] == 4


def test_lenient_missing_number_and_run_error_together():
    d = base()
    del d["normalization"]["kind_costs"]["Убрать в шкаф"]
    del variant(d, "А")["calls"][4]
    project, remarks = lenient(d)
    assert remarks == [] and set(project.errors) == {"А"}


# ---------- still refused in both modes ----------

@pytest.mark.parametrize("strict", [True, False])
def test_dictionary_error_refuses(strict):
    d = base()
    kind(d, "Развесить")["entity"] = "Нет"
    project, remarks = read_project(d, strict=strict)
    assert project is None and has(remarks, "unknown entity")


@pytest.mark.parametrize("strict", [True, False])
def test_structure_error_refuses(strict):
    d = base()
    d["name"] = 5
    project, remarks = read_project(d, strict=strict)
    assert project is None and remarks


@pytest.mark.parametrize("strict", [True, False])
def test_variant_name_error_refuses(strict):
    d = base()
    variant(d, "А")["calls"][0][1] = "Робот"
    project, remarks = read_project(d, strict=strict)
    assert project is None and has(remarks, "unknown executor Робот")


@pytest.mark.parametrize("strict", [True, False])
def test_split_error_refuses(strict):
    d = base()
    d["kinds"].append({"name": "Повесить", "entity": "Бельё", "axis": "состояние",
                       "from": "постирано", "to": "развешано"})
    d["normalization"]["kind_costs"]["Повесить"] = 1
    project, remarks = read_project(d, strict=strict)
    assert project is None and has(remarks, "same change of state")


# ---------- transition number on the run error ----------

def test_transition_error_carries_number():
    d = base()
    del variant(d, "А")["calls"][4]
    project, _ = lenient(d)
    v = project.model.variants[0]
    with pytest.raises(TransitionError) as info:
        run_variant(project.model, v)
    assert info.value.number == 5
    assert str(info.value).startswith("variant А, call 5 (Дождаться высыхания): ")
    assert info.value.reason == "Бельё/состояние is 'постирано', expected 'развешано'"
