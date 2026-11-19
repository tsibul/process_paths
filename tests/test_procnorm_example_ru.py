"""Tests of the tap example in the window language (procnorm-119).

The tap is one: the Russian file has the same structure and numbers as the English one, only
its texts differ. `New ▾ → Example` adds the tap in the window language; an example already in
the store stays as it is.
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

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
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


def _same_skeleton(en, ru, where="") -> None:
    """The two files differ only in their texts; the format keys and the numbers are equal."""
    assert type(en) is type(ru), where
    if isinstance(en, dict):
        assert len(en) == len(ru), where
        for (key_en, item_en), (key_ru, item_ru) in zip(en.items(), ru.items()):
            if key_en in FORMAT_KEYS:
                assert key_ru == key_en, where
            else:
                assert key_ru not in FORMAT_KEYS and CYRILLIC.search(key_ru), (where, key_ru)
            _same_skeleton(item_en, item_ru, where + "/" + key_en)
    elif isinstance(en, list):
        assert len(en) == len(ru), where
        for i, (item_en, item_ru) in enumerate(zip(en, ru)):
            _same_skeleton(item_en, item_ru, f"{where}/{i}")
    elif isinstance(en, str):
        if en in FIXED:
            assert ru == en, where
        else:
            assert CYRILLIC.search(ru), (where, ru)
    else:
        assert en == ru, where


def test_file_by_language_with_english_fallback():
    assert example_file("en") == EXAMPLE_FILE
    assert example_file("ru") == EXAMPLE_FILE.with_name("example_ru.json")
    assert example_file("xx") == EXAMPLE_FILE
    assert example_name("en") == EXAMPLE_NAME == "Fix a leaking tap"
    assert example_name("xx") == EXAMPLE_NAME


def test_russian_tap_loads_strictly_with_russian_name():
    project, remarks = load_file(example_file("ru"))
    assert remarks == []
    assert project.name == example_name("ru")
    assert CYRILLIC.search(project.name)
    assert load_example("ru").name == example_name("ru")


def test_russian_tap_has_the_structure_and_numbers_of_the_english_one():
    en = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
    ru = json.loads(example_file("ru").read_text(encoding="utf-8"))
    _same_skeleton(en, ru)


def test_russian_tap_compares_as_the_english_one():
    en = calc.compare(load_example("en"))
    ru = calc.compare(load_example("ru"))
    assert len(ru.executors) == len(en.executors)
    assert [r.code for r in ru.rows] == [r.code for r in en.rows] == ["T1", "T2", "T3", "T4"]
    for row_en, row_ru in zip(en.rows, ru.rows):
        assert row_ru.side == row_en.side
        assert row_ru.steps == row_en.steps
        assert row_ru.total == row_en.total
        assert list(row_ru.labour.values()) == list(row_en.labour.values())
        assert row_ru.waiting == row_en.waiting
        assert [s.total for s in row_ru.slices] == [s.total for s in row_en.slices]


def test_english_example_unchanged():
    project = load_example()
    assert project.name == "Fix a leaking tap"
    assert [r.title for r in calc.compare(project).rows] == [
        "Replace the washer", "Replace the whole tap", "Tighten the nut and wrap tape",
        "Call a plumber",
    ]


def test_add_russian_example_leaves_the_english_one(store):
    english = add_example(store)
    before = store.get(english)
    russian = add_example(store, "ru")
    assert russian != english
    assert add_example(store, "ru") == russian
    assert sorted(i.name for i in store.list()) == sorted([EXAMPLE_NAME, example_name("ru")])
    assert store.get(english) == before


def test_first_run_seeds_the_tap_in_the_language(store, tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    first_run(store, settings, "ru")
    assert [i.name for i in store.list()] == [example_name("ru")]


def test_example_menu_adds_the_tap_in_the_window_language(app, store, monkeypatch):
    english = add_example(store)
    monkeypatch.setattr(i18n, "_current", "ru")
    win = MainWindow(store)
    try:
        assert example_name("ru") in win.example_action.toolTip()
        win.show_example()
        names = [i.name for i in store.list()]
        assert sorted(names) == sorted([EXAMPLE_NAME, example_name("ru")])
        assert win.projects.currentText() == example_name("ru")
        win.show_example()
        assert len(store.list()) == 2
        assert any(i.id == english and i.name == EXAMPLE_NAME for i in store.list())
    finally:
        win.close()


def test_example_menu_in_english_adds_the_english_tap(app, store):
    win = MainWindow(store)
    try:
        win.show_example()
        assert [i.name for i in store.list()] == [EXAMPLE_NAME]
    finally:
        win.close()
