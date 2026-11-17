"""Tests of the offer bar after loading and the dot on the Step chains tab."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtWidgets import QApplication

from procnorm.store import Store
from procnorm.ui.app import MainWindow

from test_procnorm_ui_chains import _chains_file

REST = "Check how your steps were split into transitions before you compare."


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store):
    w = MainWindow(store)
    yield w
    w.close()


def _file(tmp_path, edit, name="edited.json"):
    data = json.loads(_chains_file(tmp_path).read_text(encoding="utf-8"))
    edit(data["variants"])
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _no_empty(variants):
    variants[0]["steps"][2]["calls"] = 1
    variants[0]["steps"][3]["calls"] = 2


def _two_empty(variants):
    variants[3]["steps"].append({"text": "Пусто", "calls": 0})


def _only_g_empty(variants):
    _no_empty(variants)
    _two_empty(variants)


def _no_steps(variants):
    for v in variants:
        v.pop("steps", None)


def test_before_any_load_no_bar_no_dot(win):
    assert not win.offer_visible() and not win.chains_dot()


def test_load_shows_bar_with_counts(win, tmp_path):
    assert win.load_path(_chains_file(tmp_path))
    name = win.projects.currentText()
    assert win.offer_visible()
    assert win.offer_text() == f"{name} loaded: 5 paths. {REST} 1 step has no transitions."
    assert win.tabs.currentWidget() is win.comparison
    assert win.chains_dot()


def test_plural_count_of_steps(win, tmp_path):
    win.load_path(_file(tmp_path, _two_empty))
    assert win.offer_text().endswith(f"{REST} 2 steps have no transitions.")


def test_no_empty_steps_drops_last_sentence(win, tmp_path):
    win.load_path(_file(tmp_path, _no_empty))
    assert win.offer_text() == f"{win.projects.currentText()} loaded: 5 paths. {REST}"


def test_paths_without_steps_do_not_count(win, tmp_path):
    win.load_path(_file(tmp_path, _no_steps))
    assert win.offer_text().endswith(REST)


def test_one_path_singular(win, tmp_path):
    win.load_path(_file(tmp_path, lambda v: v.__delitem__(slice(1, None))))
    assert " loaded: 1 path. " in win.offer_text()


def test_load_over_shows_bar(win, tmp_path):
    win.load_path(_file(tmp_path, _no_empty, "a.json"))
    win.offer_later_button.click()
    assert win.load_over_path(_chains_file(tmp_path))
    assert win.offer_visible() and win.chains_dot()
    assert win.offer_text().endswith("1 step has no transitions.")
    assert win.tabs.currentWidget() is win.comparison


def test_remarks_give_no_bar(win, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert not win.load_path(bad)
    assert not win.offer_visible() and not win.chains_dot()


def test_show_opens_first_path_with_empty_steps(win, tmp_path):
    win.load_path(_file(tmp_path, _only_g_empty))
    win.offer_show_button.click()
    assert win.tabs.currentWidget() is win.chains
    assert win.chains.current_code() == "Г"
    assert not win.offer_visible() and not win.chains_dot()


def test_show_without_empty_steps_opens_first_path(win, tmp_path):
    win.load_path(_file(tmp_path, _no_empty))
    win.chains.select_path("В")
    win.offer_show_button.click()
    assert win.tabs.currentWidget() is win.chains
    assert win.chains.current_code() == "А"


def test_not_now_hides_bar_keeps_dot_until_tab_opened(win, tmp_path):
    win.load_path(_chains_file(tmp_path))
    win.offer_later_button.click()
    assert not win.offer_visible() and win.chains_dot()
    assert win.tabs.currentWidget() is win.comparison
    win.tabs.setCurrentWidget(win.chains)
    assert not win.chains_dot()
    win.tabs.setCurrentWidget(win.comparison)
    assert not win.chains_dot()


def test_dot_keeps_tab_text(win, tmp_path):
    win.load_path(_chains_file(tmp_path))
    assert win.tabs.tabText(3) == "Step chains"


def test_choosing_from_list_gives_no_bar_no_dot(win, tmp_path):
    win.load_path(_file(tmp_path, _no_empty, "a.json"))
    win.load_path(_chains_file(tmp_path))
    assert win.offer_visible() and win.chains_dot()
    win.projects.setCurrentIndex(1 - win.projects.currentIndex())
    assert not win.offer_visible() and not win.chains_dot()
