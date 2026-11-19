# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the export."""

import copy
import csv
import io
import json
from decimal import Decimal
from pathlib import Path

import pytest

from measure_twice import export
from measure_twice.calc import compare, groups, money
from measure_twice.project import load_file, read_project

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"


@pytest.fixture
def project():
    p, remarks = load_file(LAUNDRY)
    assert p is not None, remarks
    return p


def grouped_project():
    """Invented data: laundry copies with tasks, a lone task and an out-of-comparison variant."""
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    for v in d["variants"]:
        v.pop("task", None)     # a project from the database may lack tasks: read leniently

    def clone(src, code, side, task=None, out=None):
        v = copy.deepcopy(next(x for x in d["variants"] if x["code"] == src))
        v["code"], v["title"], v["side"] = code, "T" + code, side
        for key, val in (("task", task), ("out_of_comparison", out)):
            if val is not None:
                v[key] = val
            else:
                v.pop(key, None)
        d["variants"].append(v)

    clone("А", "а2", "own", "Мыть")
    clone("Б", "б2", "other", "Мыть")
    clone("В", "в2", "other", "Мыть")
    clone("А", "а3", "own", "Сушить")
    clone("В", "в3", "other", "Сушить")
    clone("Б", "б4", "own", "Одна")
    clone("А", "а4", "other", "Вне", out="не | сравнивать")
    p, remarks = read_project(d, strict=False)
    assert p is not None and remarks == []
    return p


def test_csv_rows(project):
    rows = list(csv.reader(io.StringIO(export.csv_text(project))))
    assert len(rows) == 4
    head = rows[0]
    assert head[:5] == ["Group", "Code", "Title", "Side", "Steps"]
    assert "Labour · Человек" in head and "Labour · total" in head
    assert head[-3:] == ["Risk left, постирано", "Risk left, end", "Reason"]
    by = {r[1]: dict(zip(head, r)) for r in rows[1:]}
    assert by["А"]["Labour · total"] == "8.40"
    assert by["А"]["Risk left, end"] == "0.00"
    assert by["Б"]["Risk left, end"] == "8.00"
    assert by["В"]["Risk left, end"] == "3.00"
    assert by["А"]["Side"] == "Ours" and by["Б"]["Side"] == "Theirs" and by["А"]["Steps"] == "7"
    assert all(r[0] == "Task: Постирать бельё" and r[-1] == "" for r in rows[1:])


def test_csv_groups_and_reason():
    p = grouped_project()
    rows = list(csv.reader(io.StringIO(export.csv_text(p))))
    head, body = rows[0], rows[1:]
    assert [r[1] for r in body] == [r.code for g in groups(compare(p)) for r in g.rows]
    assert [r[0] for r in body] == (["Task: Мыть"] * 3 + ["Task: Сушить"] * 2
                                    + ["No comparable variant"] * 4 + ["Out of comparison"])
    assert body[-1][-1] == "не | сравнивать"
    assert all(r[-1] == "" for r in body[:-1])
    row = compare(p).excluded_rows[0]
    got = dict(zip(head, body[-1]))
    assert got["Labour · total"] == money(row.total) and got["Side"] == "Theirs"


def test_markdown(project):
    md = export.markdown(project)
    assert md.startswith("# Стирка белья\n\nТри способа")
    assert "| А | Аккуратная стирка | Ours | 7 |" in md
    assert "| 8.40 |" in md
    assert "| Б | Быстрая стирка | Theirs | 5 |" in md
    assert "| Code | Title | Side | Steps | Labour · Человек | Labour · total | Waiting | Risk left, постирано | Risk left, end |" in md
    assert "## Task: Постирать бельё" in md and "\n3 variants\n" in md
    assert "## No comparable variant" not in md
    assert "## Uncounted errors" in md and "### Вне модели" in md and "- порошок закончился" in md
    assert "## Out of comparison" not in md
    assert "## Details" in md
    assert "### А: Аккуратная стирка" in md
    assert "| # | Kind | Executor | Instrument | Scope | Cost | Scope coef. | Executor coef. | Labour | Change |" in md
    assert "Бельё/карманы: не проверены → проверены" in md


def test_markdown_groups():
    p = grouped_project()
    md = export.markdown(p)
    heads = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert heads == ["## Task: Мыть", "## Task: Сушить", "## No comparable variant",
                     "## Out of comparison", "## Uncounted errors", "## Details"]
    assert "\n3 variants\n" in md and "\n2 variants\n" in md
    assert "Not compared: no other variant has the same task" in md
    out = md[md.index("## Out of comparison"):md.index("## Details")]
    assert "| Reason |" in out and "не \\| сравнивать" in out
    assert "Reason" not in md[:md.index("## Out of comparison")]
    first = md[md.index("## Task: Мыть"):md.index("## Task: Сушить")]
    codes = [ln.split("|")[1].strip() for ln in first.splitlines() if ln.startswith("| ") and "Code" not in ln and "---" not in ln]
    assert codes == [r.code for r in groups(compare(p))[0].rows]
    assert "| а2 | Tа2 | Ours |" in first and "| б2 | Tб2 | Theirs |" in first
    assert "### а4: Tа4" in md


def test_markdown_escapes_pipe(project):
    project.name = "a|b"
    object.__setattr__(project.model.variants[0], "title", "x|y")
    md = export.markdown(project)
    assert "x\\|y" in md


def test_write_by_suffix(project, tmp_path):
    export.write(project, tmp_path / "a.md")
    export.write(project, tmp_path / "a.csv")
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == export.markdown(project)
    assert (tmp_path / "a.csv").read_text(encoding="utf-8") == export.csv_text(project)


def test_write_bad_suffix(project, tmp_path):
    with pytest.raises(ValueError):
        export.write(project, tmp_path / "a.txt")
