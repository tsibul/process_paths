# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the export."""

import csv
import io
from pathlib import Path

import pytest

from procnorm import export
from procnorm.project import load_file

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"


@pytest.fixture
def project():
    p, remarks = load_file(LAUNDRY)
    assert p is not None, remarks
    return p


def test_csv_rows(project):
    rows = list(csv.reader(io.StringIO(export.csv_text(project))))
    assert len(rows) == 4
    head = rows[0]
    assert head[:4] == ["Code", "Title", "Side", "Steps"]
    assert "Labour: Человек" in head and "Labour total" in head
    assert head[-2:] == ["Skips at постирано", "Skips at final"]
    by = {r[0]: dict(zip(head, r)) for r in rows[1:]}
    assert by["А"]["Labour total"] == "8.40"
    assert by["А"]["Skips at final"] == "0.00"
    assert by["Б"]["Skips at final"] == "8.00"
    assert by["В"]["Skips at final"] == "3.00"
    assert by["А"]["Side"] == "own" and by["А"]["Steps"] == "7"


def test_markdown(project):
    md = export.markdown(project)
    assert md.startswith("# Стирка белья\n\nТри способа")
    assert "| А | Аккуратная стирка | own | 7 |" in md
    assert "| 8.40 |" in md
    assert "| Б | Быстрая стирка | other | 5 |" in md
    assert "## Uncounted errors" in md and "### Вне модели" in md and "- порошок закончился" in md
    assert "## Out of comparison" not in md
    assert "## Details" in md
    assert "### А: Аккуратная стирка" in md
    assert "| # | Kind | Executor | Instrument | Scope | Cost | Scope coef. | Executor coef. | Labour | Change |" in md
    assert "Бельё/карманы: не проверены → проверены" in md


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
