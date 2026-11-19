# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The built-in example project: seeded once on the very first start.

The tap is one: ``example.json`` in English and ``example_<lang>.json`` with the same structure
and numbers and the texts of another window language.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from measure_twice.project import Project, load_file
from measure_twice.store import Store

EXAMPLE_FILE = Path(__file__).parent / "data" / "example.json"
EXAMPLE_NAME = "Fix a leaking tap"
SOURCE = "en"  # the language of ``EXAMPLE_FILE``
# The name of the tap in the other languages, as in their files.
NAMES = {
    "ru": "Починить подтекающий кран",
    "el": "Επισκευή βρύσης που στάζει",
}
SEEDED = "example_seeded"  # QSettings key: the example has been offered already


def example_file(lang: str = SOURCE) -> Path:
    """The example file of a language.

    :param lang: the window language.
    :return: ``example_<lang>.json``, or the English file when the language has none.
    :rtype: Path
    """
    path = EXAMPLE_FILE.with_name(f"example_{lang}.json")
    return path if lang != SOURCE and path.exists() else EXAMPLE_FILE


def example_name(lang: str = SOURCE) -> str:
    """The name of the example in a language.

    :param lang: the window language.
    :return: the name of the project in :func:`example_file`.
    :rtype: str
    """
    if example_file(lang) == EXAMPLE_FILE:
        return EXAMPLE_NAME
    return NAMES[lang]


def load_example(lang: str = SOURCE) -> Project:
    """Read the example project file.

    :param lang: the window language.
    :return: the example project.
    :rtype: Project
    :raises RuntimeError: if the file has remarks.
    """
    project, remarks = load_file(example_file(lang))
    if project is None or remarks:
        raise RuntimeError(f"The example project is broken: {remarks}")
    return project


def find_example(store: Store, lang: str = SOURCE) -> int | None:
    """The example of a language in the store.

    :param store: the project store.
    :param lang: the window language.
    :return: id of the project named as the example, or ``None``.
    :rtype: int | None
    """
    name = example_name(lang)
    return next((info.id for info in store.list() if info.name == name), None)


def add_example(store: Store, lang: str = SOURCE) -> int:
    """Add the example of a language to the store unless it is there already.

    An example of another language in the store is left as it is.

    :param store: the project store.
    :param lang: the window language.
    :return: id of the example project.
    :rtype: int
    """
    present = find_example(store, lang)
    if present is not None:
        return present
    return store.add(load_example(lang))


def first_run(store: Store, settings: QSettings, lang: str = SOURCE) -> int | None:
    """Seed the example on the very first start, once.

    :param store: the project store.
    :param settings: application settings holding the ``SEEDED`` mark.
    :param lang: the window language: the language of the example.
    :return: id of the added example, or ``None`` if nothing was added.
    :rtype: int | None
    """
    if settings.value(SEEDED) is not None:
        return None
    settings.setValue(SEEDED, True)
    settings.sync()
    if store.list():
        return None
    return add_example(store, lang)
