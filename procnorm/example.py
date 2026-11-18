# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The built-in example project: seeded once on the very first start."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from procnorm.project import Project, load_file
from procnorm.store import Store

EXAMPLE_FILE = Path(__file__).parent / "data" / "example.json"
EXAMPLE_NAME = "Fix a leaking tap"
SEEDED = "example_seeded"  # QSettings key: the example has been offered already


def load_example() -> Project:
    """Read the example project file.

    :return: the example project.
    :rtype: Project
    :raises RuntimeError: if the file has remarks.
    """
    project, remarks = load_file(EXAMPLE_FILE)
    if project is None or remarks:
        raise RuntimeError(f"The example project is broken: {remarks}")
    return project


def add_example(store: Store) -> int:
    """Add the example to the store unless it is there already.

    :param store: the project store.
    :return: id of the example project.
    :rtype: int
    """
    for info in store.list():
        if info.name == EXAMPLE_NAME:
            return info.id
    return store.add(load_example())


def first_run(store: Store, settings: QSettings) -> int | None:
    """Seed the example on the very first start, once.

    :param store: the project store.
    :param settings: application settings holding the ``SEEDED`` mark.
    :return: id of the added example, or ``None`` if nothing was added.
    :rtype: int | None
    """
    if settings.value(SEEDED) is not None:
        return None
    settings.setValue(SEEDED, True)
    settings.sync()
    if store.list():
        return None
    return add_example(store)
