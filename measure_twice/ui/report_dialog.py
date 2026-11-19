# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The report window: which pages and which ways go into the PDF, then `Save PDF…`.

The chosen ways go on every page. The file is asked for and written by the caller.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from measure_twice import i18n
from measure_twice.calc import compare, groups
from measure_twice.project import Project
from measure_twice.report import HEADINGS, PAGES
from measure_twice.ui.tables import label

CODE_ROLE = Qt.ItemDataRole.UserRole

Saver = Callable[[list[str], list[str]], bool]
"""Asks for the file and writes the report of the chosen pages and ways; ``False``: not saved."""


class ReportDialog(QDialog):
    """Three page checks and a checked list of ways; `Save PDF…` is grey while either is empty.

    :param project: the project of the Comparison tab.
    :param save: writes the report: ``save(pages, ways)``; the window closes when it returns
        ``True``.
    :param parent: the parent window.
    """

    def __init__(self, project: Project, save: Saver, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._save = save
        self.setObjectName("reportChoice")
        self.setWindowTitle(self.tr("Report (PDF)"))
        self.setModal(True)
        self.resize(520, 460)
        lay = QVBoxLayout(self)

        lay.addWidget(label(self.tr("Pages"), "h3"))
        self.pages: dict[str, QCheckBox] = {}
        for kind in PAGES:
            box = QCheckBox(i18n.shown(HEADINGS[kind]))
            box.setChecked(True)
            box.toggled.connect(self._update)
            self.pages[kind] = box
            lay.addWidget(box)

        lay.addWidget(label(self.tr("Ways (on every page)"), "h3"))
        self.ways = QListWidget()
        self.ways.setObjectName("reportWays")
        seen: set[str] = set()
        for g in groups(compare(project)):
            for r in g.rows:
                if r.code in seen:
                    continue
                seen.add(r.code)
                item = QListWidgetItem(f"{r.code}  {r.title}")
                item.setData(CODE_ROLE, r.code)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.ways.addItem(item)
        self.ways.itemChanged.connect(self._update)
        lay.addWidget(self.ways, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.save_button = QPushButton(self.tr("Save PDF…"))
        self.save_button.setProperty("primary", True)
        row.addWidget(self.cancel_button)
        row.addWidget(self.save_button)
        lay.addLayout(row)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.save)
        self._update()

    def chosen(self) -> list[str]:
        """The checked kinds of pages, in the report order."""
        return [kind for kind in PAGES if self.pages[kind].isChecked()]

    def chosen_ways(self) -> list[str]:
        """Codes of the checked ways, in the list order."""
        items = [self.ways.item(i) for i in range(self.ways.count())]
        return [i.data(CODE_ROLE) for i in items if i.checkState() == Qt.CheckState.Checked]

    def _update(self, *_args) -> None:
        self.save_button.setEnabled(bool(self.chosen()) and bool(self.chosen_ways()))

    def save(self) -> None:
        """Write the report of the checks; close when it is written."""
        pages = self.chosen()
        ways = self.chosen_ways()
        if not pages or not ways:
            return
        if self._save(pages, ways):
            self.accept()
