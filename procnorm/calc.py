# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Comparison of the variants of a checked project: labour and skipped checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from process_paths.engine import Slice, TransitionError, apply, initial_slice, run_variant, variant_entities
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
    :ivar skips: ``[(entity, axis, price)]``; ``price`` is ``None`` when not set.
    :ivar total: sum of the prices; ``None`` when a price of a skip is not set.
    """

    name: str
    index: int
    reached: bool
    skips: list[tuple[str, str, Decimal | None]]
    total: Decimal | None


@dataclass
class Row:
    """One variant in the comparison.

    :ivar code: variant code.
    :ivar title: variant title.
    :ivar side: ``"own"`` or ``"other"``.
    :ivar steps: number of calls.
    :ivar labour: ``{executor: labour}`` for the table columns; ``None`` when not set (a number
        is missing, or the run failed).
    :ivar total: total labour; ``None`` when not set.
    :ivar slices: named slices in dictionary order, then the final slice; empty when the run failed.
    :ivar task: task of the variant, ``None`` when absent.
    :ivar reason: why the variant is out of comparison: the run error (``Error at transition N:
        …``), else the missing numbers (``Not set: …``), else its ``out_of_comparison``; ``None``
        for a compared variant.
    :ivar missing: normalization numbers this variant needs and the project lacks, e.g.
        ``cost of Wash``, ``coefficient of executor X``, ``coefficient of scope Y``,
        ``skip price of E/a``.
    :ivar error: ``(call number, reason)`` of the run error, ``None`` when the run passes.
    """

    code: str
    title: str
    side: str
    steps: int
    labour: dict[str, Decimal | None]
    total: Decimal | None
    slices: list[SliceResult]
    task: str | None = None
    reason: str | None = None
    missing: list[str] = field(default_factory=list)
    error: tuple[int, str] | None = None


@dataclass
class Comparison:
    """The comparison table.

    :ivar executors: labour columns.
    :ivar slice_names: named slices, then ``"final"``.
    :ivar rows: compared variants, in file order.
    :ivar excluded: ``[(code, title, reason)]`` of variants out of comparison.
    :ivar uncounted_errors: ``{group: [text]}``.
    :ivar excluded_rows: the variants out of comparison, computed, with ``reason``; file order.
    """

    executors: list[str]
    slice_names: list[str]
    rows: list[Row]
    excluded: list[tuple[str, str, str]]
    uncounted_errors: dict[str, list[str]]
    excluded_rows: list[Row] = field(default_factory=list)


@dataclass
class Group:
    """A group of rows of the comparison.

    :ivar kind: ``"task"`` (a pair or more), ``"no-pair"`` or ``"out"``.
    :ivar task: task text for ``"task"``, otherwise ``None``.
    :ivar rows: own first, then other; within a side by total, then by code.
    """

    kind: str
    task: str | None
    rows: list[Row]


@dataclass
class Point:
    """State of a variant after one step.

    :ivar number: call number from 1.
    :ivar kind: kind of transition.
    :ivar executor: executor.
    :ivar labour: cumulative labour after the step; ``None`` from the first step whose labour is
        not set.
    :ivar skips: ``[(entity, axis)]`` of the skipped checks on the slice after the step.
    :ivar skips_count: ``len(skips)``.
    :ivar skips_total: sum of the prices of the skips; ``None`` when a price is not set.
    :ivar done_total: sum of the prices of the done checks (axis in the slice, with a value,
        not the first one); ``None`` when a price is not set.
    :ivar slices: names of the named slices reached at this step.
    """

    number: int
    kind: str
    executor: str
    labour: Decimal | None
    skips: list[tuple[str, str]]
    skips_count: int
    skips_total: Decimal | None
    done_total: Decimal | None
    slices: list[str]


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
    :ivar changes: ``[(entity, axis, before, after)]``; empty from the failed call on.

    A number that is not set is ``None``; in a variant with a run error every number is ``None``.
    """

    number: int
    kind: str
    executor: str
    instrument: str
    scope: str
    cost: Decimal | None
    scope_coefficient: Decimal | None
    executor_coefficient: Decimal | None
    labour: Decimal | None
    changes: list[tuple[str, str, str | None, str | None]]


@dataclass
class Link:
    """One human step of a variant with its transitions.

    :ivar text: the step as the human said it; ``None`` for the single link of a variant
        without ``steps``.
    :ivar calls: the transitions of the step, in order.
    :ivar slices: ``[(call number, slice name)]``: the named slices reached at calls of this link
        (a marker goes after that call).
    """

    text: str | None
    calls: list[Step]
    slices: list[tuple[int, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """A human step with no transitions."""
        return self.text is not None and not self.calls


def _cost(project: Project, kind: str) -> Decimal | None:
    """Cost of a kind; 0 for an absent zero-weight kind, ``None`` when not set."""
    cost = project.norm.kind_costs.get(kind)
    if cost is None and project.model.kind(kind).zero_weight:
        return ZERO
    return cost


def _product(*xs: Decimal | None) -> Decimal | None:
    if any(x is None for x in xs):
        return None
    out = xs[0]
    for x in xs[1:]:
        out *= x
    return out


def _add(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    return None if a is None or b is None else a + b


def _step_labour(project: Project, call) -> Decimal | None:
    n = project.norm
    return _product(_cost(project, call.kind), n.scope_coefficients.get(call.scope),
                    n.executor_coefficients.get(call.executor))


def _skips(project: Project, s: Slice) -> list[tuple[str, str, Decimal | None]]:
    """Check axes of the slice with no value or on the first value."""
    out = []
    for e, a in check_axes(project.model):
        if (e, a) not in s:
            continue
        first = project.model.entity(e).axis(a).values[0]
        if s[(e, a)] is None or s[(e, a)] == first:
            out.append((e, a, project.norm.skip_prices.get((e, a))))
    return out


def _sum(prices) -> Decimal | None:
    total = ZERO
    for p in prices:
        total = _add(total, p)
    return total


def _slice_result(project: Project, name: str, index: int, reached: bool, s: Slice) -> SliceResult:
    found = _skips(project, s)
    return SliceResult(name, index, reached, found, _sum(p for _, _, p in found))


def _columns(project: Project) -> list[str]:
    """Executors with a set coefficient above zero used in at least one call, in dictionary order."""
    used = {c.executor for v in project.model.variants for c in v.calls}
    return [x.name for x in project.model.executors
            if x.name in used and project.norm.executor_coefficients.get(x.name, ZERO) > 0]


def _missing(project: Project, v: Variant) -> list[str]:
    """Normalization numbers the variant needs and the project lacks, in dictionary order."""
    m, n = project.model, project.norm
    kinds = {c.kind for c in v.calls}
    executors = {c.executor for c in v.calls}
    scopes = {c.scope for c in v.calls}
    entities = set(variant_entities(m, v))
    out = [f"cost of {k.name}" for k in m.kinds if k.name in kinds and _cost(project, k.name) is None]
    out += [f"coefficient of executor {x.name}" for x in m.executors
            if x.name in executors and x.name not in n.executor_coefficients]
    out += [f"coefficient of scope {x}" for x in m.scopes
            if x in scopes and x not in n.scope_coefficients]
    out += [f"skip price of {e}/{a}" for e, a in check_axes(m)
            if e in entities and (e, a) not in n.skip_prices]
    return out


def _reason(project: Project, v: Variant, missing: list[str]) -> str | None:
    error = project.errors.get(v.code)
    if error is not None:
        return f"Error at transition {error[0]}: {error[1]}"
    if missing:
        return "Not set: " + ", ".join(missing)
    return v.out_of_comparison or None


def _row(project: Project, v: Variant, columns: list[str]) -> Row:
    missing = _missing(project, v)
    error = project.errors.get(v.code)
    reason = _reason(project, v, missing)
    if error is not None:
        return Row(v.code, v.title, project.sides[v.code], len(v.calls), {x: None for x in columns}, None,
                   [], project.tasks.get(v.code), reason, missing, error)
    slices = run_variant(project.model, v)
    labour: dict[str, Decimal | None] = {x: ZERO for x in columns}
    total: Decimal | None = ZERO
    for c in v.calls:
        w = _step_labour(project, c)
        total = _add(total, w)
        if c.executor in labour:
            labour[c.executor] = _add(labour[c.executor], w)
    last = len(slices) - 1
    results = []
    for ns in project.model.named_slices:
        i = find_slice(v, slices, ns)
        idx = last if i is None else i
        results.append(_slice_result(project, ns.name, idx, i is not None, slices[idx]))
    results.append(_slice_result(project, FINAL, last, True, slices[last]))
    return Row(v.code, v.title, project.sides[v.code], len(v.calls), labour, total, results,
               project.tasks.get(v.code), reason, missing, error)


def compare(project: Project) -> Comparison:
    """Build the comparison table.

    A variant with a run error or a missing number goes out of comparison with that reason.

    :param project: a checked project (strict or lenient).
    :return: the table.
    :rtype: Comparison
    """
    columns = _columns(project)
    rows, excluded, excluded_rows = [], [], []
    for v in project.model.variants:
        r = _row(project, v, columns)
        if r.reason is not None:
            excluded.append((v.code, v.title, r.reason))
            excluded_rows.append(r)
        else:
            rows.append(r)
    names = [ns.name for ns in project.model.named_slices] + [FINAL]
    return Comparison(columns, names, rows, excluded, project.norm.uncounted_errors, excluded_rows)


def _ordered(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda r: (r.side != "own", r.total is None, r.total or ZERO, r.code))


def groups(comparison: Comparison) -> list[Group]:
    """Split the rows into groups, in the default order.

    Groups with a pair (a task of two or more compared variants) go alphabetically by task,
    then variants without a pair, then variants out of comparison. Empty groups are absent.

    :param comparison: the table.
    :return: the groups.
    :rtype: list[Group]
    """
    by_task: dict[str, list[Row]] = {}
    for r in comparison.rows:
        if r.task is not None:
            by_task.setdefault(r.task, []).append(r)
    paired = sorted((t for t, rs in by_task.items() if len(rs) >= 2), key=lambda t: (t.casefold(), t))
    out = [Group("task", t, _ordered(by_task[t])) for t in paired]
    single = [r for r in comparison.rows if r.task not in paired]
    if single:
        out.append(Group("no-pair", None, _ordered(single)))
    if comparison.excluded_rows:
        out.append(Group("out", None, _ordered(comparison.excluded_rows)))
    return out


def details(project: Project, code: str) -> list[Step]:
    """Steps of one variant.

    :param project: a checked project.
    :param code: variant code.
    :return: the steps.
    :rtype: list[Step]
    """
    v = next(x for x in project.model.variants if x.code == code)
    failed = code in project.errors
    slices = _run_until_error(project, v) if failed else run_variant(project.model, v)
    n = project.norm
    out = []
    for i, c in enumerate(v.calls, 1):
        changes = []
        if i < len(slices):
            before, after = slices[i - 1], slices[i]
            changes = [(e, a, before.get((e, a)), after.get((e, a)))
                       for (e, a) in after if before.get((e, a)) != after.get((e, a))]
        if failed:
            out.append(Step(i, c.kind, c.executor, c.instrument, c.scope, None, None, None, None, changes))
        else:
            out.append(Step(i, c.kind, c.executor, c.instrument, c.scope, _cost(project, c.kind),
                            n.scope_coefficients.get(c.scope), n.executor_coefficients.get(c.executor),
                            _step_labour(project, c), changes))
    return out


def _run_until_error(project: Project, v: Variant) -> list[Slice]:
    """The slices of a variant up to the failed call (that call has none)."""
    slices = [initial_slice(project.model, v)]
    try:
        for i in range(1, len(v.calls) + 1):
            slices.append(apply(project.model, slices[-1], v, i))
    except TransitionError:
        pass
    return slices


def _done_total(project: Project, s: Slice) -> Decimal | None:
    total: Decimal | None = ZERO
    for e, a in check_axes(project.model):
        if (e, a) in s and s[(e, a)] is not None and s[(e, a)] != project.model.entity(e).axis(a).values[0]:
            total = _add(total, project.norm.skip_prices.get((e, a)))
    return total


def series(project: Project, code: str) -> list[Point]:
    """Labour, skips and reached slices after each step of one variant.

    :param project: a checked project.
    :param code: variant code.
    :return: one point per call; none for a variant with a run error.
    :rtype: list[Point]
    """
    if code in project.errors:
        return []
    v = next(x for x in project.model.variants if x.code == code)
    slices = run_variant(project.model, v)
    reached: dict[int, list[str]] = {}
    for ns in project.model.named_slices:
        i = find_slice(v, slices, ns)
        if i is not None:
            reached.setdefault(i, []).append(ns.name)
    out, labour = [], ZERO
    for i, c in enumerate(v.calls, 1):
        labour = _add(labour, _step_labour(project, c))
        found = _skips(project, slices[i])
        out.append(Point(i, c.kind, c.executor, labour, [(e, a) for e, a, _ in found], len(found),
                         _sum(p for _, _, p in found), _done_total(project, slices[i]),
                         reached.get(i, [])))
    return out


def start_point(project: Project, code: str) -> Point:
    """The point before the first step of one variant: the initial slice, no labour.

    :param project: a checked project.
    :param code: variant code.
    :return: a point with ``number`` 0, empty ``kind`` and ``executor``, zero labour and no
        reached slices; it goes before the points of :func:`series`. A variant with a run error
        has it too: the initial slice does not depend on the calls.
    :rtype: Point
    """
    v = next(x for x in project.model.variants if x.code == code)
    s0 = initial_slice(project.model, v)
    found = _skips(project, s0)
    return Point(0, "", "", ZERO, [(e, a) for e, a, _ in found], len(found),
                 _sum(p for _, _, p in found), _done_total(project, s0), [])


def chain(project: Project, code: str) -> list[Link]:
    """Human steps of one variant with their transitions and slice markers.

    :param project: a checked project.
    :param code: variant code.
    :return: the links; one link with ``text`` ``None`` and all calls if the variant has no
        ``steps``.
    :rtype: list[Link]
    """
    calls = details(project, code)
    marks = [(p.number, n) for p in series(project, code) for n in p.slices]
    steps = project.steps.get(code)
    sizes = [(None, len(calls))] if steps is None else steps
    out, pos = [], 0
    for text, n in sizes:
        part = calls[pos:pos + n]
        pos += n
        out.append(Link(text, part, [m for m in marks if pos - n < m[0] <= pos]))
    return out


def empty_steps(project: Project, code: str) -> int:
    """Number of human steps of one variant without transitions.

    :param project: a checked project.
    :param code: variant code.
    :return: the count; 0 for a variant without ``steps``.
    :rtype: int
    """
    return sum(1 for text, n in (project.steps.get(code) or []) if n == 0)


def project_empty_steps(project: Project) -> int:
    """Number of human steps without transitions over all variants of the project.

    :param project: a checked project.
    :return: the count.
    :rtype: int
    """
    return sum(empty_steps(project, v.code) for v in project.model.variants)


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
