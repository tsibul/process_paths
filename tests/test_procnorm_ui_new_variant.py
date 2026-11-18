"""Tests of a new variant on the Step chains tab and of its header: side, task, out of
comparison and parameters; each change goes to the database and moves the path between groups."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
from PySide6.QtWidgets import QApplication

from procnorm import edit
from procnorm.store import Store
from procnorm.ui.app import MainWindow
from procnorm.ui.comparison import NO_PAIR, OUT

# Made-up project: two variants of one task, a variant parameter, two executors.
TEA = {
    "format": 1,
    "name": "Tea",
    "existence_axis": {"name": "exists", "absent": "no"},
    "entities": [
        {"name": "Kettle", "axes": [{"name": "water", "values": ["cold", "hot"]}]},
        {"name": "Cup", "axes": [{"name": "tea", "values": ["empty", "full"]}]},
    ],
    "kinds": [
        {"name": "Boil", "entity": "Kettle", "axis": "water", "from": "cold", "to": "hot"},
        {"name": "Pour", "entity": "Cup", "axis": "tea", "from": "empty", "to": "full"},
    ],
    "executors": ["Host", "Guest"],
    "instruments": ["Hands"],
    "scopes": ["Cup", "Pot"],
    "batch_scope": "Pot",
    "variant_params": ["server"],
    "variants": [
        {
            "code": "T1",
            "title": "Quick tea",
            "side": "own",
            "task": "Make tea",
            "params": {"server": "Host"},
            "calls": [["Boil", "Host", "Hands", "Pot"], ["Pour", "Host", "Hands", "Cup"]],
        },
        {
            "code": "T2",
            "title": "Guest pours",
            "side": "other",
            "task": "Make tea",
            "params": {"server": "Guest"},
            "calls": [["Boil", "Host", "Hands", "Pot"], ["Pour", "Guest", "Hands", "Cup"]],
        },
    ],
    "normalization": {
        "kind_costs": {"Boil": 2, "Pour": 1},
        "executor_coefficients": {"Host": 1, "Guest": 1},
        "scope_coefficients": {"Cup": 1, "Pot": 1},
        "axis_skip_prices": {},
    },
}
TASK_GROUP = "Task: Make tea"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def win(app, store, tmp_path):
    path = tmp_path / "tea.json"
    path.write_text(json.dumps(TEA), "utf-8")
    w = MainWindow(store)
    assert w.load_path(path)
    w.resize(1200, 900)
    w.show()
    w.tabs.setCurrentWidget(w.chains)
    QApplication.processEvents()
    yield w
    w.close()


def _click(button):
    assert button.isEnabled()
    button.click()
    QApplication.processEvents()


def _data(store, pid):
    return copy.deepcopy(store.get(pid).data)


def _group_of(page, code):
    return next(title for title, _, codes in page.groups() if code in codes)


def _type(field, text):
    field.setText(text)
    field.editingFinished.emit()
    QApplication.processEvents()


def _variant(store, pid, code):
    return next(v for v in store.get(pid).data["variants"] if v["code"] == code)


def test_new_gives_new_1_then_new_2(win, store):
    pid = win.current_id
    old = _data(store, pid)
    page = win.chains
    assert page.new_button.text() == "New"
    _click(page.new_button)
    expected, _ = edit.add_variant(old, "New 1", "New variant")
    assert store.get(pid).data == expected
    assert page.current_code() == "New 1"
    assert page.path("New 1").selected
    assert _group_of(page, "New 1") == NO_PAIR
    assert page.code_edit.text() == "New 1"
    assert page.title_edit.text() == "New variant"
    _click(page.new_button)
    assert page.current_code() == "New 2"
    assert _group_of(page, "New 2") == NO_PAIR
    assert [v["code"] for v in store.get(pid).data["variants"]][-2:] == ["New 1", "New 2"]


def test_header_of_new_variant(win):
    page = win.chains
    _click(page.new_button)
    assert page.ours_radio.isChecked()
    assert not page.theirs_radio.isChecked()
    assert page.task_edit.text() == ""
    assert not page.task_hint.isHidden()
    assert page.task_hint.text() == "variants with the same task are compared"
    assert not page.out_check.isChecked()
    assert not page.reason_edit.isEnabled()
    assert list(page.param_boxes) == ["server"]
    assert page.param_boxes["server"].currentText() == "Host"  # the first executor
    assert "Steps not given" in page.head_meta()


def test_header_of_loaded_variant(win):
    page = win.chains
    page.select_path("T2")
    assert page.theirs_radio.isChecked()
    assert page.task_edit.text() == "Make tea"
    assert page.task_hint.isHidden()
    assert page.param_boxes["server"].currentText() == "Guest"
    items = page.param_boxes["server"]
    assert [items.itemText(i) for i in range(items.count())] == ["Host", "Guest"]


def test_task_moves_path_to_task_group(win, store):
    pid = win.current_id
    page = win.chains
    _click(page.new_button)
    old = _data(store, pid)
    _type(page.task_edit, "  Make tea ")
    expected, _ = edit.set_variant(old, "New 1", task="Make tea")
    assert store.get(pid).data == expected
    assert _group_of(page, "New 1") == TASK_GROUP
    assert page.current_code() == "New 1"
    assert page.path("New 1").selected
    _type(page.task_edit, "")
    assert "task" not in _variant(store, pid, "New 1")
    assert _group_of(page, "New 1") == NO_PAIR
    assert page.current_code() == "New 1"


def test_side_switch(win, store):
    pid = win.current_id
    page = win.chains
    _click(page.new_button)
    _click(page.theirs_radio)
    assert _variant(store, pid, "New 1")["side"] == "other"
    assert page.current_code() == "New 1"
    assert page.theirs_radio.isChecked()
    assert page.path("New 1").meta_text().startswith("○ Theirs")
    _click(page.ours_radio)
    assert _variant(store, pid, "New 1")["side"] == "own"


def test_out_of_comparison(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("T1")
    page.out_check.click()
    QApplication.processEvents()
    assert page.reason_edit.isEnabled()
    assert "out_of_comparison" not in _variant(store, pid, "T1")  # nothing yet without a reason
    _type(page.reason_edit, "draft")
    assert _variant(store, pid, "T1")["out_of_comparison"] == "draft"
    assert _group_of(page, "T1") == OUT
    assert _group_of(page, "T2") == NO_PAIR
    assert page.current_code() == "T1"
    assert page.out_check.isChecked()
    assert page.reason_edit.text() == "draft"
    page.out_check.click()
    QApplication.processEvents()
    assert "out_of_comparison" not in _variant(store, pid, "T1")
    assert _group_of(page, "T1") == TASK_GROUP
    assert not page.out_check.isChecked()
    assert page.reason_edit.text() == ""
    assert page.current_code() == "T1"


def test_param_choice(win, store):
    pid = win.current_id
    page = win.chains
    page.select_path("T1")
    old = _data(store, pid)
    box = page.param_boxes["server"]
    box.setCurrentIndex(box.findText("Guest"))
    box.activated.emit(box.currentIndex())
    QApplication.processEvents()
    expected, _ = edit.set_variant(old, "T1", params={"server": "Guest"})
    assert store.get(pid).data == expected
    assert page.current_code() == "T1"
    assert page.param_boxes["server"].currentText() == "Guest"


def test_refused_rename_of_new_variant(win, store):
    pid = win.current_id
    page = win.chains
    _click(page.new_button)
    _click(page.new_button)
    before = store.text(pid)
    page.code_edit.setText("New 1")
    page.code_edit.editingFinished.emit()
    QApplication.processEvents()
    assert store.text(pid) == before
    assert not page.refusal.isHidden()
    assert "variant code is taken: New 1" in page.refusal.text()
    assert page.current_code() == "New 2"
    assert page.code_edit.text() == "New 2"


NO_EXECUTOR_HINT = (
    "Add an executor on the Dictionary tab first: "
    "every new path needs one for each variant parameter."
)


def test_new_off_with_hint_until_an_executor_exists(app, store):
    w = MainWindow(store)
    try:
        assert w.new_project("Empty")
        assert w.add_word("variant_param", "helper")
        w.tabs.setCurrentWidget(w.chains)
        QApplication.processEvents()
        page = w.chains
        assert not page.new_button.isEnabled()
        assert not page.new_hint.isHidden()
        assert page.new_hint.text() == NO_EXECUTOR_HINT
        assert w.add_word("executor", "Cook")
        QApplication.processEvents()
        assert page.new_button.isEnabled()
        assert page.new_hint.isHidden()
    finally:
        w.close()


def test_new_enabled_without_variant_parameters_or_executors(app, store):
    w = MainWindow(store)
    try:
        assert w.new_project("Empty")
        w.tabs.setCurrentWidget(w.chains)
        QApplication.processEvents()
        assert w.chains.new_button.isEnabled()
        assert w.chains.new_hint.isHidden()
    finally:
        w.close()


def test_new_called_while_off_shows_the_hint_as_refusal(app, store):
    w = MainWindow(store)
    try:
        assert w.new_project("Empty")
        assert w.add_word("variant_param", "helper")
        w.tabs.setCurrentWidget(w.chains)
        QApplication.processEvents()
        pid = w.current_id
        before = store.text(pid)
        assert not w.edit_chain("new", ())
        assert store.text(pid) == before
        assert not w.chains.refusal.isHidden()
        assert w.chains.refusal.text() == NO_EXECUTOR_HINT
        assert "expected" not in w.chains.refusal.text()
    finally:
        w.close()


def test_header_fields_hidden_without_path(app, store):
    w = MainWindow(store)
    try:
        assert w.new_project("Empty")
        w.tabs.setCurrentWidget(w.chains)
        QApplication.processEvents()
        page = w.chains
        assert page.current_code() is None
        assert page.fields.isHidden()
        assert not page.new_button.isHidden()
    finally:
        w.close()
