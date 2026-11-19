# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of waiting on the screen: the norm field, the kind form, the table and the charts."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from measure_twice.store import Store
from measure_twice.ui import pages
from measure_twice.ui.app import MainWindow
from measure_twice.ui.pages import KindForm

from tests.test_procnorm_waiting import data, project_of, with_weight

WAITING_NOTE = "Waiting kinds have no labour cost and are not checks"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def _window(store, tmp_path, d):
    f = tmp_path / "paint.json"
    f.write_text(json.dumps(d, default=str), encoding="utf-8")
    w = MainWindow(store)
    assert w.load_path(f)
    w.resize(1200, 900)
    w.show()
    QApplication.processEvents()
    return w


@pytest.fixture
def win(app, store, tmp_path):
    w = _window(store, tmp_path, data())
    yield w
    w.close()


@pytest.fixture
def weighted(app, store, tmp_path):
    w = _window(store, tmp_path, with_weight(2))
    yield w
    w.close()


@pytest.fixture
def forms(app):
    """Make kind forms without a window and delete them before the next test."""
    made = []

    def make(*args):
        form = KindForm(*args)
        made.append(form)
        return form

    yield make
    for form in made:
        form.deleteLater()
    QApplication.processEvents()


def _settle():
    for _ in range(3):
        QApplication.processEvents()


# ---------- norm page ----------

def test_norm_field_texts(win):
    assert pages.WAITING_WEIGHT_LABEL == "Labour per hour of waiting (in your cost unit)"
    assert pages.WAITING_WEIGHT_HINT == "0 = waiting is shown but not added to labour"
    text = win.norm.all_text()
    assert pages.WAITING_WEIGHT_LABEL in text
    assert pages.WAITING_WEIGHT_HINT in text


def test_norm_field_shows_setting(weighted):
    assert weighted.norm.waiting_weight.text() == "2"


def test_norm_field_empty_without_setting(win):
    assert win.norm.waiting_weight.text() == ""


def test_norm_field_edit_saves_and_adds_column(win, store):
    field = win.norm.waiting_weight
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "3")
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle()
    assert store.get(win.current_id).norm.labour_per_waiting_hour == 3
    assert "Labour + waiting" in win.comparison.headers()


def test_norm_field_refusal(win, store):
    field = win.norm.waiting_weight
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, "-4")
    QTest.keyClick(field, Qt.Key.Key_Return)
    _settle()
    assert store.get(win.current_id).norm.labour_per_waiting_hour == 0
    assert win.norm.refusal("labour_per_waiting_hour").isVisibleTo(win.norm)


def test_waiting_kind_cost_not_editable(win):
    it = win.norm.number_item("kind_costs", "Settle")
    assert not it.flags() & Qt.ItemFlag.ItemIsEditable
    assert not win.norm.is_missing("kind_costs", "Settle")


# ---------- kind form ----------

def test_kind_form_has_waiting_field(forms):
    p = project_of(data())
    form = forms(p.model)
    assert form.waiting.text() == ""
    assert [form.waiting_unit.itemText(i) for i in range(form.waiting_unit.count())] == [
        "hours", "days"]
    assert form.waiting_note.text() == WAITING_NOTE
    assert "waiting" not in form.structure()


def test_kind_form_waiting_hides_cost_and_check(forms):
    p = project_of(data())
    form = forms(p.model)
    form.show()
    assert form.check.isVisibleTo(form)
    assert not form.waiting_note.isVisibleTo(form)
    form.waiting.setText("5")
    form.waiting_unit.setCurrentText("days")
    assert not form.check.isVisibleTo(form)
    assert not form.zero_weight.isVisibleTo(form)
    assert form.waiting_note.isVisibleTo(form)
    s = form.structure()
    assert s["waiting"] == "5"
    assert s["waiting_unit"] == "days"
    assert s["check"] is False
    assert s["zero_weight"] is False
    form.waiting.setText("")
    assert form.check.isVisibleTo(form)
    form.close()


def test_kind_form_fills_waiting_kind(forms):
    p = project_of(data())
    k = p.model.kind("Cure")
    form = forms(p.model, k, p.waiting.get("Cure"))
    assert form.waiting.text() == "1"
    assert form.waiting_unit.currentText() == "days"


def test_kind_form_edit_keeps_waiting(win, store):
    page = win.dictionary
    win.tabs.setCurrentWidget(page)
    _settle()
    page.edit_button("kind", "Settle").click()
    _settle()
    form = page.kind_form()
    assert form.waiting.text() == "3"
    form.waiting.setText("4")
    form.submit_button.click()
    _settle()
    k = next(x for x in store.get(win.current_id).data["kinds"] if x["name"] == "Settle")
    assert k["waiting"] == 4
    assert k["waiting_unit"] == "hours"


# ---------- comparison table and charts ----------

def test_table_waiting_column(win):
    c = win.comparison
    h = c.headers()
    assert h[h.index("Labour · total") + 1] == "Waiting"
    assert "Labour + waiting" not in h
    assert c.cell("P1", "Waiting") == "27 h"
    assert c.cell("P2", "Waiting") == "1 d"
    assert c.cell("P3", "Waiting") == "—"


def test_table_labour_waiting_column(weighted):
    c = weighted.comparison
    h = c.headers()
    assert h[h.index("Waiting") + 1] == "Labour + waiting"
    assert c.cell("P1", "Labour + waiting") == "61.00"


def test_labour_total_still_bold_on_least(win):
    assert win.comparison.is_bold("P1", "Labour · total")
    assert not win.comparison.is_bold("P1", "Waiting")


def test_charts_without_setting(win):
    pair = win.comparison.chart_pairs()[0]
    assert pair.charts.labour_waiting.isHidden()


def test_charts_with_setting(weighted):
    pair = weighted.comparison.chart_pairs()[0]
    view = pair.charts.labour_waiting
    assert not view.isHidden()
    lines = {s.name().split(" · ")[0]: [p.y() for p in s.points()] for s in view.chart().series()}
    assert lines["P1"] == [0, 2, 8, 12, 60, 61]
