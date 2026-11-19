"""Tests of the project row: the label Comparing and the grey column of the project list."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from measure_twice import store as store_module
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.tables import NOTE_ROLE, NoteDelegate, project_note

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"  # 3 ways
WASH = "Постирать"
PLUS_2 = timezone(timedelta(hours=2))
PLUS_3 = timezone(timedelta(hours=3))
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=PLUS_2)


# ---------- the text of the grey column ----------

def test_note_this_year_shows_time():
    assert project_note(6, "2026-11-18T12:32:00+00:00", NOW) == "6 ways · 18 Nov 14:32"


def test_note_past_year_shows_year():
    assert project_note(6, "2025-11-18T12:32:00+00:00", NOW) == "6 ways · 18 Nov 2025"


def test_note_one_way():
    assert project_note(1, "2026-03-05T08:05:00+00:00", NOW) == "1 way · 5 Mar 10:05"


def test_note_utc_turns_local_across_midnight():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=PLUS_3)
    assert project_note(2, "2026-11-18T23:30:00+00:00", now) == "2 ways · 19 Nov 02:30"


def test_note_local_year_decides():
    now = datetime(2026, 1, 2, 12, 0, tzinfo=PLUS_3)
    assert project_note(2, "2025-12-31T22:30:00+00:00", now) == "2 ways · 1 Jan 01:30"


def test_note_has_no_groups():
    assert "group" not in project_note(6, "2026-11-18T12:32:00+00:00", NOW)


# ---------- the window ----------

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def moscow(monkeypatch):
    """Local time UTC+3 without summer time."""
    monkeypatch.setenv("TZ", "Europe/Moscow")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def clock(monkeypatch):
    """The store writes the time set in ``clock[0]``."""
    now = ["2025-03-05T22:30:00+00:00"]
    monkeypatch.setattr(store_module, "_now", lambda: now[0])
    return now


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, moscow, clock, store):
    w = MainWindow(store)
    assert w.load_path(LAUNDRY)
    yield w
    w.close()


def _notes(w):
    return [w.projects.itemData(i, NOTE_ROLE) for i in range(w.projects.count())]


def test_label_is_comparing(win):
    texts = [w.text() for w in win.findChildren(QLabel)]
    assert "<b>Comparing:</b>" in texts
    assert "<b>Project:</b>" not in texts


def test_list_row_note_has_ways_and_local_date(win):
    assert _notes(win) == ["3 ways · 6 Mar 2025"]


def test_list_keeps_bare_name(win):
    assert win.project_names() == ["Стирка белья"]


def test_list_draws_note_column(win):
    assert isinstance(win.projects.view().itemDelegate(), NoteDelegate)


def test_every_row_has_its_note(win, clock):
    clock[0] = "2025-04-07T08:00:00+00:00"
    assert win.load_path(LAUNDRY)
    assert sorted(_notes(win)) == ["3 ways · 6 Mar 2025", "3 ways · 7 Apr 2025"]


def test_note_follows_edit(win, clock):
    clock[0] = "2025-04-07T08:00:00+00:00"
    assert win.edit_number("kind_costs", WASH, "2.5")
    assert _notes(win) == ["3 ways · 7 Apr 2025"]
