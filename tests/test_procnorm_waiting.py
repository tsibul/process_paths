# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of waiting kinds: reading, calculation, display, export, editing and storage."""

import copy
import csv
import io
import json
from decimal import Decimal
from pathlib import Path

import pytest

from measure_twice import edit, export
from measure_twice.calc import compare, series, waiting_text
from measure_twice.cli import main as cli
from measure_twice.project import read_project
from measure_twice.store import Store

LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
D = Decimal
BAD_WAITING = "kind Settle: waiting needs a number above 0 and the unit hours or days"

# Made-up project: a wall is primed, the primer settles, the wall is painted, the paint cures and
# the wall is inspected. Settle and Cure are waiting; Junior and House have coefficients that
# must not touch the waiting.
PAINT = json.loads("""
{
  "format": 1,
  "name": "Painting",
  "existence_axis": {"name": "presence", "absent": "none"},
  "entities": [
    {"name": "Wall", "axes": [
      {"name": "coat", "values": ["bare", "primed", "painted"]},
      {"name": "settled", "values": ["no", "yes"]},
      {"name": "cured", "values": ["no", "yes"]},
      {"name": "inspected", "values": ["no", "yes"]}
    ]}
  ],
  "kinds": [
    {"name": "Prime", "entity": "Wall", "axis": "coat", "from": "bare", "to": "primed"},
    {"name": "Settle", "entity": "Wall", "axis": "settled", "from": "no", "to": "yes",
     "waiting": 3, "waiting_unit": "hours"},
    {"name": "Paint", "entity": "Wall", "axis": "coat", "from": "primed", "to": "painted"},
    {"name": "Cure", "entity": "Wall", "axis": "cured", "from": "no", "to": "yes",
     "waiting": 1, "waiting_unit": "days"},
    {"name": "Inspect", "entity": "Wall", "axis": "inspected", "from": "no", "to": "yes",
     "check": true}
  ],
  "executors": ["Painter", "Junior"],
  "instruments": ["Roller"],
  "scopes": ["Room", "House"],
  "batch_scope": "House",
  "variants": [
    {"code": "P1", "title": "Settled", "side": "own", "task": "Wall",
     "calls": [["Prime", "Painter", "Roller", "Room"], ["Settle", "Junior", "Roller", "House"],
               ["Paint", "Painter", "Roller", "Room"], ["Cure", "Junior", "Roller", "House"],
               ["Inspect", "Painter", "Roller", "Room"]]},
    {"code": "P2", "title": "Straight", "side": "other", "task": "Wall",
     "calls": [["Prime", "Painter", "Roller", "Room"], ["Paint", "Painter", "Roller", "Room"],
               ["Cure", "Junior", "Roller", "House"], ["Inspect", "Painter", "Roller", "Room"]]},
    {"code": "P3", "title": "Primer only", "side": "own", "task": "Bare",
     "calls": [["Prime", "Painter", "Roller", "Room"]]}
  ],
  "normalization": {
    "kind_costs": {"Prime": 2, "Paint": 4, "Inspect": 1},
    "executor_coefficients": {"Painter": 1, "Junior": 2},
    "scope_coefficients": {"Room": 1, "House": 3},
    "axis_skip_prices": {"Wall": {"inspected": 5}}
  }
}
""", parse_float=Decimal)


def data() -> dict:
    return copy.deepcopy(PAINT)


def kind(d: dict, name: str) -> dict:
    return next(k for k in d["kinds"] if k["name"] == name)


def project_of(d, strict=True):
    p, remarks = read_project(d, strict=strict)
    assert remarks == []
    return p


def remarks_of(d, strict=True) -> list[str]:
    p, remarks = read_project(d, strict=strict)
    assert p is None
    return [str(r) for r in remarks]


def rows(p):
    return {r.code: r for r in compare(p).rows}


def with_weight(x) -> dict:
    d = data()
    d["normalization"]["labour_per_waiting_hour"] = x
    return d


# ---------- reading ----------

def test_old_file_reads_as_before():
    d = json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)
    p = project_of(d)
    assert p.waiting == {}
    assert p.norm.labour_per_waiting_hour == 0
    assert compare(p).waiting_weight == 0
    assert all(r.waiting == 0 for r in compare(p).rows)


def test_good_waiting_is_read():
    p = project_of(data())
    assert p.waiting == {"Settle": (D(3), "hours"), "Cure": (D(1), "days")}


def test_waiting_kind_needs_no_cost_in_strict_read():
    d = data()
    assert "Settle" not in d["normalization"]["kind_costs"]
    project_of(d, strict=True)


def test_waiting_kind_may_cost_zero():
    d = data()
    d["normalization"]["kind_costs"]["Settle"] = 0
    project_of(d)


@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("fields", [
    {"waiting": 0, "waiting_unit": "hours"},
    {"waiting": -2, "waiting_unit": "hours"},
    {"waiting": "3", "waiting_unit": "hours"},
    {"waiting": True, "waiting_unit": "hours"},
    {"waiting": 3, "waiting_unit": "weeks"},
    {"waiting": 3},
    {"waiting_unit": "days"},
])
def test_bad_waiting_remark(fields, strict):
    d = data()
    k = kind(d, "Settle")
    del k["waiting"]
    del k["waiting_unit"]
    k.update(fields)
    assert remarks_of(d, strict) == [BAD_WAITING]


@pytest.mark.parametrize("strict", [True, False])
def test_waiting_kind_marked_check(strict):
    d = data()
    kind(d, "Settle")["check"] = True
    d["normalization"]["axis_skip_prices"]["Wall"]["settled"] = 1
    assert "kind Settle: a waiting kind cannot be a check" in remarks_of(d, strict)


@pytest.mark.parametrize("strict", [True, False])
def test_waiting_kind_with_cost(strict):
    d = data()
    d["normalization"]["kind_costs"]["Settle"] = 5
    assert remarks_of(d, strict) == [
        "normalization, kind_costs: kind Settle is a waiting kind, its cost must be 0 or absent"]


def test_setting_is_read():
    p = project_of(with_weight(D("1.5")))
    assert p.norm.labour_per_waiting_hour == D("1.5")


@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("value, remark", [
    ("2", "normalization, labour_per_waiting_hour: number expected"),
    (-1, "normalization, labour_per_waiting_hour: must not be below zero"),
])
def test_bad_setting(value, remark, strict):
    assert remarks_of(with_weight(value), strict) == [remark]


# ---------- calculation ----------

def test_waiting_hours_summed_days_and_hours():
    r = rows(project_of(data()))
    assert r["P1"].waiting == 27
    assert r["P2"].waiting == 24
    assert r["P3"].waiting == 0


def test_waiting_has_no_labour_and_no_coefficients():
    r = rows(project_of(data()))
    assert r["P1"].total == 7
    assert r["P1"].labour["Junior"] == 0


def test_executor_only_for_waiting_needs_no_coefficient():
    d = data()
    del d["normalization"]["executor_coefficients"]["Junior"]
    del d["normalization"]["scope_coefficients"]["House"]
    p = project_of(d, strict=False)
    assert rows(p)["P1"].waiting == 27
    assert compare(p).excluded == []


def test_setting_zero_leaves_labour_alone():
    c = compare(project_of(data()))
    assert c.waiting_weight == 0
    r = {x.code: x for x in c.rows}
    assert r["P1"].labour_waiting == 7


def test_setting_above_zero_adds_waiting():
    c = compare(project_of(with_weight(2)))
    assert c.waiting_weight == 2
    r = {x.code: x for x in c.rows}
    assert r["P1"].labour_waiting == 7 + 27 * 2
    assert r["P2"].labour_waiting == 7 + 24 * 2
    assert r["P3"].labour_waiting == 2


def test_series_waiting_by_step():
    p = project_of(with_weight(2))
    pts = series(p, "P1")
    assert [x.waiting for x in pts] == [0, 3, 3, 27, 27]
    assert [x.labour_waiting for x in pts] == [2, 8, 12, 60, 61]


# ---------- display ----------

@pytest.mark.parametrize("hours, text", [
    (D(24), "1 d"),
    (D(36), "36 h"),
    (D(48), "2 d"),
    (D(3), "3 h"),
    (D(0), "—"),
])
def test_waiting_text(hours, text):
    assert waiting_text(hours) == text


# ---------- table and export ----------

def _grid(d) -> list[list[str]]:
    return list(csv.reader(io.StringIO(export.csv_text(project_of(d)))))


def test_waiting_column_after_labour_total():
    head, *body = _grid(data())
    i = head.index("Labour · total")
    assert head[i + 1] == "Waiting"
    assert "Labour + waiting" not in head
    cells = {r[1]: r[i + 1] for r in body}
    assert cells == {"P1": "27 h", "P2": "1 d", "P3": "—"}


def test_labour_waiting_column_with_setting():
    head, *body = _grid(with_weight(2))
    i = head.index("Waiting")
    assert head[i + 1] == "Labour + waiting"
    cells = {r[1]: r[i + 1] for r in body}
    assert cells == {"P1": "61.00", "P2": "55.00", "P3": "2.00"}


def test_cli_table_has_waiting(tmp_path, capsys):
    f = tmp_path / "paint.json"
    f.write_text(json.dumps(with_weight(2), default=str), encoding="utf-8")
    assert cli(["table", str(f), "--csv"]) == 0
    head = capsys.readouterr().out.splitlines()[0].split(",")
    assert head[head.index("Waiting") + 1] == "Labour + waiting"


def test_markdown_has_waiting():
    text = export.markdown(project_of(data()))
    assert "| Labour · total | Waiting |" in text
    assert "Labour + waiting" not in text


# ---------- editing ----------

def _structure(**extra) -> dict:
    s = {"entity": "Wall", "axis": "settled", "from": "yes", "to": "no"}
    s.update(extra)
    return s


def test_add_waiting_kind():
    new, remarks = edit.add_kind(data(), "Unsettle", _structure(waiting="2", waiting_unit="days"))
    assert remarks == []
    assert kind(new, "Unsettle")["waiting"] == 2
    assert kind(new, "Unsettle")["waiting_unit"] == "days"
    assert project_of(new, strict=False).waiting["Unsettle"] == (D(2), "days")


def test_add_kind_empty_waiting_is_no_waiting():
    new, remarks = edit.add_kind(data(), "Unsettle", _structure(waiting="", waiting_unit="hours"))
    assert remarks == []
    assert "waiting" not in kind(new, "Unsettle")
    assert "waiting_unit" not in kind(new, "Unsettle")


def test_add_kind_bad_waiting_refused():
    new, remarks = edit.add_kind(data(), "Settle2", _structure(waiting="abc", waiting_unit="hours"))
    assert new is None
    assert [str(r) for r in remarks] == [
        "kind Settle2: waiting needs a number above 0 and the unit hours or days"]


def test_set_kind_to_waiting_drops_cost():
    s = {"entity": "Wall", "axis": "coat", "from": "primed", "to": "painted",
         "waiting": "1.5", "waiting_unit": "hours"}
    new, remarks = edit.set_kind(data(), "Paint", s)
    assert remarks == []
    assert kind(new, "Paint")["waiting"] == D("1.5")
    assert "Paint" not in new["normalization"]["kind_costs"]


def test_cost_of_waiting_kind_refused():
    new, remarks = edit.set_number(data(), "kind_costs", "Settle", "4")
    assert new is None
    assert remarks


def test_set_waiting_weight():
    new, remarks = edit.set_number(data(), edit.WAITING_WEIGHT, None, "2,5")
    assert remarks == []
    assert new["normalization"]["labour_per_waiting_hour"] == D("2.5")
    cleared, remarks = edit.set_number(new, edit.WAITING_WEIGHT, None, "")
    assert remarks == []
    assert "labour_per_waiting_hour" not in cleared["normalization"]


def test_set_waiting_weight_below_zero_refused():
    new, remarks = edit.set_number(data(), edit.WAITING_WEIGHT, None, "-1")
    assert new is None
    assert remarks


# ---------- storage ----------

def test_store_round_trip(tmp_path):
    d = with_weight(D("0.5"))
    with Store(tmp_path / "t.db") as s:
        pid = s.add(project_of(d))
        p = s.get(pid)
        assert p.data == d
        assert p.waiting == {"Settle": (D(3), "hours"), "Cure": (D(1), "days")}
        assert p.norm.labour_per_waiting_hour == D("0.5")
        new, remarks = edit.set_number(p.data, edit.WAITING_WEIGHT, None, "1")
        s.save(pid, new)
        assert s.get(pid).norm.labour_per_waiting_hour == 1
