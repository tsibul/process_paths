# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Model dictionaries and their loading from JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


class ModelError(ValueError):
    """Raised when the model breaks a rule of the format."""


@dataclass(frozen=True)
class Axis:
    """One independent attribute of an entity.

    :ivar name: axis name, unique within the entity.
    :ivar values: allowed values; the first one is the initial value.
    :ivar inherit: ``(entity, axis)`` sources; when the entity is created, the axis
        takes the value of the first source that has a value in the slice.
    """

    name: str
    values: tuple[str, ...]
    inherit: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Entity:
    """Something that has a state.

    :ivar name: entity name.
    :ivar axes: state axes in display order.
    """

    name: str
    axes: tuple[Axis, ...]

    def axis(self, name: str) -> Axis | None:
        """Return the axis with the given name.

        :param name: axis name.
        :return: the axis or ``None``.
        :rtype: Axis | None
        """
        return next((a for a in self.axes if a.name == name), None)


@dataclass(frozen=True)
class Kind:
    """A transition kind: a change of one axis of one entity from one value to another.

    :ivar name: kind name.
    :ivar entity: entity name.
    :ivar axis: axis name.
    :ivar source: value before the transition.
    :ivar target: value after the transition.
    :ivar cost: optional cost of the kind.
    :ivar instrument_costs: optional cost of the kind per instrument.
    :ivar check: optional flag: the kind is a check.
    :ivar requires: condition: ``(entity, axis, value)`` triples that must all hold
        in the current slice for the transition to be allowed.
    :ivar zero_weight: optional flag: the transition stays in the path but does not
        count in the labour estimate.
    :ivar zero_weight_note: optional note to the zero weight.
    """

    name: str
    entity: str
    axis: str
    source: str
    target: str
    cost: Decimal | None = None
    instrument_costs: dict[str, Decimal] = field(default_factory=dict)
    check: bool | None = None
    requires: tuple[tuple[str, str, str], ...] = ()
    zero_weight: bool | None = None
    zero_weight_note: str | None = None

    @property
    def quadruple(self) -> tuple[str, str, str, str]:
        """:return: ``(entity, axis, source, target)``.
        :rtype: tuple[str, str, str, str]
        """
        return self.entity, self.axis, self.source, self.target


@dataclass(frozen=True)
class Executor:
    """Who performs a transition.

    :ivar name: executor name.
    :ivar factor: optional cost factor.
    """

    name: str
    factor: Decimal | None = None


@dataclass(frozen=True)
class Call:
    """A transition in a variant: a kind with an executor, an instrument and a scope.

    :ivar kind: kind name.
    :ivar executor: executor name.
    :ivar instrument: instrument name.
    :ivar scope: scope name: once per document or once per batch of documents.
    """

    kind: str
    executor: str
    instrument: str
    scope: str


@dataclass(frozen=True)
class Variant:
    """A linear path variant.

    :ivar code: short code, unique.
    :ivar title: title.
    :ivar calls: transitions in order.
    :ivar entities: entities of the variant; empty means the entities touched by the calls.
    :ivar initial: initial slice deviations, ``{entity: {axis: value}}``.
    :ivar out_of_comparison: optional reason why the variant is not compared with
        the competitors.
    :ivar params: variant parameters, ``{parameter: executor}``.
    """

    code: str
    title: str
    calls: tuple[Call, ...]
    entities: tuple[str, ...] = ()
    initial: dict[str, dict[str, str]] = field(default_factory=dict)
    out_of_comparison: str | None = None
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SliceGroup:
    """One group of a named slice condition; all its terms must hold ("and").

    :ivar states: ``(entity, axis, value)`` that must hold in the slice.
    :ivar params: ``(parameter, executor)`` that must hold in the variant.
    """

    states: tuple[tuple[str, str, str], ...] = ()
    params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class NamedSlice:
    """A named slice given by a condition: the first slice of a variant where any group holds.

    :ivar name: slice name.
    :ivar groups: the groups ("or" between them).
    """

    name: str
    groups: tuple[SliceGroup, ...]


@dataclass
class Model:
    """The whole model: dictionaries, variants and texts.

    :ivar entities: entities in order.
    :ivar existence_axis: name of the existence axis.
    :ivar absent_value: value of the existence axis meaning "does not exist".
    :ivar kinds: transition kinds in order.
    :ivar executors: executors in order.
    :ivar instruments: instruments in order.
    :ivar scopes: scopes in order.
    :ivar batch_scope: the scope meaning "once per batch".
    :ivar variants: variants in order.
    :ivar texts: free texts used by the Markdown output.
    :ivar forbidden: forbidden word stems.
    :ivar forbidden_exceptions: phrases removed before the forbidden word search.
    :ivar variant_params: names of the variant parameters; each variant sets every one.
    :ivar named_slices: named slices given by a condition, in file order.
    """

    entities: list[Entity]
    existence_axis: str
    absent_value: str
    kinds: list[Kind]
    executors: list[Executor]
    instruments: list[str]
    scopes: list[str]
    batch_scope: str
    variants: list[Variant]
    texts: dict[str, str] = field(default_factory=dict)
    forbidden: list[str] = field(default_factory=list)
    forbidden_exceptions: list[str] = field(default_factory=list)
    variant_params: list[str] = field(default_factory=list)
    named_slices: list[NamedSlice] = field(default_factory=list)

    def entity(self, name: str) -> Entity | None:
        """:param name: entity name.
        :return: the entity or ``None``.
        :rtype: Entity | None
        """
        return next((e for e in self.entities if e.name == name), None)

    def kind(self, name: str) -> Kind | None:
        """:param name: kind name.
        :return: the kind or ``None``.
        :rtype: Kind | None
        """
        return next((k for k in self.kinds if k.name == name), None)

    def executor(self, name: str) -> Executor | None:
        """:param name: executor name.
        :return: the executor or ``None``.
        :rtype: Executor | None
        """
        return next((x for x in self.executors if x.name == name), None)


def _dec(value: object, where: str) -> Decimal | None:
    """Convert an optional JSON number to ``Decimal``.

    :param value: parsed JSON value.
    :param where: place for the error message.
    :return: the number or ``None``.
    :rtype: Decimal | None
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ModelError(f"{where}: number expected")
    return Decimal(value)


def _parse_named_slices(data: object) -> list[NamedSlice]:
    """Build named slices from parsed JSON.

    Format: ``{name: {"any": [{"states": [[entity, axis, value], …],
    "params": [[parameter, executor], …]}, …]}}``; a group needs at least one term.

    :param data: parsed JSON.
    :return: the named slices in file order.
    :rtype: list[NamedSlice]
    """
    if not isinstance(data, dict):
        raise ModelError("named_slices: object of named slices expected")
    result = []
    for name, spec in data.items():
        where = f"named slice {name!r}"
        if not isinstance(spec, dict) or not isinstance(spec.get("any"), list) or not spec["any"]:
            raise ModelError(f"{where}: expected {{\"any\": [group, …]}}")
        groups = []
        for g in spec["any"]:
            if not isinstance(g, dict):
                raise ModelError(f"{where}: group must be an object")
            states, params = g.get("states", []), g.get("params", [])
            if not isinstance(states, list) or any(not isinstance(s, list) or len(s) != 3 for s in states):
                raise ModelError(f"{where}: states must be [[entity, axis, value], …]")
            if not isinstance(params, list) or any(not isinstance(c, list) or len(c) != 2 for c in params):
                raise ModelError(f"{where}: params must be [[parameter, executor], …]")
            if not states and not params:
                raise ModelError(f"{where}: empty group")
            groups.append(SliceGroup(tuple(tuple(s) for s in states), tuple(tuple(c) for c in params)))
        result.append(NamedSlice(name, tuple(groups)))
    return result


def parse_model(data: dict) -> Model:
    """Build a model from parsed JSON and validate it.

    :param data: parsed JSON (numbers as ``Decimal``).
    :return: the validated model.
    :rtype: Model
    """
    try:
        ex = data["existence_axis"]
        entities = [
            Entity(e["name"], tuple(
                Axis(a["name"], tuple(a["values"]), tuple(tuple(s) for s in a.get("inherit", [])))
                for a in e["axes"]))
            for e in data["entities"]
        ]
        kinds = [
            Kind(k["name"], k["entity"], k["axis"], k["from"], k["to"],
                 _dec(k.get("cost"), f"kind {k['name']}: cost"),
                 {i: _dec(c, f"kind {k['name']}: instrument cost") for i, c in
                  k.get("instrument_costs", {}).items()},
                 k.get("check"),
                 tuple(tuple(r) for r in k.get("requires", [])),
                 k.get("zero_weight"), k.get("zero_weight_note"))
            for k in data["kinds"]
        ]
        executors = [
            Executor(x, None) if isinstance(x, str) else
            Executor(x["name"], _dec(x.get("factor"), f"executor {x['name']}: factor"))
            for x in data["executors"]
        ]
        variants = [
            Variant(v["code"], v["title"], tuple(Call(*c) for c in v["calls"]),
                    tuple(v.get("entities", [])), v.get("initial", {}),
                    v.get("out_of_comparison"), dict(v.get("params", {})))
            for v in data["variants"]
        ]
        model = Model(entities, ex["name"], ex["absent"], kinds, executors,
                      list(data["instruments"]), list(data["scopes"]),
                      data["batch_scope"], variants, dict(data.get("texts", {})),
                      list(data.get("forbidden_words", [])),
                      list(data.get("forbidden_exceptions", [])),
                      list(data.get("variant_params", [])),
                      _parse_named_slices(data.get("named_slices", {})))
    except (KeyError, TypeError) as exc:
        raise ModelError(f"malformed model: {exc!r}") from exc
    validate_model(model)
    return model


def load_model(path: Path) -> Model:
    """Read a model from a JSON file.

    :param path: path to the JSON file.
    :return: the validated model.
    :rtype: Model
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_model(json.loads(text, parse_float=Decimal))


def _unique(names: list[str], what: str) -> None:
    """Raise if a name repeats.

    :param names: names to check.
    :param what: what the names are, for the error message.
    """
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ModelError(f"{what} repeats: {n}")
        seen.add(n)


def validate_model(model: Model) -> None:
    """Check the dictionaries and the names used in the variants.

    :param model: the model.
    :raises ModelError: on the first broken rule.
    """
    _unique([e.name for e in model.entities], "entity")
    for e in model.entities:
        _unique([a.name for a in e.axes], f"axis of {e.name}")
        for a in e.axes:
            if not a.values:
                raise ModelError(f"axis {e.name}/{a.name} has no values")
            _unique(list(a.values), f"value of {e.name}/{a.name}")
            for se, sa in a.inherit:
                src = model.entity(se)
                if src is None or src.axis(sa) is None:
                    raise ModelError(f"axis {e.name}/{a.name}: unknown inherit source {se}/{sa}")
        ex = e.axis(model.existence_axis)
        if ex is not None and model.absent_value not in ex.values:
            raise ModelError(f"existence axis of {e.name} lacks {model.absent_value!r}")
    _unique([k.name for k in model.kinds], "kind")
    _unique([x.name for x in model.executors], "executor")
    _unique(model.instruments, "instrument")
    _unique(model.scopes, "scope")
    if model.batch_scope not in model.scopes:
        raise ModelError(f"batch scope {model.batch_scope!r} is not among the scopes")
    for k in model.kinds:
        ent = model.entity(k.entity)
        if ent is None:
            raise ModelError(f"kind {k.name}: unknown entity {k.entity}")
        ax = ent.axis(k.axis)
        if ax is None:
            raise ModelError(f"kind {k.name}: unknown axis {k.axis}")
        for v in (k.source, k.target):
            if v not in ax.values:
                raise ModelError(f"kind {k.name}: unknown value {v}")
        if k.source == k.target:
            raise ModelError(f"kind {k.name}: from equals to")
        for i in k.instrument_costs:
            if i not in model.instruments:
                raise ModelError(f"kind {k.name}: unknown instrument {i}")
        if k.check is not None and not isinstance(k.check, bool):
            raise ModelError(f"kind {k.name}: check must be true or false")
        if k.zero_weight is not None and not isinstance(k.zero_weight, bool):
            raise ModelError(f"kind {k.name}: zero_weight must be true or false")
        if k.zero_weight_note is not None and (
                not isinstance(k.zero_weight_note, str) or not k.zero_weight_note.strip()
                or k.zero_weight is not True):
            raise ModelError(f"kind {k.name}: zero_weight_note needs zero_weight true and text")
        for r in k.requires:
            if len(r) != 3:
                raise ModelError(f"kind {k.name}: condition must be [entity, axis, value]")
            re_, ra, rv = r
            rent = model.entity(re_)
            rax = rent.axis(ra) if rent else None
            if rax is None or rv not in rax.values:
                raise ModelError(f"kind {k.name}: condition: unknown {re_}/{ra}={rv}")
            if (re_, ra) == (k.entity, k.axis):
                raise ModelError(f"kind {k.name}: condition on its own axis")
    _unique(model.variant_params, "variant parameter")
    _unique([ns.name for ns in model.named_slices], "named slice")
    for ns in model.named_slices:
        for g in ns.groups:
            for e, a, val in g.states:
                ent = model.entity(e)
                ax = ent.axis(a) if ent else None
                if ax is None or val not in ax.values:
                    raise ModelError(f"named slice {ns.name!r}: unknown {e}/{a}={val}")
            for prm, x in g.params:
                if prm not in model.variant_params:
                    raise ModelError(f"named slice {ns.name!r}: unknown variant parameter {prm}")
                if model.executor(x) is None:
                    raise ModelError(f"named slice {ns.name!r}: unknown executor {x}")
    _unique([v.code for v in model.variants], "variant code")
    for v in model.variants:
        for prm in model.variant_params:
            if prm not in v.params:
                raise ModelError(f"variant {v.code}: variant parameter {prm} not set")
        for prm, x in v.params.items():
            if prm not in model.variant_params:
                raise ModelError(f"variant {v.code}: unknown variant parameter {prm}")
            if model.executor(x) is None:
                raise ModelError(f"variant {v.code}: parameter {prm}: unknown executor {x}")
        if v.out_of_comparison is not None and (
                not isinstance(v.out_of_comparison, str) or not v.out_of_comparison.strip()):
            raise ModelError(f"variant {v.code}: out_of_comparison must be a reason text")
        for n in v.entities:
            if model.entity(n) is None:
                raise ModelError(f"variant {v.code}: unknown entity {n}")
        for en, axes in v.initial.items():
            ent = model.entity(en)
            if ent is None:
                raise ModelError(f"variant {v.code}: initial: unknown entity {en}")
            for an, val in axes.items():
                ax = ent.axis(an)
                if ax is None or val not in ax.values:
                    raise ModelError(f"variant {v.code}: initial: unknown {en}/{an}={val}")
        for i, c in enumerate(v.calls, 1):
            where = f"variant {v.code}, call {i}"
            if model.kind(c.kind) is None:
                raise ModelError(f"{where}: unknown kind {c.kind}")
            if model.executor(c.executor) is None:
                raise ModelError(f"{where}: unknown executor {c.executor}")
            if c.instrument not in model.instruments:
                raise ModelError(f"{where}: unknown instrument {c.instrument}")
            if c.scope not in model.scopes:
                raise ModelError(f"{where}: unknown scope {c.scope}")
