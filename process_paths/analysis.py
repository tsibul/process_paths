"""Counts and checks over the model."""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from itertools import combinations

from .engine import run_variant
from .model import Model, Variant

#: Default batch size for the cost per document.
DEFAULT_BATCH = 100
#: Batch sizes of the sensitivity run.
BATCH_SIZES = (1, 10, 100, 1000)


def dictionary_counts(model: Model) -> dict[str, object]:
    """Count the dictionaries.

    :param model: the model.
    :return: counts; per-entity axes and values as ``{entity: n}``.
    :rtype: dict[str, object]
    """
    return {
        "entities": len(model.entities),
        "axes": sum(len(e.axes) for e in model.entities),
        "values": sum(len(a.values) for e in model.entities for a in e.axes),
        "axes_by_entity": {e.name: len(e.axes) for e in model.entities},
        "values_by_entity": {e.name: sum(len(a.values) for a in e.axes) for e in model.entities},
        "kinds": len(model.kinds),
        "executors": len(model.executors),
        "instruments": len(model.instruments),
        "scopes": len(model.scopes),
    }


def duplicate_kinds(model: Model) -> list[tuple[str, str]]:
    """Find kinds with the same ``(entity, axis, from, to)``.

    :param model: the model.
    :return: pairs of kind names.
    :rtype: list[tuple[str, str]]
    """
    return [(a.name, b.name) for a, b in combinations(model.kinds, 2) if a.quadruple == b.quadruple]


def decomposable_kinds(model: Model) -> list[tuple[str, list[str]]]:
    """Find kinds repeated by a chain of two or more other kinds on the same axis.

    :param model: the model.
    :return: ``(kind, chain of kind names)`` for each violation.
    :rtype: list[tuple[str, list[str]]]
    """
    found = []
    for k in model.kinds:
        others = [o for o in model.kinds
                  if o is not k and (o.entity, o.axis) == (k.entity, k.axis)
                  and (o.source, o.target) != (k.source, k.target)]
        queue = deque([(k.source, [])])
        seen = {k.source}
        while queue:
            value, chain = queue.popleft()
            for o in others:
                if o.source != value:
                    continue
                if o.target == k.target:
                    found.append((k.name, chain + [o.name]))
                    queue.clear()
                    break
                if o.target not in seen:
                    seen.add(o.target)
                    queue.append((o.target, chain + [o.name]))
    return found


def variant_counts(model: Model) -> list[tuple[str, str, int, int]]:
    """Count transitions and distinct kinds per variant.

    :param model: the model.
    :return: ``(code, title, transitions, kinds)`` rows.
    :rtype: list[tuple[str, str, int, int]]
    """
    return [(v.code, v.title, len(v.calls), len({c.kind for c in v.calls})) for v in model.variants]


def unused_kinds(model: Model) -> list[str]:
    """:param model: the model.
    :return: names of kinds used in no variant.
    :rtype: list[str]
    """
    used = {c.kind for v in model.variants for c in v.calls}
    return [k.name for k in model.kinds if k.name not in used]


def identical_slices(model: Model) -> list[dict[str, object]]:
    """Find equal slices between pairs of variants.

    Slices are numbered from 0 (initial). ``full`` compares whole slices (only
    possible with the same axes); ``common`` compares the axes both variants have.

    :param model: the model.
    :return: rows ``{a, b, common_axes, full: [(i, j)], common: [(i, j)]}``.
    :rtype: list[dict[str, object]]
    """
    runs = {v.code: run_variant(model, v) for v in model.variants}
    rows = []
    for va, vb in combinations(model.variants, 2):
        sa, sb = runs[va.code], runs[vb.code]
        common = [k for k in sa[0] if k in sb[0]]
        same_axes = set(sa[0]) == set(sb[0])
        full, part = [], []
        for i, x in enumerate(sa):
            for j, y in enumerate(sb):
                if common and all(x[k] == y[k] for k in common):
                    part.append((i, j))
                    if same_axes:
                        full.append((i, j))
        rows.append({"a": va.code, "b": vb.code, "common_axes": len(common),
                     "full": full, "common": part})
    return rows


def path_cost(model: Model, variant: Variant, batch: int = DEFAULT_BATCH) -> Decimal | None:
    """Cost of a variant per one document.

    Each call costs the kind's cost for its instrument (or the kind's own cost)
    times the executor factor; a call once per batch is divided by the batch size.

    :param model: the model.
    :param variant: the variant.
    :param batch: batch size.
    :return: the cost, or ``None`` if a number is missing.
    :rtype: Decimal | None
    """
    total = Decimal(0)
    for c in variant.calls:
        k = model.kind(c.kind)
        base = k.instrument_costs.get(c.instrument, k.cost)
        factor = model.executor(c.executor).factor
        if base is None or factor is None:
            return None
        part = base * factor
        if c.scope == model.batch_scope:
            part /= batch
        total += part
    return total


def cost_missing(model: Model, variant: Variant) -> list[str]:
    """List what is missing for the cost of a variant.

    :param model: the model.
    :param variant: the variant.
    :return: missing items, e.g. ``kind: name`` or ``executor: name``.
    :rtype: list[str]
    """
    out: list[str] = []
    for c in variant.calls:
        k = model.kind(c.kind)
        if k.instrument_costs.get(c.instrument, k.cost) is None:
            out.append(f"kind: {k.name}")
        if model.executor(c.executor).factor is None:
            out.append(f"executor: {c.executor}")
    return list(dict.fromkeys(out))


def path_safety(model: Model, variant: Variant) -> int | None:
    """Number of check transitions in a variant; independent of the scope.

    :param model: the model.
    :param variant: the variant.
    :return: the number, or ``None`` if a kind of the variant has no check flag.
    :rtype: int | None
    """
    flags = [model.kind(c.kind).check for c in variant.calls]
    if any(f is None for f in flags):
        return None
    return sum(1 for f in flags if f)


def cost_ranking(model: Model, sizes: tuple[int, ...] = BATCH_SIZES) -> dict[int, list[str]] | None:
    """Order of variants by cost per document for each batch size.

    :param model: the model.
    :param sizes: batch sizes.
    :return: ``{size: [codes, cheapest first]}``, or ``None`` if a cost is missing.
    :rtype: dict[int, list[str]] | None
    """
    out = {}
    for n in sizes:
        costs = [(path_cost(model, v, n), v.code) for v in model.variants]
        if any(c is None for c, _ in costs):
            return None
        out[n] = [code for _, code in sorted(costs, key=lambda t: t[0])]
    return out


def has_numbers(model: Model) -> bool:
    """:return: whether any cost, factor or check flag is set.
    :rtype: bool
    """
    return any(k.cost is not None or k.instrument_costs or k.check is not None for k in model.kinds) \
        or any(x.factor is not None for x in model.executors)


def forbidden_hits(model: Model, text: str) -> list[str]:
    """Find forbidden word stems in a text.

    :param model: the model.
    :param text: text to search.
    :return: the stems found.
    :rtype: list[str]
    """
    low = text.lower()
    for phrase in model.forbidden_exceptions:
        low = low.replace(phrase.lower(), "")
    return [w for w in model.forbidden if w.lower() in low]

