"""Test of the Greek translation of the window (piece 32).

`lrelease` finds no unfinished or untranslated string in ``measure_twice_el.ts``; every
translation keeps the placeholders of its source; every message with a number has the two
Greek plural forms; the fonts of the window and of the PDF report draw every Greek letter of
the translation, and the report written in Greek holds the Greek text.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest
from PySide6.QtGui import QFontDatabase, QRawFont
from PySide6.QtWidgets import QApplication

from measure_twice import i18n, report
from measure_twice.project import load_file
from measure_twice.ui.tables import mono

TS = Path(__file__).parent.parent / "measure_twice" / "i18n" / "measure_twice_el.ts"
LAUNDRY = Path(__file__).parent / "data" / "laundry.json"
# {name}, {} and %n, %1: what the code fills in.
PLACEHOLDER = re.compile(r"\{[A-Za-z_]*\}|%n|%\d")
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
# Kept in Latin letters: a key name and the filters of file kinds.
LATIN = {"Esc", "Markdown (*.md)", "CSV (*.csv)", "PDF (*.pdf)"}
# A translation kept in Latin letters: «OK» of the narrow button, as in Greek Windows.
LATIN_TRANSLATION = {"OK"}


def _messages() -> list[ET.Element]:
    return list(ET.parse(TS).getroot().iter("message"))


def _forms(message: ET.Element) -> list[str]:
    translation = message.find("translation")
    if message.get("numerus") == "yes":
        return [form.text or "" for form in translation.findall("numerusform")]
    return [translation.text or ""]


def _greek_letters() -> set[str]:
    return {c for m in _messages() for form in _forms(m) for c in GREEK.findall(form)}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def greek(app, tmp_path):
    """The application in Greek, from a `.qm` built into a temporary folder."""
    if i18n._lrelease() is None:
        pytest.skip("pyside6-lrelease is not installed")
    assert i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, "el", tmp_path)
    yield app
    i18n.apply_language(app, i18n.SOURCE, tmp_path)


def test_lrelease_finds_nothing_untranslated(tmp_path: Path) -> None:
    tool = i18n._lrelease()
    if tool is None:
        pytest.skip("pyside6-lrelease is not installed")
    done = subprocess.run(
        [tool, str(TS), "-qm", str(tmp_path / "el.qm")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert re.search(r"\(\d+ finished and 0 unfinished\)", out), out
    assert "untranslated" not in out, out


def test_every_message_is_finished() -> None:
    unfinished = [
        m.findtext("source")
        for m in _messages()
        if m.find("translation").get("type") in ("unfinished", "vanished", "obsolete")
    ]
    assert unfinished == []


def test_translations_keep_the_placeholders() -> None:
    wrong = []
    for m in _messages():
        source = Counter(PLACEHOLDER.findall(m.findtext("source")))
        for form in _forms(m):
            if not form.strip() or Counter(PLACEHOLDER.findall(form)) != source:
                wrong.append((m.findtext("source"), form))
    assert wrong == []


def test_numerus_messages_have_two_forms() -> None:
    wrong = [
        m.findtext("source")
        for m in _messages()
        if m.get("numerus") == "yes" and len([f for f in _forms(m) if f.strip()]) != 2
    ]
    assert wrong == []


def test_words_are_greek() -> None:
    """A source with an English word is not left in Latin letters."""
    latin = [
        m.findtext("source")
        for m in _messages()
        if LATIN_WORD.search(m.findtext("source"))
        and m.findtext("source") not in LATIN
        and not all(GREEK.search(f) or f in LATIN_TRANSLATION for f in _forms(m))
    ]
    assert latin == []


def test_fonts_draw_every_greek_letter(app) -> None:
    letters = _greek_letters()
    assert letters
    fonts = {
        "window": QApplication.font(),
        "mono": mono(),
        "report": report.font(report.BODY),
        "report bold": report.font(report.TITLE, True),
    }
    for name, f in fonts.items():
        raw = QRawFont.fromFont(f, QFontDatabase.WritingSystem.Greek)
        assert raw.isValid(), name
        missing = sorted(c for c in letters if not raw.supportsCharacter(ord(c)))
        assert missing == [], (name, raw.familyName())


def test_pdf_report_holds_greek_text(greek, tmp_path) -> None:
    from PySide6.QtPdf import QPdfDocument

    project, remarks = load_file(LAUNDRY)
    assert project is not None, remarks
    heading = next(t.text for t in report.pages(project)[0].texts if GREEK.search(t.text))
    path = tmp_path / "report.pdf"
    report.write(project, path)
    doc = QPdfDocument(None)
    assert doc.load(str(path)) == QPdfDocument.Error.None_
    text = "".join(doc.getAllText(i).text() for i in range(doc.pageCount()))
    doc.close()
    assert GREEK.search(text)
    assert heading.split()[0] in text
