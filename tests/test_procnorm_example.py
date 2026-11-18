"""Tests of the built-in example project of procnorm."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from procnorm.example import (EXAMPLE_FILE, EXAMPLE_NAME, SEEDED, add_example, first_run,
                              load_example)
from procnorm.project import load_file
from procnorm.store import Store
from procnorm.ui.app import build_window


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def names(store):
    return [i.name for i in store.list()]


def test_example_file_loads_strictly():
    project, remarks = load_file(EXAMPLE_FILE)
    assert remarks == []
    assert project.name == EXAMPLE_NAME
    assert load_example().name == EXAMPLE_NAME


def test_first_run_seeds_empty_store(store, settings):
    pid = first_run(store, settings)
    assert names(store) == [EXAMPLE_NAME]
    assert pid == store.list()[0].id


def test_deleted_example_does_not_return(store, settings):
    pid = first_run(store, settings)
    store.delete(pid)
    assert first_run(store, settings) is None
    assert store.list() == []


def test_first_run_with_existing_project_adds_nothing(store, settings):
    other, _ = load_file(EXAMPLE_FILE)
    other.name = "Mine"
    store.add(other)
    assert first_run(store, settings) is None
    assert names(store) == ["Mine"]
    assert settings.value(SEEDED) is not None


def test_add_example_twice_gives_one_project(store):
    first = add_example(store)
    second = add_example(store)
    assert first == second
    assert names(store) == [EXAMPLE_NAME]


def test_window_opens_on_example_comparison(app, store, settings):
    pid = first_run(store, settings)
    window = build_window(store, settings, pid)
    assert window.current_id == pid
    assert window.project_names() == [EXAMPLE_NAME]
    assert window.tabs.currentWidget() is window.comparison
    window.close()


def test_packaged_example_equals_docs_example():
    docs = Path(__file__).parent.parent / "docs" / "example_tap.json"
    assert EXAMPLE_FILE.read_bytes() == docs.read_bytes()


def test_example_button_adds_example(app, store, settings):
    other, _ = load_file(EXAMPLE_FILE)
    other.name = "Mine"
    store.add(other)
    window = build_window(store, settings)
    window.tabs.setCurrentWidget(window.dictionary)
    window.example_button.click()
    assert sorted(names(store)) == sorted(["Mine", EXAMPLE_NAME])
    assert window.projects.currentText() == EXAMPLE_NAME
    assert window.tabs.currentWidget() is window.comparison
    assert window.statusBar().currentMessage() == "Added Fix a leaking tap"
    window.close()


def test_example_button_selects_existing_example(app, store, settings):
    pid = add_example(store)
    other, _ = load_file(EXAMPLE_FILE)
    other.name = "Mine"
    mine = store.add(other)
    window = build_window(store, settings, mine)
    window.tabs.setCurrentWidget(window.dictionary)
    window.example_button.click()
    assert sorted(names(store)) == sorted(["Mine", EXAMPLE_NAME])
    assert window.current_id == pid
    assert window.tabs.currentWidget() is window.comparison
    assert window.statusBar().currentMessage() == "Example is already in the list"
    window.close()
