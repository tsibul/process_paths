#!/usr/bin/env bash
# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

# Build Measure Twice for Linux: the `.qm` files, the folder dist/measure_twice, its archive.
# Run from any folder; the Python of the project's .venv is taken unless PYTHON is set.

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python="${PYTHON:-$root/.venv/bin/python}"
bin="$(dirname "$python")"
qm="$root/build/qm"

rm -rf "$qm"
mkdir -p "$qm"
for ts in "$root"/measure_twice/i18n/measure_twice_*.ts; do
  name="$(basename "$ts" .ts)"
  "$bin/pyside6-lrelease" -silent "$ts" -qm "$qm/$name.qm"
done

MEASURE_TWICE_QM="$qm" "$python" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$root/dist" \
  --workpath "$root/build/pyinstaller" \
  "$root/packaging/measure_twice.spec"

read_version='import sys, tomllib
print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])'
version="$("$python" -c "$read_version" "$root/pyproject.toml")"
archive="$root/dist/measure_twice-$version-linux-$(uname -m).tar.gz"
tar -czf "$archive" -C "$root/dist" measure_twice
echo "Built $root/dist/measure_twice and $archive"
