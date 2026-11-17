"""Tests of the New button: an empty project made in the window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtWidgets import QApplication

from procnorm.store import Store
from procnorm.ui.app import MainWindow
from tests.test_procnorm_edit_delete import with_spares


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    return tmp_path / "t.db"


@pytest.fixture
def store(db):
    s = Store(db)
    yield s
    s.close()


@pytest.fixture
def win(app, store):
    w = MainWindow(store)
    w.resize(1200, 900)
    w.show()
    yield w
    w.close()


def _answer(win, monkeypatch, name):
    """Stub the name prompt: it answers ``name`` (``None`` is a cancel) and records the
    prefilled text it was shown."""
    asked = []

    def ask(text):
        asked.append(text)
        return name

    monkeypatch.setattr(win, "ask_name", ask)
    return asked


def test_new_button_in_project_row(win):
    assert win.new_button.text() == "New"
    assert win.new_button.isEnabled()


def test_prompt_prefilled_with_new_project(win, monkeypatch):
    asked = _answer(win, monkeypatch, None)
    win.new_button.click()
    assert asked == ["New project"]


def test_new_project_listed_selected_dictionary_open(win, store, monkeypatch):
    _answer(win, monkeypatch, "Garden shed")
    win.new_button.click()
    assert win.project_names() == ["Garden shed"]
    assert win.projects.currentText() == "Garden shed"
    assert win.current_id is not None
    assert win.tabs.currentWidget() is win.dictionary
    project = store.get(win.current_id)
    assert project.name == "Garden shed"
    assert project.model.variants == []
    assert win.remarks_panel.isHidden()


def test_new_project_beside_loaded_one(win, store, monkeypatch, tmp_path):
    f = tmp_path / "shipping.json"
    f.write_text(json.dumps(with_spares(), default=float, ensure_ascii=False), encoding="utf-8")
    assert win.load_path(f)
    _answer(win, monkeypatch, "  Garden shed  ")
    win.new_button.click()
    assert len(win.project_names()) == 2
    assert win.projects.currentText() == "Garden shed"
    assert not win.offer_visible()
    assert not win.chains_dot()


def test_every_tab_shows_empty_project(app, win, monkeypatch):
    _answer(win, monkeypatch, "Garden shed")
    win.new_button.click()
    for page in (win.dictionary, win.norm, win.comparison, win.chains):
        win.tabs.setCurrentWidget(page)
        app.processEvents()
        assert page.isVisible()
    assert win.chains.codes() == []


def test_new_project_kept_after_restart(app, win, db, monkeypatch):
    _answer(win, monkeypatch, "Garden shed")
    win.new_button.click()
    pid = win.current_id
    win.close()
    with Store(db) as again:
        w2 = MainWindow(again)
        assert w2.project_names() == ["Garden shed"]
        assert w2.current_id == pid
        assert again.get(pid).model.variants == []
        w2.close()


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_name_refused_with_remark(win, store, monkeypatch, name):
    _answer(win, monkeypatch, name)
    win.new_button.click()
    assert store.list() == []
    assert win.project_names() == []
    assert not win.remarks_panel.isHidden()
    assert any("name is empty" in line for line in win.remarks_panel.lines())
    assert "not created" in win.remarks_panel.count_label.text()


def test_cancel_makes_nothing(win, store, monkeypatch):
    _answer(win, monkeypatch, None)
    win.new_button.click()
    assert store.list() == []
    assert win.remarks_panel.isHidden()


def test_remark_goes_after_good_name(win, monkeypatch):
    _answer(win, monkeypatch, "")
    win.new_button.click()
    _answer(win, monkeypatch, "Garden shed")
    win.new_button.click()
    assert win.remarks_panel.isHidden()
    assert win.project_names() == ["Garden shed"]


def test_empty_dictionary_tables_show_dash_or_add_row(win, monkeypatch):
    _answer(win, monkeypatch, "Garden shed")
    win.new_button.click()
    page = win.dictionary
    tables = (page.kinds, page.slices, page.entities, page.executors, page.instruments,
              page.params)
    for table in tables:
        assert table.rowCount() == 1
        assert table.item(0, 0).text().startswith("+ Add ")
    assert page.scopes.item(0, 0).text() == "batch"
