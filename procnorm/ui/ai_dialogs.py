# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Dialogs to ask an AI chat for a project file and to load its answer."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from procnorm.ai import request_text
from procnorm.ui.tables import label

ASK_NOTE = "Paste this into an AI chat. Bring its JSON answer back with “Paste answer”."

# What loading an answer returns: whether it loaded, and a message or the remark lines.
Loader = Callable[[str], tuple[bool, str | list[str]]]


class AskAiDialog(QDialog):
    """The user's description and the full request text to copy into an AI chat."""

    copied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aiDialog")
        self.setWindowTitle("Ask AI")
        self.setModal(True)
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(label("Describe your process"))
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(160)
        lay.addWidget(self.description)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        lay.addWidget(self.preview, 1)
        lay.addWidget(label(ASK_NOTE, "note"))
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton("Copy text")
        self.copy_button.setProperty("primary", True)
        self.copy_button.setDefault(True)
        self.close_button = QPushButton("Close")
        row.addWidget(self.copy_button)
        row.addWidget(self.close_button)
        lay.addLayout(row)
        self.description.textChanged.connect(self._update)
        self.copy_button.clicked.connect(self.copy)
        self.close_button.clicked.connect(self.reject)
        self._update()

    def _update(self) -> None:
        self.preview.setPlainText(self.text())

    def text(self) -> str:
        """The full request text."""
        return request_text(self.description.toPlainText())

    def copy(self) -> None:
        """Put the full text on the clipboard."""
        QGuiApplication.clipboard().setText(self.text())
        self.copied.emit()


class PasteAnswerDialog(QDialog):
    """A field for the AI answer; loads it and shows why it did not load.

    :param load: loads the pasted text: ``(True, message)`` or ``(False, message or remarks)``.
    :param parent: the parent window.
    """

    def __init__(self, load: Loader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load = load
        self._lines: list[str] = []
        self.setObjectName("aiDialog")
        self.setWindowTitle("Paste answer")
        self.setModal(True)
        self.resize(760, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        self.text = QPlainTextEdit()
        lay.addWidget(self.text, 1)
        self.error = label("", "err")
        self.error.hide()
        lay.addWidget(self.error)
        self.remarks = QPlainTextEdit()
        self.remarks.setObjectName("aiRemarks")
        self.remarks.setReadOnly(True)
        self.remarks.setMaximumHeight(160)
        self.remarks.hide()
        lay.addWidget(self.remarks)
        row = QHBoxLayout()
        self.copy_remarks_button = QPushButton("Copy remarks")
        self.copy_remarks_button.hide()
        row.addWidget(self.copy_remarks_button)
        row.addStretch(1)
        self.load_button = QPushButton("Load")
        self.load_button.setProperty("primary", True)
        self.load_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        row.addWidget(self.load_button)
        row.addWidget(self.cancel_button)
        lay.addLayout(row)
        self.load_button.clicked.connect(self.load)
        self.cancel_button.clicked.connect(self.reject)
        self.copy_remarks_button.clicked.connect(self.copy_remarks)

    def load(self) -> None:
        """Load the pasted text; close on success, else show the problem."""
        ok, result = self._load(self.text.toPlainText())
        if ok:
            self.accept()
            return
        if isinstance(result, str):
            self._show_error(result)
        else:
            self._show_remarks(result)

    def _show_error(self, text: str) -> None:
        self._lines = []
        self.remarks.hide()
        self.copy_remarks_button.hide()
        self.error.setText(text)
        self.error.show()

    def _show_remarks(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.error.hide()
        self.remarks.setPlainText("\n".join(self._lines))
        self.remarks.show()
        self.copy_remarks_button.show()

    def remark_lines(self) -> list[str]:
        """The shown remarks."""
        return list(self._lines)

    def copy_remarks(self) -> None:
        """Put all remarks on the clipboard."""
        QGuiApplication.clipboard().setText("\n".join(self._lines))
