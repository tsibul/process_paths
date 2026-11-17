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
