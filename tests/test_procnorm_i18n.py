"""Tests of the translation mechanism: the language key, loading `.qm`, dates, direction."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QSettings, Qt
from PySide6.QtWidgets import QApplication

from measure_twice import i18n
from measure_twice.ui.tables import project_note

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone(timedelta(hours=2)))
UPDATED = "2026-11-18T12:32:00+00:00"
MARK = "[ru] "

# A test translation: every string of the language switch carries a mark.
TEST_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ru_RU">
<context>
    <name>MainWindow</name>
    <message>
        <source>Restart now</source>
        <translation>[ru] Restart now</translation>
    </message>
    <message>
        <source>The language changes at the next start.</source>
        <translation>[ru] The language changes at the next start.</translation>
    </message>
</context>
</TS>
"""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english_after(app, tmp_path):
    """Every test leaves the application in English, left to right."""
    old = QLocale()
    yield
    i18n.apply_language(app, "en", tmp_path)
    QLocale.setDefault(old)


def settings_at(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def test_languages_in_order():
    assert list(i18n.LANGUAGES.items()) == [
        ("en", "English"),
        ("ru", "Русский"),
        ("el", "Ελληνικά"),
    ]


def test_language_key_is_written_and_read(tmp_path):
    s = settings_at(tmp_path)
    i18n.write_language(s, "el")
    s.sync()
    assert settings_at(tmp_path).value(i18n.KEY) == "el"
    assert i18n.read_language(settings_at(tmp_path)) == "el"


def test_first_start_takes_system_language_of_three(tmp_path):
    assert i18n.read_language(settings_at(tmp_path), system="ru_RU") == "ru"


def test_first_start_other_system_language_is_english(tmp_path):
    assert i18n.read_language(settings_at(tmp_path), system="de_DE") == "en"


def test_unknown_stored_language_is_english(tmp_path):
    s = settings_at(tmp_path)
    s.setValue(i18n.KEY, "xx")
    assert i18n.read_language(s, system="ru_RU") == "en"


def test_language_without_file_is_english(app, tmp_path):
    empty = tmp_path / "qm"
    empty.mkdir()
    i18n.apply_language(app, "ru", empty)
    assert QCoreApplication.translate("MainWindow", "Restart now") == "Restart now"


def test_build_without_sources_makes_nothing(tmp_path):
    assert i18n.build_qm(tmp_path / "none", tmp_path / "out") == []


def test_build_makes_qm_from_ts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "measure_twice_ru.ts").write_text(TEST_TS, encoding="utf-8")
    built = i18n.build_qm(src, tmp_path / "out")
    assert built == [tmp_path / "out" / "measure_twice_ru.qm"]
    assert built[0].stat().st_size > 0


def test_test_translation_changes_strings_and_dates(app, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "measure_twice_ru.ts").write_text(TEST_TS, encoding="utf-8")
    out = tmp_path / "out"
    i18n.build_qm(src, out)
    assert "18 Nov 14:32" in project_note(6, UPDATED, NOW)
    i18n.apply_language(app, "ru", out)
    assert QCoreApplication.translate("MainWindow", "Restart now") == MARK + "Restart now"
    note = project_note(6, UPDATED, NOW)
    assert "Nov" not in note
    assert "18 нояб." in note
    assert i18n.locale().language() == QLocale.Language.Russian


def test_english_back_removes_translation(app, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "measure_twice_ru.ts").write_text(TEST_TS, encoding="utf-8")
    out = tmp_path / "out"
    i18n.build_qm(src, out)
    i18n.apply_language(app, "ru", out)
    i18n.apply_language(app, "en", out)
    assert QCoreApplication.translate("MainWindow", "Restart now") == "Restart now"
    assert "18 Nov 14:32" in project_note(6, UPDATED, NOW)


def test_left_to_right_languages(app, tmp_path):
    for lang in i18n.LANGUAGES:
        i18n.apply_language(app, lang, tmp_path)
        assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_right_to_left_language_turns_the_window(app, tmp_path):
    # No Hebrew translation is needed: the direction comes from the locale alone.
    i18n.apply_language(app, "he", tmp_path)
    assert app.layoutDirection() == Qt.LayoutDirection.RightToLeft
    i18n.apply_language(app, "en", tmp_path)
    assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight
