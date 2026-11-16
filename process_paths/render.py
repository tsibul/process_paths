# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Markdown output of the model."""

from __future__ import annotations

from . import analysis
from .engine import Slice, changed_keys, run_variant, variant_entities
from .model import Model, Variant


def slice_line(model: Model, variant: Variant, s: Slice,
               changed: set[tuple[str, str]] | None = None) -> str:
    """Render one slice: all axes of all entities of the variant.

    :param model: the model.
    :param variant: the variant.
    :param s: the slice.
    :param changed: axes to show in bold.
    :return: one line.
    :rtype: str
    """
    parts = []
    for name in variant_entities(model, variant):
        ent = model.entity(name)
        ex_key = (name, model.existence_axis)
        if s.get(ex_key) == model.absent_value:
            keys = [ex_key]
        else:
            keys = [(name, a.name) for a in ent.axes]
        vals = [f"**{s[k]}**" if changed and k in changed else str(s[k]) for k in keys]
        parts.append(f"{name}: " + "; ".join(vals))
    return " | ".join(parts)


def _variant_block(model: Model, v: Variant) -> list[str]:
    """Render one variant: slice, transition, slice, …

    :param model: the model.
    :param v: the variant.
    :return: lines.
    :rtype: list[str]
    """
    slices = run_variant(model, v)
    out = [f"### {v.code}. {v.title}", ""]
    if v.out_of_comparison:
        out += [f"Вне сравнения с конкурентами: {v.out_of_comparison}.", ""]
    if v.params:
        out += ["Параметры варианта: " + "; ".join(f"{p} — {x}" for p, x in v.params.items()) + ".", ""]
    out += [slice_line(model, v, slices[0]), ""]
    for i, c in enumerate(v.calls, 1):
        keys = changed_keys(slices[i - 1], slices[i])
        out += [f"↓ {c.kind} ({c.executor}; {c.instrument}; {c.scope})", "",
                slice_line(model, v, slices[i], keys), ""]
    out += ["| Переходов всего | Видов переходов |", "|---|---|",
            f"| {len(v.calls)} | {len({c.kind for c in v.calls})} |", ""]
    return out


def _cost_block(model: Model) -> list[str]:
    """Render costs and safety; only called when some numbers are set.

    :param model: the model.
    :return: lines.
    :rtype: list[str]
    """
    out = ["### 2.4. Стоимость и безопасность", "",
           f"Стоимость — на один документ, размер пачки {analysis.DEFAULT_BATCH}.", "",
           "| Вариант | Стоимость | Безопасность |", "|---|---|---|"]
    for v in model.variants:
        cost = analysis.path_cost(model, v)
        safe = analysis.path_safety(model, v)
        out.append(f"| {v.code} | {'не задана' if cost is None else cost} | "
                   f"{'не задана' if safe is None else safe} |")
    ranking = analysis.cost_ranking(model)
    out.append("")
    if ranking is not None:
        out += [f"- Пачка {n}: " + ", ".join(codes) + "." for n, codes in ranking.items()]
        orders = {tuple(c) for c in ranking.values()}
        out.append("- Порядок вариантов от размера пачки " + ("не зависит." if len(orders) == 1 else "зависит."))
        out.append("")
    return out


def render_markdown(model: Model) -> str:
    """Render the whole model in the accepted structure.

    :param model: the model.
    :return: Markdown text.
    :rtype: str
    """
    t = model.texts
    n = analysis.dictionary_counts(model)
    unused = analysis.unused_kinds(model)
    idle = analysis.unused_executors(model)
    rows = analysis.variant_counts(model)
    bad = analysis.decomposable_kinds(model) + [(a, [b]) for a, b in analysis.duplicate_kinds(model)]
    L = [f"# {t.get('title', '')}", ""]
    if t.get("header"):
        L += [t["header"], ""]
    L += ["## 1. Определения", "", t.get("definitions", "").strip(), "",
          "## 2. Сводный результат", "", "### 2.1. Счёт справочников", "",
          f"- Сущностей: {n['entities']}.",
          f"- Осей: {n['axes']}; по сущностям: "
          + "; ".join(f"{e} — {c}" for e, c in n["axes_by_entity"].items()) + ".",
          f"- Значений: {n['values']}; по сущностям: "
          + "; ".join(f"{e} — {c}" for e, c in n["values_by_entity"].items()) + ".",
          f"- Видов переходов: {n['kinds']}; не задействованы ни в одном варианте: {len(unused)}"
          + (" (" + ", ".join(unused) + ")" if unused else "") + ".",
          f"- Исполнителей: {n['executors']}"
          + (f"; не задействованы ни в одном варианте: {len(idle)} (" + ", ".join(idle) + ")"
             if idle else "") + ".",
          f"- Инструментов: {n['instruments']}.",
          f"- Охватов: {n['scopes']}.", "",
          "### 2.2. Проверка разделения переходов", "",
          "- Механически: ни один вид перехода «из X в Z» не повторяется цепочкой из двух и более "
          "других видов по той же оси той же сущности, одинаковых четвёрок нет — "
          + ("нарушений нет." if not bad else "нарушения: "
             + "; ".join(f"{k} = {' + '.join(c)}" for k, c in bad) + ".")]
    if t.get("split_semantic"):
        L.append(f"- По смыслу: {t['split_semantic']}")
    L += ["", "### 2.3. Варианты пути", "",
          "| Вариант | Переходов всего | Видов переходов задействовано |", "|---|---|---|"]
    L += [f"| {c} {title} | {a} | {b} |" for c, title, a, b in rows]
    L += ["", "Механическая проверка вариантов: все названия из справочников; каждый переход меняет "
          "значение ровно одной оси одной сущности; при создании сущности вместе с наличием получают "
          "начальные значения остальные её оси (место — по правилу наличия); больше соседние срезы "
          "ничем не различаются; числа совпадают с подсчётом.", ""]
    if analysis.has_numbers(model):
        L += _cost_block(model)
    L += ["## 3. Справочники", "", "### 3.1. Сущности", ""]
    L += [f"- {e.name}" for e in model.entities]
    L += ["", "### 3.2. Оси и значения", ""]
    for e in model.entities:
        L.append(f"- **{e.name}**")
        L += [f"  - {a.name}: " + "; ".join(a.values) for a in e.axes]
    L += ["", "### 3.3. Виды переходов", "",
          "| № | Вид перехода | Сущность | Ось | Из | В | Условие | Вес 0 |",
          "|---|---|---|---|---|---|---|---|"]
    L += [f"| {i} | {k.name} | {k.entity} | {k.axis} | {k.source} | {k.target} | "
          + ("; ".join(f"{e}: {a} = {v}" for e, a, v in k.requires) or "—") + " | "
          + (("да" + (f": {k.zero_weight_note}" if k.zero_weight_note else "")) if k.zero_weight else "—")
          + " |"
          for i, k in enumerate(model.kinds, 1)]
    L += ["", "### 3.4. Исполнители", ""] + [f"- {x.name}" for x in model.executors]
    L += ["", "### 3.5. Инструменты", ""] + [f"- {x}" for x in model.instruments]
    L += ["", "### 3.6. Охваты", ""] + [f"- {x}" for x in model.scopes]
    if model.variant_params:
        L += ["", "### 3.7. Параметры варианта", ""] + [f"- {x}" for x in model.variant_params]
    L += ["", "## 4. Варианты пути", ""]
    if t.get("variants_note"):
        L += [t["variants_note"], ""]
    for v in model.variants:
        L += _variant_block(model, v)
    L += ["## 5. Сводная таблица", "", "| Вариант | Переходов всего | Видов переходов |", "|---|---|---|"]
    L += [f"| {c} {title} | {a} | {b} |" for c, title, a, b in rows]
    return "\n".join(L) + "\n"
