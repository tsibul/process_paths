# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of saving edited project data and of the lenient ``Store.get``."""

import copy
from decimal import Decimal

import pytest

from measure_twice.project import read_project
from measure_twice.store import Store, dumps
from tests.test_procnorm_project import base


@pytest.fixture
def store():
    with Store(":memory:") as s:
        yield s


def _added(store):
    project, remarks = read_project(base())
    assert project is not None, remarks
    return store.add(project)


def test_save_then_get_same_data(store):
    id = _added(store)
    data = copy.deepcopy(store.get(id).data)
    kind = next(iter(data["normalization"]["kind_costs"]))
    data["normalization"]["kind_costs"][kind] = Decimal("7.25")
    store.save(id, data)
    assert store.get(id).data == data


def test_save_text_equals_dumps(store):
    id = _added(store)
    data = copy.deepcopy(store.get(id).data)
    kind = next(iter(data["normalization"]["kind_costs"]))
    data["normalization"]["kind_costs"][kind] = Decimal("3.5")
    store.save(id, data)
    assert store.text(id) == dumps(data)
    stored = store._db.execute("SELECT data FROM project WHERE id = ?", (id,)).fetchone()[0]
    assert stored == dumps(data)


def test_get_opens_project_with_missing_number(store):
    id = _added(store)
    data = copy.deepcopy(store.get(id).data)
    kind = next(iter(data["normalization"]["kind_costs"]))
    del data["normalization"]["kind_costs"][kind]
    store.save(id, data)
    project = store.get(id)
    assert project.data == data


def test_save_unknown_id(store):
    with pytest.raises(KeyError):
        store.save(999, base())


def test_save_keeps_schema_version_one(store):
    _added(store)
    row = store._db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert row[0] == "1"
