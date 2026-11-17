# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Slices and transitions: running a variant."""

from __future__ import annotations

from .model import Model, ModelError, Variant

#: A slice: ``{(entity, axis): value}``; ``None`` for an axis of a non-existing entity.
Slice = dict[tuple[str, str], str | None]


class TransitionError(ModelError):
    """Raised when a transition cannot be applied to the current slice.

    :ivar number: 1-based number of the call that failed, or ``None``.
    :ivar reason: what is wrong, without the place.
    """

    def __init__(self, text: str, number: int | None = None, reason: str | None = None) -> None:
        super().__init__(text)
        self.number = number
        self.reason = text if reason is None else reason


def variant_entities(model: Model, variant: Variant) -> list[str]:
    """Return the entities of a variant in dictionary order.

    :param model: the model.
    :param variant: the variant.
    :return: the listed entities, or the entities touched by the calls.
    :rtype: list[str]
    """
    if variant.entities:
        names = set(variant.entities)
    else:
        names = {model.kind(c.kind).entity for c in variant.calls}
    return [e.name for e in model.entities if e.name in names]


def _absent(model: Model, s: Slice, entity: str) -> bool:
    """:return: whether the entity does not exist in the slice.
    :rtype: bool
    """
    return s.get((entity, model.existence_axis)) == model.absent_value


def _fill(model: Model, s: Slice, entity: str, preset: dict[str, str]) -> None:
    """Give the non-existence axes of an existing entity their initial values.

    :param model: the model.
    :param s: the slice, changed in place.
    :param entity: entity name.
    :param preset: values given explicitly, ``{axis: value}``.
    """
    for ax in model.entity(entity).axes:
        if ax.name == model.existence_axis:
            continue
        value = preset.get(ax.name)
        if value is None:
            for src in ax.inherit:
                inherited = s.get(src)
                if inherited is not None and inherited in ax.values:
                    value = inherited
                    break
        s[(entity, ax.name)] = value if value is not None else ax.values[0]


def initial_slice(model: Model, variant: Variant) -> Slice:
    """Build the first slice of a variant.

    :param model: the model.
    :param variant: the variant.
    :return: the initial slice.
    :rtype: Slice
    """
    s: Slice = {}
    for name in variant_entities(model, variant):
        preset = variant.initial.get(name, {})
        ent = model.entity(name)
        ex = ent.axis(model.existence_axis)
        if ex is not None:
            s[(name, ex.name)] = preset.get(ex.name, ex.values[0])
        if _absent(model, s, name):
            for ax in ent.axes:
                if ax.name != model.existence_axis:
                    s[(name, ax.name)] = None
        else:
            _fill(model, s, name, preset)
    return s


def apply(model: Model, s: Slice, variant: Variant, number: int) -> Slice:
    """Apply one call of a variant to a slice.

    :param model: the model.
    :param s: the current slice (not changed).
    :param variant: the variant.
    :param number: 1-based call number.
    :return: the next slice.
    :rtype: Slice
    :raises TransitionError: when the current value is not the kind's "from".
    """
    call = variant.calls[number - 1]
    where = f"variant {variant.code}, call {number} ({call.kind})"

    def fail(reason: str) -> TransitionError:
        return TransitionError(f"{where}: {reason}", number, reason)

    kind = model.kind(call.kind)
    if kind is None:
        raise fail("unknown kind")
    key = (kind.entity, kind.axis)
    if key not in s:
        raise fail(f"entity {kind.entity} is not in the variant")
    if s[key] != kind.source:
        raise fail(f"{kind.entity}/{kind.axis} is {s[key]!r}, expected {kind.source!r}")
    for re_, ra, rv in kind.requires:
        if s.get((re_, ra)) != rv:
            raise fail(f"condition not met: {re_}/{ra} is {s.get((re_, ra))!r}, required {rv!r}")
    nxt = dict(s)
    nxt[key] = kind.target
    if kind.axis == model.existence_axis:
        if kind.target == model.absent_value:
            for ax in model.entity(kind.entity).axes:
                if ax.name != model.existence_axis:
                    nxt[(kind.entity, ax.name)] = None
        elif kind.source == model.absent_value:
            _fill(model, nxt, kind.entity, {})
    return nxt


def run_variant(model: Model, variant: Variant) -> list[Slice]:
    """Compute all slices of a variant.

    :param model: the model.
    :param variant: the variant.
    :return: ``len(calls) + 1`` slices, the initial one first.
    :rtype: list[Slice]
    """
    slices = [initial_slice(model, variant)]
    for i in range(1, len(variant.calls) + 1):
        slices.append(apply(model, slices[-1], variant, i))
    return slices


def changed_keys(before: Slice, after: Slice) -> set[tuple[str, str]]:
    """Return the axes whose value differs between two slices.

    On a creation these are the existence axis and every axis that got its initial value.

    :param before: slice before.
    :param after: slice after.
    :return: ``{(entity, axis)}``.
    :rtype: set[tuple[str, str]]
    """
    return {k for k in after if after[k] != before.get(k)}
