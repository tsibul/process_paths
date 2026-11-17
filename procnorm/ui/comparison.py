# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Comparison tab: one tree of task groups, variants and their steps; side filter, sorting, export."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from procnorm import export
from procnorm.calc import Comparison, Group, Point, Row, compare, details, fmt, groups, money, series
from procnorm.project import FINAL, Project
from procnorm.ui import style
from procnorm.ui.pages import Page
from procnorm.ui.tables import ARROW, CHECK, DASH, Table, label, mono

SIDES = (("all", "All"), ("own", "Ours"), ("other", "Theirs"))
SIDE_TEXT = {"own": "● Ours", "other": "○ Theirs"}
NOT_REACHED = " (not reached)"
END = "end"
NO_PAIR = "No comparable variant"
NO_PAIR_NOTE = "Not compared: no other variant has the same task"
OUT = "Out of comparison"
HINT = ("Rows are grouped by task. Ours come first, then theirs; lower labour is cheaper, but skipped "
        "checks are counted separately. Click a row to see its steps.")
STEP_HEADERS = ["#", "Kind", "Executor", "Instrument", "Scope", "Cost", "Scope ×", "Executor ×", "Labour",
                "Skips left", "Changes"]
STEP_NUMERIC = {0, 5, 6, 7, 8, 9}
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


class StepsPanel(QFrame):
    """Steps of one variant under its row, then its skipped checks by slice."""

    def __init__(self, project: Project, row: Row) -> None:
        super().__init__()
        self.setObjectName("steps")
        self.changed: Callable[[], None] | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(34, 6, 10, 8)
        box.setSpacing(4)
        self.table = Table(STEP_HEADERS, STEP_NUMERIC)
        points = series(project, row.code)
        self.table.set_rows([
            [str(s.number), s.kind, s.executor, s.instrument, s.scope, fmt(s.cost), fmt(s.scope_coefficient),
             fmt(s.executor_coefficient), fmt(s.labour), str(p.skips_count),
             "; ".join(f"{e}/{a}: {b if b is not None else DASH} {ARROW} {x if x is not None else DASH}"
                       for e, a, b, x in s.changes)]
            for s, p in zip(details(project, row.code), points)])
        box.addWidget(self.table)
        self.skipped: list[QLabel] = []
        for s in row.slices:
            if s.skips:
                what = ", ".join(f"{e}/{a} ({fmt(p)})" for e, a, p in s.skips)
                w = label(f"Skipped checks, {_slice_label(s.name)}{NOT_REACHED if not s.reached else ''}: {what}")
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
    """One step of one variant in the Compare steps view: kind, running labour, skips left."""

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
        self.labour = QLabel(money(point.labour))
        self.skips = QLabel(f"Skips left: {point.skips_count}")
        self.skips.setStyleSheet(f"color: {style.ERR if point.skips_count else style.OK};")
        for w in (self.labour, self.skips):
            f = mono()
            f.setBold(last)
            w.setFont(f)
            box.addWidget(w)

    def lines(self) -> list[str]:
        """Kind, running labour, ``Skips left: N``."""
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
            head = max((fm.horizontalAdvance(x) for x in self.headerItem().text(c).split("\n")), default=0)
            self.setColumnWidth(c, max(self.sizeHintForColumn(c), head + extra))
        hh.setStretchLastSection(True)
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
    keys += [lambda r, i=i: r.slices[i].total for i in range(len(cmp.slice_names))]
    return keys


class ComparisonPage(Page):
    """The comparison of the variants of the current project."""

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
        self.hint = label(HINT, "note")
        self.box.addWidget(self.hint)
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
        self.export_bar = QWidget()
        self.export_bar.setLayout(buttons)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.box.addWidget(self.export_bar)
        self.box.addStretch(1)
        self._set_columns()

    # --- filling

    def show_project(self, p: Project | None) -> None:
        """Rebuild the tree; ``None`` empties it."""
        self.close_steps()
        self._project = p
        self._cmp = compare(p) if p is not None else None
        self._groups = groups(self._cmp) if self._cmp else []
        self._sort = None
        self._open = []
        self._set_columns()
        self.export_md.setEnabled(p is not None)
        self.export_csv.setEnabled(p is not None)
        self.notes.setText(self._notes_text())
        self._render()

    def _set_columns(self) -> None:
        cmp = self._cmp
        execs = cmp.executors if cmp else []
        names = [_slice_label(n) for n in cmp.slice_names] if cmp else []
        two = ([("Labour", x) for x in execs] + [("Labour", "total")] + [("Skipped checks", n) for n in names]
               if cmp else [])
        self._keys = ["Code", "Title", "Side", "Steps"] + [
            f"{a} · {b}" if a == "Labour" else f"{a}, {b}" for a, b in two]
        fm = QFontMetrics(_head_font())
        shown = ["Code", "Title", "Side", "Steps"] + [
            f"{a}\n{fm.elidedText(b, Qt.TextElideMode.ElideRight, HEAD_LINE)}" for a, b in two]
        t = self.tree
        t.clear()
        t.setColumnCount(len(shown))
        t.setHeaderLabels(shown)
        h = t.headerItem()
        for c, key in enumerate(self._keys):
            h.setToolTip(c, key)
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
                    for r in sorted((x for x in rows if x.side == side), key=key, reverse=desc)]
        return rows

    def _render(self) -> None:
        t = self.tree
        t.clear()
        self._items = {}
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
                self._items[r.code] = self._variant_item(top, r, g.kind != "task", r.total == least)
            top.setExpanded(True)
            t.setItemWidget(top, 0, head)
            head.ensurePolished()
            top.setSizeHint(0, QSize(0, head.sizeHint().height()))
        for code in self._open:
            if code in self._items:
                self._expand(self._items[code])
        t.fit()

    def _variant_item(self, parent: QTreeWidgetItem, r: Row, grey: bool, least: bool) -> QTreeWidgetItem:
        cmp = self._cmp
        title = r.title + (f"\nReason: {r.reason}" if r.reason else "")
        texts = [r.code, title, SIDE_TEXT.get(r.side, r.side), str(r.steps)]
        texts += [money(r.labour[x]) for x in cmp.executors] + [money(r.total)]
        texts += [money(s.total) + ("" if s.reached else NOT_REACHED) for s in r.slices]
        it = QTreeWidgetItem(parent, texts)
        it.setData(0, KIND, "variant")
        it.setData(0, CODE, r.code)
        it.setData(0, OWN, r.side == "own")
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        first_skip = len(texts) - len(r.slices)
        total = first_skip - 1
        for c in range(len(texts)):
            if c >= 3:
                it.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                f = mono()
                f.setBold(c == total and least)
                it.setFont(c, f)
            if c >= first_skip:
                s = r.slices[c - first_skip]
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
        self.hint.setVisible(on)
        self.export_bar.setVisible(on)
        for b in self.side_buttons.buttons():
            b.setEnabled(on)

    def open_codes(self) -> list[str]:
        """Codes of the shown variants with open steps, top to bottom."""
        return [c for c in self.codes() if c in self._open]

    # --- reading, for tests

    def headers(self) -> list[str]:
        """Column names in one line: ``Labour · <executor>``, ``Skipped checks, <slice>``."""
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

    def export_path(self, path: Path) -> None:
        """Write the comparison to a .md or .csv file."""
        export.write(self._project, Path(path))
