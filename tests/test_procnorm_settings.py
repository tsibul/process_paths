# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of carrying the settings over from the old program name."""

from PySide6.QtCore import QSettings

from measure_twice.ui.app import carry_settings


def _ini(path):
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_old_keys_copied_once(tmp_path):
    old = _ini(tmp_path / "old.ini")
    old.setValue("last_project", 7)
    old.setValue("group/flag", "yes")
    new = _ini(tmp_path / "new.ini")
    carry_settings(new, old)
    assert new.value("last_project", type=int) == 7
    assert new.value("group/flag") == "yes"
    assert sorted(old.allKeys()) == ["group/flag", "last_project"]
    old.setValue("last_project", 9)
    carry_settings(new, old)
    assert new.value("last_project", type=int) == 7


def test_new_keys_left_alone(tmp_path):
    old = _ini(tmp_path / "old.ini")
    old.setValue("last_project", 7)
    new = _ini(tmp_path / "new.ini")
    new.setValue("last_project", 3)
    carry_settings(new, old)
    assert new.value("last_project", type=int) == 3
    assert new.allKeys() == ["last_project"]


def test_nothing_old_nothing_copied(tmp_path):
    old = _ini(tmp_path / "old.ini")
    new = _ini(tmp_path / "new.ini")
    carry_settings(new, old)
    assert new.allKeys() == []
