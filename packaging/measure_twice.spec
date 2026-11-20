# -*- mode: python -*-
# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""PyInstaller spec of Measure Twice: one folder ``dist/measure_twice`` with the program.

Run through ``packaging/build.py``: it builds the `.qm` files first. The folder of the `.qm`
files is ``build/qm`` of the project, or the one in the ``MEASURE_TWICE_QM`` variable.
"""

import os
from pathlib import Path, PurePosixPath

ROOT = Path(SPECPATH).resolve().parent
PACKAGE = ROOT / "measure_twice"
QM = Path(os.environ.get("MEASURE_TWICE_QM") or ROOT / "build" / "qm")


def _qm_files() -> list[Path]:
    """The `.qm` file of every `.ts` source; stops the build when one is missing."""
    names = [ts.stem + ".qm" for ts in sorted((PACKAGE / "i18n").glob("measure_twice_*.ts"))]
    missing = [name for name in names if not (QM / name).is_file()]
    if missing:
        raise SystemExit(f"No {', '.join(missing)} in {QM}: run packaging/build.py")
    return [QM / name for name in names]


# Qt parts the program does not use: libraries by name, plugins by folder or by name.
UNUSED_LIBS = (
    "Qt6Qml",
    "Qt6Quick",
    "Qt6VirtualKeyboard",
    "Qt6Pdf",
    "Qt6Network",
    "Qt6EglFS",
    "Qt6EglFs",
)
UNUSED_PLUGIN_FOLDERS = {
    "egldeviceintegrations",
    "generic",
    "networkinformation",
    "tls",
}
UNUSED_PLUGINS = {
    "qtvirtualkeyboardplugin",
    "qpdf",
    "qeglfs",
    "qlinuxfb",
    "qminimalegl",
    "qvkkhrdisplay",
    "qvnc",
}
UNUSED_MODULES = [
    "PySide6.QtNetwork",
    "PySide6.QtPdf",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtVirtualKeyboard",
    "tkinter",
]


def _unused(name: str) -> bool:
    """Whether a file of the analysis, by its name in the build, is a Qt part left out."""
    path = PurePosixPath(name.replace("\\", "/"))
    stem = path.name.split(".")[0]
    if stem.startswith("lib"):
        stem = stem[3:]
    if stem.startswith(UNUSED_LIBS):
        return True
    if "plugins" in path.parts:
        return path.parent.name in UNUSED_PLUGIN_FOLDERS or stem in UNUSED_PLUGINS
    if "translations" in path.parts and "PySide6" in path.parts:
        return not stem.startswith("qtbase_")
    return False


datas = [(str(path), "measure_twice/data") for path in sorted((PACKAGE / "data").iterdir())]
datas += [(str(path), "measure_twice/i18n") for path in _qm_files()]

a = Analysis(
    [str(PACKAGE / "__main__.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["PySide6.QtCharts"],
    excludes=UNUSED_MODULES,
)
a.binaries = [entry for entry in a.binaries if not _unused(entry[0])]
a.datas = [entry for entry in a.datas if not _unused(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="measure_twice",
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="measure_twice",
)
