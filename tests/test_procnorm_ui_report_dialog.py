"""Tests of the report window opened by `Report (PDF)…` on the Comparison tab (piece 23)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QPushButton

from measure_twice import report
from measure_twice.store import Store
from measure_twice.ui import app as app_module
from measure_twice.ui.app import MainWindow
from measure_twice.ui.report_dialog import ReportDialog

EXAMPLE = Path(__file__).parent / "data" / "laundry.json"
KEPT = "Аккуратная стирка"
DROPPED = "Быстрая стирка"


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
    assert w.load_path(EXAMPLE)
    w.show()
    QApplication.processEvents()
    yield w
    w.close()


@pytest.fixture
def opened(monkeypatch):
    """Replace the modal exec by a stub that records the window and runs a given action."""
    log = {"dialogs": [], "act": None}

    def exec_(dialog):
        log["dialogs"].append(dialog)
        if log["act"] is not None:
            log["act"](dialog)
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", exec_)
    return log


@pytest.fixture
def saved(monkeypatch, tmp_path):
    """The file dialog answers a path in tmp; each question is recorded."""
    log = {"asked": 0, "path": tmp_path / "r.pdf"}

    def ask(*args, **kwargs):
        log["asked"] += 1
        return (str(log["path"]) if log["path"] is not None else "", "")

    monkeypatch.setattr(app_module.QFileDialog, "getSaveFileName", ask)
    return log


@pytest.fixture
def written(monkeypatch):
    """Record the calls of report.write instead of writing."""
    calls = []

    def write(project, path, chosen=report.PAGES, ways=None):
        calls.append({"project": project, "path": Path(path),
                      "chosen": list(chosen), "ways": None if ways is None else list(ways)})

    monkeypatch.setattr(report, "write", write)
    return calls


def _button(dialog, text) -> QPushButton:
    return next(b for b in dialog.findChildren(QPushButton) if b.text() == text)


def _page_box(dialog, kind) -> QCheckBox:
    return next(b for b in dialog.findChildren(QCheckBox) if b.text() == report.HEADINGS[kind])


def _way_items(dialog):
    return [dialog.ways.item(i) for i in range(dialog.ways.count())]


def _uncheck_way(dialog, title):
    item = next(i for i in _way_items(dialog) if title in i.text())
    item.setCheckState(Qt.CheckState.Unchecked)


def _open(win, opened, act):
    opened["act"] = act
    win.comparison.report_button.click()
    return opened["dialogs"][-1]


def test_button_next_to_exports(win):
    b = win.comparison.report_button
    assert b.text() == "Report (PDF)…"
    assert b.parent() is win.comparison.export_bar
    assert b.isEnabled()


def test_window_has_pages_ways_and_two_buttons(win, opened):
    dialog = _open(win, opened, None)
    assert isinstance(dialog, ReportDialog)
    boxes = [b.text() for b in dialog.findChildren(QCheckBox)]
    assert boxes == [report.HEADINGS[k] for k in report.PAGES]
    assert all(b.isChecked() for b in dialog.findChildren(QCheckBox))
    items = _way_items(dialog)
    assert len(items) == 3
    assert all(i.checkState() == Qt.CheckState.Checked for i in items)
    assert sorted(b.text() for b in dialog.findChildren(QPushButton)) == ["Cancel", "Save PDF…"]


def test_checks_reach_report_write(win, opened, saved, written):
    def act(dialog):
        _page_box(dialog, report.STEPS).setChecked(False)
        _uncheck_way(dialog, DROPPED)
        _button(dialog, "Save PDF…").click()

    _open(win, opened, act)
    assert len(written) == 1
    call = written[0]
    assert call["chosen"] == [report.ANSWER, report.ASSUMPTIONS]
    assert call["ways"] == ["А", "В"]
    assert call["path"] == saved["path"]
    assert call["project"] is win.comparison._project


def test_unchecked_way_is_on_no_page(win, opened, saved, written):
    def act(dialog):
        _uncheck_way(dialog, DROPPED)
        _button(dialog, "Save PDF…").click()

    _open(win, opened, act)
    call = written[0]
    laid = report.pages(call["project"], call["chosen"], call["ways"])
    assert {p.kind for p in laid} == set(report.PAGES)
    for kind in report.PAGES:
        texts = " ".join(t.text for p in laid if p.kind == kind for t in p.texts)
        assert DROPPED not in texts, kind
    texts = " ".join(t.text for p in laid for t in p.texts)
    assert KEPT in texts


def test_no_page_checked_button_grey_no_file(win, opened, saved):
    def act(dialog):
        for k in report.PAGES:
            _page_box(dialog, k).setChecked(False)
        save = _button(dialog, "Save PDF…")
        assert not save.isEnabled()
        save.click()

    _open(win, opened, act)
    assert saved["asked"] == 0
    assert not saved["path"].exists()


def test_no_way_checked_button_grey(win, opened, saved):
    def act(dialog):
        for i in _way_items(dialog):
            i.setCheckState(Qt.CheckState.Unchecked)
        assert not _button(dialog, "Save PDF…").isEnabled()
        _page_box(dialog, report.ANSWER).setChecked(False)
        _page_box(dialog, report.ANSWER).setChecked(True)
        assert not _button(dialog, "Save PDF…").isEnabled()
        _way_items(dialog)[0].setCheckState(Qt.CheckState.Checked)
        assert _button(dialog, "Save PDF…").isEnabled()

    _open(win, opened, act)
    assert saved["asked"] == 0


def test_cancel_writes_nothing(win, opened, saved, written):
    def act(dialog):
        _button(dialog, "Cancel").click()

    dialog = _open(win, opened, act)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert written == []
    assert saved["asked"] == 0


def test_file_dialog_cancel_keeps_window(win, opened, saved, written):
    saved["path"] = None

    def act(dialog):
        _button(dialog, "Save PDF…").click()

    dialog = _open(win, opened, act)
    assert saved["asked"] == 1
    assert written == []
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_real_pdf_written_with_suffix(win, opened, saved, tmp_path):
    saved["path"] = tmp_path / "report"

    def act(dialog):
        _button(dialog, "Save PDF…").click()

    dialog = _open(win, opened, act)
    out = tmp_path / "report.pdf"
    assert out.read_bytes()[:4] == b"%PDF"
    assert dialog.result() == QDialog.DialogCode.Accepted
