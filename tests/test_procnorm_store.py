# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the project store."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from measure_twice.project import load_file
from measure_twice.store import ProjectInfo, Store, default_path, dumps

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"


def _project():
    project, remarks = load_file(LAUNDRY)
    assert project is not None, remarks
    return project


def test_dumps_round_trip_decimal():
    data = {"a": [Decimal("0.1"), Decimal("1E+1"), Decimal("8.40"), 3, True, None, "я \"q\""],
            "b": {}, "c": [], "d": {"x": {"y": Decimal("-2.50")}}}
    text = dumps(data)
    assert json.loads(text, parse_float=Decimal) == data
    assert "8.40" in text and "0.1" in text and "\"8.40\"" not in text
    assert "я" in text and "\\u" not in text
    assert text.startswith("{\n  \"a\": [\n    0.1,")


def test_dumps_rejects_float():
    with pytest.raises(TypeError):
        dumps({"a": 0.5})


def test_file_store_text_parse_same_data():
    original = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    with Store(":memory:") as st:
        i = st.add(_project())
        text = st.text(i)
        assert json.loads(text, parse_float=Decimal) == original
        assert st.get(i).data == original


def test_add_list_get():
    with Store(":memory:") as st:
        i = st.add(_project())
        info = st.list()
        assert info == [ProjectInfo(i, "Стирка белья", "Три способа постирать одну загрузку белья.",
                                    info[0].updated, 3)]
        assert st.get(i).name == "Стирка белья"
        with pytest.raises(KeyError):
            st.get(i + 100)
        with pytest.raises(KeyError):
            st.text(i + 100)


def test_replace_keeps_id_and_created():
    with Store(":memory:") as st:
        i = st.add(_project())
        created = st._db.execute("SELECT created FROM project WHERE id = ?", (i,)).fetchone()[0]
        p = _project()
        p.name = "Другая"
        p.data["name"] = "Другая"
        st.replace(i, p)
        assert [x.id for x in st.list()] == [i]
        assert st.list()[0].name == "Другая"
        assert st._db.execute("SELECT created FROM project WHERE id = ?", (i,)).fetchone()[0] == created
        with pytest.raises(KeyError):
            st.replace(i + 100, p)


def test_copy_and_delete_and_order():
    with Store(":memory:") as st:
        i = st.add(_project())
        j = st.copy(i)
        assert j != i
        assert st.get(j).name == "Стирка белья (2)"
        assert json.loads(st.text(j))["name"] == "Стирка белья (2)"
        assert [x.id for x in st.list()] == [i, j]
        st.delete(i)
        assert [x.id for x in st.list()] == [j]
        with pytest.raises(KeyError):
            st.copy(i)


def _named(name):
    project = _project()
    project.name = name
    project.data["name"] = name
    return project


def test_add_numbers_taken_names():
    with Store(":memory:") as st:
        ids = [st.add(_project()) for _ in range(3)]
        assert [x.name for x in st.list()] == ["Стирка белья", "Стирка белья (2)",
                                               "Стирка белья (3)"]
        assert json.loads(st.text(ids[2]))["name"] == "Стирка белья (3)"
        assert st.get(ids[1]).name == "Стирка белья (2)"


def test_copy_takes_first_free_number():
    with Store(":memory:") as st:
        first = st.add(_project())
        st.add(_project())
        third = st.copy(first)
        assert st.get(third).name == "Стирка белья (3)"
        assert st.get(st.copy(first)).name == "Стирка белья (4)"


def test_replace_numbers_name_of_another_only():
    with Store(":memory:") as st:
        first = st.add(_project())
        second = st.add(_named("Другая"))
        st.replace(first, _project())
        assert st.get(first).name == "Стирка белья"
        st.replace(second, _project())
        assert st.get(second).name == "Стирка белья (2)"
        assert json.loads(st.text(second))["name"] == "Стирка белья (2)"
        st.replace(second, _project())
        assert st.get(second).name == "Стирка белья (2)"


def test_list_counts_ways():
    with Store(":memory:") as st:
        i = st.add(_project())
        assert st.list()[0].ways == len(st.get(i).data["variants"]) == 3


def test_file_store_survives_reopen(tmp_path):
    path = tmp_path / "p.db"
    st = Store(path)
    i = st.add(_project())
    st.close()
    with Store(path) as st2:
        assert [x.id for x in st2.list()] == [i]
        assert st2.get(i).data == _project().data
        assert st2._db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "1"


def test_default_path_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    p = default_path()
    assert p == tmp_path / "measure_twice" / "measure_twice.db"
    assert p.parent.is_dir()


def test_default_path_keeps_old_database(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    old = tmp_path / "procnorm" / "procnorm.db"
    old.parent.mkdir()
    old.write_bytes(b"made-up")
    p = default_path()
    assert p == old
    assert old.read_bytes() == b"made-up"
    assert not (tmp_path / "measure_twice").exists()


def test_default_path_new_database_wins(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    old = tmp_path / "procnorm" / "procnorm.db"
    old.parent.mkdir()
    old.write_bytes(b"old")
    new = tmp_path / "measure_twice" / "measure_twice.db"
    new.parent.mkdir()
    new.write_bytes(b"new")
    assert default_path() == new


def test_default_path_windows_keeps_old_database(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "procnorm" / "procnorm.db"
    old.parent.mkdir()
    old.write_bytes(b"made-up")
    assert default_path() == old
    assert not (tmp_path / "measure_twice").exists()
