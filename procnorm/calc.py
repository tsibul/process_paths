# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Comparison of the variants of a checked project: labour and skipped checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from process_paths.engine import Slice, run_variant
from process_paths.model import Variant
from process_paths.norm import find_slice

from procnorm.project import FINAL, Project, check_axes

ZERO = Decimal(0)


@dataclass
class SliceResult:
    """Skipped checks on one slice.

    :ivar name: named slice, or ``"final"``.
    :ivar index: slice number (0 is the initial slice).
    :ivar reached: whether the named slice condition held; an unreached slice is the final one.
    :ivar skips: ``[(entity, axis, price)]``.
    :ivar total: sum of the prices.
    """

    name: str
    index: int
    reached: bool
    skips: list[tuple[str, str, Decimal]]
    total: Decimal


@dataclass
class Row:
    """One variant in the comparison.

    :ivar code: variant code.
    :ivar title: variant title.
    :ivar side: ``"own"`` or ``"other"``.
    :ivar steps: number of calls.
    :ivar labour: ``{executor: labour}`` for the table columns.
    :ivar total: total labour.
    :ivar slices: named slices in dictionary order, then the final slice.
    """

    code: str
    title: str
    side: str
    steps: int
    labour: dict[str, Decimal]
    total: Decimal
    slices: list[SliceResult]


@dataclass
class Comparison:
    """The comparison table.

    :ivar executors: labour columns.
    :ivar slice_names: named slices, then ``"final"``.
    :ivar rows: compared variants, in file order.
    :ivar excluded: ``[(code, title, reason)]`` of variants out of comparison.
    :ivar uncounted_errors: ``{group: [text]}``.
    """

    executors: list[str]
    slice_names: list[str]
    rows: list[Row]
    excluded: list[tuple[str, str, str]]
    uncounted_errors: dict[str, list[str]]


@dataclass
class Step:
    """One call of a variant.

    :ivar number: call number from 1.
    :ivar kind: kind of transition.
    :ivar executor: executor.
    :ivar instrument: instrument.
    :ivar scope: scope.
    :ivar cost: cost of the kind.
    :ivar scope_coefficient: coefficient of the scope.
    :ivar executor_coefficient: coefficient of the executor.
    :ivar labour: cost × scope coefficient × executor coefficient.
    :ivar changes: ``[(entity, axis, before, after)]``.
    """

    number: int
    kind: str
    executor: str
    instrument: str
    scope: str
    cost: Decimal
    scope_coefficient: Decimal
    executor_coefficient: Decimal
    labour: Decimal
    changes: list[tuple[str, str, str | None, str | None]]


def _cost(project: Project, kind: str) -> Decimal:
    return project.norm.kind_costs.get(kind, ZERO)


def _step_labour(project: Project, call) -> Decimal:
    n = project.norm
    return _cost(project, call.kind) * n.scope_coefficients[call.scope] * n.executor_coefficients[call.executor]


def _skips(project: Project, s: Slice) -> list[tuple[str, str, Decimal]]:
    """Check axes of the slice with no value or on the first value."""
    out = []
    for e, a in check_axes(project.model):
        if (e, a) not in s:
            continue
        first = project.model.entity(e).axis(a).values[0]
        if s[(e, a)] is None or s[(e, a)] == first:
            out.append((e, a, project.norm.skip_prices[(e, a)]))
    return out


def _slice_result(project: Project, name: str, index: int, reached: bool, s: Slice) -> SliceResult:
    found = _skips(project, s)
    return SliceResult(name, index, reached, found, sum((p for _, _, p in found), ZERO))


def _columns(project: Project) -> list[str]:
    """Executors with coefficient above zero used in at least one call, in dictionary order."""
    used = {c.executor for v in project.model.variants for c in v.calls}
    return [x.name for x in project.model.executors
            if x.name in used and project.norm.executor_coefficients[x.name] > 0]


def _row(project: Project, v: Variant, columns: list[str]) -> Row:
    slices = run_variant(project.model, v)
    labour = {x: ZERO for x in columns}
    total = ZERO
    for c in v.calls:
        w = _step_labour(project, c)
        total += w
        if c.executor in labour:
            labour[c.executor] += w
    last = len(slices) - 1
    results = []
    for ns in project.model.named_slices:
        i = find_slice(v, slices, ns)
        idx = last if i is None else i
        results.append(_slice_result(project, ns.name, idx, i is not None, slices[idx]))
    results.append(_slice_result(project, FINAL, last, True, slices[last]))
    return Row(v.code, v.title, project.sides[v.code], len(v.calls), labour, total, results)


def compare(project: Project) -> Comparison:
    """Build the comparison table.

    :param project: a checked project.
    :return: the table.
    :rtype: Comparison
    """
    columns = _columns(project)
    rows, excluded = [], []
    for v in project.model.variants:
        if v.out_of_comparison:
            excluded.append((v.code, v.title, v.out_of_comparison))
        else:
            rows.append(_row(project, v, columns))
    names = [ns.name for ns in project.model.named_slices] + [FINAL]
    return Comparison(columns, names, rows, excluded, project.norm.uncounted_errors)


def details(project: Project, code: str) -> list[Step]:
    """Steps of one variant.

    :param project: a checked project.
    :param code: variant code.
    :return: the steps.
    :rtype: list[Step]
    """
    v = next(x for x in project.model.variants if x.code == code)
    slices = run_variant(project.model, v)
    n = project.norm
    out = []
    for i, c in enumerate(v.calls, 1):
        before, after = slices[i - 1], slices[i]
        changes = [(e, a, before.get((e, a)), after.get((e, a)))
                   for (e, a) in after if before.get((e, a)) != after.get((e, a))]
        out.append(Step(i, c.kind, c.executor, c.instrument, c.scope, _cost(project, c.kind),
                        n.scope_coefficients[c.scope], n.executor_coefficients[c.executor],
                        _step_labour(project, c), changes))
    return out


def money(d: Decimal) -> str:
    """Comparison table number: two digits after the point, half up.

    :param d: the number.
    :return: text.
    :rtype: str
    """
    return format(d.quantize(Decimal("0.01"), ROUND_HALF_UP), "f")


def fmt(d: Decimal) -> str:
    """Decimal without trailing zeros and without exponent.

    :param d: the number.
    :return: text.
    :rtype: str
    """
    t = format(d.normalize(), "f")
    return "0" if t in ("-0", "") else t
