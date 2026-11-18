# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the empty project: the start of the manual input."""

from measure_twice import edit
from measure_twice.calc import compare
from measure_twice.project import read_project
from measure_twice.store import Store


def test_empty_project_reads_leniently():
    data, none = edit.empty_project("Garden")
    assert none == []
    project, remarks = read_project(data, strict=False)
    assert remarks == []
    assert project is not None and project.name == "Garden"
    assert data["format"] == 1
    assert data["existence_axis"] == {"name": "exists", "absent": "no"}
    assert data["scopes"] == ["batch"] and data["batch_scope"] == "batch"
    for key in ("entities", "kinds", "executors", "instruments", "variants"):
        assert data[key] == []
    for table in edit.NUMBER_TABLES:
        assert data["normalization"][table] == {}


def test_empty_project_compares_to_nothing():
    project, _ = read_project(edit.empty_project("Garden")[0], strict=False)
    comparison = compare(project)
    assert comparison.rows == [] and comparison.excluded == []


def test_empty_project_is_new_each_time():
    a, _ = edit.empty_project("A")
    a["kinds"].append({})
    assert edit.empty_project("B")[0]["kinds"] == []


def test_empty_project_stored_equal():
    data, _ = edit.empty_project("Garden")
    project, _ = read_project(data, strict=False)
    with Store(":memory:") as st:
        i = st.add(project)
        assert st.get(i).data == data


def test_empty_name_refused():
    for name in ("", "   "):
        data, remarks = edit.empty_project(name)
        assert data is None and len(remarks) == 1
