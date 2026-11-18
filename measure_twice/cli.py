# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Command line: ``check`` and ``table``; without arguments the window opens."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from measure_twice import export
from measure_twice.project import load_file


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="measure-twice",
        description="Compare the path variants of a project.",
    )
    sub = p.add_subparsers(dest="command")
    c = sub.add_parser("check", help="check a project file")
    c.add_argument("file")
    t = sub.add_parser("table", help="print the comparison")
    t.add_argument("file")
    t.add_argument("--csv", action="store_true", help="CSV instead of Markdown")
    return p


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    :param argv: arguments without the program name; ``None`` takes them from ``sys.argv``.
    :return: exit code.
    :rtype: int
    """
    args = _parser().parse_args(argv)
    if args.command is None:
        from measure_twice.ui.app import main as ui_main
        ui_main()
        return 0
    project, remarks = load_file(Path(args.file))
    if args.command == "check":
        if project is None:
            for r in remarks:
                print(str(r))
            return 1
        print(f"OK: {project.name}")
        return 0
    if project is None:
        for r in remarks:
            print(str(r), file=sys.stderr)
        return 1
    sys.stdout.write(export.csv_text(project) if args.csv else export.markdown(project))
    return 0
