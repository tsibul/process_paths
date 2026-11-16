# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stretches of variants up to a goal: a set of required axis values."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from . import analysis
from .engine import Slice, run_variant
from .model import Model, ModelError, Variant

#: A goal item: ``(entity, axis, value)``.
GoalItem = tuple[str, str, str]


@dataclass(frozen=True)
class Goal:
    """A named goal.

    :ivar name: goal name.
    :ivar items: required values; the goal is reached when all of them hold.
    """

    name: str
    items: tuple[GoalItem, ...]


@dataclass
class Reach:
    """The stretch of one variant up to a goal.

    :ivar label: variant label (``code`` or ``file/code`` for several models).
    :ivar model: the model of the variant.
    :ivar variant: the variant.
    :ivar index: number of the first slice where the goal holds, or ``None``.
    :ivar calls: calls up to the goal slice.
    :ivar by_executor: calls per executor, in dictionary order.
    :ivar by_scope: calls per scope, in dictionary order.
    :ivar cost: cost per document of the stretch, or ``None`` if a number is missing.
    :ivar shifted: ``{(entity, axis): value}`` that differ in the goal slice from the reference
        (the initial slice value, or the first axis value for an entity created on the stretch),
        except the goal axes.
    :ivar rest: calls after the goal slice.
    """

    label: str
    model: Model
    variant: Variant
    index: int | None
    calls: int
    by_executor: dict[str, int]
    by_scope: dict[str, int]
    cost: Decimal | None
    shifted: dict[tuple[str, str], str]
    rest: int


def parse_goal_text(text: str) -> Goal:
    """Parse ``Entity/axis=value; Entity/axis=value`` into a goal named by the text.

    :param text: goal text.
    :return: the goal.
    :rtype: Goal
    """
    items = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        left, sep, value = part.partition("=")
        entity, sep2, axis = left.rpartition("/")
        if not sep or not sep2 or not entity.strip() or not axis.strip():
            raise ModelError(f"goal {text!r}: expected Entity/axis=value")
        items.append((entity.strip(), axis.strip(), value.strip()))
    if not items:
        raise ModelError(f"goal {text!r} is empty")
    return Goal(text.strip(), tuple(items))


def load_goals(path: Path) -> list[Goal]:
    """Read named goals from JSON: ``{name: [[entity, axis, value], …], …}``.

    :param path: path to the JSON file.
    :return: the goals in file order.
    :rtype: list[Goal]
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ModelError(f"{path}: expected an object of named goals")
    goals = []
    for name, items in data.items():
        if not isinstance(items, list) or not items or any(
                not isinstance(i, list) or len(i) != 3 for i in items):
            raise ModelError(f"goal {name!r}: expected [[entity, axis, value], …]")
        goals.append(Goal(name, tuple(tuple(i) for i in items)))
    return goals


def check_goal(model: Model, goal: Goal) -> None:
    """Check that the goal names exist in the dictionaries.

    :param model: the model.
    :param goal: the goal.
    :raises ModelError: on an unknown name.
    """
    for e, a, v in goal.items:
        ent = model.entity(e)
        ax = ent.axis(a) if ent else None
        if ax is None or v not in ax.values:
            raise ModelError(f"goal {goal.name!r}: unknown {e}/{a}={v}")


def dictionaries(model: Model) -> tuple:
    """Structure of the dictionaries, without the optional numbers.

    :param model: the model.
    :return: a comparable value.
    :rtype: tuple
    """
    return (
        model.existence_axis, model.absent_value,
        tuple((e.name, tuple((a.name, a.values, a.inherit) for a in e.axes)) for e in model.entities),
        tuple((k.name, k.quadruple, k.requires) for k in model.kinds),
        tuple(x.name for x in model.executors),
        tuple(model.instruments), tuple(model.scopes), model.batch_scope,
        tuple(model.variant_params), tuple(model.named_slices),
    )


def check_same_dictionaries(models: list[tuple[str, Model]]) -> None:
    """Raise if the models do not share the dictionaries.

    :param models: ``(name, model)`` pairs.
    :raises ModelError: naming the first model that differs from the first one.
    """
    first_name, first = models[0]
    ref = dictionaries(first)
    for name, m in models[1:]:
        if dictionaries(m) != ref:
            raise ModelError(f"dictionaries of {name} differ from {first_name}")


def holds(s: Slice, goal: Goal) -> bool:
    """:return: whether all goal values hold in the slice (absent axes do not hold).
    :rtype: bool
    """
    return all(s.get((e, a)) == v for e, a, v in goal.items)


def reach_variant(model: Model, variant: Variant, goal: Goal, label: str,
                  batch: int = analysis.DEFAULT_BATCH) -> Reach:
    """Measure the stretch of a variant up to the goal.

    :param model: the model.
    :param variant: the variant.
    :param goal: the goal.
    :param label: variant label.
    :param batch: batch size for the cost.
    :return: the stretch.
    :rtype: Reach
    """
    slices = run_variant(model, variant)
    index = next((i for i, s in enumerate(slices) if holds(s, goal)), None)
    end = index if index is not None else len(slices) - 1
    calls = variant.calls[:end]
    goal_axes = {(e, a) for e, a, _ in goal.items}
    first, last = slices[0], slices[end]
    shifted = {}
    for ent in model.entities:
        for ax in ent.axes:
            k = (ent.name, ax.name)
            if k in goal_axes or k not in last or last[k] is None:
                continue
            # reference: the initial slice value, or the first dictionary value for a created entity
            ref = first[k] if first.get(k) is not None else ax.values[0]
            if last[k] != ref:
                shifted[k] = last[k]
    ex = Counter(c.executor for c in calls)
    sc = Counter(c.scope for c in calls)
    return Reach(label, model, variant, index, len(calls),
                 {x.name: ex[x.name] for x in model.executors if ex[x.name]},
                 {s: sc[s] for s in model.scopes if sc[s]},
                 analysis.calls_cost(model, calls, batch), shifted,
                 len(variant.calls) - len(calls) if index is not None else 0)


def reach_all(models: list[tuple[str, Model]], goal: Goal,
              batch: int = analysis.DEFAULT_BATCH) -> list[Reach]:
    """Measure every variant of every model.

    :param models: ``(name, model)`` pairs with the same dictionaries.
    :param goal: the goal.
    :param batch: batch size for the cost.
    :return: one stretch per variant, in model and variant order.
    :rtype: list[Reach]
    """
    out = []
    for name, m in models:
        check_goal(m, goal)
        for v in m.variants:
            label = v.code if len(models) == 1 else f"{name}/{v.code}"
            out.append(reach_variant(m, v, goal, label, batch))
    return out


def compare(base: Reach, other: Reach) -> tuple[list[str], list[str], list[str], list[str]]:
    """Axes moved by the goal: only in the base, only in the other, in both alike, in both differently.

    :param base: the base stretch.
    :param other: the other stretch.
    :return: four lists; the first three of ``Entity/axis``, the last of
        ``Entity/axis: base value / other value``.
    :rtype: tuple[list[str], list[str], list[str], list[str]]
    """
    a, b = set(base.shifted), set(other.shifted)
    order = [(e.name, x.name) for e in base.model.entities for x in e.axes]
    fmt = lambda keys: [f"{e}/{x}" for e, x in order if (e, x) in keys]  # noqa: E731
    both = a & b
    alike = {k for k in both if base.shifted[k] == other.shifted[k]}
    differ = [f"{e}/{x}: {base.shifted[(e, x)]} / {other.shifted[(e, x)]}"
              for e, x in order if (e, x) in both - alike]
    return fmt(a - b), fmt(b - a), fmt(alike), differ


def find_base(reaches: list[Reach], label: str) -> Reach:
    """Find the base variant by label or, if unique, by code.

    :param reaches: the stretches.
    :param label: ``code`` or ``file/code``.
    :return: the stretch.
    :rtype: Reach
    """
    exact = [r for r in reaches if r.label == label]
    if exact:
        return exact[0]
    by_code = [r for r in reaches if r.variant.code == label]
    if len(by_code) == 1:
        return by_code[0]
    raise ModelError(f"base variant {label!r} not found or ambiguous")


def _counts(d: dict[str, int]) -> str:
    return ", ".join(f"{k} {n}" for k, n in d.items()) or "—"


def _values(r: Reach) -> str:
    return "; ".join(f"{e}/{a} = {v}" for (e, a), v in r.shifted.items()) or "—"


def render_text(goal: Goal, reaches: list[Reach], base: Reach | None) -> str:
    """Plain text output.

    :param goal: the goal.
    :param reaches: the stretches.
    :param base: the base stretch or ``None``.
    :return: text.
    :rtype: str
    """
    L = [f"goal: {goal.name}"]
    for r in reaches:
        if r.index is None:
            L.append(f"  {r.label}: not reached")
            continue
        cost = "not set" if r.cost is None else str(r.cost)
        L += [f"  {r.label}: slice {r.index}; calls {r.calls} (executors: {_counts(r.by_executor)}; "
              f"scopes: {_counts(r.by_scope)}); cost {cost}; rest {r.rest}",
              f"    moved: {_values(r)}"]
    if base is not None:
        L.append(f"  compared with {base.label}:")
        for r in reaches:
            if r is base:
                continue
            if r.index is None or base.index is None:
                L.append(f"    {r.label}: goal not reached")
                continue
            a, b, alike, differ = compare(base, r)
            L.append(f"    {r.label}: only {base.label}: {', '.join(a) or '-'}; "
                     f"only {r.label}: {', '.join(b) or '-'}; alike: {len(alike)}; "
                     f"differently: {'; '.join(differ) or '-'}")
    return "\n".join(L) + "\n"


def render_markdown(goals: list[tuple[Goal, list[Reach], Reach | None]], batch: int) -> str:
    """Markdown output in Russian.

    :param goals: ``(goal, stretches, base)`` per goal.
    :param batch: batch size used for the cost.
    :return: Markdown text.
    :rtype: str
    """
    L = ["# Участки вариантов до цели", "",
         "Цель достигнута в срезе, если все её оси имеют указанные значения. Срез 0 — начальный. "
         f"Стоимость — на один документ, размер пачки {batch}; если числа не заданы, указано «не задана».",
         ""]
    for n, (goal, reaches, base) in enumerate(goals, 1):
        L += [f"## {n}. Цель: {goal.name}", "",
              "Значения цели: " + "; ".join(f"{e}/{a} = {v}" for e, a, v in goal.items) + ".", "",
              "| Вариант | Срез цели | Переходов до цели | По исполнителям | По охватам | Стоимость | Остаток |",
              "|---|---|---|---|---|---|---|"]
        for r in reaches:
            if r.index is None:
                L.append(f"| {r.label} {r.variant.title} | не достигнута | — | — | — | — | — |")
                continue
            cost = "не задана" if r.cost is None else str(r.cost)
            L.append(f"| {r.label} {r.variant.title} | {r.index} | {r.calls} | {_counts(r.by_executor)} | "
                     f"{_counts(r.by_scope)} | {cost} | {r.rest} |")
        L += ["", "Сделано к моменту цели сверх самой цели:", ""]
        L += [f"- **{r.label}**: {_values(r)}" for r in reaches if r.index is not None]
        L.append("")
        if base is not None:
            L += [f"Сравнение с опорным вариантом {base.label} (оси, сдвинутые к моменту цели):", "",
                  f"| Вариант | Только у {base.label} | Только у варианта | У обоих одинаково | "
                  f"У обоих по-разному ({base.label} / вариант) |", "|---|---|---|---|---|"]
            for r in reaches:
                if r is base:
                    continue
                if r.index is None or base.index is None:
                    L.append(f"| {r.label} | цель не достигнута | — | — | — |")
                    continue
                a, b, alike, differ = compare(base, r)
                L.append(f"| {r.label} | {', '.join(a) or '—'} | {', '.join(b) or '—'} | "
                         f"{', '.join(alike) or '—'} | {'; '.join(differ) or '—'} |")
            L.append("")
    return "\n".join(L)
