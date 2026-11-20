"""Lists, their buttons and the head of a variant: nothing cut or squeezed in any language."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from measure_twice import i18n
from measure_twice.example import add_example
from measure_twice.store import Store
from measure_twice.ui.app import MainWindow

ARROW = 16  # room the arrow of a closed list takes at its right


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lang(app, tmp_path, request):
    """The language of the test, its `.qm` built from the sources; English again after."""
    i18n.build_qm(out=tmp_path)
    i18n.apply_language(app, request.param, tmp_path)
    yield request.param
    i18n.apply_language(app, "en", tmp_path)


def _text_room(box) -> int:
    """Width the closed list needs to show its longest item with the arrow beside it."""
    widest = max(box.fontMetrics().horizontalAdvance(box.itemText(i)) for i in range(box.count()))
    return widest + ARROW


# ---------- 2: the head of a variant ----------

@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_title_and_buttons_on_their_row_meta_below(app, lang, tmp_path):
    store = Store(tmp_path / "p.db")
    add_example(store, "ru")
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    try:
        w.resize(1100, 780)
        w.show()
        w.tabs.setCurrentWidget(w.chains)
        QApplication.processEvents()
        page = w.chains
        code = page.current_code()
        assert code
        title = page.title_edit
        for b in (page.copy_button, page.delete_button):
            assert abs(b.geometry().center().y() - title.geometry().center().y()) <= 2
            assert b.width() >= b.sizeHint().width()
        meta = page.meta
        assert meta.wordWrap()
        assert meta.mapTo(page, meta.rect().topLeft()).y() >= \
            title.mapTo(page, title.rect().bottomLeft()).y()
        assert title.width() >= title.fontMetrics().horizontalAdvance(title.text())
    finally:
        w.close()
        store.close()


# ---------- 3: the closed lists of the input row ----------

def _window(store, tmp_path, lang: str, width: int) -> MainWindow:
    add_example(store, lang)
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w.resize(width, 780)
    w.show()
    QApplication.processEvents()
    return w


@pytest.mark.parametrize("width", [900, 1100, 1500])
@pytest.mark.parametrize("lang", ["en", "ru", "el"], indirect=True)
def test_input_lists_by_longest_item_buttons_whole(app, lang, width, tmp_path):
    store = Store(tmp_path / "p.db")
    w = _window(store, tmp_path, lang, width)
    try:
        w.tabs.setCurrentWidget(w.chains)
        table = w.chains.table
        table.open_input(("call", 1))
        QApplication.processEvents()
        row = table.input
        for field_, box in row.lists.items():
            assert box.width() >= _text_room(box), field_
            assert box.geometry().right() <= row.width(), field_  # inside the row, not cut
            box.showPopup()
            QApplication.processEvents()
            assert box.view().sizeHintForColumn(0) <= box.view().width(), field_
            box.hidePopup()
        for b in (row.add_button, row.cancel_button):
            assert b.width() >= b.sizeHint().width(), b.text()
            assert b.mapTo(table, b.rect().topRight()).x() <= table.viewport().width(), b.text()
        r = table.kinds.index("input")
        assert table.rowHeight(r) >= row.heightForWidth(row.width())  # wrapped lines not cut
    finally:
        w.close()
        store.close()


# ---------- 4: the field of a parameter ----------

def _open_add(w: MainWindow, what: str):
    for table in w.dictionary.tables():
        for kind, owner in list(table._adds):
            if kind == what:
                table.open_add(kind, owner)
                QApplication.processEvents()
                return table._editor
    raise AssertionError(what)


@pytest.mark.parametrize("lang,hint", [("en", "name"), ("ru", "имя"), ("el", "όνομα")],
                         indirect=["lang"])
def test_parameter_hint_short_field_wide(app, lang, hint, tmp_path):
    store = Store(tmp_path / "p.db")
    w = _window(store, tmp_path, lang, 1100)
    try:
        w.tabs.setCurrentWidget(w.dictionary)
        other = _open_add(w, "executor").name.width()
        param = _open_add(w, "variant_param")
        assert param.name.placeholderText() == hint
        assert param.name.width() >= 1.4 * other - 1
        assert param.executor.width() >= _text_room(param.executor)
        for b in (param.add_button, param.esc_button):
            assert b.width() >= b.sizeHint().width(), b.text()
    finally:
        w.close()
        store.close()


# ---------- 5: translations ----------

@pytest.mark.parametrize("lang,text", [
    ("en", "Delete T1?"), ("ru", "Удалить T1?"), ("el", "Διαγραφή T1;"),
], indirect=["lang"])
def test_delete_variant_question_translated(app, lang, text, monkeypatch, tmp_path):
    store = Store(tmp_path / "p.db")
    add_example(store, "en")
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    asked = []
    monkeypatch.setattr(w, "confirm", lambda t: asked.append(t) or False)
    try:
        w.chains.select_path("T1")
        w.chains.delete_button.click()
        QApplication.processEvents()
        assert asked == [text]
    finally:
        w.close()
        store.close()


@pytest.mark.parametrize("lang,text", [
    ("en", "New project"), ("ru", "Новый проект"), ("el", "Νέο έργο"),
], indirect=["lang"])
def test_new_project_name_translated(app, lang, text, monkeypatch, tmp_path):
    store = Store(tmp_path / "p.db")
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    asked = []
    monkeypatch.setattr(w, "ask_name", lambda t: asked.append(t))
    try:
        w.on_new()
        assert asked == [text]
    finally:
        w.close()
        store.close()


@pytest.mark.parametrize("lang,words", [
    ("ru", {"yes": "&Да", "no": "&Нет"}),
    ("el", {"yes": "&Ναι", "no": "&Όχι", "ok": "OK", "cancel": "Άκυρο"}),
], indirect=["lang"])
def test_dialog_buttons_translated(app, lang, words):
    box = QMessageBox(QMessageBox.Icon.Question, "", "",
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    assert box.button(QMessageBox.StandardButton.Yes).text() == words["yes"]
    assert box.button(QMessageBox.StandardButton.No).text() == words["no"]
    if "ok" in words:
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        ok = bb.button(QDialogButtonBox.StandardButton.Ok).text().replace("&", "")
        cancel = bb.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "")
        assert ok == words["ok"] and cancel == words["cancel"]
