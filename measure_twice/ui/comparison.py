# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Comparison tab: one tree of task groups, variants and their steps; side filter, sorting, export."""

from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from measure_twice import export
from measure_twice.calc import Comparison, Group, Point, Row, compare, details, fmt, groups, series
from measure_twice.project import FINAL, Project
from measure_twice.ui import style
from measure_twice.ui.labour_scale import LabourScale
from measure_twice.ui.line_charts import LineCharts
from measure_twice.ui.pages import Page
from measure_twice.ui.tables import ARROW, CHECK, DASH, Table, label, mono

SIDES = (("all", "All"), ("own", "Ours"), ("other", "Theirs"))
SIDE_TEXT = style.SIDE_TEXT
NOT_REACHED = " (not reached)"
END = "end"
RISK = "Risk left"
RISK_TIP = "Price you gave to each check this way does not do."
NO_PAIR = "No comparable variant"
NO_PAIR_NOTE = "Not compared: no other variant has the same task"
OUT = "Out of comparison"
HINT = ("Rows are grouped by task. Ours come first, then theirs; lower labour is cheaper, but risk left "
        "is counted separately. Click a row to see its steps.")
STEP_HEADERS = ["#", "Kind", "Executor", "Instrument", "Scope", "Cost", "Scope ×", "Executor ×", "Labour",
                "Risk left", "Changes"]
STEP_NUMERIC = {0, 5, 6, 7, 8, 9}
PAD_X = 8  # horizontal item padding of the table stylesheet, px
PAD_Y = 6  # vertical item padding and border of the table stylesheet, px
CHANGES_SHARE = 2  # Changes gets twice the room of another text column of the steps table
HEAD_LINE = 120  # widest second line of a column label, px; longer names are elided
CHEVRON = 20  # room for ▸ / ▾ in the first column, px
STRIPE = 3  # accent stripe of our rows, px
KIND = Qt.ItemDataRole.UserRole  # "group", "variant" or "steps"
CODE = Qt.ItemDataRole.UserRole + 1
OWN = Qt.ItemDataRole.UserRole + 2


def _slice_label(name: str) -> str:
    return END if name == FINAL else name


def _head_font() -> QFont:
    f = QFont()
    f.setPixelSize(13)
    f.setBold(True)
    return f


class FirstCell(QStyledItemDelegate):
    """First cell of a variant row: the ▸ / ▾ sign and, for ours, the accent stripe on the left."""

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self.tree = tree

    def paint(self, painter, option, index) -> None:
        if index.data(KIND) != "variant":
            super().paint(painter, option, index)
            return
        r = option.rect
        if index.data(OWN):
            painter.fillRect(QRect(r.left(), r.top(), STRIPE, r.height()), QColor(style.ACCENT))
        painter.save()
        painter.setPen(QColor(style.TEXT2))
        sign = "▾" if self.tree.isExpanded(index) else "▸"
        painter.drawText(QRect(r.left() + STRIPE + 5, r.top(), CHEVRON, r.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sign)
        painter.restore()
        opt = QStyleOptionViewItem(option)
        opt.rect = r.adjusted(CHEVRON, 0, 0, 0)
        super().paint(painter, opt, index)

    def updateEditorGeometry(self, editor, option, index) -> None:  # noqa: N802 (Qt name)
        """Group headers and steps fill the whole row, without the item padding."""
        if index.data(KIND) in ("group", "steps"):
            editor.setGeometry(option.rect)
        else:
            super().updateEditorGeometry(editor, option, index)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt name)
        s = super().sizeHint(option, index)
        if index.data(KIND) == "variant":
            return QSize(s.width() + CHEVRON, s.height())
        if index.data(KIND) in ("group", "steps"):
            return QSize(0, s.height())  # spanned rows do not widen the first column
        return s


class GroupHeader(QFrame):
    """Header row of a group: title on the left, ``N variants`` on the right, a note under it."""

    def __init__(self, title: str, count: str, note: str | None, grey: bool, compare: bool = False) -> None:
        super().__init__()
        self.setObjectName("group")
        self.setProperty("grey", grey)
        self.grey = grey
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(2)
        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("groupTitle")
        top.addWidget(self.title)
        top.addStretch(1)
        self.actions = QHBoxLayout()  # count, then the group's buttons
        self.actions.setSpacing(12)
        top.addLayout(self.actions)
        self.count = QLabel(count)
        self.count.setObjectName("groupNote")
        self.actions.addWidget(self.count)
        self.compare = None
        if compare:
            self.compare = QPushButton("Compare steps")
            self.compare.setObjectName("small")
            self.actions.addWidget(self.compare)
        box.addLayout(top)
        self.note = None
        if note:
            self.note = QLabel(note)
            self.note.setObjectName("groupNote")
            box.addWidget(self.note)


class WrapTable(Table):
    """Steps table: ``Changes`` takes the rest of the width and text wraps by words, never cutting one.

    A horizontal scroll appears only when the widest words of the text columns alone exceed the width."""

    def __init__(self, headers: list[str], numeric: set[int]) -> None:
        super().__init__(headers, numeric)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def fit(self) -> None:
        super().fit()  # every column by content and header
        self.horizontalHeader().setStretchLastSection(False)
        self._natural = [self.columnWidth(c) for c in range(self.columnCount())]
        if self._natural:
            self._natural[-1] = max(self._natural[-1], self.sizeHintForColumn(self.columnCount() - 1))
        self._floor = [self._widest_word(c) for c in range(self.columnCount())]
        self._natural = [max(n, f) for n, f in zip(self._natural, self._floor)]
        self._wrap()

    def _widest_word(self, c: int) -> int:
        """Width of the widest single word of a column, header included, with the item padding."""
        fm = self.fontMetrics()
        head = QFont(self.font())
        head.setPixelSize(13)
        head.setBold(True)
        hm = QFontMetrics(head)
        words = [hm.horizontalAdvance(w) for w in self.horizontalHeaderItem(c).text().split()]
        nm = QFontMetrics(mono())
        for r in range(self.rowCount()):
            it = self.item(r, c)
            if c in self.numeric:  # a number cell does not wrap: ``not set`` stays on one line
                words += [nm.horizontalAdvance(it.text())] if it else []
            else:
                words += [fm.horizontalAdvance(w) for w in (it.text().split() if it else [])]
        return max(words, default=0) + 2 * self._pad()

    def _pad(self) -> int:
        """Space between a cell's edge and its text: stylesheet padding plus the style's text margin."""
        return PAD_X + self.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, self) + 1

    def _fit_rows(self) -> None:
        """Rows tall enough for every wrapped line (the stylesheet padding is not in Qt's own hint)."""
        self.resizeRowsToContents()
        fm = self.fontMetrics()
        for r in range(self.rowCount()):
            need = 0
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if it and it.text():
                    box = QRect(0, 0, max(self.columnWidth(c) - 2 * self._pad(), 1), 100000)
                    need = max(need, fm.boundingRect(box, Qt.TextFlag.TextWordWrap, it.text()).height())
            self.setRowHeight(r, max(self.rowHeight(r), need + PAD_Y))

    def _wrap(self) -> None:
        """Numbers keep their width; the text columns share the rest, a narrow one getting all it needs
        and ``Changes`` (the last) at least ``CHANGES_SHARE`` shares plus what is left."""
        natural = getattr(self, "_natural", [])
        if not natural:
            return
        last = len(natural) - 1
        room = self.viewport().width() - sum(natural[c] for c in self.numeric)
        pool = sorted((c for c in range(last) if c not in self.numeric), key=lambda c: natural[c])
        for c in self.numeric:
            self.setColumnWidth(c, natural[c])
        while pool and natural[pool[0]] <= room // (len(pool) + CHANGES_SHARE):
            c = pool.pop(0)
            self.setColumnWidth(c, natural[c])
            room -= natural[c]
        floor = getattr(self, "_floor", [0] * len(natural))
        share = room // (len(pool) + CHANGES_SHARE) if pool else 0
        for c in pool:
            self.setColumnWidth(c, max(share, floor[c]))
        room -= sum(self.columnWidth(c) for c in pool)
        self.setColumnWidth(last, max(room, floor[last]))
        self._fit_rows()
        total = sum(self.columnWidth(c) for c in range(len(natural)))
        self._content_width = total  # wider than the view only when the words alone do not fit
        self._fit_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._wrap()


class StepsPanel(QFrame):
    """Steps of one variant under its row, then its unchecked axes by slice."""

    def __init__(self, project: Project, row: Row) -> None:
        super().__init__()
        self.setObjectName("steps")
        self.changed: Callable[[], None] | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(34, 6, 10, 8)
        box.setSpacing(4)
        self.table = WrapTable(STEP_HEADERS, STEP_NUMERIC)
        failed = row.error is not None
        points = series(project, row.code)  # none for a variant with a run error
        self.table.set_rows([
            [str(s.number), s.kind, s.executor, s.instrument, s.scope] + export.step_numbers(s, failed)
            + [DASH if failed else str(points[i].skips_count),
               "; ".join(f"{e}/{a}: {b if b is not None else DASH} {ARROW} {x if x is not None else DASH}"
                         for e, a, b, x in s.changes)]
            for i, s in enumerate(details(project, row.code))])
        box.addWidget(self.table)
        self.skipped: list[QLabel] = []
        for s in row.slices:
            if s.skips:
                what = ", ".join(f"{e}/{a} ({export.number(p, fmt)})" for e, a, p in s.skips)
                name = f", {_slice_label(s.name)}" if len(row.slices) > 1 else ""
                reached = NOT_REACHED if not s.reached else ""
                w = label(f"Not checked{name}{reached}: {what}")
                w.setObjectName("skipped")
                self.skipped.append(w)
                box.addWidget(w)

    def event(self, e) -> bool:
        """A new height of the steps table reaches the tree row."""
        out = super().event(e)
        if e.type() == QEvent.Type.LayoutRequest and self.changed is not None:
            self.changed()
        return out


class StepCell(QFrame):
    """One step of one variant in the Compare steps view: kind, running labour, risk left."""

    def __init__(self, point: Point, last: bool, own: bool) -> None:
        super().__init__()
        self.setObjectName("cell")
        self.setProperty("own", own)
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.kind = QLabel(point.kind)
        self.kind.setObjectName("cellKind")
        self.kind.setWordWrap(True)
        top.addWidget(self.kind, 1)
        self.marker = QLabel(" ".join(f"{n} {CHECK}" for n in point.slices))
        self.marker.setObjectName("pill")
        self.marker.setVisible(bool(point.slices))
        top.addWidget(self.marker, 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(top)
        self.labour = QLabel(export.number(point.labour))
        self.skips = QLabel(f"Risk left: {point.skips_count}")
        self.skips.setStyleSheet(f"color: {style.ERR if point.skips_count else style.OK};")
        for w in (self.labour, self.skips):
            f = mono()
            f.setBold(last)
            w.setFont(f)
            box.addWidget(w)

    def lines(self) -> list[str]:
        """Kind, running labour, ``Risk left: N``."""
        return [self.kind.text(), self.labour.text(), self.skips.text()]

    def marker_text(self) -> str:
        """Names of the slices reached at this step, each with ✓; empty when none."""
        return self.marker.text()

    def bold(self) -> bool:
        """Whether the numbers are bold (the last step of the variant)."""
        return self.labour.font().bold()


class StepsView(QFrame):
    """Compare steps: the variants of one group as columns, step numbers on the left."""

    def __init__(self, project: Project, group: Group, rows: list[Row]) -> None:
        super().__init__()
        self.group = group
        self.setObjectName("stepsView")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        head = GroupHeader(f"Task: {group.task}", f"{len(group.rows)} variants", None, False, compare=True)
        head.setObjectName("viewHead")
        head.compare.setCheckable(True)
        head.compare.setChecked(True)
        head.compare.clicked.connect(lambda: head.compare.setChecked(True))
        self.back = QPushButton("Back to table")
        self.back.setObjectName("small")
        head.actions.addWidget(self.back)
        self.title = head.title
        box.addWidget(head)
        grid_frame = QFrame()
        grid_frame.setObjectName("grid")
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        corner = QFrame()
        corner.setObjectName("hc")
        grid.addWidget(corner, 0, 0)
        grid.setColumnMinimumWidth(0, 56)
        self._codes = [r.code for r in rows]
        self._heads: list[tuple[QLabel, QLabel, QLabel]] = []
        self._cells: dict[tuple[int, str], StepCell] = {}
        points = {r.code: series(project, r.code) for r in rows}
        steps = max((len(x) for x in points.values()), default=0)
        for j, r in enumerate(rows, 1):
            hc = QFrame()
            hc.setObjectName("hc")
            hc.setProperty("own", r.side == "own")
            hb = QVBoxLayout(hc)
            hb.setContentsMargins(10, 8, 10, 8)
            hb.setSpacing(0)
            line = QHBoxLayout()
            line.setSpacing(6)
            code, title, side = QLabel(r.code), QLabel(r.title), QLabel(SIDE_TEXT.get(r.side, r.side))
            code.setObjectName("colCode")
            title.setWordWrap(True)
            side.setObjectName("groupNote")
            line.addWidget(code, 0, Qt.AlignmentFlag.AlignTop)
            line.addWidget(title, 1)
            hb.addLayout(line)
            hb.addWidget(side)
            self._heads.append((code, title, side))
            grid.addWidget(hc, 0, j)
            grid.setColumnStretch(j, 1)
            for i in range(1, steps + 1):
                ps = points[r.code]
                if i <= len(ps):
                    w = StepCell(ps[i - 1], i == len(ps), r.side == "own")
                    self._cells[(i, r.code)] = w
                else:
                    w = QFrame()
                    w.setObjectName("empty")
                grid.addWidget(w, i, j)
        for i in range(1, steps + 1):
            n = QLabel(str(i))
            n.setObjectName("sn")
            n.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(n, i, 0)
        self._steps = steps
        box.addWidget(grid_frame)
        self.scale = LabourScale(project, rows)
        box.addWidget(self.scale)

    def codes(self) -> list[str]:
        """Codes of the columns, left to right."""
        return list(self._codes)

    def heads(self) -> list[tuple[str, str, str]]:
        """Column labels: code, title, ``● Ours`` / ``○ Theirs``."""
        return [(a.text(), b.text(), c.text()) for a, b, c in self._heads]

    def step_count(self) -> int:
        """Number of step rows: the longest variant."""
        return self._steps

    def cell(self, step: int, code: str) -> StepCell | None:
        """A cell; ``None`` below the last step of a shorter variant."""
        return self._cells.get((step, code))


class ChartPair(QWidget):
    """The two line charts of one task under the table, with the task name above them."""

    def __init__(self, project: Project, group: Group, rows: list[Row]) -> None:
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 12, 0, 0)
        box.setSpacing(4)
        self.title = QLabel(f"Task: {group.task}")
        self.title.setObjectName("groupTitle")
        box.addWidget(self.title)
        self.charts = LineCharts()  # the lines of this task only, as the rows of the table
        self.charts.set_rows(project, rows)
        box.addWidget(self.charts)


class GroupTree(QTreeWidget):
    """A read-only tree that takes the height of its rows (the page scrolls, not the tree)."""

    def __init__(self) -> None:
        super().__init__()
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setExpandsOnDoubleClick(False)
        self.setUniformRowHeights(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegateForColumn(0, FirstCell(self))
        hh = self.header()
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        hh.setSectionsMovable(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

    def visible_items(self) -> list[QTreeWidgetItem]:
        """Rows as laid out: groups, their variants, the steps of open variants."""
        out = []
        for g in range(self.topLevelItemCount()):
            top = self.topLevelItem(g)
            out.append(top)
            for v in range(top.childCount()):
                it = top.child(v)
                out.append(it)
                if it.isExpanded():
                    out += [it.child(i) for i in range(it.childCount())]
        return out

    def fit(self) -> None:
        """Columns by content and two-line labels; full height."""
        fm = QFontMetrics(_head_font())
        extra = 16 + 16
        hh = self.header()
        hh.setStretchLastSection(False)
        for c in range(self.columnCount()):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            head = max((fm.horizontalAdvance(x) for x in self.headerItem().text(c).split("\n")), default=0)
            self.setColumnWidth(c, max(self.sizeHintForColumn(c), head + extra))
        if self.columnCount() > 1:
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Title takes the rest
        self.sync_heights()

    def sync_heights(self) -> None:
        """Spanned rows take the height of their widgets; the tree takes the height of all rows."""
        for it in self.visible_items():
            w = self.itemWidget(it, 0)
            if w is not None and it.sizeHint(0).height() != w.sizeHint().height():
                it.setSizeHint(0, QSize(0, w.sizeHint().height()))
        self.doItemsLayout()
        rows = sum(self.visualItemRect(it).height() for it in self.visible_items())
        self.setFixedHeight(self.header().sizeHint().height() + rows + 2 * self.frameWidth())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self.sync_heights()


def _sort_keys(cmp: Comparison) -> list[Callable[[Row], object]]:
    keys: list[Callable[[Row], object]] = [lambda r: r.code, lambda r: r.title, lambda r: r.side,
                                           lambda r: r.steps]
    keys += [lambda r, x=x: r.labour[x] for x in cmp.executors]
    keys.append(lambda r: r.total)
    keys.append(lambda r: None if r.error else r.waiting)
    if cmp.waiting_weight > 0:
        keys.append(lambda r: r.labour_waiting)
    keys += [lambda r, i=i: r.slices[i].total if r.slices else None for i in range(len(cmp.slice_names))]
    return keys  # None: a number not set or a run error


class ComparisonPage(Page):
    """The comparison of the variants of the current project."""

    copied = Signal(str)  # a table or a chart was copied; the status text

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._cmp: Comparison | None = None
        self._groups: list[Group] = []
        self._side = "all"
        self._sort: tuple[int, Qt.SortOrder] | None = None
        self._open: list[str] = []
        self._keys: list[str] = []
        self._items: dict[str, QTreeWidgetItem] = {}
        self.steps_view: StepsView | None = None
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
        self.tree = GroupTree()
        self.tree.header().sectionClicked.connect(self._header_clicked)
        self.tree.itemClicked.connect(self._item_clicked)
        self.box.addWidget(self.tree)
        self.charts_box = QWidget()  # one pair of charts per task group, under the table
        self.charts_lay = QVBoxLayout(self.charts_box)
        self.charts_lay.setContentsMargins(0, 0, 0, 0)
        self.charts_lay.setSpacing(0)
        self._pairs: list[ChartPair] = []
        self.box.addWidget(self.charts_box)
        self.hint = label(HINT, "note")
        self.box.addWidget(self.hint)
        self.notes = label("", "note")
        self.notes.setTextFormat(Qt.TextFormat.PlainText)
        self.box.addWidget(self.notes)
        buttons = QHBoxLayout()
        self.export_md = QPushButton("Export table (Markdown)")
        self.export_md.setProperty("primary", True)
        self.export_csv = QPushButton("Export table (CSV)")
        buttons.addWidget(self.export_md)
        buttons.addWidget(self.export_csv)
        self.copy_table_button = QPushButton("Copy table")
        self.copy_table_button.clicked.connect(self.copy_table)
        buttons.addWidget(self.copy_table_button)
        self.report_button = QPushButton("Report (PDF)…")
        buttons.addWidget(self.report_button)
        buttons.addStretch(1)
        self.export_bar = QWidget()
        self.export_bar.setLayout(buttons)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.box.addWidget(self.export_bar)
        self.box.addStretch(1)
        self._set_columns()

    # --- filling

    def show_project(self, p: Project | None, keep: bool = False) -> None:
        """Rebuild the tree; ``None`` empties it.

        :param p: the project.
        :param keep: after an edit of the same project: keep the sorting (by column name), the open
            rows, the open Compare steps view and the scroll place; the side filter always stays.
        """
        sort = (self._keys[self._sort[0]], self._sort[1]) if keep and self._sort is not None else None
        opened = list(self._open) if keep else []
        task = self.steps_view.group.task if keep and self.steps_view is not None else None
        scroll = self.verticalScrollBar().value()
        self.close_steps()
        self._project = p
        self._cmp = compare(p) if p is not None else None
        self._groups = groups(self._cmp) if self._cmp else []
        self._sort = None
        self._open = []
        self._set_columns()
        if sort is not None and sort[0] in self._keys:
            self._sort = (self._keys.index(sort[0]), sort[1])
            self.tree.header().setSortIndicator(self._sort[0], sort[1])
        codes = {r.code for g in self._groups for r in g.rows}
        self._open = [c for c in opened if c in codes]
        self.export_md.setEnabled(p is not None)
        self.export_csv.setEnabled(p is not None)
        self.report_button.setEnabled(p is not None)
        self.notes.setText(self._notes_text())
        self._render()
        g = next((g for g in self._groups if g.kind == "task" and g.task == task), None)
        if g is not None:
            self.open_steps(g)
        if keep:
            self.verticalScrollBar().setValue(scroll)

    def _set_columns(self) -> None:
        cmp = self._cmp
        execs = cmp.executors if cmp else []
        names = [_slice_label(n) for n in cmp.slice_names] if cmp else []
        labour = [("Labour", x) for x in execs] + [("Labour", "total")] if cmp else []
        waiting = export.waiting_headers(cmp) if cmp else []
        skips = [(RISK, n) for n in names]
        fm = QFontMetrics(_head_font())

        def two_lines(a: str, b: str) -> str:
            return f"{a}\n{fm.elidedText(b, Qt.TextElideMode.ElideRight, HEAD_LINE)}"

        self._keys = (["Code", "Title", "Side", "Steps"]
                      + [f"{a} · {b}" for a, b in labour]
                      + waiting
                      + [f"{a}, {b}" for a, b in skips])
        shown = (["Code", "Title", "Side", "Steps"]
                 + [two_lines(a, b) for a, b in labour]
                 + waiting
                 + [two_lines(a, b) for a, b in skips])
        t = self.tree
        t.clear()
        t.setColumnCount(len(shown))
        t.setHeaderLabels(shown)
        h = t.headerItem()
        for c, key in enumerate(self._keys):
            h.setToolTip(c, RISK_TIP if key.startswith(f"{RISK}, ") else key)
            if c >= 3:
                h.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        t.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

    def _notes_text(self) -> str:
        cmp = self._cmp
        if cmp is None or not cmp.uncounted_errors:
            return ""
        lines = ["Uncounted errors (shown, never counted):"]
        lines += [f"  {g}: {text}" for g, texts in cmp.uncounted_errors.items() for text in texts]
        return "\n".join(lines)

    def _shown_rows(self, g: Group) -> list[Row]:
        rows = [r for r in g.rows if self._side == "all" or r.side == self._side]
        if self._sort is not None:
            col, order = self._sort
            key = _sort_keys(self._cmp)[col]
            desc = order == Qt.SortOrder.DescendingOrder
            rows = [r for side in ("own", "other")
                    for r in sorted((x for x in rows if x.side == side and key(x) is not None), key=key,
                                    reverse=desc)
                    + [x for x in rows if x.side == side and key(x) is None]]  # no number: last
        return rows

    def _render(self) -> None:
        t = self.tree
        t.clear()
        self._items = {}
        self.copy_table_button.setEnabled(any(self._shown_rows(g) for g in self._groups))
        self._render_charts()
        if self._cmp is None:
            t.fit()
            return
        for g in self._groups:
            rows = self._shown_rows(g)
            if not rows:
                continue
            top = QTreeWidgetItem(t)
            top.setData(0, KIND, "group")
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            top.setFirstColumnSpanned(True)
            if g.kind == "task":
                head = GroupHeader(f"Task: {g.task}", f"{len(g.rows)} variants", None, False, compare=True)
                head.compare.clicked.connect(lambda _=False, g=g: self.open_steps(g))
            elif g.kind == "no-pair":
                head = GroupHeader(NO_PAIR, "", NO_PAIR_NOTE, True)
            else:
                head = GroupHeader(OUT, "", None, True)
            least = min(r.total for r in rows) if g.kind == "task" else None
            for r in rows:
                self._items[r.code] = self._variant_item(top, r, g.kind != "task",
                                                         g.kind == "task" and r.total == least)
            top.setExpanded(True)
            t.setItemWidget(top, 0, head)
            head.ensurePolished()
            top.setSizeHint(0, QSize(0, head.sizeHint().height()))
        for code in self._open:
            if code in self._items:
                self._expand(self._items[code])
        t.fit()

    def _render_charts(self) -> None:
        """One pair of charts per task group with a variant shown; lines as the rows of the table."""
        for pair in self._pairs:
            self.charts_lay.removeWidget(pair)
            pair.hide()
            pair.deleteLater()
        self._pairs = []
        if self._cmp is None:
            return
        for g in self._groups:
            rows = self._shown_rows(g)
            if g.kind != "task" or not rows:
                continue
            pair = ChartPair(self._project, g, rows)
            self.charts_lay.addWidget(pair)
            self._pairs.append(pair)
            pair.charts.copied.connect(self.copied)

    def _variant_item(self, parent: QTreeWidgetItem, r: Row, grey: bool, least: bool) -> QTreeWidgetItem:
        cmp = self._cmp
        title = r.title + (f"\nReason: {r.reason}" if r.reason else "")
        texts = [r.code, title, SIDE_TEXT.get(r.side, r.side), str(r.steps)] + export.numbers(cmp, r)
        it = QTreeWidgetItem(parent, texts)
        it.setData(0, KIND, "variant")
        it.setData(0, CODE, r.code)
        it.setData(0, OWN, r.side == "own")
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        first_skip = len(texts) - len(cmp.slice_names)
        total = 4 + len(cmp.executors)
        for c in range(len(texts)):
            if c >= 3:
                it.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                f = mono()
                f.setBold(c == total and least)
                it.setFont(c, f)
            s = r.slices[c - first_skip] if c >= first_skip and r.slices else None
            if s is not None and s.total is not None:
                it.setForeground(c, QBrush(QColor(style.ERR if s.total > 0 else style.OK)))
            elif grey:
                it.setForeground(c, QBrush(QColor(style.TEXT2)))
        steps = QTreeWidgetItem(it)
        steps.setData(0, KIND, "steps")
        steps.setData(0, CODE, r.code)
        steps.setFlags(Qt.ItemFlag.ItemIsEnabled)
        steps.setFirstColumnSpanned(True)
        return it

    def _expand(self, it: QTreeWidgetItem) -> None:
        it.setExpanded(True)
        child = it.child(0)
        if self.tree.itemWidget(child, 0) is None:
            code = it.data(0, CODE)
            row = next(r for g in self._groups for r in g.rows if r.code == code)
            panel = StepsPanel(self._project, row)
            self.tree.setItemWidget(child, 0, panel)
            panel.ensurePolished()  # the stylesheet's fonts, before the columns are measured
            panel.table.fit()
            panel.changed = self.tree.sync_heights
            child.setSizeHint(0, QSize(0, panel.sizeHint().height()))

    # --- filter, sorting, opening

    def set_side(self, side: str) -> None:
        """Show all variants, or only ``"own"`` or ``"other"`` ones."""
        self._side = side
        for b, (key, _) in zip(self.side_buttons.buttons(), SIDES):
            b.setChecked(key == side)
        self._render()

    def sort(self, header: str, order: Qt.SortOrder) -> None:
        """Sort the rows within each group, ours above theirs, by the column with this header."""
        col = self.headers().index(header)
        self._sort = (col, order)
        self.tree.header().setSortIndicator(col, order)
        self._render()

    def _header_clicked(self, col: int) -> None:
        order = Qt.SortOrder.AscendingOrder
        if self._sort is not None and self._sort == (col, Qt.SortOrder.AscendingOrder):
            order = Qt.SortOrder.DescendingOrder
        self.sort(self._keys[col], order)

    def _item_clicked(self, it: QTreeWidgetItem, _col: int) -> None:
        if it.data(0, KIND) == "variant":
            self.toggle(it.data(0, CODE))

    def toggle(self, code: str) -> None:
        """Open the steps of a variant under its row, or close them."""
        it = self._items.get(code)
        if code in self._open:
            self._open.remove(code)
            if it is not None:
                it.setExpanded(False)
        else:
            self._open.append(code)
            if it is not None:
                self._expand(it)
        self.tree.sync_heights()

    def open_steps(self, g: Group) -> None:
        """Show the Compare steps view of a group in place of the table."""
        self.close_steps()
        self.steps_view = StepsView(self._project, g, self._shown_rows(g))
        self.steps_view.back.clicked.connect(self.close_steps)
        self.box.insertWidget(self.box.indexOf(self.tree) + 1, self.steps_view)
        self._table_mode(False)

    def close_steps(self) -> None:
        """Back to the table, with its open rows, sorting and filter as they were."""
        if self.steps_view is None:
            return
        self.box.removeWidget(self.steps_view)
        self.steps_view.hide()
        self.steps_view.deleteLater()
        self.steps_view = None
        self._table_mode(True)

    def _table_mode(self, on: bool) -> None:
        self.tree.setVisible(on)
        self.charts_box.setVisible(on)
        self.hint.setVisible(on)
        self.export_bar.setVisible(on)
        for b in self.side_buttons.buttons():
            b.setEnabled(on)

    def open_codes(self) -> list[str]:
        """Codes of the shown variants with open steps, top to bottom."""
        return [c for c in self.codes() if c in self._open]

    # --- reading, for tests

    def headers(self) -> list[str]:
        """Column names in one line: ``Labour · <executor>``, ``Risk left, <slice>``."""
        return list(self._keys)

    def header_text(self, header: str) -> str:
        """Column label as shown, in two lines."""
        return self.tree.headerItem().text(self._keys.index(header))

    def header_tooltip(self, header: str) -> str:
        """Tooltip of a column label: the full name."""
        return self.tree.headerItem().toolTip(self._keys.index(header))

    def codes(self) -> list[str]:
        """Codes of the shown rows, top to bottom."""
        return [it.data(0, CODE) for it in self.tree.visible_items() if it.data(0, KIND) == "variant"]

    def item(self, code: str) -> QTreeWidgetItem:
        """Row of a shown variant."""
        return self._items[code]

    def cell(self, code: str, header: str) -> str:
        """Text of one cell."""
        return self._items[code].text(self._keys.index(header))

    def is_bold(self, code: str, header: str) -> bool:
        """Whether a cell is bold."""
        return self._items[code].font(self._keys.index(header)).bold()

    def chart_pairs(self) -> list[ChartPair]:
        """Chart pairs under the table, top to bottom."""
        return list(self._pairs)

    def group_headers(self) -> list[GroupHeader]:
        """Headers of the shown groups, top to bottom."""
        t = self.tree
        return [t.itemWidget(t.topLevelItem(i), 0) for i in range(t.topLevelItemCount())]

    def steps(self, code: str) -> Table:
        """Steps table of an open variant."""
        return self._panel(code).table

    def skipped_labels(self, code: str) -> list[QLabel]:
        """Skipped-check lines under the steps of an open variant."""
        return self._panel(code).skipped

    def _panel(self, code: str) -> StepsPanel:
        return self.tree.itemWidget(self._items[code].child(0), 0)

    def notes_text(self) -> str:
        """Uncounted errors as shown."""
        return self.notes.text()

    # --- export

    def copy_table(self) -> None:
        """Put the shown table on the clipboard as HTML and as tab-separated text."""
        if self._cmp is None:
            return
        shown = [(g, self._shown_rows(g)) for g in self._groups]
        lines = export.shown_table(self._cmp, [(g, rows) for g, rows in shown if rows])
        text = "\n".join("\t".join(cells) for cells in lines)
        head = "".join(f"<th>{html.escape(c)}</th>" for c in lines[0])
        body = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>"
                       for cells in lines[1:])
        data = QMimeData()
        data.setHtml(f"<table border=\"1\"><tr>{head}</tr>{body}</table>")
        data.setText(text)
        QGuiApplication.clipboard().setMimeData(data)
        self.copied.emit("Copied table")

    def export_path(self, path: Path) -> None:
        """Write the comparison to a .md or .csv file."""
        export.write(self._project, Path(path))
