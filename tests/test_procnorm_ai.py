"""Tests of the AI request text, the JSON extraction and the Ask AI and Paste answer dialogs."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton

from procnorm.ai import INSTRUCTIONS_FILE, extract_json, instructions, request_text
from procnorm.store import Store
from procnorm.ui.app import MainWindow

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


# --- the buttons


def _bar_texts(win) -> list[str]:
    bar = next(lay for lay in win.findChildren(QHBoxLayout)
               if lay.indexOf(win.example_button) >= 0)
    texts = []
    for i in range(bar.count()):
        w = bar.itemAt(i).widget()
        if isinstance(w, QPushButton):
            texts.append(w.text())
    return texts


def test_buttons_at_the_end_of_the_row(win):
    texts = _bar_texts(win)
    assert texts[-3:] == ["Ask AI", "Paste answer", "Example"]
    assert texts[-4] == "Delete"
    assert win.example_button.toolTip() == "Add the Fix a leaking tap example"
    assert win.example_button.isEnabled()


# --- Ask AI


def test_ask_ai_preview_follows_description(win):
    dlg = win.ask_ai_dialog()
    assert dlg.windowTitle() == "Ask AI"
    assert dlg.preview.isReadOnly()
    dlg.description.setPlainText("We bake bread at night.")
    assert dlg.preview.toPlainText() == request_text("We bake bread at night.")


def test_ask_ai_copy_text(win):
    dlg = win.ask_ai_dialog()
    dlg.description.setPlainText("We wash a car.")
    dlg.copy_button.click()
    assert QGuiApplication.clipboard().text() == request_text("We wash a car.")
    assert win.statusBar().currentMessage() == "Copied. Paste it into the AI chat."


# --- Paste answer


def test_load_text_adds_project(win, store):
    ok, message = win.load_text("Done:\n```json\n" + _example_text() + "\n```\n")
    assert ok
    assert message == "Loaded Change a bike tyre"
    assert win.project_names() == ["Change a bike tyre"]


def test_paste_answer_loads_fenced_json(win, store):
    dlg = win.paste_answer_dialog()
    assert dlg.windowTitle() == "Paste answer"
    dlg.show()
    dlg.text.setPlainText("Here it is.\n```json\n" + _example_text() + "\n```\nGood luck.")
    dlg.load_button.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert not dlg.isVisible()
    infos = store.list()
    assert [i.name for i in infos] == ["Change a bike tyre"]
    assert win.current_id == infos[0].id
    assert win.projects.currentText() == "Change a bike tyre"
    assert win.offer_visible()
    assert win.statusBar().currentMessage() == "Loaded Change a bike tyre"


def test_paste_answer_without_json_keeps_dialog(win, store):
    dlg = win.paste_answer_dialog()
    dlg.show()
    dlg.text.setPlainText("I could not make the file.")
    dlg.load_button.click()
    assert dlg.isVisible()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert dlg.error.isVisible()
    assert dlg.error.text() == "No JSON object found in the text."
    assert dlg.error.objectName() == "err"
    assert store.list() == []
    dlg.close()


def test_paste_answer_with_remarks_lists_them(win, store):
    dlg = win.paste_answer_dialog()
    dlg.show()
    text = "```json\n" + _broken_text() + "\n```"
    dlg.text.setPlainText(text)
    dlg.load_button.click()
    assert dlg.isVisible()
    assert dlg.text.toPlainText() == text
    assert store.list() == []
    lines = dlg.remark_lines()
    assert lines == ["kind Shut off water: unknown entity No such entity"]
    assert dlg.remarks.isVisible()
    assert dlg.remarks.toPlainText() == "\n".join(lines)
    assert not dlg.error.isVisible()
    assert dlg.copy_remarks_button.isVisible()
    assert dlg.copy_remarks_button.text() == "Copy remarks"
    dlg.copy_remarks_button.click()
    assert QGuiApplication.clipboard().text() == "\n".join(lines)
    dlg.close()


def test_paste_answer_cancel(win, store):
    dlg = win.paste_answer_dialog()
    dlg.show()
    dlg.cancel_button.click()
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()
