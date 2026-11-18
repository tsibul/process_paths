"""Tests of the Step chains tab of the procnorm window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from procnorm.calc import compare, groups
from procnorm.project import load_file, read_project
from procnorm.store import Store
from procnorm.ui import style
from procnorm.ui.app import MainWindow

EXAMPLE = Path(__file__).parent / "data" / "laundry.json"
TASK = "Постирать бельё"
STEPS_A = [("Разобрать бельё", 2), ("Постирать", 2), ("Позвонить маме", 0), ("Развесить и убрать", 3)]
STEPS_V = [("Запустить машину", 3), ("Сушить и убрать", 3)]


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


def _chains_file(tmp_path: Path) -> Path:
    """laundry.json with invented steps: a task group А, Б, В; Г without a pair; Д out of comparison.

    Б has no ``steps``; А has a step with ``calls: 0``."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    calls = {v["code"]: v["calls"] for v in data["variants"]}
    steps = {"А": STEPS_A, "В": STEPS_V, "Г": [("Всё сразу", 5)], "Д": [("Всё", 7)]}
    spec = [("А", "А", "own", TASK, None), ("Б", "Б", "other", TASK, None), ("В", "В", "other", TASK, None),
            ("Г", "Б", "own", "Одна задача", None), ("Д", "А", "other", TASK, "чужая машина")]
    variants = []
    for code, src, side, task, out in spec:
        v = {"code": code, "title": f"Вариант {code}", "side": side, "task": task, "calls": calls[src]}
        if out:
            v["out_of_comparison"] = out
        if code in steps:
            v["steps"] = [{"text": t, "calls": n} for t, n in steps[code]]
        variants.append(v)
    data["variants"] = variants
    p = tmp_path / "chains.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def chains(win, tmp_path):
    p = _chains_file(tmp_path)
    assert win.load_path(p)
    win.chains_path = p
    return win


def test_tab_is_fourth(chains):
    assert chains.tabs.count() == 4
    assert chains.tabs.tabText(3) == "Step chains"
    assert chains.tabs.widget(3) is chains.chains
    assert chains.tabs.currentWidget() is chains.comparison


def test_groups_and_order_equal_groups(chains):
    project, _ = load_file(chains.chains_path)
    expected = []
    for g in groups(compare(project)):
        title = {"task": f"Task: {g.task}", "no-pair": "No comparable variant", "out": "Out of comparison"}[g.kind]
        expected.append((title, [r.code for r in g.rows]))
    page = chains.chains
    assert [(t, codes) for t, _, codes in page.groups()] == expected
    assert [grey for _, grey, _ in page.groups()] == [False, True, True]
    assert page.codes() == ["А", "Б", "В", "Г", "Д"]


def test_path_lines(chains):
    page = chains.chains
    a, b = page.path("А"), page.path("Б")
    assert a.title_text() == "А Вариант А"
    assert a.meta_text() == "● Ours · 7 transitions"
    assert b.meta_text() == "○ Theirs · 5 transitions"
    assert a.warn_text() == "1 step without transitions"
    assert [page.path(c).warn_text() for c in "БВГД"] == [None] * 4


def test_own_stripe_and_out_grey(chains):
    page = chains.chains
    assert [page.path(c).own for c in "АБВГД"] == [True, False, False, True, False]
    assert [page.path(c).grey for c in "АБВГД"] == [False, False, False, False, True]


def test_first_path_selected(chains):
    page = chains.chains
    assert page.current_code() == "А"
    assert [page.path(c).selected for c in page.codes()] == [True, False, False, False, False]
    page.select_path("В")
    assert page.current_code() == "В"
    assert [page.path(c).selected for c in page.codes()] == [False, False, True, False, False]


def test_click_selects(chains):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    page = chains.chains
    QTest.mouseClick(page.path("Г"), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
    assert page.current_code() == "Г"


def test_chain_head(chains):
    page = chains.chains
    assert page.head_title() == "А Вариант А"
    assert page.head_meta() == f"● Ours · Task: {TASK} · 4 steps · 7 transitions"
    page.select_path("Г")
    assert page.head_meta() == "● Ours · Task: Одна задача · 1 step · 5 transitions"


def test_chain_head_without_task(win, tmp_path):
    # a file without a task is refused now; a project from the database may still lack one
    text = _chains_file(tmp_path).read_text(encoding="utf-8")
    data = json.loads(text, parse_float=Decimal)
    del data["variants"][3]["task"]
    project, remarks = read_project(data, strict=False)
    assert remarks == []
    win.refresh(win.store.add(project))
    page = win.chains
    page.select_path("Г")
    assert page.head_meta() == "● Ours · 1 step · 5 transitions"


def test_step_rows_and_transitions_under_them(chains):
    rows = chains.chains.rows()
    project, _ = load_file(chains.chains_path)
    calls = project.model.variants[0].calls
    call = [("call", str(i), c.kind, c.executor, c.instrument, c.scope) for i, c in enumerate(calls, 1)]
    assert rows == [
        ("step", "1", "Разобрать бельё"), call[0], call[1],
        ("step", "2", "Постирать"), call[2], call[3], ("slice", "slice “постирано” reached"),
        ("step", "3", "Позвонить маме"), ("none", "No transitions"),
        ("step", "4", "Развесить и убрать"), call[4], call[5], call[6],
    ]


def test_step_row_bold_and_no_transitions_grey(chains):
    t = chains.chains.table
    kinds = chains.chains.row_kinds()
    step = kinds.index("step")
    none = kinds.index("none")
    assert t.item(step, 1).font().bold()
    item = t.item(none, 2)
    assert item.foreground().color() == QColor(style.TEXT2)
    assert t.columnSpan(step, 1) == 5
    assert t.columnSpan(none, 2) == 4


def test_slice_marker_after_its_transition(chains):
    page = chains.chains
    page.select_path("В")
    kinds = [r[0] for r in page.rows()]
    rows = page.rows()
    i = kinds.index("slice")
    assert rows[i - 1][:2] == ("call", "3")
    assert rows[i + 1] == ("step", "2", "Сушить и убрать")
    assert kinds.count("slice") == 1


def test_path_without_steps(chains):
    page = chains.chains
    page.select_path("Б")
    rows = page.rows()
    assert [r[0] for r in rows] == ["call", "call", "slice", "call", "call", "call"]
    assert [r[1] for r in rows if r[0] == "call"] == ["1", "2", "3", "4", "5"]
    assert page.head_meta() == f"○ Theirs · Task: {TASK} · Steps not given · 5 transitions"


def test_reserved_column_empty(chains):
    t = chains.chains.table
    last = t.columnCount() - 1
    assert t.horizontalHeaderItem(last).text() == ""
    assert all(not t.item(r, last) or not t.item(r, last).text() for r in range(t.rowCount()))


def test_no_project_empties_tab(chains, store):
    chains.confirm = lambda text: True
    chains.delete_project()
    page = chains.chains
    assert page.codes() == [] and page.current_code() is None and page.rows() == []
    assert page.head_title() == "" and page.head_meta() == ""
