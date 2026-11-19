"""Tests of the Greek tap example (piece 34, as procnorm-119 for Russian).

The Greek file has the same structure and numbers as the English one, only its texts differ;
the path codes stay T1-T4.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import re

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from measure_twice import calc, i18n
from measure_twice.example import (
    EXAMPLE_FILE,
    EXAMPLE_NAME,
    add_example,
    example_file,
    example_name,
    first_run,
    load_example,
)
from measure_twice.project import load_file
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
# The keys of the file format; every other object key is a name of the project.
FORMAT_KEYS = {
    "format", "name", "description", "existence_axis", "absent", "entities", "axes", "values",
    "kinds", "entity", "axis", "from", "to", "check", "requires", "zero_weight",
    "zero_weight_note", "waiting", "waiting_unit", "executors", "instruments", "scopes",
    "batch_scope", "named_slices", "any", "states", "variants", "code", "title", "side", "task",
    "calls", "steps", "text", "normalization", "batch_size", "kind_costs",
    "executor_coefficients", "scope_coefficients", "axis_skip_prices",
}
# Texts that are values of the format, not names: they stay as they are.
FIXED = {"own", "other", "days", "T1", "T2", "T3", "T4"}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def _same_skeleton(en, el, where="") -> None:
    """The two files differ only in their texts; the format keys and the numbers are equal."""
    assert type(en) is type(el), where
    if isinstance(en, dict):
        assert len(en) == len(el), where
        for (key_en, item_en), (key_el, item_el) in zip(en.items(), el.items()):
            if key_en in FORMAT_KEYS:
                assert key_el == key_en, where
            else:
                assert key_el not in FORMAT_KEYS and GREEK.search(key_el), (where, key_el)
            _same_skeleton(item_en, item_el, where + "/" + key_en)
    elif isinstance(en, list):
        assert len(en) == len(el), where
        for i, (item_en, item_el) in enumerate(zip(en, el)):
            _same_skeleton(item_en, item_el, f"{where}/{i}")
    elif isinstance(en, str):
        if en in FIXED:
            assert el == en, where
        else:
            assert GREEK.search(el), (where, el)
    else:
        assert en == el, where


def test_greek_file_and_name_by_language():
    assert example_file("el") == EXAMPLE_FILE.with_name("example_el.json")
    assert example_name("el") == "Επισκευή βρύσης που στάζει"
    assert example_name("en") == EXAMPLE_NAME


def test_greek_tap_loads_strictly_with_greek_name():
    project, remarks = load_file(example_file("el"))
    assert remarks == []
    assert project.name == example_name("el")
    assert GREEK.search(project.name)
    assert load_example("el").name == example_name("el")


def test_greek_tap_has_the_structure_and_numbers_of_the_english_one():
    en = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
    el = json.loads(example_file("el").read_text(encoding="utf-8"))
    _same_skeleton(en, el)


def test_greek_tap_compares_as_the_english_one():
    en = calc.compare(load_example("en"))
    el = calc.compare(load_example("el"))
    assert len(el.executors) == len(en.executors)
    assert [r.code for r in el.rows] == [r.code for r in en.rows] == ["T1", "T2", "T3", "T4"]
    for row_en, row_el in zip(en.rows, el.rows):
        assert row_el.side == row_en.side
        assert row_el.steps == row_en.steps
        assert row_el.total == row_en.total
        assert list(row_el.labour.values()) == list(row_en.labour.values())
        assert row_el.waiting == row_en.waiting
        assert [s.total for s in row_el.slices] == [s.total for s in row_en.slices]


def test_add_greek_example_leaves_the_others(store):
    english = add_example(store)
    russian = add_example(store, "ru")
    greek = add_example(store, "el")
    assert len({english, russian, greek}) == 3
    assert add_example(store, "el") == greek
    names = sorted(i.name for i in store.list())
    assert names == sorted([EXAMPLE_NAME, example_name("ru"), example_name("el")])


def test_first_run_seeds_the_greek_tap(store, tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    first_run(store, settings, "el")
    assert [i.name for i in store.list()] == [example_name("el")]


def test_example_menu_adds_the_tap_in_greek(app, store, monkeypatch):
    english = add_example(store)
    monkeypatch.setattr(i18n, "_current", "el")
    win = MainWindow(store)
    try:
        assert example_name("el") in win.example_action.toolTip()
        win.show_example()
        names = [i.name for i in store.list()]
        assert sorted(names) == sorted([EXAMPLE_NAME, example_name("el")])
        assert win.projects.currentText() == example_name("el")
        win.show_example()
        assert len(store.list()) == 2
        assert any(i.id == english and i.name == EXAMPLE_NAME for i in store.list())
    finally:
        win.close()
