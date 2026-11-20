"""Tests of `packaging/build.py`: the `.qm` files, the archive, the tools of each system."""

import importlib.util
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "packaging" / "build.py"


@pytest.fixture(scope="module")
def build():
    # Loaded by path: the name `packaging` is taken by the library of the same name.
    spec = importlib.util.spec_from_file_location("measure_twice_build", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shell_script_is_gone():
    assert not (ROOT / "packaging" / "build.sh").exists()


def test_archive_format_follows_the_system(build):
    assert build.archive_format("linux") == "gztar"
    assert build.archive_format("win32") == "zip"


def test_archive_name(build, tmp_path):
    linux = build.archive_base(tmp_path, "0.1.0", "linux", "x86_64")
    windows = build.archive_base(tmp_path, "0.1.0", "win32", "AMD64")
    assert linux == tmp_path / "measure_twice-0.1.0-linux-x86_64"
    assert windows == tmp_path / "measure_twice-0.1.0-windows-amd64"


def test_lrelease_lies_next_to_python(build):
    linux = build.lrelease_path(Path("/p/.venv/bin/python"), "linux")
    windows = build.lrelease_path(Path("C:/p/.venv/Scripts/python.exe"), "win32")
    assert linux == Path("/p/.venv/bin/pyside6-lrelease")
    assert windows == Path("C:/p/.venv/Scripts/pyside6-lrelease.exe")


def test_version_is_read_from_pyproject(build):
    assert build.version(ROOT) == "0.1.0"


def test_compile_qm_makes_one_qm_per_ts(build, tmp_path):
    import sys

    tool = build.lrelease_path(Path(sys.executable), sys.platform)
    if not tool.exists():
        pytest.skip("no pyside6-lrelease next to the interpreter")
    built = build.compile_qm(ROOT / "measure_twice" / "i18n", tmp_path / "qm", tool)
    names = sorted(p.name for p in built)
    assert names == ["measure_twice_el.qm", "measure_twice_ru.qm"]
    assert all(p.stat().st_size > 0 for p in built)


def test_ico_holds_every_size(build, tmp_path):
    from PySide6.QtGui import QGuiApplication, QImageReader

    app = QGuiApplication.instance() or QGuiApplication([])
    svg = ROOT / "measure_twice" / "data" / "icon.svg"
    ico = build.make_ico(svg, tmp_path / "icon" / "measure_twice.ico")
    reader = QImageReader(str(ico), b"ico")
    sizes = []
    for i in range(reader.imageCount()):
        reader.jumpToImage(i)
        image = reader.read()
        assert not image.isNull()
        sizes.append(image.width())
    assert app is not None
    assert sorted(sizes) == [16, 32, 48, 256]


def test_ico_needs_a_valid_svg(build, tmp_path):
    bad = tmp_path / "bad.svg"
    bad.write_text("not svg")
    with pytest.raises(ValueError):
        build.make_ico(bad, tmp_path / "x.ico")


@pytest.mark.parametrize("system", ["linux", "win32"])
def test_archive_holds_the_program_folder(build, tmp_path, system):
    folder = tmp_path / "dist" / "measure_twice"
    folder.mkdir(parents=True)
    (folder / "measure_twice").write_text("program")
    base = build.archive_base(tmp_path / "dist", "0.1.0", system, "x86_64")
    archive = build.make_archive(folder, base, system)
    if system == "linux":
        assert archive.name.endswith(".tar.gz")
        names = tarfile.open(archive).getnames()
    else:
        assert archive.suffix == ".zip"
        names = zipfile.ZipFile(archive).namelist()
    assert "measure_twice/measure_twice" in names
