# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end test of piece 14 in the window: variant «Б» of the example file
tests/data/laundry.json is entered into a project with the laundry dictionary only by actions of
the window (New, the header fields, the input rows of transitions) and equals the variant of the
file without its human steps."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from procnorm.store import Store
from procnorm.ui.app import MainWindow

TEXT = (Path(__file__).parent / "data" / "laundry.json").read_text("utf-8")
LAUNDRY = json.loads(TEXT, parse_float=Decimal)

CODE = "Б"


def _find(data, code):
    return next(v for v in data["variants"] if v["code"] == code)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "b.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    data = json.loads(TEXT)
    data["variants"].remove(_find(data, CODE))
    path = tmp_path / "laundry_without_b.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    w = MainWindow(store)
    assert w.load_path(path)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.chains)
    QApplication.processEvents()
    yield w
    w.close()


def _click(button):
    assert button.isEnabled()
    button.click()
    QApplication.processEvents()


def _type(field, text):
    """Replace the text of a field as a paste does (QTest types only Latin keys), then leave it."""
    field.setFocus()
    field.selectAll()
    field.insert(text)
    field.editingFinished.emit()
    QApplication.processEvents()


def test_variant_b_entered_in_the_window_equals_the_file(win, store):
    full = _find(LAUNDRY, CODE)
    expected = {k: v for k, v in full.items() if k != "steps"}
    page = win.chains

    _click(page.new_button)
    assert page.current_code() == "New 1"
    page.code_edit.setFocus()
    page.code_edit.selectAll()
    page.code_edit.insert(CODE)
    _type(page.title_edit, full["title"])
    assert page.current_code() == CODE
    _click(page.theirs_radio)
    _type(page.task_edit, full["task"])

    t = page.table
    _click(t.buttons_at(t.kinds.index("none")).add)
    for number, call in enumerate(full["calls"], 1):
        t = page.table
        inp = t.input
        assert call[0] in inp.allowed(), (number, inp.reasons())
        for field_, value in zip(("kind", "executor", "instrument", "scope"), call):
            inp.set_value(field_, value)
        assert inp.values() == call
        _click(inp.add_button)
        assert page.refusal.isHidden()
        assert page.current_code() == CODE

    data = store.get(win.current_id).data
    assert _find(data, CODE) == expected
    assert [v["code"] for v in data["variants"]] == ["А", "В", CODE]
