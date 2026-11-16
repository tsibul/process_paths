# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Panel with the remarks of a file that did not load."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout

from procnorm.project import Remark
from procnorm.ui.tables import label


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
        self.copy_button = QPushButton("Copy remarks")
        self.copy_button.setProperty("primary", True)
        self.copy_button.clicked.connect(self.copy)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        top.addWidget(self.copy_button)
        top.addWidget(close)
        lay.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setMaximumHeight(220)
        lay.addWidget(self.text)
        lay.addWidget(label("Nothing was stored. Fix the file and load it again.", "note"))
        self.hide()

    def show_remarks(self, path: Path, remarks: list[Remark]) -> None:
        """Show the remarks of one file."""
        self._lines = [str(r) for r in remarks]
        self.count_label.setText(f"{len(self._lines)} remark(s) — {Path(path).name} was not loaded")
        self.text.setPlainText("\n".join(self._lines))
        self.show()

    def lines(self) -> list[str]:
        """The shown remarks."""
        return list(self._lines)

    def copy(self) -> None:
        """Put all remarks on the clipboard."""
        QGuiApplication.clipboard().setText("\n".join(self._lines))
