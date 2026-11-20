"""Test of the Russian translation of the window (piece 29).

`lrelease` finds no unfinished or untranslated string in ``measure_twice_ru.ts``; every
translation keeps the placeholders of its source; every message with a number has the three
Russian plural forms.
"""

import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from measure_twice import i18n

TS = Path(__file__).parent.parent / "measure_twice" / "i18n" / "measure_twice_ru.ts"
# {name}, {} and %n, %1: what the code fills in.
PLACEHOLDER = re.compile(r"\{[A-Za-z_]*\}|%n|%\d")


def _messages() -> list[ET.Element]:
    return list(ET.parse(TS).getroot().iter("message"))


def _forms(message: ET.Element) -> list[str]:
    translation = message.find("translation")
    if message.get("numerus") == "yes":
        return [form.text or "" for form in translation.findall("numerusform")]
    return [translation.text or ""]


def test_lrelease_finds_nothing_untranslated(tmp_path: Path) -> None:
    tool = i18n._lrelease()
    if tool is None:
        pytest.skip("pyside6-lrelease is not installed")
    done = subprocess.run(
        [tool, str(TS), "-qm", str(tmp_path / "ru.qm")],
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


def test_numerus_messages_have_three_forms() -> None:
    wrong = [
        m.findtext("source")
        for m in _messages()
        if m.get("numerus") == "yes" and len([f for f in _forms(m) if f.strip()]) != 3
    ]
    assert wrong == []
