# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export of the comparison to Markdown and CSV."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from procnorm.calc import Comparison, Group, Row, compare, details, fmt, groups, money
from procnorm.project import FINAL, Project

DASH = "—"
ARROW = "→"


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
            + ["Labour · total"]
            + [f"Skipped checks, {'end' if n == FINAL else n}" for n in cmp.slice_names])


def _row(cmp: Comparison, r: Row) -> list[str]:
    out = [r.code, r.title, SIDES.get(r.side, r.side), str(r.steps)]
    out += [money(r.labour[x]) for x in cmp.executors]
    out.append(money(r.total))
    for s in r.slices:
        out.append(money(s.total) + ("" if s.reached else " (not reached)"))
    return out


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
            rows.append([str(s.number), s.kind, s.executor, s.instrument, s.scope, fmt(s.cost),
                         fmt(s.scope_coefficient), fmt(s.executor_coefficient), fmt(s.labour),
                         "; ".join(_change(c) for c in s.changes)])
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
