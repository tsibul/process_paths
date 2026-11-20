"""Path codes in the AI prompts and instructions (piece 41).

Codes given in the task are kept; new paths continue the series; codes are Latin everywhere.
"""

import re
from pathlib import Path

import pytest

from measure_twice import ai
from measure_twice.ai import prompts, task_limit

DATA = Path(ai.__file__).parent / "data"
LANGS = ("en", "ru", "el")
CODE_VALUE = re.compile(r'"code"\s*:\s*"([^"]*)"')
CODE_LIST = re.compile(r"(?:[:·]|αλλιώς) ((?:\w, ){2,3}\.\.\.)")
TABLE_ROW = re.compile(r"^\| (\S) [^|]+ \| \d", re.MULTILINE)
QUOTED = re.compile(r"[«\"]([А-ЯΑ-Ω])[»\"]")


def read(kind, lang):
    return (DATA / f"ai_{kind}_{lang}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", LANGS)
def test_prompt_1_keeps_given_codes(lang):
    text = prompts(lang)[0].text
    assert "T1" in text and "T5" in text and "T4" in text


@pytest.mark.parametrize("lang", LANGS)
def test_prompt_1_leaves_room_for_task(lang):
    assert task_limit(lang) >= 1000


@pytest.mark.parametrize("lang", LANGS)
def test_prompt_5_within_limit_and_keeps_rule(lang):
    text = prompts(lang)[4].text
    assert len(text) <= 5000
    assert "T5" in text


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", ("prompts", "instructions"))
def test_code_values_are_latin(lang, kind):
    values = CODE_VALUE.findall(read(kind, lang))
    assert values
    for value in values:
        assert value.isascii(), value


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", ("prompts", "instructions"))
def test_code_lists_are_latin(lang, kind):
    text = read(kind, lang)
    for lists in CODE_LIST.findall(text):
        assert lists.isascii(), lists
    for letter in TABLE_ROW.findall(text):
        assert letter.isascii(), letter
    for letter in QUOTED.findall(text):
        assert letter.isascii(), letter


@pytest.mark.parametrize("lang", LANGS)
def test_instructions_do_not_say_remarks_are_english(lang):
    text = read("instructions", lang).lower()
    for phrase in ("on english", "in english", "στα αγγλικά", "на английском"):
        for line in text.splitlines():
            if "remark" in line or "замечан" in line or "παρατηρ" in line:
                assert phrase not in line, line
