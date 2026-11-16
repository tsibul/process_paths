# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Labour and skips of variants by a normalization file.

The labour of a call is ``kind cost × scope coefficient × executor coefficient``; the labour of
a variant is the sum over its calls. A skip is a check axis (an axis changed by a kind marked
``check``) that is still on its initial value (the first value of the axis) in a slice.
Skips are counted in every named slice of the slices file and in the final slice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .engine import Slice, run_variant
from .model import Model, ModelError, Variant

#: Name of the final slice in the output.
FINAL = "final"


@dataclass(frozen=True)
class Normalization:
    """Numbers for labour and skips.

    :ivar kind_costs: cost of each transition kind.
    :ivar executor_coefficients: coefficient of each executor.
    :ivar scope_coefficients: coefficient of each scope.
    :ivar axis_skip_prices: price of a skip of each check axis, by axis name.
    :ivar batch_size: batch size the scope coefficients are given for, or ``None``.
    :ivar uncounted: errors not counted in the skips, ``{group: [text, …]}``.
    """

    kind_costs: dict[str, Decimal]
    executor_coefficients: dict[str, Decimal]
    scope_coefficients: dict[str, Decimal]
    axis_skip_prices: dict[str, Decimal]
    batch_size: Decimal | None = None
    uncounted: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Alternative:
    """One alternative of a named slice condition.

    :ivar states: ``(entity, axis, value)`` that must all hold in the slice.
    :ivar calls: ``(kind, executor)`` pairs; if given, the variant must contain a call
        matching at least one of them.
    """

    states: tuple[tuple[str, str, str], ...]
    calls: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class NamedSlice:
    """A named slice: the first slice of a variant where any alternative holds.

    :ivar name: slice name.
    :ivar alternatives: the alternatives.
    :ivar otherwise_final: when no slice matches, the named slice is the final one.
    """

    name: str
    alternatives: tuple[Alternative, ...]
    otherwise_final: bool = False


@dataclass
class SliceSkips:
    """Skips in one slice of a variant.

    :ivar name: slice name.
    :ivar index: slice number (0 is the initial one), or ``None`` when not reached.
    :ivar reached: whether the condition holds in some slice.
    :ivar skips: ``(entity, axis, price)`` in dictionary order, or ``None`` when not counted.
    :ivar total: sum of the prices, or ``None`` when not counted.
    """

    name: str
    index: int | None
    reached: bool
    skips: list[tuple[str, str, Decimal]] | None
    total: Decimal | None


@dataclass
class VariantNorm:
    """Labour and skips of one variant.

    :ivar variant: the variant.
    :ivar labour: labour per executor, in dictionary order.
    :ivar total: labour of all executors.
    :ivar slices: skips per named slice, then the final slice.
    """

    variant: Variant
    labour: dict[str, Decimal]
    total: Decimal
    slices: list[SliceSkips]


def _number(value: object, where: str) -> Decimal:
    """:return: the JSON number as ``Decimal``.
    :rtype: Decimal
    :raises ModelError: if the value is not a number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ModelError(f"{where}: number expected")
    return Decimal(value)


def _numbers(data: dict, key: str) -> dict[str, Decimal]:
    """:return: ``{name: number}`` of a required section.
    :rtype: dict[str, Decimal]
    """
    section = data.get(key)
    if not isinstance(section, dict):
        raise ModelError(f"normalization: section {key!r} missing or not an object")
    return {n: _number(v, f"normalization: {key}: {n}") for n, v in section.items()}


def parse_normalization(data: dict) -> Normalization:
    """Build a normalization from parsed JSON.

    :param data: parsed JSON (floats as ``Decimal``).
    :return: the normalization.
    :rtype: Normalization
    """
    if not isinstance(data, dict):
        raise ModelError("normalization: object expected")
    batch = data.get("batch_size")
    uncounted = data.get("uncounted_errors", {})
    if not isinstance(uncounted, dict) or any(not isinstance(v, list) for v in uncounted.values()):
        raise ModelError("normalization: uncounted_errors must be {group: [text, …]}")
    return Normalization(_numbers(data, "kind_costs"), _numbers(data, "executor_coefficients"),
                         _numbers(data, "scope_coefficients"), _numbers(data, "axis_skip_prices"),
                         None if batch is None else _number(batch, "normalization: batch_size"),
                         {k: [str(t) for t in v] for k, v in uncounted.items()})


def load_normalization(path: Path) -> Normalization:
    """Read a normalization file.

    :param path: path to the JSON file.
    :return: the normalization.
    :rtype: Normalization
    """
    return parse_normalization(json.loads(Path(path).read_text(encoding="utf-8"),
                                          parse_float=Decimal))


def parse_slices(data: dict) -> list[NamedSlice]:
    """Build named slices from parsed JSON.

    Format: ``{name: {"any": [{"states": [[entity, axis, value], …],
    "calls": [[kind, executor], …]}, …], "otherwise": "final"}}``; ``calls`` and
    ``otherwise`` are optional.

    :param data: parsed JSON.
    :return: the named slices in file order.
    :rtype: list[NamedSlice]
    """
    if not isinstance(data, dict):
        raise ModelError("slices: object of named slices expected")
    result = []
    for name, spec in data.items():
        where = f"slice {name!r}"
        if name == FINAL:
            raise ModelError(f"{where}: name is reserved for the final slice")
        if not isinstance(spec, dict) or not isinstance(spec.get("any"), list) or not spec["any"]:
            raise ModelError(f"{where}: expected {{\"any\": [alternative, …]}}")
        otherwise = spec.get("otherwise")
        if otherwise not in (None, FINAL):
            raise ModelError(f"{where}: otherwise must be {FINAL!r}")
        alts = []
        for alt in spec["any"]:
            states = alt.get("states") if isinstance(alt, dict) else None
            calls = alt.get("calls", []) if isinstance(alt, dict) else None
            if (not isinstance(states, list) or not states
                    or any(not isinstance(s, list) or len(s) != 3 for s in states)):
                raise ModelError(f"{where}: states must be [[entity, axis, value], …]")
            if not isinstance(calls, list) or any(not isinstance(c, list) or len(c) != 2 for c in calls):
                raise ModelError(f"{where}: calls must be [[kind, executor], …]")
            alts.append(Alternative(tuple(tuple(s) for s in states), tuple(tuple(c) for c in calls)))
        result.append(NamedSlice(name, tuple(alts), otherwise == FINAL))
    return result


def load_slices(path: Path) -> list[NamedSlice]:
    """Read a named slices file.

    :param path: path to the JSON file.
    :return: the named slices.
    :rtype: list[NamedSlice]
    """
    return parse_slices(json.loads(Path(path).read_text(encoding="utf-8")))


def check_axes(model: Model) -> list[tuple[str, str]]:
    """Return the check axes: axes changed by kinds marked ``check``, in dictionary order.

    :param model: the model.
    :return: ``[(entity, axis)]``.
    :rtype: list[tuple[str, str]]
    """
    marked = {(k.entity, k.axis) for k in model.kinds if k.check}
    return [(e.name, a.name) for e in model.entities for a in e.axes if (e.name, a.name) in marked]


def validate(model: Model, norm: Normalization, slices: list[NamedSlice]) -> None:
    """Check that the normalization and the slices match the dictionaries.

    :param model: the model.
    :param norm: the normalization.
    :param slices: the named slices.
    :raises ModelError: listing every mismatch found.
    """
    problems = []
    kinds = [k.name for k in model.kinds]
    problems += [f"kind without cost: {k}" for k in kinds if k not in norm.kind_costs]
    problems += [f"cost of unknown kind: {k}" for k in norm.kind_costs if k not in kinds]
    for k in model.kinds:
        cost = norm.kind_costs.get(k.name)
        if k.zero_weight and cost is not None and cost != 0:
            problems.append(f"kind {k.name}: zero_weight but cost {cost}")
    execs = [x.name for x in model.executors]
    problems += [f"executor without coefficient: {x}" for x in execs if x not in norm.executor_coefficients]
    problems += [f"coefficient of unknown executor: {x}" for x in norm.executor_coefficients if x not in execs]
    problems += [f"scope without coefficient: {s}" for s in model.scopes if s not in norm.scope_coefficients]
    problems += [f"coefficient of unknown scope: {s}" for s in norm.scope_coefficients if s not in model.scopes]
    axes = check_axes(model)
    names = [a for _, a in axes]
    problems += [f"check axis name on several entities: {a}" for a in sorted(set(names)) if names.count(a) > 1]
    problems += [f"check axis without skip price: {e}/{a}" for e, a in axes if a not in norm.axis_skip_prices]
    problems += [f"skip price of an axis that is not a check axis: {a}"
                 for a in norm.axis_skip_prices if a not in names]
    for ns in slices:
        for alt in ns.alternatives:
            for e, a, v in alt.states:
                ent = model.entity(e)
                ax = ent.axis(a) if ent else None
                if ax is None or v not in ax.values:
                    problems.append(f"slice {ns.name!r}: unknown {e}/{a}={v}")
            for k, x in alt.calls:
                if model.kind(k) is None:
                    problems.append(f"slice {ns.name!r}: unknown kind {k}")
                if model.executor(x) is None:
                    problems.append(f"slice {ns.name!r}: unknown executor {x}")
    if problems:
        raise ModelError("normalization does not match the model:\n  " + "\n  ".join(problems))


def labour(model: Model, norm: Normalization, variant: Variant) -> tuple[dict[str, Decimal], Decimal]:
    """Labour of a variant per executor and in total.

    :param model: the model.
    :param norm: the normalization.
    :param variant: the variant.
    :return: ``({executor: labour}, total)``, executors in dictionary order.
    :rtype: tuple[dict[str, Decimal], Decimal]
    """
    by = {x.name: Decimal(0) for x in model.executors}
    for c in variant.calls:
        by[c.executor] += (norm.kind_costs[c.kind] * norm.scope_coefficients[c.scope]
                           * norm.executor_coefficients[c.executor])
    return by, sum(by.values(), Decimal(0))


def skips(model: Model, norm: Normalization, s: Slice) -> list[tuple[str, str, Decimal]]:
    """Check axes still on their initial value in a slice.

    An axis without a value (its entity does not exist or is not in the variant) is a skip too.

    :param model: the model.
    :param norm: the normalization.
    :param s: the slice.
    :return: ``(entity, axis, price)`` in dictionary order.
    :rtype: list[tuple[str, str, Decimal]]
    """
    result = []
    for e, a in check_axes(model):
        if s.get((e, a)) in (None, model.entity(e).axis(a).values[0]):
            result.append((e, a, norm.axis_skip_prices[a]))
    return result


def _holds(variant: Variant, s: Slice, alt: Alternative) -> bool:
    """:return: whether the alternative holds in the slice of the variant.
    :rtype: bool
    """
    if alt.calls and not any((c.kind, c.executor) in alt.calls for c in variant.calls):
        return False
    return all(s.get((e, a)) == v for e, a, v in alt.states)


def find_slice(variant: Variant, slices: list[Slice], ns: NamedSlice) -> int | None:
    """Number of the first slice where the named slice condition holds.

    :param variant: the variant.
    :param slices: all slices of the variant.
    :param ns: the named slice.
    :return: the slice number or ``None``.
    :rtype: int | None
    """
    return next((i for i, s in enumerate(slices) if any(_holds(variant, s, a) for a in ns.alternatives)),
                None)


def _slice_skips(model: Model, norm: Normalization, name: str, index: int | None, reached: bool,
                 slices: list[Slice]) -> SliceSkips:
    if index is None:
        return SliceSkips(name, None, reached, None, None)
    found = skips(model, norm, slices[index])
    return SliceSkips(name, index, reached, found, sum((p for _, _, p in found), Decimal(0)))


def norm_variant(model: Model, norm: Normalization, named: list[NamedSlice], variant: Variant) -> VariantNorm:
    """Labour and skips of one variant.

    :param model: the model.
    :param norm: the normalization.
    :param named: the named slices.
    :param variant: the variant.
    :return: the result.
    :rtype: VariantNorm
    """
    slices = run_variant(model, variant)
    by, total = labour(model, norm, variant)
    final = len(slices) - 1
    out = []
    for ns in named:
        i = find_slice(variant, slices, ns)
        idx = i if i is not None else (final if ns.otherwise_final else None)
        out.append(_slice_skips(model, norm, ns.name, idx, i is not None, slices))
    out.append(_slice_skips(model, norm, FINAL, final, True, slices))
    return VariantNorm(variant, by, total, out)


def norm_all(model: Model, norm: Normalization, named: list[NamedSlice]) -> list[VariantNorm]:
    """Labour and skips of all variants, after validation.

    :param model: the model.
    :param norm: the normalization.
    :param named: the named slices.
    :return: results in variant order.
    :rtype: list[VariantNorm]
    """
    validate(model, norm, named)
    return [norm_variant(model, norm, named, v) for v in model.variants]


def _num(d: Decimal | None) -> int | str | None:
    """:return: an integral number as ``int``, any other as its text, ``None`` unchanged.
    :rtype: int | str | None
    """
    if d is None:
        return None
    return int(d) if d == d.to_integral_value() else str(d)


def to_json(model: Model, norm: Normalization, results: list[VariantNorm]) -> dict:
    """JSON-ready result.

    :param model: the model.
    :param norm: the normalization.
    :param results: the results.
    :return: a dictionary for ``json.dumps``.
    :rtype: dict
    """
    return {
        "batch_size": _num(norm.batch_size),
        "check_axes": [[e, a] for e, a in check_axes(model)],
        "uncounted_errors": norm.uncounted,
        "variants": [{
            "code": r.variant.code,
            "title": r.variant.title,
            "out_of_comparison": r.variant.out_of_comparison,
            "labour": {x: _num(n) for x, n in r.labour.items()},
            "labour_total": _num(r.total),
            "slices": [{
                "name": s.name, "index": s.index, "reached": s.reached,
                "skips": None if s.skips is None else
                [{"entity": e, "axis": a, "price": _num(p)} for e, a, p in s.skips],
                "total": _num(s.total),
            } for s in r.slices],
        } for r in results],
    }


def _fmt(d: Decimal | None) -> str:
    return "—" if d is None else str(_num(d))


def _slice_cell(s: SliceSkips) -> str:
    """:return: slice number with a note when the condition did not hold.
    :rtype: str
    """
    if s.index is None:
        return "не наступает"
    return str(s.index) if s.reached else f"не наступает (= конечный, {s.index})"


def render_markdown(model: Model, norm: Normalization, results: list[VariantNorm]) -> str:
    """Markdown output in Russian.

    The labour columns are the executors with a non-zero coefficient; «вместе» is all executors.

    :param model: the model.
    :param norm: the normalization.
    :param results: the results.
    :return: Markdown text.
    :rtype: str
    """
    execs = [x.name for x in model.executors if norm.executor_coefficients[x.name] != 0]
    names = [("конечный" if s.name == FINAL else s.name) for s in results[0].slices] if results else []
    batch = f" Пачка: {_fmt(norm.batch_size)} документов." if norm.batch_size is not None else ""
    L = ["# Труд и пропуски по нормировке", "",
         f"Труд — в нажатиях на пачку.{batch} Пропуск — ось проверки, оставшаяся на начальном значении; "
         "сумма — сумма цен пропусков. Срез 0 — начальный. Варианты вне сравнения посчитаны, "
         "но в сравнение не входят.", "",
         "| Вариант | " + " | ".join(f"Труд: {x}" for x in execs) + " | Труд вместе | "
         + " | ".join(f"Срез «{n}» | Пропуски «{n}» | Сумма «{n}»" for n in names)
         + " | Сравнение |",
         "|" + "---|" * (2 + len(execs) + 3 * len(names) + 1)]
    for r in results:
        cells = [f"{r.variant.code} {r.variant.title}"] + [_fmt(r.labour[x]) for x in execs] + [_fmt(r.total)]
        for s in r.slices:
            listed = "—" if s.skips is None else (", ".join(a for _, a, _ in s.skips) or "нет")
            cells += [_slice_cell(s), listed, _fmt(s.total)]
        cells.append("вне сравнения" if r.variant.out_of_comparison else "да")
        L.append("| " + " | ".join(cells) + " |")
    ooc = [r.variant for r in results if r.variant.out_of_comparison]
    if ooc:
        L += ["", "Вне сравнения:", ""] + [f"- **{v.code}**: {v.out_of_comparison}" for v in ooc]
    if norm.uncounted:
        L += ["", "Ошибки без счёта (в сумму пропусков не входят):", ""]
        for group, items in norm.uncounted.items():
            L.append(f"- {group}: " + "; ".join(items))
    return "\n".join(L) + "\n"
