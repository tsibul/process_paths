# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build Measure Twice for the current system: the `.qm` files, the icon, the folder, its archive.

Run with the Python of the project's ``.venv``::

    .venv/bin/python packaging/build.py          # Linux
    .venv\\Scripts\\python packaging\\build.py     # Windows

The result is ``dist/measure_twice`` and next to it ``measure_twice-<version>-<system>-<machine>``
as ``.tar.gz`` on Linux or ``.zip`` on Windows.
"""

from __future__ import annotations

import os
import platform
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "measure_twice"
ICON_SIZES = (16, 32, 48, 256)


def lrelease_path(python: Path, system: str) -> Path:
    """The `lrelease` of PySide6 next to the interpreter."""
    suffix = ".exe" if system.startswith("win") else ""
    return python.parent / ("pyside6-lrelease" + suffix)


def version(root: Path) -> str:
    """The version of the project from ``pyproject.toml``."""
    with open(root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def archive_format(system: str) -> str:
    """The archive format of :func:`shutil.make_archive` for the system."""
    return "zip" if system.startswith("win") else "gztar"


def archive_base(dist: Path, ver: str, system: str, machine: str) -> Path:
    """The path of the archive without its extension."""
    name = "windows" if system.startswith("win") else system
    return dist / f"{NAME}-{ver}-{name}-{machine.lower()}"


def compile_qm(sources: Path, out: Path, tool: Path) -> list[Path]:
    """Build a `.qm` file for every ``measure_twice_<lang>.ts``; stops on the first failure.

    :param sources: the folder of the `.ts` files.
    :param out: the folder of the `.qm` files, emptied first.
    :param tool: `pyside6-lrelease`.
    :return: the built files.
    :rtype: list[Path]
    """
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    built = []
    for ts in sorted(sources.glob(f"{NAME}_*.ts")):
        qm = out / (ts.stem + ".qm")
        subprocess.run([str(tool), "-silent", str(ts), "-qm", str(qm)], check=True)
        built.append(qm)
    return built


def make_ico(svg: Path, out: Path, sizes: tuple[int, ...] = ICON_SIZES) -> Path:
    """Draw the SVG icon at every size and write them as one `.ico` file.

    Each picture is kept in the `.ico` as PNG. Qt draws and encodes them; the `.ico` directory
    is written here, since the `ico` writer of Qt keeps only one picture per file.

    :param svg: the icon.
    :param out: the `.ico` file; its folder is made when absent.
    :param sizes: the sizes in pixels, at most 256.
    :return: the `.ico` file.
    :rtype: Path
    :raises ValueError: when the SVG cannot be read.
    """
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise ValueError(f"Not a valid SVG: {svg}")
    pictures = []
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        pictures.append((size, bytes(buffer.data())))
    header = struct.pack("<HHH", 0, 1, len(pictures))
    offset = len(header) + 16 * len(pictures)
    entries = b""
    for size, png in pictures:
        side = size % 256  # 0 stands for 256
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + entries + b"".join(png for size, png in pictures))
    return out


def make_archive(folder: Path, base: Path, system: str) -> Path:
    """Pack the program folder; inside the archive it keeps its name.

    :return: the archive.
    :rtype: Path
    """
    made = shutil.make_archive(
        str(base),
        archive_format(system),
        root_dir=folder.parent,
        base_dir=folder.name,
    )
    return Path(made)


def _make_ico_offscreen(svg: Path, out: Path) -> Path:
    """:func:`make_ico` under a Qt application that needs no screen."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    made = make_ico(svg, out)
    del app
    return made


def main() -> int:
    """Build everything; the exit code of the first failed step, else 0."""
    python = Path(sys.executable)
    qm = ROOT / "build" / "qm"
    dist = ROOT / "dist"
    ico = ROOT / "build" / "icon" / f"{NAME}.ico"
    compile_qm(ROOT / NAME / "i18n", qm, lrelease_path(python, sys.platform))
    _make_ico_offscreen(ROOT / NAME / "data" / "icon.svg", ico)
    env = dict(os.environ, MEASURE_TWICE_QM=str(qm), MEASURE_TWICE_ICO=str(ico))
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        str(ROOT / "packaging" / f"{NAME}.spec"),
    ]
    done = subprocess.run(command, env=env)
    if done.returncode != 0:
        return done.returncode
    folder = dist / NAME
    base = archive_base(dist, version(ROOT), sys.platform, platform.machine())
    archive = make_archive(folder, base, sys.platform)
    print(f"Built {folder} and {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
