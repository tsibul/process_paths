"""Tests of the build: dependencies, the PyInstaller spec, the `.qm` files of a frozen program."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from measure_twice import i18n

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "measure_twice.spec"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _names(requirements: list[str]) -> set[str]:
    """Names of the requirements without versions, in lower case."""
    out = set()
    for line in requirements:
        name = line
        for sign in "<>=!~;[ ":
            name = name.split(sign)[0]
        out.add(name.strip().lower())
    return out


def test_pyside6_is_a_dependency():
    assert "pyside6" in _names(_pyproject()["project"]["dependencies"])


def test_dev_group_has_pyinstaller_and_pytest():
    dev = _names(_pyproject()["dependency-groups"]["dev"])
    assert {"pyinstaller", "pytest"} <= dev


class _Recorder:
    """Stands for a class of PyInstaller: keeps the arguments of every call."""

    calls: dict[str, list] = {}

    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args, **kwargs):
        self.calls.setdefault(self.name, []).append((args, kwargs))
        return MagicMock()  # has every attribute the spec reads, such as `a.pure`


def _run_spec(qm_dir: Path) -> dict[str, list]:
    """Execute the spec with the PyInstaller classes replaced; the calls by class name."""
    _Recorder.calls = {}
    names = ("Analysis", "PYZ", "EXE", "COLLECT")
    spec_globals = {name: _Recorder(name) for name in names}
    spec_globals["SPECPATH"] = str(SPEC.parent)
    spec_globals["__file__"] = str(SPEC)
    old = os.environ.get("MEASURE_TWICE_QM")
    os.environ["MEASURE_TWICE_QM"] = str(qm_dir)
    try:
        exec(compile(SPEC.read_text(encoding="utf-8"), str(SPEC), "exec"), spec_globals)
    finally:
        if old is None:
            os.environ.pop("MEASURE_TWICE_QM", None)
        else:
            os.environ["MEASURE_TWICE_QM"] = old
    return _Recorder.calls


@pytest.fixture
def qm_dir(tmp_path):
    folder = tmp_path / "qm"
    folder.mkdir()
    for lang in ("ru", "el"):
        (folder / f"measure_twice_{lang}.qm").write_bytes(b"qm")
    return folder


def _datas(calls) -> list[tuple[str, str]]:
    (args, kwargs), = calls["Analysis"]
    return [(str(Path(src).resolve()), dest) for src, dest in kwargs["datas"]]


def test_spec_takes_every_data_file(qm_dir):
    datas = _datas(_run_spec(qm_dir))
    data = ROOT / "measure_twice" / "data"
    for path in sorted(data.iterdir()):
        assert (str(path.resolve()), "measure_twice/data") in datas


def test_spec_takes_the_qm_files_into_the_i18n_folder(qm_dir):
    datas = _datas(_run_spec(qm_dir))
    for lang in ("ru", "el"):
        qm = qm_dir / f"measure_twice_{lang}.qm"
        assert (str(qm.resolve()), "measure_twice/i18n") in datas


def test_spec_needs_a_qm_for_every_ts(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit):
        _run_spec(empty)


def test_spec_builds_a_folder_with_qtcharts(qm_dir):
    calls = _run_spec(qm_dir)
    assert "COLLECT" in calls  # a folder, not one file
    (args, kwargs), = calls["Analysis"]
    assert "PySide6.QtCharts" in kwargs["hiddenimports"]


def test_frozen_program_reads_qm_next_to_the_code():
    assert i18n.qm_folder(frozen=True) == i18n.SOURCES
    assert i18n.qm_folder(frozen=False) != i18n.SOURCES


def test_frozen_program_does_not_run_lrelease(tmp_path, monkeypatch):
    for lang in ("ru", "el"):
        (tmp_path / f"measure_twice_{lang}.qm").write_bytes(b"qm")

    def no_tool():
        raise AssertionError("lrelease must not run in the build")

    monkeypatch.setattr(i18n, "_lrelease", no_tool)
    built = i18n.build_qm(tmp_path, tmp_path, frozen=True)
    assert [p.name for p in built] == ["measure_twice_el.qm", "measure_twice_ru.qm"]
