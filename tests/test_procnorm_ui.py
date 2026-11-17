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
    assert [c.cell(code, "Labour · total") for code in c.codes()] == ["8.40", "3.40", "5.40"]
    assert c.cell("А", "Labour · Человек") == "8.40"
    assert c.cell("Б", "Skipped checks, постирано") == "8.00"
    assert c.cell("А", "Skipped checks, end") == "0.00"
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
    c.sort("Labour · total", Qt.SortOrder.AscendingOrder)
    assert c.codes() == ["А", "Б", "В"]  # ours first; 3.4 < 23.4; as text "23.40" < "3.40"
    c.sort("Labour · total", Qt.SortOrder.DescendingOrder)
    assert c.codes() == ["А", "В", "Б"]


def test_details(loaded):
    c = loaded.comparison
    c.toggle("Б")
    t = c.steps("Б")
    assert t.rowCount() == 5
    assert t.item(0, t.columnCount() - 1).text() == "Цикл стирки/наличие: нет → есть"


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
    assert "Labour · total" in csv.read_text(encoding="utf-8")


# --- comparison tree: groups by task (piece 5)

LONG = "Очень длинное имя исполнителя для проверки обрезки"
HINT = ("Rows are grouped by task. Ours come first, then theirs; lower labour is cheaper, but skipped "
        "checks are counted separately. Click a row to see its steps.")
T_FAST, T_WASH, T_SORT = "Быстро постирать", "Постирать загрузку", "Разобрать бельё"


def _twelve(tmp_path: Path) -> Path:
    """Twelve variants from the three of laundry.json: three task groups, no pair, out of comparison."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    calls = {v["code"]: v["calls"] for v in data["variants"]}  # А 8.40, Б 3.40, В 5.40
    long_calls = json.loads(json.dumps(calls["В"]))
    long_calls[0][1] = LONG
    spec = [  # code, from, side, task, out
        ("А", "А", "own", T_WASH, None), ("Б", "Б", "other", T_WASH, None),
        ("В", "В", "other", T_WASH, None), ("Г", "Б", "own", T_WASH, None),
        ("Е", "А", "own", T_FAST, None), ("Ж", None, "other", T_FAST, None),
        ("З", "Б", "other", T_FAST, None), ("И", "А", "own", T_SORT, None),
        ("К", "В", "own", T_SORT, None), ("Л", "Б", "own", "Одна задача", None),
        ("М", "В", "other", None, None), ("Н", "А", "other", T_WASH, "чужая машина"),
    ]
    variants = []
    for code, src, side, task, out in spec:
        v = {"code": code, "title": f"Вариант {code}", "side": side,
             "calls": long_calls if src is None else calls[src]}
        if task:
            v["task"] = task
        if out:
            v["out_of_comparison"] = out
        variants.append(v)
    data["variants"] = variants
    data["executors"].append(LONG)
    data["normalization"]["executor_coefficients"][LONG] = 1
    p = tmp_path / "twelve.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def twelve(win, tmp_path):
    p = _twelve(tmp_path)
    assert win.load_path(p)
    win.twelve_path = p
    return win


DEFAULT = ["Е", "З", "Ж", "Г", "А", "Б", "В", "К", "И", "Л", "М", "Н"]


def test_groups_headers_and_marketing_texts(twelve):
    c = twelve.comparison
    heads = [(h.title.text(), h.count.text(), h.note.text() if h.note else None, h.grey)
             for h in c.group_headers()]
    assert heads == [
        (f"Task: {T_FAST}", "3 variants", None, False),
        (f"Task: {T_WASH}", "4 variants", None, False),
        (f"Task: {T_SORT}", "2 variants", None, False),
        ("No comparable variant", "", "Not compared: no other variant has the same task", True),
        ("Out of comparison", "", None, True),
    ]
    assert c.hint.text() == HINT
    assert c.cell("А", "Side") == "● Ours"
    assert c.cell("Б", "Side") == "○ Theirs"
    assert c.headers() == ["Code", "Title", "Side", "Steps", "Labour · Человек", f"Labour · {LONG}",
                           "Labour · total", "Skipped checks, постирано", "Skipped checks, end"]
    assert c.header_text("Labour · total") == "Labour\ntotal"
    assert c.header_text("Skipped checks, end") == "Skipped checks\nend"


def test_default_order(twelve):
    assert twelve.comparison.codes() == DEFAULT


def test_out_of_comparison_row_has_numbers_and_reason(twelve):
    c = twelve.comparison
    assert c.cell("Н", "Labour · total") == "8.40"
    assert c.cell("Н", "Title") == "Вариант Н\nReason: чужая машина"
    assert "Out of comparison:" not in c.notes_text()


def test_sort_keeps_groups_and_ours_on_top(twelve):
    c = twelve.comparison
    c.sort("Labour · total", Qt.SortOrder.DescendingOrder)
    assert c.codes() == ["Е", "Ж", "З", "А", "Г", "В", "Б", "И", "К", "Л", "М", "Н"]
    assert [h.title.text() for h in c.group_headers()][:3] == [f"Task: {x}" for x in (T_FAST, T_WASH, T_SORT)]


def test_sort_by_header_click(twelve):
    c = twelve.comparison
    col = c.headers().index("Labour · total")
    c.tree.header().sectionClicked.emit(col)
    assert c.codes() == DEFAULT
    c.tree.header().sectionClicked.emit(col)
    assert c.codes()[:3] == ["Е", "Ж", "З"]


def test_filter_theirs_hides_ours_and_empty_groups(twelve):
    c = twelve.comparison
    c.set_side("other")
    assert c.codes() == ["З", "Ж", "Б", "В", "М", "Н"]
    heads = [(h.title.text(), h.count.text()) for h in c.group_headers()]
    assert heads == [(f"Task: {T_FAST}", "3 variants"), (f"Task: {T_WASH}", "4 variants"),
                     ("No comparable variant", ""), ("Out of comparison", "")]
    c.set_side("all")
    assert c.codes() == DEFAULT


def test_two_open_at_once_steps_and_skips_left(twelve):
    from procnorm.calc import details, series
    from procnorm.project import load_file
    project, _ = load_file(twelve.twelve_path)
    c = twelve.comparison
    assert c.open_codes() == []
    c.toggle("А")
    c.toggle("Б")
    assert set(c.open_codes()) == {"А", "Б"}
    for code in ("А", "Б"):
        t = c.steps(code)
        assert t.rowCount() == len(details(project, code))
        heads = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
        col = heads.index("Skips left")
        assert [t.item(r, col).text() for r in range(t.rowCount())] == \
            [str(p.skips_count) for p in series(project, code)]
    c.toggle("А")
    assert c.open_codes() == ["Б"]


def test_click_row_opens_and_closes(twelve):
    c = twelve.comparison
    it = c.item("Б")
    c.tree.itemClicked.emit(it, 0)
    assert c.open_codes() == ["Б"]
    c.tree.itemClicked.emit(it, 3)
    assert c.open_codes() == []


def test_no_details_table(twelve):
    c = twelve.comparison
    assert not hasattr(c, "details")
    c.toggle("Б")
    assert "DETAILS" not in c.all_text()


def test_skipped_lines_under_steps(twelve):
    c = twelve.comparison
    c.toggle("Б")
    lines = c.skipped_labels("Б")
    assert [x.text() for x in lines] == [
        "Skipped checks, постирано: Бельё/карманы (5), Бельё/цвета (3)",
        "Skipped checks, end: Бельё/карманы (5), Бельё/цвета (3)",
    ]
    assert all(x.objectName() != "err" for x in lines)
    c.toggle("А")
    assert c.skipped_labels("А") == []


def _bold(c):
    return [code for code in c.codes() if c.is_bold(code, "Labour · total")]


def test_lowest_total_bold(twelve):
    c = twelve.comparison
    # Быстро: З; Постирать: Г and Б equal; Разобрать: К; none in no pair and out
    assert _bold(c) == ["З", "Г", "Б", "К"]
    c.set_side("own")
    assert _bold(c) == ["Е", "Г", "К"]
    c.set_side("other")
    assert _bold(c) == ["З", "Б"]


def test_long_executor_header_elided(twelve):
    c = twelve.comparison
    key = f"Labour · {LONG}"
    text = c.header_text(key)
    first, second = text.split("\n")
    assert first == "Labour"
    assert second.endswith("…") and LONG.startswith(second[:-1]) and second != LONG
    assert c.header_tooltip(key) == key


def test_screenshot_twelve(twelve):
    """Offscreen picture of the tab for a look against the mockup."""
    out = os.environ.get("PROCNORM_SHOT")
    if not out:
        pytest.skip("set PROCNORM_SHOT to a .png path")
    c = twelve.comparison
    c.toggle("Б")
    twelve.resize(1200, 900)
    twelve.show()
    QApplication.processEvents()
    page = c.widget()
    page.resize(1200, page.sizeHint().height())
    QApplication.processEvents()
    assert page.grab().save(out)
