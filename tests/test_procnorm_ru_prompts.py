"""Tests of the Russian prompts and instructions for the AI chat (piece 31).

The file is chosen by the window language; a language without its file gets the English one.
The Russian prompts keep the steps and the placeholders of the English ones, and the keys of the
file format stay English.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from measure_twice import ai, i18n
from measure_twice.ai import (
    PROMPT_LIMIT,
    extract_json,
    instructions,
    instructions_file,
    prompts,
    prompts_file,
    remarks_prompt,
    task_limit,
    task_prompt,
)
from measure_twice.project import parse_text
from measure_twice.store import Store
from measure_twice.ui.ai_scenario import AiScenarioDialog
from measure_twice.ui.app import MainWindow

DATA = Path(ai.__file__).parent / "data"
DOCS = Path(__file__).parent.parent / "docs"
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
FILE_PROMPT_LIMIT = 5000
TASK_FIELD_CAP = 1000


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _example(text: str) -> dict:
    """The example object of prompt 5."""
    return json.loads(extract_json(text[text.index('{"format"'):]))


def _keys(value, path="") -> set[str]:
    """The keys of the format in an example: object keys under the format's own fields."""
    out = set()
    if isinstance(value, dict):
        for key, item in value.items():
            named = path.endswith(("kind_costs", "executor_coefficients",
                                   "scope_coefficients", "axis_skip_prices",
                                   "axis_skip_prices/*", "named_slices"))
            if not named:
                out.add(key)
            out |= _keys(item, path + "/" + ("*" if named else key))
    elif isinstance(value, list):
        for item in value:
            out |= _keys(item, path)
    return out


def test_files_are_chosen_by_language():
    assert prompts_file("ru") == DATA / "ai_prompts_ru.md"
    assert instructions_file("ru") == DATA / "ai_instructions_ru.md"
    assert prompts_file("en") == DATA / "ai_prompts_en.md"
    assert instructions_file("en") == DATA / "ai_instructions_en.md"


def test_language_without_files_falls_back_to_english():
    assert prompts_file("xx") == DATA / "ai_prompts_en.md"
    assert instructions_file("xx") == DATA / "ai_instructions_en.md"
    assert [p.text for p in prompts("xx")] == [p.text for p in prompts()]


def test_russian_instructions_are_the_russian_format_text():
    assert instructions("ru") == (DOCS / "input_format_ru.md").read_text(encoding="utf-8")
    assert instructions() == (DOCS / "input_format_en.md").read_text(encoding="utf-8")


def test_russian_prompts_have_the_same_steps_and_placeholders():
    english = prompts("en")
    russian = prompts("ru")
    assert [p.number for p in russian] == [p.number for p in english]
    for en, ru in zip(english, russian):
        assert sorted(PLACEHOLDER.findall(ru.text)) == sorted(PLACEHOLDER.findall(en.text))
        assert CYRILLIC.search(ru.name) and CYRILLIC.search(ru.note) and CYRILLIC.search(ru.text)


def test_russian_prompts_fit_the_limits():
    russian = prompts("ru")
    for prompt in russian:
        assert len(prompt.text) <= PROMPT_LIMIT, prompt.number
    assert len(russian[4].text) <= FILE_PROMPT_LIMIT
    assert task_limit("ru") >= TASK_FIELD_CAP


def test_russian_example_keeps_the_english_keys_and_loads():
    english = _example(prompts("en")[4].text)
    russian = _example(prompts("ru")[4].text)
    assert _keys(russian) == _keys(english)
    project, remarks = parse_text(json.dumps(russian, ensure_ascii=False))
    assert remarks == []
    assert CYRILLIC.search(project.name)


def test_russian_task_and_remarks_prompts():
    text = task_prompt("Течёт кран.", "ru")
    assert "Течёт кран." in text and "{task}" not in text
    text = remarks_prompt(["первое", "второе"], "ru")
    assert "первое\nвторое" in text and "{remarks}" not in text


def test_russian_remarks_are_cut_with_a_russian_tail():
    many = [f"замечание номер {i} " + "x" * 80 for i in range(200)]
    text = remarks_prompt(many, "ru")
    assert len(text) <= PROMPT_LIMIT
    assert re.search(r"^и ещё \d+$", text, re.MULTILINE)
    assert "more" not in text


def test_scenario_shows_prompts_of_the_window_language(app, tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_current", "ru")
    dialog = AiScenarioDialog(lambda text: (False, []))
    try:
        russian = prompts("ru")
        assert dialog.cards[1].title.text() == f"2. {russian[1].name}"
        assert dialog.prompt_text(2) == russian[1].text
        dialog.task.setPlainText("Течёт кран.")
        assert dialog.prompt_text(1) == task_prompt("Течёт кран.", "ru")
    finally:
        dialog.close()


def test_scenario_in_english_keeps_english_prompts(app):
    dialog = AiScenarioDialog(lambda text: (False, []))
    try:
        assert dialog.prompt_text(2) == prompts("en")[1].text
    finally:
        dialog.close()


def test_step_six_carries_the_remarks_in_russian(app, tmp_path):
    built = i18n.build_qm(out=tmp_path)
    if not built:
        pytest.skip("pyside6-lrelease is not installed")
    store = Store(tmp_path / "t.db")
    i18n.apply_language(app, "ru", tmp_path)
    try:
        win = MainWindow(store)
        dialog = win.ai_scenario()
        broken = (DOCS / "example_tap.json").read_text(encoding="utf-8")
        broken = broken.replace('"entity": "Tap"', '"entity": "No such entity"', 1)
        dialog.answer.setPlainText(broken)
        dialog.load()
        text = dialog.prompt_text(6)
        assert text.startswith(prompts("ru")[5].text.split("{remarks}")[0])
        assert "No such entity" in text
        remark_lines = text.split("\n")
        assert any("No such entity" in line and CYRILLIC.search(line) for line in remark_lines)
        dialog.close()
        win.close()
    finally:
        i18n.apply_language(app, "en", tmp_path)
        store.close()


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_file_prompt_marks_code_as_required(lang):
    """The loader refuses a variant without a code, so prompt 5 says the field is required."""
    text = prompts(lang)[4].text
    assert 'variants: {"code"*' in text
    assert len(text) <= FILE_PROMPT_LIMIT
