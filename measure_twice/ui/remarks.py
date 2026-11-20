# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Panel with the remarks of a file that did not load or a project that was not created."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from measure_twice import i18n
from measure_twice.project import Remark
from measure_twice.ui.tables import label, translate


FILE_NOTE = QT_TRANSLATE_NOOP("RemarksPanel", "Nothing was stored. Fix the file and load it again.")
NAME_NOTE = QT_TRANSLATE_NOOP("RemarksPanel", "Nothing was stored. Enter a name and try again.")


class RemarksPanel(QFrame):
    """Every remark of the file, one per line, with copying to the clipboard."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("remarks")
        self._lines: list[str] = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.count_label = label("", "err")
        top.addWidget(self.count_label, 1)
        self.copy_button = QPushButton(self.tr("Copy remarks"))
        self.copy_button.setProperty("primary", True)
        self.copy_button.clicked.connect(self.copy)
        close = QPushButton(self.tr("Close"))
        close.clicked.connect(self.hide)
        top.addWidget(self.copy_button)
        top.addWidget(close)
        lay.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setMaximumHeight(220)
        lay.addWidget(self.text)
        self.note = label(translate("RemarksPanel", FILE_NOTE), "note")
        lay.addWidget(self.note)
        self.hide()

    def show_remarks(self, path: Path, remarks: list[Remark]) -> None:
        """Show the remarks of one file."""
        self._lines = [i18n.remark(r) for r in remarks]
        count = self._count()
        text = self.tr("{count} — {name} was not loaded")
        self.count_label.setText(text.format(count=count, name=Path(path).name))
        self.text.setPlainText("\n".join(self._lines))
        self.note.setText(translate("RemarksPanel", FILE_NOTE))
        self.show()

    def show_name_remarks(self, remarks: list[Remark]) -> None:
        """Show why a new project was not created."""
        self._lines = [i18n.remark(r) for r in remarks]
        text = self.tr("{count} — the project was not created")
        self.count_label.setText(text.format(count=self._count()))
        self.text.setPlainText("\n".join(self._lines))
        self.note.setText(translate("RemarksPanel", NAME_NOTE))
        self.show()

    def _count(self) -> str:
        """``N remark(s)`` in the language of the window."""
        n = len(self._lines)
        return translate("RemarksPanel", "%n remark(s)", "", n)

    def lines(self) -> list[str]:
        """The shown remarks."""
        return list(self._lines)

    def copy(self) -> None:
        """Put all remarks on the clipboard."""
        QGuiApplication.clipboard().setText("\n".join(self._lines))
