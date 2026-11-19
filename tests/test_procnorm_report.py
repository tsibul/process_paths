# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the PDF report without charts (piece 21): the list of pages, then the file."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from measure_twice import report
from measure_twice.calc import compare
from measure_twice.export import _header
from measure_twice.project import load_file, read_project

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
STAGES = 22
WAYS = 11
EXECUTORS = ["Старший специалист отдела", "Помощник руководителя группы"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def laundry():
    p, remarks = load_file(LAUNDRY)
    assert p is not None, remarks
    return p


def _big_data() -> dict:
    """Invented large example: 11 ways, up to 22 steps, 9 table columns, names up to 31 chars."""
    stages = [f"этап {i:02d}" for i in range(STAGES + 1)]
    kinds = [{"name": f"Согласовать бумаги с отделом {i:02d}", "entity": "Заявка",
              "axis": "стадия", "from": stages[i - 1], "to": stages[i]}
             for i in range(1, STAGES + 1)]
    check = {"name": "Сверить реквизиты с договором", "entity": "Заявка", "axis": "сверка",
             "from": "нет", "to": "да", "check": True}
    variants = []
    for n in range(WAYS):
        steps = STAGES if n % 3 == 0 else 12 + n
        calls = [] if n % 2 else [[check["name"], EXECUTORS[0], "почта", "одна заявка"]]
        calls += [[k["name"], EXECUTORS[i % 2], "почта", "одна заявка"]
                  for i, k in enumerate(kinds[:steps - len(calls)])]
        variants.append({"code": f"W{n + 1}",
                         "title": f"Путь номер {n + 1:02d} через все отделы",
                         "side": "own" if n < 6 else "other", "task": "Провести заявку",
                         "calls": calls})
    kinds.append(check)
    return {"format": 1, "name": "Большой выдуманный пример",
            "existence_axis": {"name": "наличие", "absent": "нет"},
            "entities": [{"name": "Заявка",
                          "axes": [{"name": "стадия", "values": stages},
                                   {"name": "сверка", "values": ["нет", "да"]}]}],
            "kinds": kinds, "executors": EXECUTORS, "instruments": ["почта"],
            "scopes": ["одна заявка"], "batch_scope": "одна заявка", "variants": variants,
            "normalization": {"kind_costs": {k["name"]: 3 for k in kinds},
                              "executor_coefficients": {EXECUTORS[0]: 2, EXECUTORS[1]: 1},
                              "scope_coefficients": {"одна заявка": 1},
                              "axis_skip_prices": {"Заявка": {"сверка": 7}}}}


@pytest.fixture
def big():
    data = _big_data()
    p, remarks = read_project(data)
    assert p is not None, remarks
    return p


def test_big_example_is_as_planned(big):
    assert len(big.model.variants) == WAYS
    assert max(len(v.calls) for v in big.model.variants) == STAGES
    assert len(_header(compare(big))) == 9
    names = [k.name for k in big.model.kinds] + [v.title for v in big.model.variants] + EXECUTORS
    assert max(len(n) for n in names) == 31


def _kinds(pages):
    return [p.kind for p in pages]


def _all_text(page) -> str:
    return " ".join(t.text for t in page.texts)


def test_laundry_pages(app, laundry):
    pages = report.pages(laundry)
    assert _kinds(pages) == ["answer", "answer", "steps", "steps", "assumptions"]  # charts: 2nd
    answer = _all_text(pages[0])
    for word in ("Code", "Risk left, end", "Аккуратная стирка", "Ours", "Theirs"):
        assert word in answer
    steps = [t.text for t in pages[2].texts]
    assert "1. Проверить карманы (2.00)" in steps
    assert "3. Запустить машину (5.40)" in steps
    assumptions = _all_text(pages[4])
    assert report.SAME_UNIT in assumptions
    assert "minutes" not in assumptions
    for word in ("Человек", "Машина", "каждая вещь", "вся загрузка", "карманы", "цвета"):
        assert word in assumptions


def test_big_steps_pages_half_of_ways(app, big):
    pages = report.pages(big)
    assert _kinds(pages).count("steps") == math.ceil(WAYS / 2)


def test_steps_pages_follow_chosen_ways(app, big):
    ways = ["W1", "W2", "W3"]
    pages = report.pages(big, ways=ways)
    assert _kinds(pages).count("steps") == 2
    for page in pages:
        text = _all_text(page)
        assert "W4" not in text and "W11" not in text


def test_chosen_pages_only(app, laundry):
    assert _kinds(report.pages(laundry, chosen=["assumptions"])) == ["assumptions"]
    assert _kinds(report.pages(laundry, chosen=["steps", "answer"])) == ["answer", "answer",
                                                                         "steps", "steps"]


def test_pages_are_landscape_a4():
    assert report.PAGE_WIDTH > report.PAGE_HEIGHT
    assert round(report.PAGE_WIDTH) == 842 and round(report.PAGE_HEIGHT) == 595


def test_wrap_splits_long_text(app):
    font = report.font(report.BODY)
    text = "Согласовать бумаги с отделом 07 и ещё раз согласовать"
    lines = report.wrap(text, font, 60)
    assert len(lines) > 1
    assert " ".join(lines).replace("  ", " ") == text
    for line in lines:
        assert report.text_width(line, font) <= 60


def test_long_names_wrap_in_answer(app, big):
    answer = report.pages(big)[0]
    texts = [t.text for t in answer.texts]
    names = [f"Labour · {x}" for x in EXECUTORS] + [v.title for v in big.model.variants]
    assert any(name not in texts for name in names)
    words = _all_text(answer).split()
    for name in names:
        assert all(word in words for word in name.split())


@pytest.mark.parametrize("which", ["laundry", "big"])
def test_no_line_past_margin(app, laundry, big, which):
    project = laundry if which == "laundry" else big
    for page in report.pages(project):
        for t in page.texts:
            assert t.x >= report.MARGIN - 0.01
            assert t.x + t.width <= report.PAGE_WIDTH - report.MARGIN + 0.01
            assert report.text_width(t.text, report.font(t.size, t.bold)) <= t.width + 0.01
            assert t.y >= report.MARGIN - 0.01
            assert t.y + t.height <= report.PAGE_HEIGHT - report.MARGIN + 0.01


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


@pytest.mark.parametrize("which", ["laundry", "big"])
def test_file(app, laundry, big, which, tmp_path):
    project = laundry if which == "laundry" else big
    path = tmp_path / "report.pdf"
    report.write(project, path)
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert _pdf_pages(data) == len(report.pages(project))



def test_step_heading_above_its_actions(app, laundry):
    page = report.pages(laundry, chosen=["steps"])[0]
    texts = {t.text: t for t in page.texts}
    head = texts["Загрузить бельё и включить машину"]
    assert head.grey
    first = next(t for t in page.texts if t.text.startswith("4. "))
    assert head.y < first.y
    assert not first.grey
    second = next(t for t in page.texts if t.text.startswith("5. "))
    assert head.y < first.y < second.y
    assert texts["Достать порошок"].grey  # a step with 0 calls: a grey line alone
    assert "1. Проверить карманы (2.00)" in texts


def test_no_headings_without_steps(app, big):
    for page in report.pages(big, chosen=["steps"]):
        assert not [t for t in page.texts if t.grey]
