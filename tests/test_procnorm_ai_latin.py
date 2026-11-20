"""The customer's decision: the abbreviation for artificial intelligence is «AI» in Latin."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "measure_twice" / "i18n"
DATA = ROOT / "measure_twice" / "data"
LANGUAGES = ("ru", "el")

# The abbreviation as a whole word: Cyrillic ИИ, Greek ΤΝ, also «Τ.Ν.» and «Τ. Ν.».
ABBREVIATION = re.compile(r"(?<!\w)(?:ИИ|ии|ΤΝ|Τ\.\s?Ν\.?)(?!\w)", re.IGNORECASE)
LATIN = re.compile(r"(?<!\w)AI(?!\w)")


def _messages(language):
    tree = ET.parse(I18N / f"measure_twice_{language}.ts")
    return list(tree.iter("message"))


def _data_files(language):
    return [
        DATA / f"ai_prompts_{language}.md",
        DATA / f"ai_instructions_{language}.md",
        DATA / f"example_{language}.json",
        ROOT / "docs" / f"example_tap_description_{language}.txt",
    ]


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_cyrillic_or_greek_abbreviation_in_ts(language):
    found = []
    for message in _messages(language):
        for tag in ("translation", "translatorcomment"):
            text = message.findtext(tag) or ""
            if ABBREVIATION.search(text):
                found.append((message.findtext("source"), tag))
    assert not found


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_cyrillic_or_greek_abbreviation_in_data(language):
    for path in _data_files(language):
        if path.exists():
            assert not ABBREVIATION.search(path.read_text(encoding="utf-8")), path.name


@pytest.mark.parametrize("language", LANGUAGES)
def test_window_strings_with_ai_keep_ai(language):
    checked = 0
    for message in _messages(language):
        source = message.findtext("source") or ""
        translation = message.findtext("translation") or ""
        if LATIN.search(source):
            checked += 1
            assert LATIN.search(translation), source
    assert checked >= 7


@pytest.mark.parametrize("language", LANGUAGES)
def test_prompts_say_ai(language):
    text = (DATA / f"ai_prompts_{language}.md").read_text(encoding="utf-8")
    assert LATIN.search(text)
