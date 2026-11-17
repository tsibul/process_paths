# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Step chains tab: the paths by group on the left, the human steps of one path with their transitions."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QLabel, QStyle, QVBoxLayout, QWidget

from procnorm.calc import Link, Row, chain, compare, empty_steps, groups
from procnorm.project import Project
from procnorm.ui import style
from procnorm.ui.comparison import NO_PAIR, OUT, PAD_X, SIDE_TEXT, GroupHeader
from procnorm.ui.pages import Page
from procnorm.ui.tables import Table, item, mono

LIST_WIDTH = 300  # px, as the mockup's path list
STEP_COL = 32  # step number column, px
RESERVED = 150  # empty room right of Scope for the editing buttons of version 2, px
SLICE_ROW = 26  # height of a slice marker row, px
SLACK = 4  # rounding room so a measured text does not wrap, px
ROW_PAD = 14  # vertical padding and border of a row, px
HEADERS = ["", "#", "Kind", "Executor", "Instrument", "Scope", ""]
NO_TRANSITIONS = "No transitions"
STEPS_NOT_GIVEN = "Steps not given"
SEP = " · "


def _count(n: int, one: str) -> str:
    return f"{n} {one if n == 1 else one + 's'}"


def _slice_text(name: str) -> str:
    return f"slice “{name}” reached"


def _title_html(code: str, title: str) -> str:
    return f"<b>{escape(code)}</b> {escape(title)}"


class PathItem(QFrame):
    """One path of the list: code and title; side and transitions; steps without transitions."""

    def __init__(self, row: Row, empty: int, grey: bool, chosen: Callable[[str], None]) -> None:
        super().__init__()
        self.setObjectName("path")
        self.code = row.code
        self.own = row.side == "own"
        self.grey = grey
        self.selected = False
        self._chosen = chosen
        self._plain_title = f"{row.code} {row.title}"
        self.setProperty("own", self.own)
        self.setProperty("grey", grey)
        self.setProperty("cur", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(1)
        self.title = QLabel(_title_html(row.code, row.title))
        self.title.setObjectName("pathTitle")
        self.title.setWordWrap(True)
        box.addWidget(self.title)
        self.meta = QLabel(f"{SIDE_TEXT.get(row.side, row.side)}{SEP}{_count(row.steps, 'transition')}")
        self.meta.setObjectName("groupNote")
        box.addWidget(self.meta)
        self.warn = None
        if empty:
            self.warn = QLabel(f"{_count(empty, 'step')} without transitions")
            self.warn.setObjectName("warn")
            box.addWidget(self.warn)

    def set_selected(self, on: bool) -> None:
        """Highlight the path as chosen."""
        self.selected = on
        self.setProperty("cur", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() == Qt.MouseButton.LeftButton:
            self._chosen(self.code)
        super().mousePressEvent(event)

    def title_text(self) -> str:
        """``<code> <title>`` without markup."""
        return self._plain_title

    def meta_text(self) -> str:
        """``● Ours`` / ``○ Theirs`` · ``N transitions``."""
        return self.meta.text()

    def warn_text(self) -> str | None:
        """``N step(s) without transitions``; ``None`` when every step has transitions."""
        return self.warn.text() if self.warn is not None else None


class SliceMark(QWidget):
    """A dashed accent line across the chain with ``slice “<name>” reached`` on it."""

    def __init__(self, text: str, offset: Callable[[], int]) -> None:
        super().__init__()
        self.text = text
        self._offset = offset
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(style.BG))
        accent = QColor(style.ACCENT)
        pen = QPen(accent, 1.5, Qt.PenStyle.DashLine)
        y = self.height() // 2
        p.setPen(pen)
        p.drawLine(10, y, self.width() - 10, y)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        x = self._offset()
        w = fm.horizontalAdvance(self.text) + 12
        box = QRect(x, 0, w, self.height())
        p.fillRect(box, QColor(style.BG))
        p.setPen(accent)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class ChainTable(Table):
    """Human steps across the table, each followed by its transitions; slice markers between them.

    Columns: step number, ``#``, ``Kind``, ``Executor``, ``Instrument``, ``Scope`` and an empty one
    kept for the editing buttons of version 2. ``Kind`` takes the rest of the width."""

    def __init__(self) -> None:
        super().__init__(HEADERS, {1})
        self.kinds: list[str] = []
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_chain(self, links: list[Link]) -> None:
        """Replace all rows with the links of one path."""
        self.clearSpans()
        self.setRowCount(0)
        self.kinds = []
        rows: list[tuple[str, object]] = []
        n = 0
        for link in links:
            if link.text is not None:
                n += 1
                rows.append(("step", (str(n), link.text)))
            if link.empty:
                rows.append(("none", None))
            marks = dict()
            for number, name in link.slices:
                marks.setdefault(number, []).append(name)
            for c in link.calls:
                rows.append(("call", c))
                rows += [("slice", name) for name in marks.get(c.number, [])]
        self.setRowCount(len(rows))
        step_bg = QColor(style.STEP_BG)
        for r, (kind, data) in enumerate(rows):
            self.kinds.append(kind)
            if kind == "step":
                number, text = data
                for c in range(self.columnCount()):
                    it = item("")
                    it.setBackground(step_bg)
                    self.setItem(r, c, it)
                num = self.item(r, 0)
                num.setText(number)
                num.setForeground(QColor(style.ACCENT))
                f = num.font()
                f.setBold(True)
                num.setFont(f)
                txt = self.item(r, 1)
                txt.setText(text)
                f = txt.font()
                f.setBold(True)
                txt.setFont(f)
                self.setSpan(r, 1, 1, 5)
            elif kind == "none":
                it = item(NO_TRANSITIONS)
                it.setForeground(QColor(style.TEXT2))
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
                self.setItem(r, 2, it)
                self.setSpan(r, 2, 1, 4)
            elif kind == "call":
                for c, text in enumerate([str(data.number), data.kind, data.executor, data.instrument,
                                          data.scope], 1):
                    self.setItem(r, c, item(text, c in self.numeric))
            else:
                self.setSpan(r, 0, 1, self.columnCount())
                self.setCellWidget(r, 0, SliceMark(_slice_text(data), self._kind_left))
        self.fit()

    def _kind_left(self) -> int:
        return self.columnWidth(0) + self.columnWidth(1)

    def fit(self) -> None:
        """Columns by the transitions and the labels; ``Kind`` takes the rest; rows by wrapped text."""
        if not hasattr(self, "kinds"):
            return
        self.ensurePolished()  # the stylesheet's font, before the columns are measured
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(0)
        head = QFont(self.font())
        head.setPixelSize(13)
        head.setBold(True)
        hm, fm, nm = QFontMetrics(head), self.fontMetrics(), QFontMetrics(mono())
        pad = 2 * self._pad() + SLACK
        for c in range(1, 6):
            width = hm.horizontalAdvance(HEADERS[c]) + pad
            for r, kind in enumerate(self.kinds):
                it = self.item(r, c)
                if kind == "call" and it is not None:
                    m = nm if c in self.numeric else fm
                    width = max(width, m.horizontalAdvance(it.text()) + pad)
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, width)
        for c, w in ((0, STEP_COL), (6, RESERVED)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, w)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._content_width = 0
        self._fit_rows()

    def _pad(self) -> int:
        """Space between a cell's edge and its text: stylesheet padding plus the style's text margin."""
        return PAD_X + self.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, self) + 1

    def _fit_rows(self) -> None:
        """Every row tall enough for its wrapped text; slice markers of a fixed height."""
        fm = self.fontMetrics()
        bold = QFont(self.font())
        bold.setBold(True)
        bm = QFontMetrics(bold)
        pad = 2 * self._pad()
        for r, kind in enumerate(self.kinds):
            if kind == "slice":
                self.setRowHeight(r, SLICE_ROW)
                continue
            need = fm.height()
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if it is None or not it.text():
                    continue
                span = sum(self.columnWidth(c + i) for i in range(self.columnSpan(r, c)))
                m = bm if kind == "step" else fm
                box = QRect(0, 0, max(span - pad, 1), 100000)
                need = max(need, m.boundingRect(box, Qt.TextFlag.TextWordWrap, it.text()).height())
            self.setRowHeight(r, need + ROW_PAD)
        self._fit_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._fit_rows()

    def rows(self) -> list[tuple[str, ...]]:
        """Rows as texts: ``("step", n, text)``, ``("call", #, kind, executor, instrument, scope)``,
        ``("none", "No transitions")``, ``("slice", "slice “<name>” reached")``."""
        out: list[tuple[str, ...]] = []
        for r, kind in enumerate(self.kinds):
            if kind == "step":
                out.append(("step", self.item(r, 0).text(), self.item(r, 1).text()))
            elif kind == "none":
                out.append(("none", self.item(r, 2).text()))
            elif kind == "call":
                out.append(("call",) + tuple(self.item(r, c).text() for c in range(1, 6)))
            else:
                out.append(("slice", self.cellWidget(r, 0).text))
        return out


class ChainsPage(Page):
    """Paths of the current project by group, and the chain of the chosen one."""

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._rows: dict[str, Row] = {}
        self._items: dict[str, PathItem] = {}
        self._groups: list[tuple[str, bool, list[str]]] = []
        self._current: str | None = None
        split = QHBoxLayout()
        split.setSpacing(16)
        self.list = QFrame()
        self.list.setObjectName("pathList")
        self.list.setFixedWidth(LIST_WIDTH)
        self.list_box = QVBoxLayout(self.list)
        self.list_box.setContentsMargins(1, 1, 1, 1)
        self.list_box.setSpacing(0)
        split.addWidget(self.list, 0, Qt.AlignmentFlag.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(10, 0, 10, 8)
        self.title = QLabel("")
        self.title.setObjectName("chainTitle")
        head.addWidget(self.title, 1)
        self.meta = QLabel("")
        self.meta.setObjectName("groupNote")
        head.addWidget(self.meta, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        right.addLayout(head)
        self.table = ChainTable()
        right.addWidget(self.table)
        right.addStretch(1)
        split.addLayout(right, 1)
        self.box.addLayout(split)
        self.box.addStretch(1)

    # --- filling

    def show_project(self, p: Project | None) -> None:
        """Rebuild the list and show the first path; ``None`` empties the tab."""
        self._project = p
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._rows, self._items, self._groups, self._current = {}, {}, [], None
        self.list.setVisible(p is not None)
        if p is not None:
            head = QLabel("Paths")
            head.setObjectName("listHead")
            self.list_box.addWidget(head)
            for g in groups(compare(p)):
                if g.kind == "task":
                    title, grey = f"Task: {g.task}", False
                else:
                    title, grey = (NO_PAIR if g.kind == "no-pair" else OUT), True
                self.list_box.addWidget(GroupHeader(title, "", None, grey))
                for r in g.rows:
                    self._rows[r.code] = r
                    it = PathItem(r, empty_steps(p, r.code), g.kind == "out", self.select_path)
                    self._items[r.code] = it
                    self.list_box.addWidget(it)
                self._groups.append((title, grey, [r.code for r in g.rows]))
        codes = self.codes()
        self.select_path(codes[0] if codes else None)

    def select_path(self, code: str | None) -> None:
        """Show the chain of a path and highlight it in the list; ``None`` shows nothing."""
        if code is not None and code not in self._items:
            return
        self._current = code
        for c, it in self._items.items():
            it.set_selected(c == code)
        if code is None:
            self.title.setText("")
            self.meta.setText("")
            self.table.set_chain([])
            return
        r = self._rows[code]
        steps = self._project.steps.get(code)
        parts = [SIDE_TEXT.get(r.side, r.side)]
        if r.task is not None:
            parts.append(f"Task: {r.task}")
        parts.append(STEPS_NOT_GIVEN if steps is None else _count(len(steps), "step"))
        parts.append(_count(r.steps, "transition"))
        self.title.setText(_title_html(r.code, r.title))
        self.meta.setText(SEP.join(parts))
        self.table.set_chain(chain(self._project, code))

    # --- reading, for tests and other parts of the window

    def codes(self) -> list[str]:
        """Codes of the paths, top to bottom."""
        return [c for _, _, codes in self._groups for c in codes]

    def groups(self) -> list[tuple[str, bool, list[str]]]:
        """Groups of the list: header text, grey, codes."""
        return [(t, g, list(c)) for t, g, c in self._groups]

    def path(self, code: str) -> PathItem:
        """Row of a path in the list."""
        return self._items[code]

    def current_code(self) -> str | None:
        """Code of the chosen path."""
        return self._current

    def head_title(self) -> str:
        """``<code> <title>`` of the chosen path, without markup."""
        r = self._rows.get(self._current) if self._current else None
        return f"{r.code} {r.title}" if r else ""

    def head_meta(self) -> str:
        """Side · ``Task: <task>`` · ``N steps`` or ``Steps not given`` · ``M transitions``."""
        return self.meta.text()

    def rows(self) -> list[tuple[str, ...]]:
        """Rows of the chain as texts."""
        return self.table.rows()

    def row_kinds(self) -> list[str]:
        """``step``, ``call``, ``none`` or ``slice`` for every row of the chain."""
        return list(self.table.kinds)
