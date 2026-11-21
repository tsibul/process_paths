# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The user guide window: the Markdown guide of the language of the window, read-only.

The guides are ``measure_twice/data/user_guide_<lang>.md``, one for every language of the window; a
language without one would show the English guide.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from measure_twice import i18n

DATA = Path(__file__).resolve().parent.parent / "data"
TITLE = QT_TRANSLATE_NOOP("MainWindow", "User guide")


def guide_file(lang: str) -> Path:
    """The guide of a language.

    :param lang: the language code.
    :return: its file, or the English one when the language has none.
    :rtype: Path
    """
    path = DATA / f"user_guide_{lang}.md"
    return path if path.is_file() else DATA / f"user_guide_{i18n.SOURCE}.md"


class GuideDialog(QDialog):
    """The guide of the current language in a window; it does not hold the main window.

    :param title: the window title, already translated.
    :param parent: the parent window.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("userGuide")
        self.setWindowTitle(title)
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMarkdown(guide_file(i18n.current()).read_text(encoding="utf-8"))
        lay.addWidget(self.browser)
        row = QHBoxLayout()
        row.addStretch(1)
        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.close_button)
        lay.addLayout(row)
