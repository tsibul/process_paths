"""Test of the remarks and the export in the window language (piece 27).

The core does not know Qt: a remark keeps its English template and its substitutions, and the
window translates it when it shows it. A test translation puts every source string of the
program in guillemets, so a translated template is seen with its substitutions filled in. The
command line stays in English; the Markdown and CSV export and the PDF report follow the window,
and the numbers of the CSV keep the point under a language with a decimal comma.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QApplication

from measure_twice import edit, export, i18n, report
from measure_twice.calc import compare
from measure_twice.cli import main as cli
from measure_twice.project import read_project
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow
from measure_twice.ui.remarks import RemarksPanel

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "measure_twice"
CORE = [PACKAGE / name for name in ("project.py", "edit.py", "calc.py", "export.py")]
SOURCES = sorted(PACKAGE.glob("*.py")) + sorted((PACKAGE / "ui").glob("*.py"))
LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
MARK = "«"


def lupdate() -> str | None:
    near = Path(sys.executable).parent / "pyside6-lupdate"
    return str(near) if near.exists() else shutil.which("pyside6-lupdate")


def extract(files: list[Path], ts: Path) -> ET.ElementTree:
    """Run `lupdate` on the files into a new `.ts`."""
    tool = lupdate()
    if tool is None:
        pytest.skip("pyside6-lupdate is needed")
    done = subprocess.run(
        [tool, *map(str, files), "-ts", str(ts), "-target-language", "ru_RU"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
    return ET.parse(ts)


def laundry() -> dict:
    return json.loads(LAUNDRY.read_text(encoding="utf-8"), parse_float=Decimal)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def marked(tmp_path_factory) -> Path:
    """The folder with the `.qm` where every source string is translated to «string»."""
    if i18n._lrelease() is None:
        pytest.skip("pyside6-lrelease is needed")
    folder = tmp_path_factory.mktemp("marked")
    ts = folder / "measure_twice_ru.ts"
    tree = extract(SOURCES, ts)
    for message in tree.iter("message"):
        source = message.find("source").text or ""
        translation = message.find("translation")
        translation.attrib.pop("type", None)
        if message.get("numerus") == "yes":
            for form in list(translation):
                translation.remove(form)
            for _ in range(3):
                ET.SubElement(translation, "numerusform").text = MARK + source + "»"
        else:
            translation.text = MARK + source + "»"
    tree.write(ts, encoding="utf-8", xml_declaration=True)
    i18n.build_qm(folder, folder)
    return folder


@pytest.fixture
def russian(app, marked):
    old = QLocale()
    i18n.apply_language(app, "ru", marked)
    yield
    i18n.apply_language(app, "en", marked)
    QLocale.setDefault(old)


def remarks_of(data: dict) -> list:
    project, remarks = read_project(data)
    assert project is None
    return remarks


# --- lupdate finds the templates of the core


def test_core_has_no_qt():
    for path in CORE + [PACKAGE / "message.py"]:
        assert "PySide6" not in path.read_text(encoding="utf-8"), path.name


def test_lupdate_finds_core_templates(tmp_path):
    tree = extract(CORE, tmp_path / "core.ts")
    found = {}
    for context in tree.iter("context"):
        name = context.find("name").text
        found[name] = {m.find("source").text for m in context.iter("message")}
    assert "unknown field {field}" in found["Project"]
    assert "entity {name}" in found["Project"]
    assert "{where}, step {number}" in found["Project"]
    assert "no such variant" in found["Edit"]
    assert "{name}: not a number: {text}" in found["Edit"]
    assert "Not set: {items}" in found["Calc"]
    assert "Labour · {executor}" in found["Export"]
    assert "Details" in found["Export"]
    assert sum(len(s) for s in found.values()) > 150


def test_numerus_template_is_found(tmp_path):
    tree = extract(CORE, tmp_path / "core.ts")
    numerus = {m.find("source").text for m in tree.iter("message") if m.get("numerus") == "yes"}
    assert "steps cover %n calls, the variant has {count}" in numerus
    assert "%n variants" in numerus


# --- a remark is translated when shown


def test_remark_translated_with_substitutions(russian):
    data = laundry()
    data["entities"][0]["colour"] = 1
    remark = next(r for r in remarks_of(data) if "colour" in r.text)
    assert str(remark) == "entity Бельё: unknown field 'colour'"
    assert i18n.remark(remark) == "«entity Бельё»: «unknown field 'colour'»"


def test_nested_place_is_translated(russian):
    data = laundry()
    data["variants"][0]["steps"] = [{"text": "Wash", "calls": "a"}]
    remark = next(r for r in remarks_of(data) if "calls must be" in r.text)
    assert str(remark).startswith("variant А, step 1: ")
    assert i18n.remark(remark) == "««variant А», step 1»: «calls must be an integer, 0 or more»"


def test_plural_template(russian):
    data = laundry()
    count = len(data["variants"][0]["calls"])
    data["variants"][0]["steps"] = [{"text": "Wash", "calls": 1}]
    remark = next(r for r in remarks_of(data) if "steps cover" in r.text)
    assert remark.text == f"steps cover 1 calls, the variant has {count}"
    assert i18n.shown(remark.text) == f"«steps cover 1 calls, the variant has {count}»"


def test_edit_refusal_translated(russian):
    data = laundry()
    _, remarks = edit.set_number(data, "kind_costs", "Постирать", "abc")
    assert str(remarks[0]) == "normalization, kind_costs: Постирать: not a number: abc"
    assert i18n.shown(remarks[0].text) == "«{name}: not a number: {text}»".format(
        name="Постирать", text="abc")


def test_delete_places_translated(russian):
    data = laundry()
    _, remarks = edit.delete(data, "executor", "Человек")
    text = i18n.shown(remarks[0].text)
    first, _, places = text.partition("\n")
    assert first == "«Человек is used and cannot be deleted:"
    assert places and all(line.startswith("«") for line in places.split("\n"))
    assert "\n" in remarks[0].text and MARK not in remarks[0].text


def test_panel_shows_translated_remarks(russian, tmp_path):
    data = laundry()
    data["entities"][0]["colour"] = 1
    panel = RemarksPanel()
    project, remarks = read_project(data)
    panel.show_remarks(tmp_path / "bad.json", remarks)
    assert panel.lines() and all(MARK in line for line in panel.lines())


def test_reason_translated(russian):
    data = laundry()
    del data["normalization"]["kind_costs"]["Постирать"]
    project, remarks = read_project(data, strict=False)
    assert project is not None, remarks
    row = next(r for r in compare(project).rows + compare(project).excluded_rows if r.missing)
    assert str(row.reason).startswith("Not set: cost of ")
    assert i18n.shown(row.reason).startswith("«Not set: «cost of ")


# --- the command line stays English


def test_cli_prints_english(russian, tmp_path, capsys):
    data = laundry()
    data["entities"][0]["colour"] = 1
    bad = tmp_path / "bad.json"
    data["normalization"]["scope_coefficients"]["вся загрузка"] = 0.1
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert cli(["check", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "entity Бельё: unknown field 'colour'" in out.splitlines()
    assert MARK not in out
    assert cli(["table", str(LAUNDRY)]) == 0
    out = capsys.readouterr().out
    assert "## Details" in out and MARK not in out
    assert cli(["table", "--csv", str(LAUNDRY)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Group,Code,Title,") and MARK not in out


# --- the export follows the window, the numbers of the CSV keep the point


def project():
    found, remarks = read_project(laundry())
    assert found is not None, remarks
    return found


def check_csv(text: str) -> None:
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "«Group»"
    assert all(cell.startswith(MARK) for cell in rows[0])
    total = rows[0].index("«Labour · total»")
    numbers = [r[total] for r in rows[1:]]
    assert numbers and all(re.fullmatch(r"\d+\.\d\d", n) for n in numbers), numbers
    cells = [c for r in rows[1:] for c in r]
    assert not any(re.fullmatch(r"\d+,\d+", c) for c in cells)


def test_csv_in_window_language(russian):
    assert QLocale().decimalPoint() == ","
    check_csv(export.csv_text(project(), i18n.shown))


def test_markdown_in_window_language(russian):
    text = export.markdown(project(), i18n.shown)
    assert "## «Details»" in text
    assert "«Labour · Человек»" in text
    assert "«Labour · total»" in text
    assert "## Details" not in text


def test_window_export(russian, tmp_path):
    store = Store(tmp_path / "t.db")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    win = MainWindow(store, settings)
    try:
        assert win.load_path(LAUNDRY)
        win.comparison.export_path(tmp_path / "out.csv")
        check_csv((tmp_path / "out.csv").read_text(encoding="utf-8"))
        win.comparison.export_path(tmp_path / "out.md")
        assert "## «Details»" in (tmp_path / "out.md").read_text(encoding="utf-8")
    finally:
        win.close()
        store.close()


def test_report_in_window_language(russian):
    found = project()
    texts = [t.text for page in report.pages(found) for t in page.texts]
    assert f"{found.name} · «Answer»" in texts
    assert "«Executor coefficients»" in texts
    assert "«Executor»" in texts
    assert not any(t == "Executor coefficients" for t in texts)


def test_report_english_without_translation(app):
    found = project()
    texts = [t.text for page in report.pages(found) for t in page.texts]
    assert f"{found.name} · Answer" in texts
    assert MARK not in "".join(texts)


def test_data_copy_keeps_english():
    data = laundry()
    data["entities"][0]["colour"] = 1
    remark = next(r for r in remarks_of(data) if "colour" in r.text)
    assert copy.deepcopy(remark) == remark
