# -*- mode: python -*-
# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""PyInstaller spec of Measure Twice: one folder ``dist/measure_twice`` with the program.

Run through ``packaging/build.sh``: it builds the `.qm` files first. The folder of the `.qm`
files is ``build/qm`` of the project, or the one in the ``MEASURE_TWICE_QM`` variable.
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
PACKAGE = ROOT / "measure_twice"
QM = Path(os.environ.get("MEASURE_TWICE_QM") or ROOT / "build" / "qm")


def _qm_files() -> list[Path]:
    """The `.qm` file of every `.ts` source; stops the build when one is missing."""
    names = [ts.stem + ".qm" for ts in sorted((PACKAGE / "i18n").glob("measure_twice_*.ts"))]
    missing = [name for name in names if not (QM / name).is_file()]
    if missing:
        raise SystemExit(f"No {', '.join(missing)} in {QM}: run packaging/build.sh")
    return [QM / name for name in names]


datas = [(str(path), "measure_twice/data") for path in sorted((PACKAGE / "data").iterdir())]
datas += [(str(path), "measure_twice/i18n") for path in _qm_files()]

a = Analysis(
    [str(PACKAGE / "__main__.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["PySide6.QtCharts"],
    excludes=["tkinter"],
)

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
