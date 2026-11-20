"""Tests of the Greek prompts and instructions for the AI chat (piece 34).

The file is chosen by the window language, as for Russian. The Greek prompts keep the steps and
the placeholders of the English ones, the Greek instructions keep the structure of the English
ones, and the keys of the file format stay English.
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
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
FILE_PROMPT_LIMIT = 5000
TASK_FIELD_CAP = 1000
JSON_BLOCK = re.compile(r"^```json\n(.*?)^```", re.DOTALL | re.MULTILINE)


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
                                   "axis_skip_prices/*", "named_slices",
                                   "uncounted_errors"))
            if not named:
                out.add(key)
            out |= _keys(item, path + "/" + ("*" if named else key))
    elif isinstance(value, list):
        for item in value:
            out |= _keys(item, path)
    return out


def _outline(text: str) -> list[str]:
    """The skeleton of a Markdown text: heading levels and numbers, table rows, code fences."""
    out = []
    for line in text.splitlines():
        heading = re.match(r"^(#+) ([\d.]*)", line)
        if heading:
            out.append(heading.group(1) + " " + heading.group(2))
        elif line.startswith("|"):
            out.append("|" * line.count(" | "))
        elif line.startswith("```"):
            out.append(line)
    return out


def test_files_are_chosen_by_language():
    assert prompts_file("el") == DATA / "ai_prompts_el.md"
    assert instructions_file("el") == DATA / "ai_instructions_el.md"


def test_greek_instructions_keep_the_english_structure():
    english = instructions("en")
    greek = instructions("el")
    assert greek == (DATA / "ai_instructions_el.md").read_text(encoding="utf-8")
    assert GREEK.search(greek)
    assert _outline(greek) == _outline(english)
    assert len(greek.splitlines()) == len(english.splitlines())


def test_greek_instructions_example_keeps_the_english_keys_and_loads():
    english_blocks = JSON_BLOCK.findall(instructions("en"))
    greek_blocks = JSON_BLOCK.findall(instructions("el"))
    assert len(greek_blocks) == len(english_blocks)
    english = json.loads(english_blocks[-1])
    greek = json.loads(greek_blocks[-1])
    assert _keys(greek) == _keys(english)
    project, remarks = parse_text(json.dumps(greek, ensure_ascii=False))
    assert remarks == []
    assert GREEK.search(project.name)


def test_greek_prompts_have_the_same_steps_and_placeholders():
    english = prompts("en")
    greek = prompts("el")
    assert [p.number for p in greek] == [p.number for p in english]
    for en, el in zip(english, greek):
        assert sorted(PLACEHOLDER.findall(el.text)) == sorted(PLACEHOLDER.findall(en.text))
        assert GREEK.search(el.name) and GREEK.search(el.note) and GREEK.search(el.text)


def test_greek_prompts_fit_the_limits():
    greek = prompts("el")
    for prompt in greek:
        assert len(prompt.text) <= PROMPT_LIMIT, prompt.number
    assert len(greek[4].text) <= FILE_PROMPT_LIMIT
    assert task_limit("el") >= TASK_FIELD_CAP


def test_greek_example_keeps_the_english_keys_and_loads():
    english = _example(prompts("en")[4].text)
    greek = _example(prompts("el")[4].text)
    assert _keys(greek) == _keys(english)
    project, remarks = parse_text(json.dumps(greek, ensure_ascii=False))
    assert remarks == []
    assert GREEK.search(project.name)


def test_greek_file_prompt_marks_code_as_required():
    """The loader refuses a variant without a code, so prompt 5 says the field is required."""
    text = prompts("el")[4].text
    assert 'variants: {"code"*' in text
    assert len(text) <= FILE_PROMPT_LIMIT


def test_greek_task_and_remarks_prompts():
    text = task_prompt("Η βρύση στάζει.", "el")
    assert "Η βρύση στάζει." in text and "{task}" not in text
    text = remarks_prompt(["πρώτη", "δεύτερη"], "el")
    assert "πρώτη\nδεύτερη" in text and "{remarks}" not in text


def test_greek_remarks_are_cut_with_a_greek_tail():
    many = [f"παρατήρηση αριθμός {i} " + "x" * 80 for i in range(200)]
    text = remarks_prompt(many, "el")
    assert len(text) <= PROMPT_LIMIT
    assert re.search(r"^και \d+ ακόμη$", text, re.MULTILINE)
    assert "more" not in text


def test_scenario_shows_prompts_of_the_greek_window(app, monkeypatch):
    monkeypatch.setattr(i18n, "_current", "el")
    dialog = AiScenarioDialog(lambda text: (False, []))
    try:
        greek = prompts("el")
        assert dialog.cards[1].title.text() == f"2. {greek[1].name}"
        assert dialog.prompt_text(2) == greek[1].text
        dialog.task.setPlainText("Η βρύση στάζει.")
        assert dialog.prompt_text(1) == task_prompt("Η βρύση στάζει.", "el")
    finally:
        dialog.close()


def test_step_six_carries_the_remarks_in_greek(app, tmp_path):
    built = i18n.build_qm(out=tmp_path)
    if not built:
        pytest.skip("pyside6-lrelease is not installed")
    store = Store(tmp_path / "t.db")
    i18n.apply_language(app, "el", tmp_path)
    try:
        win = MainWindow(store)
        dialog = win.ai_scenario()
        broken = (DOCS / "example_tap.json").read_text(encoding="utf-8")
        broken = broken.replace('"entity": "Tap"', '"entity": "No such entity"', 1)
        dialog.answer.setPlainText(broken)
        dialog.load()
        text = dialog.prompt_text(6)
        assert text.startswith(prompts("el")[5].text.split("{remarks}")[0])
        remark_lines = text.split("\n")
        assert any("No such entity" in line and GREEK.search(line) for line in remark_lines)
        dialog.close()
        win.close()
    finally:
        i18n.apply_language(app, "en", tmp_path)
        store.close()
