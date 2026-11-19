# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the wording of piece 24a: "check price" instead of "skip price" in visible texts."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from measure_twice import report
from dataclasses import replace

from measure_twice.calc import _missing
from measure_twice.project import load_file
from measure_twice.ui.pages import NormPage

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def laundry():
    p, remarks = load_file(LAUNDRY)
    assert p is not None, remarks
    return p


def _visible_texts(page) -> list[str]:
    out = [w.text() for w in page.findChildren(QLabel)]
    for t in page.findChildren(QTableWidget):
        out += [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())
                if t.horizontalHeaderItem(c) is not None]
    return out


def test_settings_tab_has_check_prices(app, laundry):
    page = NormPage()
    page.show_project(laundry)
    texts = _visible_texts(page)
    assert "CHECK PRICES" in texts
    assert "Check price" in texts
    assert not [t for t in texts if "skip" in t.lower()]


def test_report_pages_have_no_skip(app, laundry):
    for page in report.pages(laundry):
        assert "skip" not in " ".join(t.text for t in page.texts).lower()


def test_assumptions_page_check_prices_and_sentence(app, laundry):
    page = report.pages(laundry, chosen=["assumptions"])[0]
    lines = [t.text for t in page.texts]
    assert "Check prices" in lines
    assert "Check price" in lines
    assert report.CHECK_PRICE_NOTE == (
        "Check price is added to Risk left when a way does not do the check.")
    assert report.CHECK_PRICE_NOTE in lines
    ys = {t.text: t.y for t in page.texts}
    assert ys[report.CHECK_PRICE_NOTE] > ys["Check price"]


def test_missing_price_remark_says_check(app, laundry):
    bare = replace(laundry, norm=replace(laundry.norm, skip_prices={}))
    found = [t for v in bare.model.variants for t in _missing(bare, v)]
    assert any(t.startswith("check price of ") for t in found)
    assert not [t for t in found if "skip" in t.lower()]
