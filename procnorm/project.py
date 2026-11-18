# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project file: reading and checking with the full list of remarks.

The check runs in stages; a stage runs only when the stages before it gave no remark,
so that one mistake does not produce a cascade of false remarks:

1. structure: fields, types, JSON numbers;
2. dictionary, variant names and normalization;
3. variant runs (step by step) and the split check.

The lenient read (``strict=False``) is for a project from the database and after an edit: a missing
normalization number is no remark, and a variant that fails its run stays, with the error kept in
``Project.errors``. Every other remark refuses the project in both modes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from process_paths.analysis import decomposable_kinds, duplicate_kinds
from process_paths.engine import TransitionError, run_variant
from process_paths.model import (Axis, Call, Entity, Executor, Kind, Model, NamedSlice, SliceGroup,
                                 Variant)

FORMAT = 1
FINAL = "final"
SIDES = ("own", "other")

TOP_FIELDS = {"format", "name", "description", "existence_axis", "entities", "kinds", "executors",
              "instruments", "scopes", "batch_scope", "variant_params", "named_slices", "variants",
              "normalization"}
ENTITY_FIELDS = {"name", "axes"}
AXIS_FIELDS = {"name", "values", "inherit"}
KIND_FIELDS = {"name", "entity", "axis", "from", "to", "requires", "check", "zero_weight",
               "zero_weight_note"}
VARIANT_FIELDS = {"code", "title", "side", "calls", "params", "entities", "initial",
                  "out_of_comparison", "task", "steps"}
STEP_FIELDS = {"text", "calls"}
NORM_FIELDS = {"batch_size", "kind_costs", "executor_coefficients", "scope_coefficients",
               "axis_skip_prices", "uncounted_errors"}


@dataclass(frozen=True)
class Remark:
    """One remark of the check.

    :ivar where: place in the file.
    :ivar text: what is wrong.
    """

    where: str
    text: str

    def __str__(self) -> str:
        return f"{self.where}: {self.text}" if self.where else self.text


@dataclass
class Normalization:
    """Numbers of the project.

    :ivar kind_costs: ``{kind: cost}``; a zero-weight kind may be missing (its cost is 0).
    :ivar executor_coefficients: ``{executor: coefficient}``.
    :ivar scope_coefficients: ``{scope: coefficient}``.
    :ivar skip_prices: ``{(entity, check axis): price}``.
    :ivar uncounted_errors: ``{group: [text]}``, shown, never counted.
    :ivar batch_size: informational batch size, or ``None``.
    """

    kind_costs: dict[str, Decimal]
    executor_coefficients: dict[str, Decimal]
    scope_coefficients: dict[str, Decimal]
    skip_prices: dict[tuple[str, str], Decimal]
    uncounted_errors: dict[str, list[str]] = field(default_factory=dict)
    batch_size: Decimal | None = None


@dataclass
class Project:
    """A checked project.

    :ivar name: project name.
    :ivar description: project description, may be empty.
    :ivar model: dictionary and variants.
    :ivar sides: ``{variant code: "own" | "other"}``.
    :ivar norm: normalization.
    :ivar data: the parsed file, kept to store and export it unchanged.
    :ivar tasks: ``{variant code: task text as entered, or None}``.
    :ivar steps: ``{variant code: [(step text as entered, calls count)], or None}``; ``None`` when
        the variant has no ``steps``.
    :ivar errors: ``{variant code: (1-based number of the failed call, reason)}``; only a lenient
        read fills it.
    """

    name: str
    description: str
    model: Model
    sides: dict[str, str]
    norm: Normalization
    data: dict
    tasks: dict[str, str | None] = field(default_factory=dict)
    steps: dict[str, list[tuple[str, int]] | None] = field(default_factory=dict)
    errors: dict[str, tuple[int, str]] = field(default_factory=dict)


class _Remarks:
    """Collects remarks."""

    def __init__(self) -> None:
        self.items: list[Remark] = []

    def add(self, where: str, text: str) -> None:
        self.items.append(Remark(where, text))

    def __len__(self) -> int:
        return len(self.items)


def _is_number(v: object) -> bool:
    return isinstance(v, (int, Decimal)) and not isinstance(v, bool)


def _is_text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _text_list(r: _Remarks, where: str, v: object) -> bool:
    if not isinstance(v, list) or not all(_is_text(x) for x in v):
        r.add(where, "list of names expected")
        return False
    return True


def _unknown_fields(r: _Remarks, where: str, obj: dict, allowed: set[str]) -> None:
    for k in obj:
        if k not in allowed:
            r.add(where, f"unknown field {k!r}")


def _obj(r: _Remarks, where: str, v: object) -> bool:
    if not isinstance(v, dict):
        r.add(where, "object expected")
        return False
    return True


def _required(r: _Remarks, where: str, obj: dict, keys: tuple[str, ...]) -> bool:
    ok = True
    for k in keys:
        if k not in obj:
            r.add(where, f"field {k!r} is missing")
            ok = False
    return ok


def _triples(r: _Remarks, where: str, v: object, size: int) -> None:
    if not isinstance(v, list) or any(
            not isinstance(t, list) or len(t) != size or not all(isinstance(x, str) for x in t) for t in v):
        r.add(where, f"list of [{', '.join(['name'] * size)}] expected")


def _numbers_map(r: _Remarks, where: str, v: object) -> None:
    if not _obj(r, where, v):
        return
    for k, x in v.items():
        if not _is_number(x):
            r.add(f"{where} {k!r}", "number expected")


def _check_steps(r: _Remarks, w: str, v: dict) -> None:
    steps = v["steps"]
    if not isinstance(steps, list):
        r.add(w, "steps must be a list")
        return
    ok = True
    total = 0
    for i, s in enumerate(steps, 1):
        ws = f"{w}, step {i}"
        if not _obj(r, ws, s):
            ok = False
            continue
        n = len(r)
        _unknown_fields(r, ws, s, STEP_FIELDS)
        _required(r, ws, s, ("text", "calls"))
        if "text" in s and not _is_text(s["text"]):
            r.add(ws, "text must be a text")
        if "calls" in s:
            if isinstance(s["calls"], int) and not isinstance(s["calls"], bool) and s["calls"] >= 0:
                total += s["calls"]
            else:
                r.add(ws, "calls must be an integer, 0 or more")
        ok = ok and len(r) == n
    if ok and isinstance(v.get("calls"), list) and total != len(v["calls"]):
        r.add(w, f"steps cover {total} calls, the variant has {len(v['calls'])}")


def _check_structure(data: object, r: _Remarks) -> None:
    """Stage 1: fields, types, JSON numbers."""
    if not _obj(r, "file", data):
        return
    _unknown_fields(r, "file", data, TOP_FIELDS)
    _required(r, "file", data, ("format", "name", "existence_axis", "entities", "kinds", "executors",
                                "instruments", "scopes", "batch_scope", "variants", "normalization"))
    if "format" in data and data["format"] != FORMAT:
        r.add("format", f"must be {FORMAT}")
    if "name" in data and not _is_text(data["name"]):
        r.add("name", "text expected")
    if "description" in data and not isinstance(data["description"], str):
        r.add("description", "text expected")
    ex = data.get("existence_axis")
    if ex is not None and _obj(r, "existence_axis", ex):
        _unknown_fields(r, "existence_axis", ex, {"name", "absent"})
        if _required(r, "existence_axis", ex, ("name", "absent")):
            if not _is_text(ex["name"]) or not _is_text(ex["absent"]):
                r.add("existence_axis", "name and absent must be texts")
    for i, e in enumerate(data.get("entities", []) if isinstance(data.get("entities"), list) else [], 1):
        w = f"entity {i}"
        if not _obj(r, w, e):
            continue
        if _is_text(e.get("name")):
            w = f"entity {e['name']}"
        _unknown_fields(r, w, e, ENTITY_FIELDS)
        if not _required(r, w, e, ("name", "axes")):
            continue
        if not _is_text(e["name"]):
            r.add(w, "name must be a text")
        if not isinstance(e["axes"], list):
            r.add(w, "axes: list expected")
            continue
        for j, a in enumerate(e["axes"], 1):
            wa = f"{w}, axis {j}"
            if not _obj(r, wa, a):
                continue
            if _is_text(a.get("name")):
                wa = f"{w}, axis {a['name']}"
            _unknown_fields(r, wa, a, AXIS_FIELDS)
            if not _required(r, wa, a, ("name", "values")):
                continue
            if not _is_text(a["name"]):
                r.add(wa, "name must be a text")
            _text_list(r, f"{wa}, values", a["values"])
            if "inherit" in a:
                _triples(r, f"{wa}, inherit", a["inherit"], 2)
    if not isinstance(data.get("entities", []), list):
        r.add("entities", "list expected")
    if isinstance(data.get("kinds"), list):
        for i, k in enumerate(data["kinds"], 1):
            w = f"kind {i}"
            if not _obj(r, w, k):
                continue
            if _is_text(k.get("name")):
                w = f"kind {k['name']}"
            _unknown_fields(r, w, k, KIND_FIELDS)
            if _required(r, w, k, ("name", "entity", "axis", "from", "to")):
                for f in ("name", "entity", "axis", "from", "to"):
                    if not _is_text(k[f]):
                        r.add(w, f"{f} must be a text")
            if "requires" in k:
                _triples(r, f"{w}, requires", k["requires"], 3)
            for f in ("check", "zero_weight"):
                if f in k and not isinstance(k[f], bool):
                    r.add(w, f"{f} must be true or false")
            if "zero_weight_note" in k and (not _is_text(k["zero_weight_note"])
                                            or k.get("zero_weight") is not True):
                r.add(w, "zero_weight_note needs zero_weight true and a text")
    elif "kinds" in data:
        r.add("kinds", "list expected")
    for f in ("executors", "instruments", "scopes"):
        if f in data:
            _text_list(r, f, data[f])
    if "batch_scope" in data and not _is_text(data["batch_scope"]):
        r.add("batch_scope", "text expected")
    if "variant_params" in data:
        _text_list(r, "variant_params", data["variant_params"])
    ns = data.get("named_slices", {})
    if _obj(r, "named_slices", ns):
        for name, spec in ns.items():
            w = f"named slice {name}"
            if not _obj(r, w, spec):
                continue
            _unknown_fields(r, w, spec, {"any"})
            groups = spec.get("any")
            if not isinstance(groups, list) or not groups:
                r.add(w, "\"any\": non-empty list of groups expected")
                continue
            for g in groups:
                if not _obj(r, w, g):
                    continue
                _unknown_fields(r, w, g, {"states", "params"})
                _triples(r, f"{w}, states", g.get("states", []), 3)
                _triples(r, f"{w}, params", g.get("params", []), 2)
                if not g.get("states") and not g.get("params"):
                    r.add(w, "empty group")
    if isinstance(data.get("variants"), list):
        for i, v in enumerate(data["variants"], 1):
            w = f"variant {i}"
            if not _obj(r, w, v):
                continue
            if _is_text(v.get("code")):
                w = f"variant {v['code']}"
            _unknown_fields(r, w, v, VARIANT_FIELDS)
            if _required(r, w, v, ("code", "title", "calls")):
                for f in ("code", "title"):
                    if not _is_text(v[f]):
                        r.add(w, f"{f} must be a text")
                _triples(r, f"{w}, calls", v["calls"], 4)
            if "side" in v and v["side"] not in SIDES:
                r.add(w, "side must be \"own\" or \"other\"")
            if "params" in v and (not isinstance(v["params"], dict)
                                  or not all(isinstance(x, str) for x in v["params"].values())):
                r.add(f"{w}, params", "object {parameter: executor} expected")
            if "entities" in v:
                _text_list(r, f"{w}, entities", v["entities"])
            if "initial" in v and (not isinstance(v["initial"], dict) or not all(
                    isinstance(a, dict) and all(isinstance(x, str) for x in a.values())
                    for a in v["initial"].values())):
                r.add(f"{w}, initial", "object {entity: {axis: value}} expected")
            if "task" in v and not _is_text(v["task"]):
                r.add(w, "task must be a text")
            if "steps" in v:
                _check_steps(r, w, v)
            if "out_of_comparison" in v and not _is_text(v["out_of_comparison"]):
                r.add(w, "out_of_comparison must be a reason text")
    elif "variants" in data:
        r.add("variants", "list expected")
    n = data.get("normalization")
    if n is not None and _obj(r, "normalization", n):
        _unknown_fields(r, "normalization", n, NORM_FIELDS)
        _required(r, "normalization", n, ("kind_costs", "executor_coefficients", "scope_coefficients",
                                          "axis_skip_prices"))
        for f in ("kind_costs", "executor_coefficients", "scope_coefficients"):
            if f in n:
                _numbers_map(r, f"normalization, {f}", n[f])
        sp = n.get("axis_skip_prices", {})
        if _obj(r, "normalization, axis_skip_prices", sp):
            for en, axes in sp.items():
                _numbers_map(r, f"normalization, axis_skip_prices, {en}", axes)
        if "batch_size" in n and not _is_number(n["batch_size"]):
            r.add("normalization, batch_size", "number expected")
        ue = n.get("uncounted_errors", {})
        if _obj(r, "normalization, uncounted_errors", ue):
            for g, texts in ue.items():
                if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
                    r.add(f"normalization, uncounted_errors, {g}", "list of texts expected")


def _build_model(data: dict) -> Model:
    """Build the model from a file that passed stage 1."""
    ex = data["existence_axis"]
    entities = [Entity(e["name"], tuple(Axis(a["name"], tuple(a["values"]),
                                             tuple(tuple(s) for s in a.get("inherit", [])))
                                        for a in e["axes"]))
                for e in data["entities"]]
    kinds = [Kind(k["name"], k["entity"], k["axis"], k["from"], k["to"], None, {}, k.get("check"),
                  tuple(tuple(t) for t in k.get("requires", [])), k.get("zero_weight"),
                  k.get("zero_weight_note"))
             for k in data["kinds"]]
    variants = [Variant(v["code"], v["title"], tuple(Call(*c) for c in v["calls"]),
                        tuple(v.get("entities", [])), dict(v.get("initial", {})),
                        v.get("out_of_comparison"), dict(v.get("params", {})))
                for v in data["variants"]]
    slices = [NamedSlice(name, tuple(SliceGroup(tuple(tuple(s) for s in g.get("states", [])),
                                                tuple(tuple(p) for p in g.get("params", [])))
                                     for g in spec["any"]))
              for name, spec in data.get("named_slices", {}).items()]
    return Model(entities, ex["name"], ex["absent"], kinds, [Executor(x) for x in data["executors"]],
                 list(data["instruments"]), list(data["scopes"]), data["batch_scope"], variants,
                 variant_params=list(data.get("variant_params", [])), named_slices=slices)


def _repeats(r: _Remarks, where: str, names: list[str], what: str) -> None:
    seen: set[str] = set()
    for n in names:
        if n in seen:
            r.add(where, f"{what} repeats: {n}")
        seen.add(n)


def _value_ok(model: Model, e: str, a: str, v: str | None = None) -> bool:
    ent = model.entity(e)
    ax = ent.axis(a) if ent else None
    return ax is not None and (v is None or v in ax.values)


def check_axes(model: Model) -> list[tuple[str, str]]:
    """Check axes: axes changed by a kind marked ``check``, in dictionary order.

    :param model: the model.
    :return: ``[(entity, axis)]``.
    :rtype: list[tuple[str, str]]
    """
    marked = {(k.entity, k.axis) for k in model.kinds if k.check}
    return [(e.name, a.name) for e in model.entities for a in e.axes if (e.name, a.name) in marked]


def _check_dictionary(model: Model, r: _Remarks) -> None:
    """Stage 2a: dictionary names and references."""
    _repeats(r, "entities", [e.name for e in model.entities], "entity")
    for e in model.entities:
        w = f"entity {e.name}"
        _repeats(r, w, [a.name for a in e.axes], "axis")
        for a in e.axes:
            if not a.values:
                r.add(f"{w}, axis {a.name}", "no values")
            _repeats(r, f"{w}, axis {a.name}", list(a.values), "value")
            for se, sa in a.inherit:
                if not _value_ok(model, se, sa):
                    r.add(f"{w}, axis {a.name}", f"unknown inherit source {se}/{sa}")
        ex = e.axis(model.existence_axis)
        if ex is not None and model.absent_value not in ex.values:
            r.add(w, f"existence axis lacks the value {model.absent_value!r}")
    _repeats(r, "kinds", [k.name for k in model.kinds], "kind")
    _repeats(r, "executors", [x.name for x in model.executors], "executor")
    _repeats(r, "instruments", model.instruments, "instrument")
    _repeats(r, "scopes", model.scopes, "scope")
    if model.batch_scope not in model.scopes:
        r.add("batch_scope", f"{model.batch_scope!r} is not among the scopes")
    for k in model.kinds:
        w = f"kind {k.name}"
        ent = model.entity(k.entity)
        ax = ent.axis(k.axis) if ent else None
        if ent is None:
            r.add(w, f"unknown entity {k.entity}")
        elif ax is None:
            r.add(w, f"unknown axis {k.entity}/{k.axis}")
        else:
            for v in (k.source, k.target):
                if v not in ax.values:
                    r.add(w, f"unknown value {k.entity}/{k.axis}={v}")
        if k.source == k.target:
            r.add(w, "from equals to")
        for re_, ra, rv in k.requires:
            if not _value_ok(model, re_, ra, rv):
                r.add(w, f"condition: unknown {re_}/{ra}={rv}")
            if (re_, ra) == (k.entity, k.axis):
                r.add(w, "condition on its own axis")
    _repeats(r, "variant_params", model.variant_params, "variant parameter")
    execs = {x.name for x in model.executors}
    for ns in model.named_slices:
        w = f"named slice {ns.name}"
        if ns.name == FINAL:
            r.add(w, f"the name {FINAL!r} is reserved for the final slice")
        for g in ns.groups:
            for e, a, v in g.states:
                if not _value_ok(model, e, a, v):
                    r.add(w, f"unknown {e}/{a}={v}")
            for p, x in g.params:
                if p not in model.variant_params:
                    r.add(w, f"unknown variant parameter {p}")
                if x not in execs:
                    r.add(w, f"unknown executor {x}")


def _check_variant_names(model: Model, r: _Remarks) -> set[str]:
    """Stage 2b: names used by the variants.

    :return: codes of variants with a remark.
    """
    bad: set[str] = set()
    _repeats(r, "variants", [v.code for v in model.variants], "variant code")
    execs = {x.name for x in model.executors}
    for v in model.variants:
        w = f"variant {v.code}"
        before = len(r)
        for p in model.variant_params:
            if p not in v.params:
                r.add(w, f"variant parameter {p} not set")
        for p, x in v.params.items():
            if p not in model.variant_params:
                r.add(w, f"unknown variant parameter {p}")
            elif x not in execs:
                r.add(w, f"parameter {p}: unknown executor {x}")
        for n in v.entities:
            if model.entity(n) is None:
                r.add(w, f"unknown entity {n}")
        for en, axes in v.initial.items():
            for an, val in axes.items():
                if not _value_ok(model, en, an, val):
                    r.add(f"{w}, initial", f"unknown {en}/{an}={val}")
        for i, c in enumerate(v.calls, 1):
            wc = f"{w}, call {i}"
            if model.kind(c.kind) is None:
                r.add(wc, f"unknown kind {c.kind}")
            if c.executor not in execs:
                r.add(wc, f"unknown executor {c.executor}")
            if c.instrument not in model.instruments:
                r.add(wc, f"unknown instrument {c.instrument}")
            if c.scope not in model.scopes:
                r.add(wc, f"unknown scope {c.scope}")
        if len(r) > before:
            bad.add(v.code)
    return bad


def _check_norm(model: Model, n: dict, r: _Remarks, strict: bool = True) -> Normalization:
    """Stage 2c: normalization against the dictionary; a strict read needs every number."""
    w = "normalization"
    costs = {k: Decimal(x) for k, x in n["kind_costs"].items()}
    ex = {k: Decimal(x) for k, x in n["executor_coefficients"].items()}
    sc = {k: Decimal(x) for k, x in n["scope_coefficients"].items()}
    prices = {(e, a): Decimal(x) for e, axes in n["axis_skip_prices"].items() for a, x in axes.items()}
    kinds = {k.name: k for k in model.kinds}
    for k in model.kinds:
        if k.zero_weight:
            if k.name in costs and costs[k.name] != 0:
                r.add(f"{w}, kind_costs", f"kind {k.name} has zero_weight, its cost must be 0 or absent")
        elif strict and k.name not in costs:
            r.add(f"{w}, kind_costs", f"kind without cost: {k.name}")
    for name, x in costs.items():
        if name not in kinds:
            r.add(f"{w}, kind_costs", f"cost of unknown kind: {name}")
        elif x < 0:
            r.add(f"{w}, kind_costs", f"kind {name}: cost below zero")
    for what, have, names in (("executor", ex, [x.name for x in model.executors]),
                              ("scope", sc, model.scopes)):
        f = f"{w}, {what}_coefficients"
        for name in names:
            if strict and name not in have:
                r.add(f, f"{what} without coefficient: {name}")
        for name, x in have.items():
            if name not in names:
                r.add(f, f"coefficient of unknown {what}: {name}")
            elif x < 0:
                r.add(f, f"{what} {name}: coefficient below zero")
    axes = check_axes(model)
    for e, a in axes:
        if strict and (e, a) not in prices:
            r.add(f"{w}, axis_skip_prices", f"check axis without skip price: {e}/{a}")
    for (e, a), x in prices.items():
        if (e, a) not in axes:
            r.add(f"{w}, axis_skip_prices", f"{e}/{a} is not a check axis")
        elif x <= 0:
            r.add(f"{w}, axis_skip_prices", f"{e}/{a}: price must be above zero")
    batch = n.get("batch_size")
    if batch is not None and Decimal(batch) <= 0:
        r.add(f"{w}, batch_size", "must be above zero")
    return Normalization(costs, ex, sc, prices, {g: list(t) for g, t in n.get("uncounted_errors", {}).items()},
                         Decimal(batch) if batch is not None else None)


def _check_runs(model: Model, skip: set[str], r: _Remarks,
                errors: dict[str, tuple[int, str]] | None = None) -> None:
    """Stage 3: run every variant step by step; the split check.

    :param errors: when given, a run error goes here as ``{code: (call number, reason)}`` instead
        of a remark.
    """
    for v in model.variants:
        if v.code in skip:
            continue
        try:
            run_variant(model, v)
        except TransitionError as exc:
            if errors is None:
                r.add("", str(exc))
            else:
                errors[v.code] = (exc.number, exc.reason)
    for a, b in duplicate_kinds(model):
        r.add("kinds", f"same change of state: {a} = {b}")
    for k, chain in decomposable_kinds(model):
        r.add("kinds", f"kind {k} repeats the chain {' + '.join(chain)}")


def _require_tasks(data: object, r: _Remarks) -> None:
    """Stage 1, strict read only: every variant of a file has a task.

    A project from the database and an edit are read leniently, so a project saved before the
    task became required still opens and its variants without a task stay without a pair.
    """
    if not isinstance(data, dict) or not isinstance(data.get("variants"), list):
        return
    for v in data["variants"]:
        if not isinstance(v, dict) or "task" in v:
            continue
        code = v.get("code")
        if _is_text(code):
            where = f"variant {code}"
        else:
            where = f"variant {data['variants'].index(v) + 1}"
        r.add(where, "task is required")


def read_project(data: object, strict: bool = True) -> tuple[Project | None, list[Remark]]:
    """Check a parsed project file and build the project.

    :param data: parsed JSON, numbers as ``int`` or ``Decimal``.
    :param strict: ``False`` for the lenient read: a missing normalization number is no remark,
        a run error goes to ``Project.errors``.
    :return: ``(project, [])`` or ``(None, remarks)``.
    :rtype: tuple[Project | None, list[Remark]]
    """
    r = _Remarks()
    _check_structure(data, r)
    if strict:
        _require_tasks(data, r)
    if r:
        return None, r.items
    model = _build_model(data)
    _check_dictionary(model, r)
    dict_ok = not r
    bad = _check_variant_names(model, r)
    norm = _check_norm(model, data["normalization"], r, strict) if dict_ok else None
    errors: dict[str, tuple[int, str]] = {}
    if dict_ok:
        _check_runs(model, bad, r, None if strict else errors)
    if r:
        return None, r.items
    sides = {v["code"]: v.get("side", "own") for v in data["variants"]}
    tasks = {v["code"]: v.get("task") for v in data["variants"]}
    steps = {v["code"]: [(s["text"], s["calls"]) for s in v["steps"]] if "steps" in v else None
             for v in data["variants"]}
    return Project(data["name"], data.get("description", ""), model, sides, norm, data, tasks,
                   steps, errors), []


def parse_text(text: str) -> tuple[Project | None, list[Remark]]:
    """Read a project from JSON text.

    :param text: file contents.
    :return: ``(project, [])`` or ``(None, remarks)``.
    :rtype: tuple[Project | None, list[Remark]]
    """
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        return None, [Remark("file", f"not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}")]
    return read_project(data)


def load_file(path: Path) -> tuple[Project | None, list[Remark]]:
    """Read a project file.

    :param path: path to the file.
    :return: ``(project, [])`` or ``(None, remarks)``.
    :rtype: tuple[Project | None, list[Remark]]
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [Remark("file", f"cannot read: {exc}")]
    return parse_text(text)
