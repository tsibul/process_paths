# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export of the comparison to Markdown and CSV."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from measure_twice.calc import (Comparison, Group, Row, Step, compare, details, fmt, groups, money,
                                waiting_text)
from measure_twice.project import FINAL, Project

DASH = "—"
ARROW = "→"
NOT_SET = "not set"
NOT_REACHED = " (not reached)"
WAITING = "Waiting"
LABOUR_WAITING = "Labour + waiting"


def number(d: Decimal | None, form=money) -> str:
    """A number as shown and exported: ``form(d)``, or ``not set`` for ``None``.

    :param d: the number, ``None`` when not set.
    :param form: :func:`money` or :func:`fmt`.
    :return: text.
    :rtype: str
    """
    return NOT_SET if d is None else form(d)


def waiting_headers(cmp: Comparison) -> list[str]:
    """The waiting columns after the labour total: ``Waiting``, and ``Labour + waiting`` when
    ``labour_per_waiting_hour`` is above 0.

    :param cmp: the table.
    :return: the column names.
    :rtype: list[str]
    """
    return [WAITING] + ([LABOUR_WAITING] if cmp.waiting_weight > 0 else [])


def numbers(cmp: Comparison, r: Row) -> list[str]:
    """Labour, total, waiting and skipped checks of a comparison row, as shown and exported.

    A variant with a run error has no numbers: every cell is ``—``.

    :param cmp: the table.
    :param r: one of its rows.
    :return: one text per labour column, the total, the waiting columns, then one per slice.
    :rtype: list[str]
    """
    extra = waiting_headers(cmp)
    if r.error is not None:
        return [DASH] * (len(cmp.executors) + 1 + len(extra) + len(cmp.slice_names))
    out = [number(r.labour[x]) for x in cmp.executors] + [number(r.total)]
    out.append(waiting_text(r.waiting))
    if LABOUR_WAITING in extra:
        out.append(number(r.labour_waiting))
    return out + [number(s.total) + ("" if s.reached else NOT_REACHED) for s in r.slices]


def step_numbers(s: Step, failed: bool) -> list[str]:
    """Cost, scope coefficient, executor coefficient and labour of one step.

    :param s: the step.
    :param failed: the variant has a run error: every number is ``—``.
    :return: four texts.
    :rtype: list[str]
    """
    xs = (s.cost, s.scope_coefficient, s.executor_coefficient, s.labour)
    return [DASH] * 4 if failed else [number(x, fmt) for x in xs]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |",
             "|" + "|".join(" --- " for _ in rows[0]) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return lines


SIDES = {"own": "Ours", "other": "Theirs"}
NO_PAIR = "No comparable variant"
NO_PAIR_NOTE = "Not compared: no other variant has the same task"
OUT = "Out of comparison"


def _header(cmp: Comparison) -> list[str]:
    return (["Code", "Title", "Side", "Steps"] + [f"Labour · {x}" for x in cmp.executors]
            + ["Labour · total"] + waiting_headers(cmp)
            + [f"Skipped checks, {'end' if n == FINAL else n}" for n in cmp.slice_names])


def _row(cmp: Comparison, r: Row) -> list[str]:
    return [r.code, r.title, SIDES.get(r.side, r.side), str(r.steps)] + numbers(cmp, r)


def _group_name(g: Group) -> str:
    if g.kind == "task":
        return f"Task: {g.task}"
    return NO_PAIR if g.kind == "no-pair" else OUT


def _grid(cmp: Comparison) -> list[list[str]]:
    out = [["Group"] + _header(cmp) + ["Reason"]]
    for g in groups(cmp):
        out += [[_group_name(g)] + _row(cmp, r) + [r.reason or ""] for r in g.rows]
    return out


def _change(c: tuple[str, str, str | None, str | None]) -> str:
    e, a, before, after = c
    return f"{e}/{a}: {before if before is not None else DASH} {ARROW} {after if after is not None else DASH}"


def markdown(project: Project) -> str:
    """Markdown export of the comparison.

    :param project: a checked project.
    :return: Markdown text.
    :rtype: str
    """
    cmp = compare(project)
    out = [f"# {project.name}", ""]
    if project.description:
        out += [project.description, ""]
    for g in groups(cmp):
        out += [f"## {_group_name(g)}", ""]
        if g.kind == "task":
            out += [f"{len(g.rows)} variants", ""]
        elif g.kind == "no-pair":
            out += [NO_PAIR_NOTE, ""]
        head = _header(cmp) + (["Reason"] if g.kind == "out" else [])
        body = [_row(cmp, r) + ([r.reason or ""] if g.kind == "out" else []) for r in g.rows]
        out += _table([head] + body) + [""]
    if cmp.uncounted_errors:
        out += ["## Uncounted errors", ""]
        for group, items in cmp.uncounted_errors.items():
            out += [f"### {group}", ""] + [f"- {t}" for t in items] + [""]
    out += ["## Details", ""]
    head = ["#", "Kind", "Executor", "Instrument", "Scope", "Cost", "Scope coef.", "Executor coef.",
            "Labour", "Change"]
    for r in cmp.rows + cmp.excluded_rows:
        out += [f"### {r.code}: {r.title}", ""]
        rows = [head]
        for s in details(project, r.code):
            rows.append([str(s.number), s.kind, s.executor, s.instrument, s.scope]
                        + step_numbers(s, r.error is not None) + ["; ".join(_change(c) for c in s.changes)])
        out += _table(rows) + [""]
    return "\n".join(out)


def csv_text(project: Project) -> str:
    """CSV export of the comparison table.

    :param project: a checked project.
    :return: CSV text with a header row.
    :rtype: str
    """
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(_grid(compare(project)))
    return buf.getvalue()


def write(project: Project, path: Path) -> None:
    """Write the export; the format follows the suffix.

    :param project: a checked project.
    :param path: file path ending in ``.md`` or ``.csv``.
    :raises ValueError: other suffix.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".md":
        text = markdown(project)
    elif suffix == ".csv":
        text = csv_text(project)
    else:
        raise ValueError(f"unknown export format: {path.suffix!r}, use .md or .csv")
    path.write_text(text, encoding="utf-8", newline="")
