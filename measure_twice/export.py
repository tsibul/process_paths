# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export of the comparison to Markdown and CSV.

The texts are English; ``tr`` (the window gives its translation, ``measure_twice.i18n.shown``)
turns each heading and cell into the language shown. The numbers keep the point.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path
from typing import Callable

from measure_twice.calc import (Comparison, Group, Row, Step, compare, details, fmt, groups, money,
                                waiting_text)
from measure_twice.message import QT_TRANSLATE_NOOP, translate
from measure_twice.project import FINAL, Project

DASH = "—"
ARROW = "→"
NOT_SET = QT_TRANSLATE_NOOP("Export", "not set")
NOT_REACHED = QT_TRANSLATE_NOOP("Export", "{number} (not reached)")
WAITING = QT_TRANSLATE_NOOP("Export", "Waiting")
LABOUR_WAITING = QT_TRANSLATE_NOOP("Export", "Labour + waiting")

Tr = Callable[[str], str]


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
    return out + [_risk(s) for s in r.slices]


def _risk(s) -> str:
    shown = number(s.total)
    return shown if s.reached else NOT_REACHED.format(number=shown)


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


def _table(rows: list[list[str]], tr: Tr = str) -> list[str]:
    lines = ["| " + " | ".join(_cell(tr(c)) for c in rows[0]) + " |",
             "|" + "|".join(" --- " for _ in rows[0]) + "|"]
    lines += ["| " + " | ".join(_cell(tr(c)) for c in r) + " |" for r in rows[1:]]
    return lines


SIDES = {"own": QT_TRANSLATE_NOOP("Export", "Ours"), "other": QT_TRANSLATE_NOOP("Export", "Theirs")}
NO_PAIR = QT_TRANSLATE_NOOP("Export", "No comparable variant")
NO_PAIR_NOTE = QT_TRANSLATE_NOOP("Export", "Not compared: no other variant has the same task")
OUT = QT_TRANSLATE_NOOP("Export", "Out of comparison")
GROUP = QT_TRANSLATE_NOOP("Export", "Group")
REASON = QT_TRANSLATE_NOOP("Export", "Reason")
UNCOUNTED = QT_TRANSLATE_NOOP("Export", "Uncounted errors")
DETAILS = QT_TRANSLATE_NOOP("Export", "Details")


def _header(cmp: Comparison) -> list[str]:
    labour = QT_TRANSLATE_NOOP("Export", "Labour · {executor}")
    risk = QT_TRANSLATE_NOOP("Export", "Risk left, {slice}")
    end = QT_TRANSLATE_NOOP("Export", "end")
    head = [
        QT_TRANSLATE_NOOP("Export", "Code"),
        QT_TRANSLATE_NOOP("Export", "Title"),
        QT_TRANSLATE_NOOP("Export", "Side"),
        QT_TRANSLATE_NOOP("Export", "Steps"),
    ]
    return (head + [labour.format(executor=x) for x in cmp.executors]
            + [QT_TRANSLATE_NOOP("Export", "Labour · total")] + waiting_headers(cmp)
            + [risk.format(slice=end if n == FINAL else n) for n in cmp.slice_names])


def _row(cmp: Comparison, r: Row) -> list[str]:
    return [r.code, r.title, SIDES.get(r.side, r.side), str(r.steps)] + numbers(cmp, r)


def _group_name(g: Group) -> str:
    if g.kind == "task":
        return QT_TRANSLATE_NOOP("Export", "Task: {task}").format(task=g.task)
    return NO_PAIR if g.kind == "no-pair" else OUT


def _grid(cmp: Comparison) -> list[list[str]]:
    out = [[GROUP] + _header(cmp) + [REASON]]
    for g in groups(cmp):
        out += [[_group_name(g)] + _row(cmp, r) + [r.reason or ""] for r in g.rows]
    return out


def shown_table(cmp: Comparison, shown: list[tuple[Group, list[Row]]], tr: Tr = str
                ) -> list[list[str]]:
    """The comparison table as the window shows it: a header line and a line per shown row.

    :param cmp: the table.
    :param shown: groups with the rows of each that the window shows, in its order.
    :param tr: turns a text into the language shown.
    :return: lines of cells; the first cell is the group name, then the columns of the window.
    :rtype: list[list[str]]
    """
    out = [[GROUP] + _header(cmp)]
    for g, rows in shown:
        out += [[_group_name(g)] + _row(cmp, r) for r in rows]
    return [[tr(c) for c in line] for line in out]


def _change(c: tuple[str, str, str | None, str | None]) -> str:
    e, a, before, after = c
    return f"{e}/{a}: {before if before is not None else DASH} {ARROW} {after if after is not None else DASH}"


def markdown(project: Project, tr: Tr = str) -> str:
    """Markdown export of the comparison.

    :param project: a checked project.
    :param tr: turns a text into the language shown.
    :return: Markdown text.
    :rtype: str
    """
    cmp = compare(project)
    out = [f"# {project.name}", ""]
    if project.description:
        out += [project.description, ""]
    for g in groups(cmp):
        out += [f"## {tr(_group_name(g))}", ""]
        if g.kind == "task":
            out += [tr(translate("Export", "%n variants", "", len(g.rows))), ""]
        elif g.kind == "no-pair":
            out += [tr(NO_PAIR_NOTE), ""]
        head = _header(cmp) + ([REASON] if g.kind == "out" else [])
        body = [_row(cmp, r) + ([r.reason or ""] if g.kind == "out" else []) for r in g.rows]
        out += _table([head] + body, tr) + [""]
    if cmp.uncounted_errors:
        out += [f"## {tr(UNCOUNTED)}", ""]
        for group, items in cmp.uncounted_errors.items():
            out += [f"### {group}", ""] + [f"- {t}" for t in items] + [""]
    out += [f"## {tr(DETAILS)}", ""]
    head = [
        "#",
        QT_TRANSLATE_NOOP("Export", "Kind"),
        QT_TRANSLATE_NOOP("Export", "Executor"),
        QT_TRANSLATE_NOOP("Export", "Instrument"),
        QT_TRANSLATE_NOOP("Export", "Scope"),
        QT_TRANSLATE_NOOP("Export", "Cost"),
        QT_TRANSLATE_NOOP("Export", "Scope coef."),
        QT_TRANSLATE_NOOP("Export", "Executor coef."),
        QT_TRANSLATE_NOOP("Export", "Labour"),
        QT_TRANSLATE_NOOP("Export", "Change"),
    ]
    for r in cmp.rows + cmp.excluded_rows:
        out += [f"### {r.code}: {r.title}", ""]
        rows = [head]
        for s in details(project, r.code):
            rows.append([str(s.number), s.kind, s.executor, s.instrument, s.scope]
                        + step_numbers(s, r.error is not None) + ["; ".join(_change(c) for c in s.changes)])
        out += _table(rows, tr) + [""]
    return "\n".join(out)


def csv_text(project: Project, tr: Tr = str) -> str:
    """CSV export of the comparison table; the numbers keep the point in any language.

    :param project: a checked project.
    :param tr: turns a text into the language shown.
    :return: CSV text with a header row.
    :rtype: str
    """
    buf = io.StringIO()
    rows = [[tr(c) for c in line] for line in _grid(compare(project))]
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def write(project: Project, path: Path, tr: Tr = str) -> None:
    """Write the export; the format follows the suffix.

    :param project: a checked project.
    :param path: file path ending in ``.md`` or ``.csv``.
    :param tr: turns a text into the language shown.
    :raises ValueError: other suffix.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".md":
        text = markdown(project, tr)
    elif suffix == ".csv":
        text = csv_text(project, tr)
    else:
        raise ValueError(f"unknown export format: {path.suffix!r}, use .md or .csv")
    path.write_text(text, encoding="utf-8", newline="")
