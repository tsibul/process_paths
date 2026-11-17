# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the command line."""

import csv
import io
from pathlib import Path

from procnorm.cli import main

LAUNDRY = str(Path(__file__).parent / "data" / "laundry.json")


def test_check_ok(capsys):
    assert main(["check", LAUNDRY]) == 0
    assert capsys.readouterr().out == "OK: Стирка белья\n"


def test_check_broken(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{\"format\": 1}", encoding="utf-8")
    assert main(["check", str(f)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert len(out) > 1 and any("missing" in line for line in out)


def test_check_not_json_and_missing(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{", encoding="utf-8")
    assert main(["check", str(f)]) == 1
    assert "not valid JSON" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "none.json")]) == 1
    assert "cannot read" in capsys.readouterr().out


def test_table_markdown(capsys):
    assert main(["table", LAUNDRY]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Стирка белья")
    assert "## Details" in out


def test_table_csv(capsys):
    assert main(["table", LAUNDRY, "--csv"]) == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert len(rows) == 4 and rows[0][:2] == ["Group", "Code"]


def test_table_broken(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{\"format\": 1}", encoding="utf-8")
    assert main(["table", str(f)]) == 1
    cap = capsys.readouterr()
    assert cap.out == "" and "missing" in cap.err
