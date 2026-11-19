# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""SQLite storage of projects: one table of projects, the project file text kept as it is."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from measure_twice.project import Project, read_project

SCHEMA_VERSION = "1"


def _dump(v: object, level: int, out: list[str]) -> None:
    pad = "  " * (level + 1)
    if v is None:
        out.append("null")
    elif isinstance(v, bool):
        out.append("true" if v else "false")
    elif isinstance(v, int):
        out.append(str(v))
    elif isinstance(v, Decimal):
        if not v.is_finite():
            raise ValueError(f"cannot write {v}")
        out.append(format(v, "f"))
    elif isinstance(v, str):
        out.append(json.dumps(v, ensure_ascii=False))
    elif isinstance(v, (list, tuple)):
        if not v:
            out.append("[]")
            return
        out.append("[\n")
        for i, x in enumerate(v):
            out.append(pad)
            _dump(x, level + 1, out)
            out.append(",\n" if i < len(v) - 1 else "\n")
        out.append("  " * level + "]")
    elif isinstance(v, dict):
        if not v:
            out.append("{}")
            return
        out.append("{\n")
        for i, (k, x) in enumerate(v.items()):
            if not isinstance(k, str):
                raise TypeError(f"key must be a string: {k!r}")
            out.append(pad + json.dumps(k, ensure_ascii=False) + ": ")
            _dump(x, level + 1, out)
            out.append(",\n" if i < len(v) - 1 else "\n")
        out.append("  " * level + "}")
    else:
        raise TypeError(f"cannot write {type(v).__name__}")


def dumps(data: object) -> str:
    """Write JSON text: indent 2, no ASCII escapes, Decimal as a plain number.

    :param data: dict, list, str, int, Decimal, bool or None.
    :return: JSON text.
    :rtype: str
    """
    out: list[str] = []
    _dump(data, 0, out)
    return "".join(out)


def default_path() -> Path:
    """Path of the database; the folder is created.

    When the new database does not exist yet but the one of the old program name
    (``procnorm/procnorm.db``) does, the old one is used in place: nothing is copied or moved,
    and the new folder is not created.

    :return: the path.
    :rtype: Path
    """
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    folder = base / "measure_twice"
    path = folder / "measure_twice.db"
    old = base / "procnorm" / "procnorm.db"
    if not path.exists() and old.exists():
        return old
    folder.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProjectInfo:
    """A line of the project list.

    :ivar id: project id.
    :ivar name: project name.
    :ivar description: project description.
    :ivar updated: time of the last write, ISO, UTC.
    :ivar ways: number of ways (variants) in the project.
    """

    id: int
    name: str
    description: str
    updated: str
    ways: int


class Store:
    """Projects in an SQLite file; every write is committed at once."""

    def __init__(self, path: Path | str) -> None:
        """Open the database and create the tables when they are missing.

        :param path: file path or ``":memory:"``.
        """
        self._db = sqlite3.connect(str(path))
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
            self._db.execute("CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY, "
                             "name TEXT NOT NULL, description TEXT NOT NULL, created TEXT NOT NULL, "
                             "updated TEXT NOT NULL, data TEXT NOT NULL)")
            self._db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                             (SCHEMA_VERSION,))

    def _free_name(self, name: str, own_id: int | None = None) -> str:
        """The name itself when no other project has it, else ``"<name> (2)"``, ``(3)``, ...

        A name ending in `` (n)`` whose base name is another project is numbered from the base,
        so the name does not grow.

        :param name: wanted name.
        :param own_id: id of the project being written, its own name is not taken.
        :return: the first free name.
        :rtype: str
        """
        taken = {row[0] for row in self._db.execute(
            "SELECT name FROM project WHERE id IS NOT ?", (own_id,))}
        match = re.fullmatch(r"(.*) \(\d+\)", name)
        if match and match.group(1) in taken:
            name = match.group(1)
        free, number = name, 1
        while free in taken:
            number += 1
            free = f"{name} ({number})"
        return free

    def add(self, project: Project) -> int:
        """Add a project.

        A name taken by another project gets the number ``" (2)"``, ``" (3)"``, ...

        :param project: a checked project.
        :return: its id.
        :rtype: int
        """
        now = _now()
        name = self._free_name(project.name)
        data = {**project.data, "name": name}
        with self._db:
            cur = self._db.execute(
                "INSERT INTO project(name, description, created, updated, data) VALUES(?, ?, ?, ?, ?)",
                (name, project.description, now, now, dumps(data)))
        return int(cur.lastrowid)

    def replace(self, id: int, project: Project) -> None:
        """Load a project over a stored one: the id and the creation time stay.

        A name taken by another project gets a number; its own name stays as it is.

        :param id: project id.
        :param project: a checked project.
        :raises KeyError: no such id.
        """
        name = self._free_name(project.name, id)
        data = {**project.data, "name": name}
        with self._db:
            cur = self._db.execute(
                "UPDATE project SET name = ?, description = ?, updated = ?, data = ? WHERE id = ?",
                (name, project.description, _now(), dumps(data), id))
        if cur.rowcount == 0:
            raise KeyError(id)

    def save(self, id: int, data: dict) -> None:
        """Write edited project data over a stored project, one UPDATE.

        The list columns ``name`` and ``description`` follow the data; the id and the
        creation time stay.

        :param id: project id.
        :param data: the whole project file as parsed JSON.
        :raises KeyError: no such id.
        """
        with self._db:
            cur = self._db.execute(
                "UPDATE project SET name = ?, description = ?, updated = ?, data = ? WHERE id = ?",
                (data["name"], data.get("description", ""), _now(), dumps(data), id))
        if cur.rowcount == 0:
            raise KeyError(id)

    def list(self) -> list[ProjectInfo]:
        """List the projects.

        :return: projects ordered by name, then id.
        :rtype: list[ProjectInfo]
        """
        rows = self._db.execute(
            "SELECT id, name, description, updated, data FROM project ORDER BY name, id").fetchall()
        return [ProjectInfo(r[0], r[1], r[2], r[3], len(json.loads(r[4])["variants"]))
                for r in rows]

    def _data_text(self, id: int) -> str:
        row = self._db.execute("SELECT data FROM project WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        return row[0]

    def get(self, id: int) -> Project:
        """Read a project.

        :param id: project id.
        :return: the project, checked again leniently: a missing number or a broken variant
            does not refuse the project.
        :rtype: Project
        :raises KeyError: no such id.
        """
        project, remarks = read_project(json.loads(self._data_text(id), parse_float=Decimal),
                                        strict=False)
        if project is None:
            raise ValueError("stored project is not valid: " + "; ".join(str(r) for r in remarks))
        return project

    def text(self, id: int) -> str:
        """The project file text.

        :param id: project id.
        :return: JSON text.
        :rtype: str
        :raises KeyError: no such id.
        """
        return dumps(json.loads(self._data_text(id), parse_float=Decimal))

    def copy(self, id: int) -> int:
        """Copy a project under the first free name ``"<name> (2)"``, ``(3)``, ...

        :param id: project id.
        :return: id of the copy.
        :rtype: int
        :raises KeyError: no such id.
        """
        data = json.loads(self._data_text(id), parse_float=Decimal)
        data["name"] = self._free_name(data["name"])
        now = _now()
        desc = data.get("description", "")
        with self._db:
            cur = self._db.execute(
                "INSERT INTO project(name, description, created, updated, data) VALUES(?, ?, ?, ?, ?)",
                (data["name"], desc, now, now, dumps(data)))
        return int(cur.lastrowid)

    def delete(self, id: int) -> None:
        """Delete a project.

        :param id: project id.
        """
        with self._db:
            self._db.execute("DELETE FROM project WHERE id = ?", (id,))

    def close(self) -> None:
        """Close the database."""
        self._db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
