"""Tests of the procnorm window (version 1)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from procnorm.store import Store
from procnorm.ui.app import MainWindow

EXAMPLE = Path(__file__).parent / "data" / "laundry.json"


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


@pytest.fixture
def loaded(win):
    assert win.load_path(EXAMPLE)
    return win


def _broken(tmp_path: Path) -> Path:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["kinds"][0]["entity"] = "Нет такой"
    data["kinds"][1]["axis"] = "нет оси"
    p = tmp_path / "broken.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_appears_in_list(loaded, store):
    infos = store.list()
    assert len(infos) == 1
    assert loaded.project_names() == ["Стирка белья"]
    assert loaded.current_id == infos[0].id


def test_comparison_rows_and_totals(loaded):
    c = loaded.comparison
    assert c.codes() == ["А", "Б", "В"]
    assert [c.cell(code, "Labour total") for code in c.codes()] == ["8.40", "3.40", "5.40"]
    assert c.cell("А", "Labour: Человек") == "8.40"
    assert c.cell("Б", "Skips at постирано") == "8.00"
    assert c.cell("А", "Skips at final") == "0.00"
    assert c.headers()[:4] == ["Code", "Title", "Side", "Steps"]


def test_filter_side(loaded):
    c = loaded.comparison
    c.set_side("other")
    assert c.codes() == ["Б", "В"]
    c.set_side("own")
    assert c.codes() == ["А"]
    c.set_side("all")
    assert len(c.codes()) == 3


def test_numeric_sort(win, tmp_path):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["normalization"]["kind_costs"]["Проверить карманы"] = 20
    p = tmp_path / "big.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert win.load_path(p)
    c = win.comparison
    c.sort("Labour total", Qt.SortOrder.AscendingOrder)
    assert c.codes() == ["Б", "В", "А"]  # 3.4 < 23.4 < 26.4; as text "23.40" < "26.40" < "3.40"
    c.sort("Labour total", Qt.SortOrder.DescendingOrder)
    assert c.codes() == ["А", "В", "Б"]


def test_details(loaded):
    c = loaded.comparison
    c.select_code("Б")
    assert c.details.rowCount() == 5
    texts = [c.details.item(r, c.details.columnCount() - 1).text() for r in range(5)]
    assert texts[0] == "Цикл стирки/наличие: нет → есть"


def test_excluded_and_uncounted_listed(loaded):
    assert "порошок закончился" in loaded.comparison.notes_text()


def test_broken_file_shows_remarks(win, store, tmp_path):
    assert not win.load_path(_broken(tmp_path))
    assert store.list() == []
    assert not win.remarks_panel.isHidden()
    lines = win.remarks_panel.lines()
    assert len(lines) >= 2
    assert any("Нет такой" in x for x in lines)
    assert str(len(lines)) in win.remarks_panel.count_label.text()


def test_copy_remarks(win, tmp_path, app):
    win.load_path(_broken(tmp_path))
    win.remarks_panel.copy()
    assert app.clipboard().text() == "\n".join(win.remarks_panel.lines())


def test_good_load_hides_remarks(win, tmp_path):
    win.load_path(_broken(tmp_path))
    win.load_path(EXAMPLE)
    assert win.remarks_panel.isHidden()


def test_load_over(loaded, store, tmp_path):
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["name"] = "Другая"
    p = tmp_path / "other.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pid = loaded.current_id
    assert loaded.load_over_path(p)
    assert [i.name for i in store.list()] == ["Другая"]
    assert loaded.current_id == pid
    assert loaded.project_names() == ["Другая"]


def test_load_over_broken_keeps_project(loaded, store, tmp_path):
    assert not loaded.load_over_path(_broken(tmp_path))
    assert [i.name for i in store.list()] == ["Стирка белья"]


def test_save_file(loaded, store, tmp_path):
    out = tmp_path / "out.json"
    loaded.save_path(out)
    assert out.read_text(encoding="utf-8") == store.text(loaded.current_id)


def test_copy_and_delete(loaded, store):
    first = loaded.current_id
    loaded.copy_project()
    assert len(store.list()) == 2
    assert loaded.current_id != first
    loaded.confirm = lambda text: False
    loaded.delete_project()
    assert len(store.list()) == 2
    loaded.confirm = lambda text: True
    loaded.delete_project()
    assert [i.id for i in store.list()] == [first]
    assert loaded.current_id == first


def test_delete_last_empties_window(loaded, store):
    loaded.confirm = lambda text: True
    loaded.delete_project()
    assert store.list() == []
    assert loaded.current_id is None
    assert loaded.comparison.codes() == []


def test_reopen_store_keeps_project(app, tmp_path):
    path = tmp_path / "t.db"
    ini = str(tmp_path / "ui.ini")
    s = Store(path)
    w = MainWindow(s, QSettings(ini, QSettings.Format.IniFormat))
    w.load_path(EXAMPLE)
    w.copy_project()
    last = w.current_id
    w.close()
    s.close()
    s2 = Store(path)
    w2 = MainWindow(s2, QSettings(ini, QSettings.Format.IniFormat))
    assert len(w2.project_names()) == 2
    assert w2.current_id == last
    assert w2.comparison.codes() == ["А", "Б", "В"]
    w2.close()
    s2.close()


def test_dictionary_tab(loaded):
    t = loaded.dictionary.all_text()
    for word in ("Бельё", "карманы", "не проверены, проверены", "Проверить карманы",
                 "не проверены → проверены", "Цикл стирки/наличие = есть", "ожидание, труда нет",
                 "Человек", "сушилка", "вся загрузка", "постирано"):
        assert word in t


def test_norm_tab(loaded):
    t = loaded.norm.all_text()
    for word in ("Разобрать по цветам", "0.1", "Бельё", "цвета", "10", "порошок закончился",
                 "Аккуратная стирка", "other"):
        assert word in t
    loaded.norm.select_variant("Б")
    assert loaded.norm.calls.rowCount() == 5


def test_export(loaded, tmp_path):
    md = tmp_path / "c.md"
    csv = tmp_path / "c.csv"
    loaded.comparison.export_path(md)
    loaded.comparison.export_path(csv)
    assert "8.40" in md.read_text(encoding="utf-8")
    assert "Labour total" in csv.read_text(encoding="utf-8")
