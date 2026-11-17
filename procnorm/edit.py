# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Edits of a loaded project: pure functions over the parsed file (``Project.data``).

An edit takes ``data`` and returns a new ``data`` or refuses; the argument is never changed. The new
``data`` is checked by the same lenient read as a file from the database, so an edited variant equals
the same variant read from a file.
"""

import copy
import re
from decimal import Decimal

from procnorm.project import FINAL, Remark, read_project

NUMBER_TABLES = ("kind_costs", "executor_coefficients", "scope_coefficients", "axis_skip_prices")

_NUMBER = re.compile(r"-?(\d+\.?\d*|\.\d+)")


def _parse(text: str) -> int | Decimal | None:
    """Read a typed number as the file reader does: whole numbers as ``int``, others as ``Decimal``."""
    s = text.strip().replace(",", ".")
    if not _NUMBER.fullmatch(s):
        return None
    return Decimal(s) if "." in s else int(s)


def set_number(data: dict, table: str, key: str | tuple[str, str], text: str
               ) -> tuple[dict | None, list[Remark]]:
    """Set, change or clear one number of the normalization.

    :param data: the parsed project file; not changed.
    :param table: ``kind_costs``, ``executor_coefficients``, ``scope_coefficients`` or
        ``axis_skip_prices``.
    :param key: the name (kind, executor, scope), or ``(entity, check axis)`` for ``axis_skip_prices``.
    :param text: the typed number, comma or point; empty text removes the number ("not set").
    :return: ``(new data, [])``, or ``(None, remarks)`` when the edit is refused.
    :rtype: tuple[dict | None, list[Remark]]
    """
    where = f"normalization, {table}"

    def refuse(reason: str) -> tuple[None, list[Remark]]:
        return None, [Remark(where, reason)]

    if table not in NUMBER_TABLES:
        return refuse(f"unknown table: {table}")
    pair = table == "axis_skip_prices"
    if pair != isinstance(key, tuple) or (pair and len(key) != 2):
        return refuse("key must be (entity, axis)" if pair else "key must be a name")
    label = " / ".join(key) if pair else key
    if table == "kind_costs" and any(
            k.get("name") == key and k.get("zero_weight") is True for k in data.get("kinds", [])):
        return refuse(f"kind {label} has zero weight, its cost is always 0")

    number = None
    if text.strip():
        number = _parse(text)
        if number is None:
            return refuse(f"{label}: not a number: {text.strip()}")
        if pair and number <= 0:
            return refuse(f"{label}: price must be above zero")
        if number < 0:
            return refuse(f"{label}: must not be below zero")

    new = copy.deepcopy(data)
    norm = new["normalization"]
    if pair:
        entity, axis = key
        if number is None:
            prices = norm.get(table, {}).get(entity, {})
            prices.pop(axis, None)
            if not prices:
                norm.get(table, {}).pop(entity, None)
        else:
            norm.setdefault(table, {}).setdefault(entity, {})[axis] = number
    elif number is None:
        norm.get(table, {}).pop(key, None)
    else:
        norm.setdefault(table, {})[key] = number

    project, remarks = read_project(new, strict=False)
    if project is None:
        return None, remarks
    return new, []


# ---------- transitions and variants ----------

def _variant(new: dict, code: str) -> dict | None:
    return next((v for v in new["variants"] if v["code"] == code), None)


def _checked(new: dict) -> tuple[dict | None, list[Remark]]:
    project, remarks = read_project(new, strict=False)
    if project is None:
        return None, remarks
    return new, []


def _step_at(steps: list[dict], index: int) -> tuple[int, int]:
    """The step that holds the call with the 0-based ``index``, and the call's offset in the step."""
    start = 0
    for k, s in enumerate(steps):
        if index < start + s["calls"]:
            return k, index - start
        start += s["calls"]
    raise IndexError(index)


def add_call(data: dict, code: str, after: int, call: list[str] | tuple[str, ...],
             step: int | None = None) -> tuple[dict | None, list[Remark]]:
    """Add a transition to a variant.

    The transition joins the step of the row it is added under; ``step`` names the step explicitly
    (needed for an empty step, which has no row).

    :param data: the parsed project file; not changed.
    :param code: the variant code.
    :param after: 1-based number of the transition the new one goes under; 0 puts it first.
    :param call: ``(kind, executor, instrument, scope)``.
    :param step: 0-based step index; ``None`` takes the step of transition ``after`` (the first
        step for ``after`` 0).
    :return: ``(new data, [])``, or ``(None, remarks)`` when the edit is refused.
    :rtype: tuple[dict | None, list[Remark]]
    """
    where = f"variant {code}"
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(where, "no such variant")]
    n = len(v["calls"])
    if not isinstance(after, int) or not 0 <= after <= n:
        return None, [Remark(where, f"cannot add after transition {after}, the variant has {n}")]
    if len(call) != 4:
        return None, [Remark(where, "a transition is (kind, executor, instrument, scope)")]
    if "steps" in v:
        steps = v["steps"]
        if step is None:
            step = 0 if after == 0 else _step_at(steps, after - 1)[0]
        elif not isinstance(step, int) or not 0 <= step < len(steps):
            return None, [Remark(where, f"no such step: {step}")]
        else:
            start = sum(s["calls"] for s in steps[:step])
            if not start <= after <= start + steps[step]["calls"]:
                return None, [Remark(where, f"transition {after} is not at step {step + 1}")]
        steps[step]["calls"] += 1
    v["calls"].insert(after, list(call))
    return _checked(new)


def remove_call(data: dict, code: str, number: int) -> tuple[dict | None, list[Remark]]:
    """Remove a transition; its step keeps its place, with one call less.

    :param number: 1-based number of the transition.
    """
    where = f"variant {code}"
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(where, "no such variant")]
    if not isinstance(number, int) or not 1 <= number <= len(v["calls"]):
        return None, [Remark(where, f"no such transition: {number}")]
    if "steps" in v:
        v["steps"][_step_at(v["steps"], number - 1)[0]]["calls"] -= 1
    del v["calls"][number - 1]
    return _checked(new)


def move_call(data: dict, code: str, number: int, delta: int) -> tuple[dict | None, list[Remark]]:
    """Move a transition one place up (``delta`` -1) or down (+1).

    Inside a step the neighbours swap. A first call of a step moved up becomes the last of the
    previous step, a last call moved down becomes the first of the next step: the order of the
    transitions stays, the step counts change.

    :param number: 1-based number of the transition.
    """
    where = f"variant {code}"
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(where, "no such variant")]
    calls = v["calls"]
    if not isinstance(number, int) or not 1 <= number <= len(calls):
        return None, [Remark(where, f"no such transition: {number}")]
    if delta not in (-1, 1):
        return None, [Remark(where, "move by -1 or +1")]
    i = number - 1
    refuse = (None, [Remark(where, f"transition {number} cannot move {'up' if delta < 0 else 'down'}")])
    if "steps" not in v:
        if not 0 <= i + delta < len(calls):
            return refuse
        calls[i], calls[i + delta] = calls[i + delta], calls[i]
        return _checked(new)
    steps = v["steps"]
    k, offset = _step_at(steps, i)
    inside = 0 < offset if delta < 0 else offset < steps[k]["calls"] - 1
    if inside:
        calls[i], calls[i + delta] = calls[i + delta], calls[i]
    elif 0 <= k + delta < len(steps):
        steps[k]["calls"] -= 1
        steps[k + delta]["calls"] += 1
    else:
        return refuse
    return _checked(new)


def copy_code(code: str) -> str:
    """The code of a copy of the variant ``code``."""
    return f"{code} (copy)"


def copy_variant(data: dict, code: str) -> tuple[dict | None, list[Remark]]:
    """Copy a variant under the code ``<code> (copy)``, right after the original; all else is kept
    (title, side, task, calls, steps). A copy whose code is taken is refused."""
    where = f"variant {code}"
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(where, "no such variant")]
    name = copy_code(code)
    if _variant(new, name) is not None:
        return None, [Remark(where, f"variant code is taken: {name}")]
    twin = copy.deepcopy(v)
    twin["code"] = name
    new["variants"].insert(new["variants"].index(v) + 1, twin)
    return _checked(new)


def delete_variant(data: dict, code: str) -> tuple[dict | None, list[Remark]]:
    """Delete a variant."""
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(f"variant {code}", "no such variant")]
    new["variants"].remove(v)
    return _checked(new)


def rename_variant(data: dict, code: str, new_code: str, title: str
                   ) -> tuple[dict | None, list[Remark]]:
    """Change the code and the title of a variant. Empty text and a taken code are refused."""
    where = f"variant {code}"
    new = copy.deepcopy(data)
    v = _variant(new, code)
    if v is None:
        return None, [Remark(where, "no such variant")]
    new_code, title = new_code.strip(), title.strip()
    if not new_code or not title:
        return None, [Remark(where, "code and title must not be empty")]
    if new_code != code and _variant(new, new_code) is not None:
        return None, [Remark(where, f"variant code is taken: {new_code}")]
    v["code"], v["title"] = new_code, title
    return _checked(new)


# ---------- dictionary words ----------

WORDS = ("entity", "axis", "value", "kind", "executor", "instrument", "scope", "variant_param",
         "named_slice")

_LISTS = {"executor": "executors", "instrument": "instruments", "scope": "scopes",
          "variant_param": "variant_params"}
_CALL_FIELD = {"kind": 0, "executor": 1, "instrument": 2, "scope": 3}
_COEFFICIENTS = {"kind": "kind_costs", "executor": "executor_coefficients",
                 "scope": "scope_coefficients"}


def _rekey(d: dict, old: str, new: str) -> dict:
    """The dict with the key ``old`` named ``new``, in the same order."""
    return {(new if k == old else k): v for k, v in d.items()}


def _swap(items: list, old: str, new: str) -> None:
    items[:] = [new if x == old else x for x in items]


def _entity(new: dict, name: str) -> dict | None:
    return next((e for e in new["entities"] if e["name"] == name), None)


def _axis(new: dict, entity: str, axis: str) -> dict | None:
    e = _entity(new, entity)
    return next((a for a in e["axes"] if a["name"] == axis), None) if e else None


def _states(new: dict):
    """Every ``[entity, axis, value]`` triple: kind conditions and named slice conditions."""
    for k in new["kinds"]:
        yield from k.get("requires", [])
    for spec in new.get("named_slices", {}).values():
        for g in spec["any"]:
            yield from g.get("states", [])


def _rename_entity(new: dict, old: str, name: str) -> str | None:
    if _entity(new, old) is None:
        return "no such entity"
    if name == old:
        return None
    if _entity(new, name) is not None:
        return f"entity name is taken: {name}"
    for e in new["entities"]:
        if e["name"] == old:
            e["name"] = name
        for a in e["axes"]:
            for src in a.get("inherit", []):
                if src[0] == old:
                    src[0] = name
    for k in new["kinds"]:
        if k["entity"] == old:
            k["entity"] = name
    for t in _states(new):
        if t[0] == old:
            t[0] = name
    for v in new["variants"]:
        if "entities" in v:
            _swap(v["entities"], old, name)
        if "initial" in v:
            v["initial"] = _rekey(v["initial"], old, name)
    norm = new["normalization"]
    if "axis_skip_prices" in norm:
        norm["axis_skip_prices"] = _rekey(norm["axis_skip_prices"], old, name)
    return None


def _rename_axis(new: dict, old: tuple[str, str], name: str) -> str | None:
    entity, axis = old
    if _axis(new, entity, axis) is None:
        return "no such axis"
    if name == axis:
        return None
    existence = new["existence_axis"]
    if axis == existence["name"]:
        # one word for every entity that appears or disappears
        targets = {e["name"] for e in new["entities"] if any(a["name"] == axis for a in e["axes"])}
        if any(a["name"] == name for e in new["entities"] for a in e["axes"]):
            return f"axis name is taken: {name}"
        existence["name"] = name
    else:
        targets = {entity}
        if _axis(new, entity, name) is not None:
            return f"axis name is taken: {name}"
        if name == existence["name"]:
            return f"the name {name!r} is the existence axis"
    for e in new["entities"]:
        for a in e["axes"]:
            if e["name"] in targets and a["name"] == axis:
                a["name"] = name
            for src in a.get("inherit", []):
                if src[0] in targets and src[1] == axis:
                    src[1] = name
    for k in new["kinds"]:
        if k["entity"] in targets and k["axis"] == axis:
            k["axis"] = name
    for t in _states(new):
        if t[0] in targets and t[1] == axis:
            t[1] = name
    for v in new["variants"]:
        for e, axes in v.get("initial", {}).items():
            if e in targets:
                v["initial"][e] = _rekey(axes, axis, name)
    prices = new["normalization"].get("axis_skip_prices", {})
    for e, axes in prices.items():
        if e in targets:
            prices[e] = _rekey(axes, axis, name)
    return None


def _value_axes(new: dict, entity: str, axis: str, value: str) -> set[tuple[str, str]]:
    """The axes where ``value`` is one word with the value of ``entity/axis``.

    The value "does not exist" is one for all existence axes; an axis that inherits takes the value
    of its source by name, so the value is one along the inherit links.
    """
    existence = new["existence_axis"]
    if axis == existence["name"] and value == existence["absent"]:
        found = {(e["name"], a["name"]) for e in new["entities"] for a in e["axes"]
                 if a["name"] == axis}
    else:
        found = {(entity, axis)}
    links = [((e["name"], a["name"]), tuple(src)) for e in new["entities"] for a in e["axes"]
             for src in a.get("inherit", [])]
    grown = True
    while grown:
        grown = False
        for x, y in links:
            for p, q in ((x, y), (y, x)):
                if p in found and q not in found:
                    ax = _axis(new, *q)
                    if ax is not None and value in ax["values"]:
                        found.add(q)
                        grown = True
    return found


def _rename_value(new: dict, old: tuple[str, str, str], name: str) -> str | None:
    entity, axis, value = old
    ax = _axis(new, entity, axis)
    if ax is None or value not in ax["values"]:
        return "no such value"
    if name == value:
        return None
    targets = _value_axes(new, entity, axis, value)
    for e, a in sorted(targets):
        if name in _axis(new, e, a)["values"]:
            return f"value is taken: {e}/{a}={name}"
    existence = new["existence_axis"]
    if axis == existence["name"] and value == existence["absent"]:
        existence["absent"] = name
    for e, a in targets:
        _swap(_axis(new, e, a)["values"], value, name)
    for k in new["kinds"]:
        if (k["entity"], k["axis"]) in targets:
            for f in ("from", "to"):
                if k[f] == value:
                    k[f] = name
    for t in _states(new):
        if (t[0], t[1]) in targets and t[2] == value:
            t[2] = name
    for v in new["variants"]:
        for e, axes in v.get("initial", {}).items():
            for a, x in axes.items():
                if (e, a) in targets and x == value:
                    axes[a] = name
    return None


def _rename_named_slice(new: dict, old: str, name: str) -> str | None:
    slices = new.get("named_slices", {})
    if old not in slices:
        return "no such named slice"
    if name == old:
        return None
    if name == FINAL:
        return f"the name {FINAL!r} is reserved for the final slice"
    if name in slices:
        return f"named slice name is taken: {name}"
    new["named_slices"] = _rekey(slices, old, name)
    return None


def _rename_simple(new: dict, what: str, old: str, name: str) -> str | None:
    """Kind, executor, instrument, scope, variant parameter."""
    label = what.replace("_", " ")
    names = [k["name"] for k in new["kinds"]] if what == "kind" else new.get(_LISTS[what], [])
    if old not in names:
        return f"no such {label}"
    if name == old:
        return None
    if name in names:
        return f"{label} name is taken: {name}"
    if what == "kind":
        for k in new["kinds"]:
            if k["name"] == old:
                k["name"] = name
    else:
        _swap(new[_LISTS[what]], old, name)
    if what in _CALL_FIELD:
        i = _CALL_FIELD[what]
        for v in new["variants"]:
            for c in v["calls"]:
                if c[i] == old:
                    c[i] = name
    if what == "scope" and new["batch_scope"] == old:
        new["batch_scope"] = name
    if what == "executor":
        for v in new["variants"]:
            for p, x in v.get("params", {}).items():
                if x == old:
                    v["params"][p] = name
    if what == "variant_param":
        for v in new["variants"]:
            if "params" in v:
                v["params"] = _rekey(v["params"], old, name)
    if what in ("executor", "variant_param"):
        i = 1 if what == "executor" else 0
        for spec in new.get("named_slices", {}).values():
            for g in spec["any"]:
                for pair in g.get("params", []):
                    if pair[i] == old:
                        pair[i] = name
    if what in _COEFFICIENTS:
        norm = new["normalization"]
        if _COEFFICIENTS[what] in norm:
            norm[_COEFFICIENTS[what]] = _rekey(norm[_COEFFICIENTS[what]], old, name)
    return None


def rename(data: dict, what: str, old: str | tuple[str, ...], name: str
           ) -> tuple[dict | None, list[Remark]]:
    """Rename a dictionary word everywhere in the project.

    Changes the word in the dictionary, kinds and their conditions, inherit sources, the existence
    axis and its "does not exist" value, the batch scope, named slice conditions, the variants
    (calls, params, entities, initial) and the normalization. Human texts (titles, tasks, steps) are
    not touched. An empty name and a taken name are refused; the same name changes nothing.

    A value is one word along the inherit links (an inheriting axis takes the value by name), and
    "does not exist" is one word for all existence axes; the existence axis is one name for all
    entities. Such a word is renamed in all its axes.

    :param data: the parsed project file; not changed.
    :param what: one of :data:`WORDS`.
    :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
    :param name: the new name; spaces around it are dropped.
    :return: ``(new data, [])``, or ``(None, remarks)`` when the edit is refused.
    :rtype: tuple[dict | None, list[Remark]]
    """
    size = {"axis": 2, "value": 3}.get(what)
    shaped = (isinstance(old, tuple) and len(old) == size and all(isinstance(x, str) for x in old)
              if size else isinstance(old, str))
    label = "/".join(old) if size and shaped else str(old)
    where = f"{what.replace('_', ' ')} {label}"
    if what not in WORDS:
        return None, [Remark(where, f"unknown kind of word: {what}")]
    if not shaped:
        return None, [Remark(where, f"name must be ({', '.join(('entity', 'axis', 'value')[:size])})"
                                    if size else "name must be a text")]
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        return None, [Remark(where, "name must not be empty")]
    new = copy.deepcopy(data)
    if what == "entity":
        reason = _rename_entity(new, old, name)
    elif what == "axis":
        reason = _rename_axis(new, old, name)
    elif what == "value":
        reason = _rename_value(new, old, name)
    elif what == "named_slice":
        reason = _rename_named_slice(new, old, name)
    else:
        reason = _rename_simple(new, what, old, name)
    if reason is not None:
        return None, [Remark(where, reason)]
    return _checked(new)


# ---------- usages and deletion of dictionary words ----------

def _exists(data: dict, what: str, old) -> bool:
    if what == "entity":
        return _entity(data, old) is not None
    if what == "axis":
        return _axis(data, *old) is not None
    if what == "value":
        ax = _axis(data, old[0], old[1])
        return ax is not None and old[2] in ax["values"]
    if what == "named_slice":
        return old in data.get("named_slices", {})
    if what == "kind":
        return any(k["name"] == old for k in data["kinds"])
    return old in data.get(_LISTS[what], [])


def _places(data: dict, what: str, old) -> list[str]:
    """Every place where the word is used; the normalization numbers are not among them."""
    out: list[str] = []
    variants, kinds = data["variants"], data["kinds"]
    slices = data.get("named_slices", {})
    if what in _CALL_FIELD:
        i = _CALL_FIELD[what]
        for v in variants:
            out += [f"variant {v['code']}, call {n}" for n, c in enumerate(v["calls"], 1)
                    if c[i] == old]
    if what == "scope" and data["batch_scope"] == old:
        out.append("batch scope")
    if what in ("executor", "variant_param"):
        for v in variants:
            for p, x in v.get("params", {}).items():
                if (x if what == "executor" else p) == old:
                    out.append(f"variant {v['code']}, parameter {p}")
        i = 1 if what == "executor" else 0
        for name, spec in slices.items():
            if any(pair[i] == old for g in spec["any"] for pair in g.get("params", [])):
                out.append(f"slice {name}")
    if what in ("entity", "axis", "value"):
        out += _structure_places(data, what, old)
    return out


def _structure_places(data: dict, what: str, old) -> list[str]:
    """Places of an entity, an axis or a value (several axes when it is one word along inherit)."""
    entity = old if what == "entity" else old[0]
    axis = old[1] if what != "entity" else None
    value = old[2] if what == "value" else None
    if what == "entity":
        targets = None
    elif what == "value":
        targets = _value_axes(data, entity, axis, value)
    else:
        targets = {(entity, axis)}

    def hit(e: str, a: str | None, x: str | None = None) -> bool:
        if what == "entity":
            return e == entity
        if (e, a) not in targets:
            return False
        return what == "axis" or x == value

    out: list[str] = []
    for v in data["variants"]:
        if what == "entity" and entity in v.get("entities", []):
            out.append(f"variant {v['code']}, entities")
        if any(hit(e, a, x) for e, axes in v.get("initial", {}).items()
               for a, x in axes.items()):
            out.append(f"variant {v['code']}, initial")
    for k in data["kinds"]:
        if what == "value":
            out += [f"kind {k['name']}, {f}" for f in ("from", "to")
                    if hit(k["entity"], k["axis"], k[f])]
        elif hit(k["entity"], k["axis"]):
            out.append(f"kind {k['name']}")
        if any(hit(*t) for t in k.get("requires", [])):
            out.append(f"kind {k['name']}, condition")
    for name, spec in data.get("named_slices", {}).items():
        if any(hit(*t) for g in spec["any"] for t in g.get("states", [])):
            out.append(f"slice {name}")
    for e in data["entities"]:
        for a in e["axes"]:
            if what != "value" and any(src[0] == entity and (what == "entity" or src[1] == axis)
                                       for src in a.get("inherit", [])) \
                    and not (what == "entity" and e["name"] == entity):
                out.append(f"axis {e['name']}/{a['name']}, inherit")
    if what == "value":
        existence = data["existence_axis"]
        if axis == existence["name"] and value == existence["absent"]:
            out.append("existence axis")
        for e, a in sorted(targets):
            if _axis(data, e, a)["values"][0] == value:
                out.append(f"initial value of {e}/{a}")
    return out


def usages(data: dict, what: str, old: str | tuple[str, ...]) -> list[str]:
    """The places where a dictionary word is used, one text each, without repeats.

    The places are: variant calls, parameters, entities and initial states; kinds and their
    conditions; named slice conditions; inherit sources; the batch scope; the existence axis; the
    first value of an axis (the initial state when a variant does not set it). A normalization
    number is not a place. An unknown word, or a name of a wrong shape, has none.

    :param data: the parsed project file; not changed.
    :param what: one of :data:`WORDS`.
    :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
    :return: the places, in the order of variants, kinds, slices.
    :rtype: list[str]
    """
    if _shape(what, old) is None or not _exists(data, what, old):
        return []
    found = _places(data, what, old)
    return list(dict.fromkeys(found))


def _shape(what: str, old) -> str | None:
    """The name for messages, or None when ``what`` or the shape of ``old`` is wrong."""
    if what not in WORDS:
        return None
    size = {"axis": 2, "value": 3}.get(what)
    if size:
        ok = isinstance(old, tuple) and len(old) == size and all(isinstance(x, str) for x in old)
        return "/".join(old) if ok else None
    return old if isinstance(old, str) else None


def delete(data: dict, what: str, old: str | tuple[str, ...]) -> tuple[dict | None, list[Remark]]:
    """Delete a dictionary word that is not used anywhere, with its normalization number.

    A used word is refused with the remark ``<name> is used and cannot be deleted:`` and one place
    per line (all of them, see :func:`usages`). Deleting an entity takes its axes and their skip
    prices; an axis takes its skip price.

    :param data: the parsed project file; not changed.
    :param what: one of :data:`WORDS`.
    :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
    :return: ``(new data, [])``, or ``(None, remarks)`` when the edit is refused.
    :rtype: tuple[dict | None, list[Remark]]
    """
    label = _shape(what, old)
    where = f"{what.replace('_', ' ')} {label if label is not None else old}"
    if what not in WORDS:
        return None, [Remark(where, f"unknown kind of word: {what}")]
    if label is None:
        size = {"axis": 2, "value": 3}.get(what)
        return None, [Remark(where, f"name must be ({', '.join(('entity', 'axis', 'value')[:size])})"
                                    if size else "name must be a text")]
    if not _exists(data, what, old):
        return None, [Remark(where, f"no such {what.replace('_', ' ')}")]
    places = usages(data, what, old)
    if places:
        short = old[-1] if isinstance(old, tuple) else old
        return None, [Remark(where, f"{short} is used and cannot be deleted:\n" + "\n".join(places))]
    new = copy.deepcopy(data)
    norm = new["normalization"]
    if what == "entity":
        new["entities"] = [e for e in new["entities"] if e["name"] != old]
        norm.get("axis_skip_prices", {}).pop(old, None)
    elif what == "axis":
        _axes = _entity(new, old[0])["axes"]
        _axes[:] = [a for a in _axes if a["name"] != old[1]]
        norm.get("axis_skip_prices", {}).get(old[0], {}).pop(old[1], None)
    elif what == "value":
        for e, a in _value_axes(new, *old):
            _axis(new, e, a)["values"].remove(old[2])
    elif what == "named_slice":
        del new["named_slices"][old]
    elif what == "kind":
        new["kinds"] = [k for k in new["kinds"] if k["name"] != old]
    else:
        new[_LISTS[what]].remove(old)
    if what in _COEFFICIENTS:
        norm.get(_COEFFICIENTS[what], {}).pop(old, None)
    return _checked(new)


def empty_project(name: str) -> tuple[dict | None, list[Remark]]:
    """Make the data of a project with no variants and no kinds, the start of the manual input.

    It holds the three words the file cannot lack: the existence axis ``exists`` with the absent
    value ``no``, and the one scope ``batch``, which is also the batch scope.

    :param name: the project name; empty or blank is refused.
    :return: ``(new data, [])``, or ``(None, remarks)`` when the edit is refused.
    :rtype: tuple[dict | None, list[Remark]]
    """
    name = name.strip()
    if not name:
        return None, [Remark("name", "name is empty")]
    data = {
        "format": 1,
        "name": name,
        "existence_axis": {"name": "exists", "absent": "no"},
        "entities": [],
        "kinds": [],
        "executors": [],
        "instruments": [],
        "scopes": ["batch"],
        "batch_scope": "batch",
        "variants": [],
        "normalization": {table: {} for table in NUMBER_TABLES},
    }
    project, remarks = read_project(data, strict=False)
    if project is None:
        return None, remarks
    return data, []
