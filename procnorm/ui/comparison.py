# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Comparison tab: the table from ``compare``, side filter, sorting, details, export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QButtonGroup, QHBoxLayout, QPushButton, QTableWidgetItem

from procnorm import export
from procnorm.calc import Comparison, compare, details, fmt, money
from procnorm.project import Project
from procnorm.ui import style
from procnorm.ui.pages import Page
from procnorm.ui.tables import ARROW, DASH, Table, label, mono

SIDES = (("all", "All"), ("own", "Own"), ("other", "Other"))
NOT_REACHED = " (not reached)"


class SortItem(QTableWidgetItem):
    """A cell that sorts by its key (Decimal or int for numbers), not by its text."""

    def __init__(self, text: str, key: object, numeric: bool) -> None:
        super().__init__(text)
        self.key = key
        self.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if numeric:
            self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setFont(mono())

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortItem):
            return self.key < other.key
        return super().__lt__(other)


class ComparisonPage(Page):
    """The comparison of the variants of the current project."""

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._cmp: Comparison | None = None
        self._side = "all"
        self.box.addWidget(label("Comparison", "h2"))
        bar = QHBoxLayout()
        bar.addWidget(label("Side:", "note"))
        self.side_buttons = QButtonGroup(self)
        for key, text in SIDES:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self.set_side(k))
            self.side_buttons.addButton(b)
            bar.addWidget(b)
        bar.addStretch(1)
        self.box.addLayout(bar)
        self.table = Table(["Code", "Title", "Side", "Steps"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.itemSelectionChanged.connect(self._row_selected)
        self.box.addWidget(self.table)
        self.box.addWidget(label("Sort by any column; filter by side. Lower labour is cheaper, but skipped "
                                 "checks are counted separately.", "note"))
        self.details_title = label("", "h3")
        self.box.addWidget(self.details_title)
        self.details = Table(["#", "Kind", "Executor", "Instrument", "Scope", "Cost", "Scope ×", "Executor ×",
                              "Labour", "Changes"], {0, 5, 6, 7, 8})
        self.box.addWidget(self.details)
        self.skipped = label("", "err")
        self.box.addWidget(self.skipped)
        self.notes = label("", "note")
        self.notes.setTextFormat(Qt.TextFormat.PlainText)
        self.box.addWidget(self.notes)
        buttons = QHBoxLayout()
        self.export_md = QPushButton("Export Markdown")
        self.export_md.setProperty("primary", True)
        self.export_csv = QPushButton("Export CSV")
        buttons.addWidget(self.export_md)
        buttons.addWidget(self.export_csv)
        buttons.addStretch(1)
        self.box.addLayout(buttons)
        self.box.addStretch(1)

    # --- filling

    def show_project(self, p: Project | None) -> None:
        """Rebuild the table; ``None`` empties it."""
        self._project = p
        self._cmp = compare(p) if p is not None else None
        cmp = self._cmp
        t = self.table
        t.setSortingEnabled(False)
        t.clearSelection()
        execs = cmp.executors if cmp else []
        names = cmp.slice_names if cmp else []
        headers = (["Code", "Title", "Side", "Steps"] + [f"Labour: {x}" for x in execs] + ["Labour total"]
                   + [f"Skips at {n}" for n in names]) if cmp else ["Code", "Title", "Side", "Steps"]
        t.numeric = set(range(3, len(headers)))
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        for c in range(len(headers)):
            h = t.horizontalHeaderItem(c)
            h.setTextAlignment((Qt.AlignmentFlag.AlignRight if c in t.numeric else Qt.AlignmentFlag.AlignLeft)
                               | Qt.AlignmentFlag.AlignVCenter)
        rows = cmp.rows if cmp else []
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = [SortItem(row.code, row.code, False), SortItem(row.title, row.title, False),
                     SortItem(row.side, row.side, False), SortItem(str(row.steps), row.steps, True)]
            cells += [SortItem(money(row.labour[x]), row.labour[x], True) for x in execs]
            total = SortItem(money(row.total), row.total, True)
            f = total.font()
            f.setBold(True)
            total.setFont(f)
            cells.append(total)
            for s in row.slices:
                it = SortItem(money(s.total) + ("" if s.reached else NOT_REACHED), s.total, True)
                it.setForeground(QBrush(QColor(style.ERR if s.total > 0 else style.OK)))
                cells.append(it)
            for c, it in enumerate(cells):
                t.setItem(r, c, it)
        t.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        t.setSortingEnabled(True)
        self.export_md.setEnabled(p is not None)
        self.export_csv.setEnabled(p is not None)
        self._apply_side()
        self.notes.setText(self._notes_text())
        if self.codes():
            self.select_code(self.codes()[0])
        else:
            self._row_selected()

    def _notes_text(self) -> str:
        cmp = self._cmp
        if cmp is None:
            return ""
        lines = []
        if cmp.excluded:
            lines.append("Out of comparison:")
            lines += [f"  {code} · {title} — {reason}" for code, title, reason in cmp.excluded]
        if cmp.uncounted_errors:
            lines.append("Uncounted errors (shown, never counted):")
            lines += [f"  {g}: {text}" for g, texts in cmp.uncounted_errors.items() for text in texts]
        return "\n".join(lines)

    # --- filter, sorting, selection

    def set_side(self, side: str) -> None:
        """Show all variants, or only ``"own"`` or ``"other"`` ones."""
        self._side = side
        for b, (key, _) in zip(self.side_buttons.buttons(), SIDES):
            b.setChecked(key == side)
        self._apply_side()

    def _apply_side(self) -> None:
        t = self.table
        for r in range(t.rowCount()):
            t.setRowHidden(r, self._side != "all" and t.item(r, 2).text() != self._side)
        t.fit()
        sel = t.selectionModel().selectedRows()
        if sel and t.isRowHidden(sel[0].row()):
            t.clearSelection()

    def sort(self, header: str, order: Qt.SortOrder) -> None:
        """Sort by the column with this header."""
        self.table.sortByColumn(self.headers().index(header), order)

    def headers(self) -> list[str]:
        """Column headers."""
        t = self.table
        return [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]

    def codes(self) -> list[str]:
        """Codes of the shown rows, top to bottom."""
        t = self.table
        return [t.item(r, 0).text() for r in range(t.rowCount()) if not t.isRowHidden(r)]

    def cell(self, code: str, header: str) -> str:
        """Text of one cell."""
        t = self.table
        c = self.headers().index(header)
        r = next(r for r in range(t.rowCount()) if t.item(r, 0).text() == code)
        return t.item(r, c).text()

    def select_code(self, code: str) -> None:
        """Select a variant and show its steps."""
        t = self.table
        for r in range(t.rowCount()):
            if t.item(r, 0).text() == code:
                t.selectRow(r)
                return

    def _row_selected(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if self._project is None or not sel:
            self.details_title.setText("")
            self.details.set_rows([])
            self.skipped.setText("")
            return
        r = sel[0].row()
        code = self.table.item(r, 0).text()
        row = next(x for x in self._cmp.rows if x.code == code)
        self.details_title.setText(f"DETAILS: {row.code} · {row.title}")
        self.details.set_rows([
            [str(s.number), s.kind, s.executor, s.instrument, s.scope, fmt(s.cost), fmt(s.scope_coefficient),
             fmt(s.executor_coefficient), fmt(s.labour),
             "; ".join(f"{e}/{a}: {b if b is not None else DASH} {ARROW} {x if x is not None else DASH}"
                       for e, a, b, x in s.changes)]
            for s in details(self._project, code)])
        parts = []
        for s in row.slices:
            if s.skips:
                what = ", ".join(f"{e}/{a} ({fmt(p)})" for e, a, p in s.skips)
                parts.append(f"Skipped at {s.name}{NOT_REACHED if not s.reached else ''}: {what}")
        self.skipped.setText("\n".join(parts))

    def notes_text(self) -> str:
        """Out-of-comparison variants and uncounted errors as shown."""
        return self.notes.text()

    # --- export

    def export_path(self, path: Path) -> None:
        """Write the comparison to a .md or .csv file."""
        export.write(self._project, Path(path))
