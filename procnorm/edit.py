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

from procnorm.project import Remark, read_project

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
