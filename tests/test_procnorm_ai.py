"""Tests of the AI request text, the six prompts, the JSON extraction and the AI scenario screen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog

from measure_twice.ai import (
    INSTRUCTIONS_FILE,
    PROMPT_LIMIT,
    PROMPTS_FILE,
    extract_json,
    instructions,
    parse_prompts,
    prompts,
    remarks_prompt,
    request_text,
    task_limit,
    task_prompt,
)
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

DOCS = Path(__file__).parent.parent / "docs"
EXAMPLE = DOCS / "example_tap.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store):
    w = MainWindow(store)
    yield w
    w.close()


def _example_text(name: str = "Change a bike tyre") -> str:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["name"] = name
    return json.dumps(data, ensure_ascii=False, indent=2)


def _broken_text() -> str:
    data = json.loads(_example_text())
    data["kinds"][0]["entity"] = "No such entity"
    return json.dumps(data, ensure_ascii=False)


# --- the request text


def test_packaged_instructions_equal_docs_format():
    docs = DOCS / "input_format_en.md"
    assert INSTRUCTIONS_FILE.read_bytes() == docs.read_bytes()


def test_instructions_are_the_format_text():
    expected = (DOCS / "input_format_en.md").read_text(encoding="utf-8")
    assert instructions() == expected


def test_request_text_puts_description_after_instructions():
    text = request_text("We repaint a fence.\nTwo people.")
    head = instructions().rstrip("\n")
    assert text == head + "\n\nMy process:\nWe repaint a fence.\nTwo people."


# --- the six prompts

PROMPTS_MD = """# Some title

Intro text.

## Prompt 1. Start

Use it first.

```text
Line one {task}
Line two
```

## Prompt 2. Finish

Use it last.

```text
Fix:
{remarks}
```
"""


def test_packaged_prompts_equal_docs_prompts():
    assert PROMPTS_FILE.read_bytes() == (DOCS / "ai_prompts_en.md").read_bytes()


def test_parse_prompts_takes_number_name_note_and_text():
    found = parse_prompts(PROMPTS_MD)
    assert [(p.number, p.name, p.note) for p in found] == [
        (1, "Start", "Use it first."),
        (2, "Finish", "Use it last."),
    ]
    assert found[0].text == "Line one {task}\nLine two"
    assert found[1].text == "Fix:\n{remarks}"


def test_six_prompts_from_the_packaged_file():
    found = prompts()
    assert [p.number for p in found] == [1, 2, 3, 4, 5, 6]
    assert [p.name for p in found] == [
        "Task",
        "Steps",
        "Same actions and checks",
        "Who and how much",
        "File",
        "Remarks",
    ]
    assert found[1].note == "Use it when the list of ways is agreed."
    assert found[0].text.startswith("We will prepare a file for Measure Twice")
    assert "{task}" in found[0].text
    assert "{remarks}" in found[5].text
    assert found[4].text.startswith("Step 5. File.")
    assert '"normalization": {' in found[4].text
    assert not found[4].text.endswith("```")


def test_prompt_one_marks_added_ways_in_the_title():
    text = prompts()[0].text
    assert 'End the title of each added way with "(added)"' in text
    assert "action names get no mark" in text
    assert "through our conversation" in text


def test_prompt_two_names_steps_not_in_my_words():
    text = prompts()[1].text
    assert "the steps you added that are not in my words" in text


def test_prompt_three_takes_a_check_from_my_words():
    text = prompts()[2].text
    assert "If my words call an action a check, it is a check." in text
    assert "A check changes an attribute of its own, not the state it looks at" in text
    assert "Diagnosis and finding the cause are ordinary actions" not in text


def test_prompt_four_marks_waiting_instead_of_asking():
    text = prompts()[3].text
    assert "ask me for each" not in text
    assert 'mark each with "?"' in text


def test_prompt_four_warns_about_added_steps():
    text = prompts()[3].text
    assert "If steps not in my words change a way's total noticeably" in text


def test_prompt_four_scales_skip_price_to_the_fix():
    text = prompts()[3].text
    assert "comparable to the work of fixing what the skip lets through" in text


def test_prompt_one_requires_added_ways_to_differ_in_actions():
    text = " ".join(prompts()[0].text.split())
    assert "An added way must differ from the others in its actions." in text


def test_prompt_three_makes_a_leaving_part_absent_not_new():
    text = prompts()[2].text
    assert "never add a new thing for the old part" in text
    assert "make the same thing absent with its exists attribute" in text


def test_prompt_five_keeps_way_codes_and_drops_paying_line():
    text = prompts()[4].text
    assert '"code"* (keep given; new: T5 after T4; none: A, B, C, ...)' in text
    assert "Paying is not labour: no kind for it." not in text


def test_task_prompt_fills_the_task():
    text = task_prompt("We wash a car.")
    assert "My task: We wash a car.\n" in text
    assert "{task}" not in text


def test_remarks_prompt_puts_one_remark_per_line():
    text = remarks_prompt(["kind A: bad", "variant B: worse"])
    assert "Its remarks:\nkind A: bad\nvariant B: worse\n" in text
    assert "{remarks}" not in text


def test_prompt_limit_is_six_thousand():
    assert PROMPT_LIMIT == 6000


def test_every_prompt_fits_the_limit():
    for prompt in prompts():
        assert len(prompt.text) <= PROMPT_LIMIT


def test_task_limit_fills_prompt_one_to_the_limit():
    limit = task_limit()
    assert limit > 0
    assert len(task_prompt("x" * limit)) == PROMPT_LIMIT


def test_few_remarks_go_in_whole():
    lines = [f"variant V{i}: a made-up remark" for i in range(5)]
    text = remarks_prompt(lines)
    assert "\n".join(lines) in text
    assert "more" not in text.replace("Its remarks:", "")


def test_many_remarks_are_cut_with_and_more():
    lines = [f"variant V{i}: " + "a made-up remark " * 5 for i in range(200)]
    text = remarks_prompt(lines)
    assert len(text) <= PROMPT_LIMIT
    head, rest = text.split("Its remarks:\n", 1)
    shown = rest.split("\n")
    kept = next(i for i, line in enumerate(shown) if line.startswith("and "))
    assert 0 < kept < 200
    assert shown[:kept] == lines[:kept]
    assert shown[kept] == f"and {200 - kept} more"
    tail = f"and {200 - kept} more"
    one_more = text.replace(tail, lines[kept] + "\n" + f"and {200 - kept - 1} more")
    assert len(one_more) > PROMPT_LIMIT


# --- extracting the JSON


def test_extract_bare_object():
    assert extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_fence_with_chat_around():
    text = 'Here is your file:\n```json\n{"a": {"b": 2}}\n```\nTell me if it loads.'
    assert extract_json(text) == '{"a": {"b": 2}}'


def test_extract_plain_fence_starting_with_brace():
    text = 'Sure.\n```\n{"a": 1}\n```\n'
    assert extract_json(text) == '{"a": 1}'


def test_plain_fence_without_brace_is_skipped():
    text = 'Run:\n```\npip install x\n```\nThen {"a": 1} done.'
    assert extract_json(text) == '{"a": 1}'


def test_extract_object_with_text_before_and_after():
    text = 'The answer is {"a": [1, 2], "b": {}} and that is all.'
    assert extract_json(text) == '{"a": [1, 2], "b": {}}'


def test_extract_braces_inside_strings():
    text = 'x {"a": "}{ \\" }", "b": "{"} y'
    assert extract_json(text) == '{"a": "}{ \\" }", "b": "{"}'


def test_extract_nothing_found():
    assert extract_json("No object here, sorry.") is None
    assert extract_json("An open { never closed") is None


# --- the entry button


def test_ai_item_first_in_new_menu(win):
    texts = [a.text() for a in win.new_menu.actions()]
    assert texts[0] == "With AI…"
    assert texts[-1] == "Example"
    assert "Ask AI" not in texts
    assert "Paste answer" not in texts
    assert win.example_action.toolTip() == "Add the Fix a leaking tap example"
    assert win.example_action.isEnabled()


# --- loading an answer


def test_button_row_fits_the_default_width(win):
    win.show()
    QApplication.processEvents()
    right = win.more_menu_button.mapTo(win, win.more_menu_button.rect().topRight()).x()
    assert right < win.width()
    assert win.width() >= 1100
    assert win.width() == max(1100, win.minimumSizeHint().width())


def test_load_text_adds_project(win, store):
    ok, message = win.load_text("Done:\n```json\n" + _example_text() + "\n```\n")
    assert ok
    assert message == "Loaded Change a bike tyre"
    assert win.project_names() == ["Change a bike tyre"]


# --- the scenario screen


NOTES = [
    "Describe the job in one or two sentences, then copy the prompt into your AI chat.",
    "Use it when you have agreed on the list of ways.",
    "Use it when you have agreed on the steps of each way.",
    "Use it when you have agreed on the actions and the checks.",
    "Use it when you have agreed who does what and how long it takes.",
    "The program found problems in the file. Copy this prompt into the same chat.",
]
TASK = "We change a bike tyre: patch the tube, fit a new tube, ask a shop."


def _scenario(win):
    dlg = win.ai_scenario()
    dlg.show()
    return dlg


def _states(dlg) -> list[str]:
    return [card.state for card in dlg.cards]


def _copy_and_next(dlg, number):
    card = dlg.cards[number - 1]
    card.copy_button.click()
    card.next_button.click()


def _to_step_five(dlg):
    dlg.task.setPlainText(TASK)
    for number in (1, 2, 3, 4):
        _copy_and_next(dlg, number)


def test_scenario_opens_at_step_one(win):
    dlg = _scenario(win)
    assert dlg.windowTitle() == "Add a process with AI"
    assert [card.title.text() for card in dlg.cards] == [
        "1. Task",
        "2. Steps",
        "3. Same actions and checks",
        "4. Who and how much",
        "5. File",
        "6. Remarks",
    ]
    assert _states(dlg) == ["current", "future", "future", "future", "future", "future"]
    first = dlg.cards[0]
    assert first.note.text() == NOTES[0]
    assert first.prompt_view.isVisible()
    assert first.prompt_view.isReadOnly()
    assert dlg.task.isVisible()
    assert first.copy_button.text() == "Copy prompt"
    assert not first.copy_button.isEnabled()
    assert not first.next_button.isVisible()
    for card in dlg.cards[1:]:
        assert not card.prompt_view.isVisible()
        assert not card.again_button.isVisible()
    dlg.close()


def test_task_fills_prompt_one_and_copy(win):
    dlg = _scenario(win)
    first = dlg.cards[0]
    dlg.task.setPlainText(TASK)
    assert first.prompt_view.toPlainText() == task_prompt(TASK)
    assert first.copy_button.isEnabled()
    first.copy_button.click()
    assert QGuiApplication.clipboard().text() == task_prompt(TASK)
    assert first.copied.text() == "✓ Copied. Paste it into your AI chat."
    assert first.copied.isVisible()
    assert first.next_button.isVisible()
    assert first.next_button.text() == "Next step"
    dlg.close()


def test_header_notes_are_the_screen_wording(win):
    dlg = _scenario(win)
    assert [card.note.text() for card in dlg.cards] == NOTES
    dlg.close()


def test_task_field_is_held_to_the_limit(win):
    dlg = _scenario(win)
    limit = task_limit()
    assert dlg.task_left.text() == f"{limit} characters left"
    assert dlg.task_left.isVisible()
    dlg.task.setPlainText("We wash a car.")
    assert dlg.task_left.text() == f"{limit - 14} characters left"
    dlg.task.setPlainText("y" * (limit + 50))
    assert dlg.task.toPlainText() == "y" * limit
    assert dlg.task_left.text() == "0 characters left"
    assert len(dlg.cards[0].prompt_view.toPlainText()) == PROMPT_LIMIT
    dlg.close()


def test_next_step_folds_the_done_step(win):
    dlg = _scenario(win)
    dlg.task.setPlainText(TASK)
    _copy_and_next(dlg, 1)
    assert _states(dlg) == ["done", "current", "future", "future", "future", "future"]
    first, second = dlg.cards[0], dlg.cards[1]
    assert first.mark.text() == "✓"
    assert first.summary.text() == TASK
    assert first.again_button.isVisible()
    assert first.again_button.text() == "Show prompt again"
    assert not first.prompt_view.isVisible()
    assert not dlg.task.isVisible()
    assert second.prompt_view.toPlainText() == prompts()[1].text
    assert not second.next_button.isVisible()
    second.copy_button.click()
    assert QGuiApplication.clipboard().text() == prompts()[1].text
    _copy_and_next(dlg, 2)
    assert _states(dlg) == ["done", "done", "current", "future", "future", "future"]
    assert dlg.cards[1].summary.text() == "Prompt copied"
    dlg.close()


def test_show_prompt_again_opens_and_copies(win):
    dlg = _scenario(win)
    dlg.task.setPlainText(TASK)
    _copy_and_next(dlg, 1)
    first = dlg.cards[0]
    first.again_button.click()
    assert first.prompt_view.isVisible()
    assert first.prompt_view.toPlainText() == task_prompt(TASK)
    assert first.again_button.text() == "Hide prompt"
    assert not first.next_button.isVisible()
    assert not dlg.task.isVisible()
    QGuiApplication.clipboard().setText("")
    first.copy_button.click()
    assert QGuiApplication.clipboard().text() == task_prompt(TASK)
    assert _states(dlg) == ["done", "current", "future", "future", "future", "future"]
    first.again_button.click()
    assert not first.prompt_view.isVisible()
    assert first.again_button.text() == "Show prompt again"
    dlg.close()


def test_step_five_has_answer_field_and_load(win):
    dlg = _scenario(win)
    _to_step_five(dlg)
    assert _states(dlg) == ["done", "done", "done", "done", "current", "future"]
    fifth = dlg.cards[4]
    assert fifth.prompt_view.toPlainText() == prompts()[4].text
    assert dlg.answer.isVisible()
    assert dlg.load_button.isVisible()
    assert dlg.load_button.text() == "Load file"
    assert not fifth.next_button.isVisible()
    assert not dlg.error.isVisible()
    dlg.close()


def test_load_without_json_stays_at_step_five(win, store):
    dlg = _scenario(win)
    _to_step_five(dlg)
    dlg.answer.setPlainText("I could not make the file.")
    dlg.load_button.click()
    assert dlg.isVisible()
    assert dlg.error.isVisible()
    assert dlg.error.text() == "No JSON object found in the text."
    assert dlg.error.objectName() == "err"
    assert _states(dlg) == ["done", "done", "done", "done", "current", "future"]
    assert store.list() == []
    dlg.close()


def test_refused_file_opens_step_six(win, store):
    dlg = _scenario(win)
    _to_step_five(dlg)
    dlg.answer.setPlainText("```json\n" + _broken_text() + "\n```")
    dlg.load_button.click()
    assert dlg.isVisible()
    assert store.list() == []
    assert _states(dlg) == ["done", "done", "done", "done", "done", "current"]
    assert dlg.cards[4].summary.text() == "Not accepted: 1 remark"
    sixth = dlg.cards[5]
    expected = remarks_prompt(["kind Shut off water: unknown entity No such entity"])
    assert sixth.prompt_view.toPlainText() == expected
    sixth.copy_button.click()
    assert QGuiApplication.clipboard().text() == expected
    assert dlg.back_button.isVisible()
    assert dlg.back_button.text() == "Back to step 5"
    assert not sixth.next_button.isVisible()
    dlg.close()


def test_back_to_step_five_and_load_the_fixed_file(win, store):
    dlg = _scenario(win)
    _to_step_five(dlg)
    dlg.answer.setPlainText(_broken_text())
    dlg.load_button.click()
    dlg.back_button.click()
    assert _states(dlg) == ["done", "done", "done", "done", "current", "future"]
    assert dlg.answer.isVisible()
    assert dlg.answer.toPlainText() == ""
    dlg.answer.setPlainText("Fixed:\n```json\n" + _example_text() + "\n```\n")
    dlg.load_button.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert not dlg.isVisible()
    infos = store.list()
    assert [i.name for i in infos] == ["Change a bike tyre"]
    assert win.current_id == infos[0].id
    assert win.projects.currentText() == "Change a bike tyre"
    assert win.offer_visible()
    assert win.statusBar().currentMessage() == "Loaded Change a bike tyre"


def test_closed_scenario_keeps_its_place(win):
    dlg = _scenario(win)
    dlg.task.setPlainText(TASK)
    _copy_and_next(dlg, 1)
    dlg.close_button.click()
    assert not dlg.isVisible()
    again = win.ai_scenario()
    assert again is dlg
    assert _states(again) == ["done", "current", "future", "future", "future", "future"]


def test_scenario_starts_anew_after_a_load(win):
    dlg = _scenario(win)
    _to_step_five(dlg)
    dlg.answer.setPlainText(_example_text())
    dlg.load_button.click()
    again = win.ai_scenario()
    assert again is not dlg
    assert _states(again) == ["current", "future", "future", "future", "future", "future"]
