# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `Paste AI answer` window: one field for the answer, `Load` and `Cancel`.

The loading itself is the loader of the AI scenario screen; nothing is kept between openings.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from measure_twice.ui.ai_scenario import ANSWER_CAPTION, Loader
from measure_twice.ui.tables import label, translate



class PasteDialog(QDialog):
    """A window with one text field; a good answer is loaded and the window closes.

    :param load: loads the pasted answer: ``(True, message)`` or ``(False, message or remarks)``.
    :param parent: the parent window.
    """

    def __init__(self, load: Loader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load = load
        self.setObjectName("pasteAnswer")
        self.setWindowTitle(self.tr("Paste AI answer"))
        self.setModal(True)
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(label(translate("AiScenarioDialog", ANSWER_CAPTION), "aiCaption"))
        self.answer = QPlainTextEdit()
        self.answer.setObjectName("aiAnswer")
        lay.addWidget(self.answer, 1)
        self.error = label("", "err")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.load_button = QPushButton(self.tr("Load"))
        self.load_button.setProperty("primary", True)
        row.addWidget(self.cancel_button)
        row.addWidget(self.load_button)
        lay.addLayout(row)
        self.cancel_button.clicked.connect(self.reject)
        self.load_button.clicked.connect(self.load)

    def load(self) -> None:
        """Load the answer; close on success, else show the remarks under the field."""
        ok, result = self._load(self.answer.toPlainText())
        if ok:
            self.accept()
            return
        self.error.setText(result if isinstance(result, str) else "\n".join(result))
        self.error.setVisible(bool(self.error.text()))
