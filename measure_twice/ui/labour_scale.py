# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Labour scale of the Compare steps view: one bar per variant on a shared axis of running labour.

The widget first builds the list of what it draws (segments, zero-step lines, check marks, slice dashes,
status strip, end label) from :func:`series` and :func:`start_point`, then paints that list.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QStaticText
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from measure_twice.calc import Point, Row, fmt, money, series, start_point
from measure_twice.project import Project
from measure_twice.ui import style
from measure_twice.ui.tables import CHECK, mono

LABEL_W = 230
AXIS_H = 22
ROW_H = 72
END_ROOM = 140
SEG_TOP, SEG_H = 26, 20
STRIP_TOP, STRIP_H = 50, 6
LEGEND_GAP = 16
LEGEND_LINE = 22
END_NOTE = "Right of bar: Labour · total · Skipped checks, end"


@dataclass
class Segment:
    """One step with labour: from ``start`` to ``end`` of running labour."""

    number: int
    start: Decimal
    end: Decimal
    executor: str
    color: str
    text_color: str
    text: str
    tip: str


@dataclass
class Mark:
    """A mark at the end of a step: zero-labour line, check or slice dash (``name``)."""

    number: int
    at: Decimal
    name: str = ""
    tip: str = ""


@dataclass
class Piece:
    """One piece of the status strip under the bar."""

    start: Decimal
    end: Decimal
    color: str


@dataclass
class ScaleRow:
    """What the scale draws for one variant."""

    code: str
    title: str
    side: str
    own: bool
    total: Decimal
    skips_total: Decimal
    skips_color: str
    segments: list[Segment] = field(default_factory=list)
    zeros: list[Mark] = field(default_factory=list)
    checks: list[Mark] = field(default_factory=list)
    slices: list[Mark] = field(default_factory=list)
    strip: list[Piece] = field(default_factory=list)

    def end_text(self) -> tuple[str, str]:
        """Right of the bar: total labour and the skipped checks at the end."""
        return money(self.total), money(self.skips_total)


def _ticks(end: Decimal) -> list[Decimal]:
    """Round ticks from 0 to the first one at or beyond ``end``."""
    if end <= 0:
        return [Decimal(0), Decimal(1)]
    raw = end / 5
    mag = Decimal(10) ** raw.adjusted()
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    n = (end / step).to_integral_value(ROUND_CEILING)
    return [i * step for i in range(int(n) + 1)]


def _row(project: Project, r: Row, colors: dict[str, tuple[str, str]]) -> ScaleRow:
    pts: list[Point] = [start_point(project, r.code)] + series(project, r.code)
    last = pts[-1]
    out = ScaleRow(r.code, r.title, style.SIDE_TEXT.get(r.side, r.side), r.side == "own", last.labour,
                   last.skips_total, style.OK if last.skips_total == 0 else style.ERR)
    for a, b in zip(pts, pts[1:]):
        step = b.labour - a.labour
        tip = f"{b.kind}, {b.executor}: {money(step)}"
        if step:
            fill, ink = colors[b.executor]
            out.segments.append(Segment(b.number, a.labour, b.labour, b.executor, fill, ink, money(step), tip))
        else:
            out.zeros.append(Mark(b.number, b.labour, tip=tip))
        if b.done_total > a.done_total:
            out.checks.append(Mark(b.number, b.labour))
        if b.slices:
            out.slices.append(Mark(b.number, b.labour, ", ".join(b.slices)))
        out.strip.append(Piece(a.labour, b.labour, style.SCALE_OPEN if a.skips_count else style.SCALE_DONE))
    return out


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class LabourScale(QWidget):
    """Labour scale of a group: rows are the given variants in the given order.

    A variant with a number not set or a run error has no bar."""

    def __init__(self, project: Project, rows: list[Row]) -> None:
        super().__init__()
        names = [e.name for e in project.model.executors]
        colors = {e: style.SCALE_STEPS[i % len(style.SCALE_STEPS)] for i, e in enumerate(names)}
        self._rows = [_row(project, r, colors) for r in rows if not (r.missing or r.error)]
        self._end = max((r.total for r in self._rows), default=Decimal(0))
        self._ticks = _ticks(self._end)
        used = {s.executor for r in self._rows for s in r.segments}
        slice_names = list(dict.fromkeys(m.name for r in self._rows for m in r.slices))
        self._legend: list[tuple[str, str, str | None]] = (
            [("swatch", f"{e} step", colors[e][0]) for e in names if e in used]
            + [("zero", "zero-labour step", None), ("check", "check step", None)]
            + [("slice", f"slice “{n}”", None) for n in slice_names or ["named"]]
            + [("swatch", "skipped checks still open", style.SCALE_OPEN),
               ("swatch", "all checked", style.SCALE_DONE)])
        self.setMouseTracking(True)
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    # What is drawn ----------------------------------------------------------------------------------

    def rows(self) -> list[ScaleRow]:
        """What each row draws, top to bottom."""
        return list(self._rows)

    def axis_end(self) -> Decimal:
        """The largest total labour among the rows; 0 without rows."""
        return self._end

    def ticks(self) -> list[Decimal]:
        """Round ticks of the axis, from 0 to the first one at or beyond :meth:`axis_end`."""
        return list(self._ticks)

    def legend(self) -> list[tuple[str, str | None]]:
        """Legend items: text and swatch colour (``None`` for a drawn sign)."""
        return [(t, c) for _, t, c in self._legend]

    # Geometry ---------------------------------------------------------------------------------------

    def _plot_w(self) -> float:
        return max(100.0, self.width() - LABEL_W - END_ROOM)

    def x_of(self, value: Decimal) -> float:
        """Horizontal position of a running labour value."""
        return LABEL_W + float(value) / float(self._ticks[-1]) * self._plot_w()

    def _top(self, i: int) -> int:
        return AXIS_H + i * ROW_H

    def point_at(self, row: int, value: Decimal) -> QPoint:
        """A point on the bar of row ``row`` at a running labour value."""
        return QPoint(round(self.x_of(value)), self._top(row) + SEG_TOP + SEG_H // 2)

    def tip_at(self, pos: QPoint) -> str | None:
        """Tooltip of the step under ``pos``: ``<kind>, <executor>: <labour>``; ``None`` elsewhere."""
        i = (pos.y() - AXIS_H) // ROW_H
        if pos.y() < AXIS_H or i >= len(self._rows):
            return None
        y = pos.y() - self._top(i)
        if not SEG_TOP - 4 <= y <= SEG_TOP + SEG_H + 4:
            return None
        r = self._rows[i]
        for z in r.zeros:
            if abs(pos.x() - self.x_of(z.at)) <= 3:
                return z.tip
        for s in r.segments:
            if self.x_of(s.start) <= pos.x() < self.x_of(s.end):
                return s.tip
        return None

    def _legend_layout(self, width: int) -> tuple[list[tuple[float, float, int]], int]:
        """Positions of the legend items and of the end note; the legend height."""
        fm = QFontMetrics(_font(13))
        x, y, out = 0.0, 0.0, []
        for k, (_, text, _c) in enumerate(self._legend):
            w = 21 + fm.horizontalAdvance(text)
            if x and x + w > width:
                x, y = 0.0, y + LEGEND_LINE
            out.append((x, y, k))
            x += w + LEGEND_GAP
        y += LEGEND_LINE
        out.append((0.0, y, -1))
        return out, int(y + LEGEND_LINE)

    def _body_h(self) -> int:
        return AXIS_H + len(self._rows) * ROW_H

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt)
        return self._body_h() + 12 + self._legend_layout(width - 4)[1]

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(1100, self.heightForWidth(1100))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt)
        return QSize(LABEL_W + END_ROOM + 100, self.heightForWidth(LABEL_W + END_ROOM + 100))

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            tip = self.tip_at(e.pos())
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)

    # Painting ---------------------------------------------------------------------------------------

    def paintEvent(self, _e) -> None:  # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(style.BG))
        self._paint_axis(p)
        for i, r in enumerate(self._rows):
            self._paint_row(p, i, r)
        self._paint_legend(p)
        p.end()

    def _paint_axis(self, p: QPainter) -> None:
        body = self._body_h()
        p.setFont(_font(11))
        for t in self._ticks:
            x = self.x_of(t)
            p.setPen(QPen(QColor(style.BORDER), 1))
            p.drawLine(QPointF(x, 0), QPointF(x, AXIS_H))
            p.setPen(QPen(QColor(style.SCALE_GRID), 1))
            p.drawLine(QPointF(x, AXIS_H), QPointF(x, body))
            p.setPen(QColor(style.TEXT2))
            p.drawText(QRectF(x + 4, 2, 60, AXIS_H - 2), Qt.AlignmentFlag.AlignLeft, fmt(t))
        p.setPen(QPen(QColor(style.BORDER), 1))
        p.drawLine(QPointF(LABEL_W, AXIS_H), QPointF(self.x_of(self._ticks[-1]), AXIS_H))
        p.drawLine(QPointF(LABEL_W, 0), QPointF(LABEL_W, AXIS_H))

    def _paint_row(self, p: QPainter, i: int, r: ScaleRow) -> None:
        top = self._top(i)
        p.setPen(QPen(QColor(style.BORDER), 1))
        p.drawLine(QPointF(0, top + ROW_H - 0.5), QPointF(self.width(), top + ROW_H - 0.5))
        if r.own:
            p.fillRect(QRectF(0, top, 3, ROW_H), QColor(style.ACCENT))
        # labels
        p.setPen(QColor(style.TEXT))
        p.setFont(_font(14))
        head = QStaticText(f"<b>{html.escape(r.code)}</b> {html.escape(r.title)}")
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setTextWidth(LABEL_W - 24)
        p.drawStaticText(QPointF(12, top + 6), head)
        dot, _, word = r.side.partition(" ")
        side = QStaticText(f'<span style="color:{style.ACCENT}">{html.escape(dot)}</span> '
                           f'<span style="color:{style.TEXT2}">{html.escape(word)}</span>')
        side.setTextFormat(Qt.TextFormat.RichText)
        p.setFont(_font(13))
        p.drawStaticText(QPointF(12, top + 8 + head.size().height()), side)
        # segments
        seg_y = top + SEG_TOP
        p.setFont(_font(11))
        fm = p.fontMetrics()
        for s in r.segments:
            x0, x1 = self.x_of(s.start), self.x_of(s.end)
            rect = QRectF(x0, seg_y, x1 - x0, SEG_H)
            p.fillRect(rect, QColor(s.color))
            p.setPen(QPen(QColor(style.BG), 1))
            p.drawLine(QPointF(x1 - 0.5, seg_y), QPointF(x1 - 0.5, seg_y + SEG_H))
            if fm.horizontalAdvance(s.text) + 6 <= x1 - x0:
                p.setPen(QColor(s.text_color))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, s.text)
        for z in r.zeros:
            p.fillRect(QRectF(self.x_of(z.at) - 1, seg_y, 2, SEG_H), QColor(style.TEXT))
        # status strip
        for s in r.strip:
            if s.end > s.start:
                x0, x1 = self.x_of(s.start), self.x_of(s.end)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(s.color))
                p.drawRoundedRect(QRectF(x0, top + STRIP_TOP, x1 - x0, STRIP_H), 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # checks
        p.setFont(_font(12, True))
        p.setPen(QColor(style.TEXT))
        for c in r.checks:
            x = self.x_of(c.at)
            p.drawText(QRectF(x - 30, top + 8, 30, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       CHECK)
        # slice dashes
        p.setFont(_font(11))
        nfm = p.fontMetrics()
        for m in r.slices:
            x = self.x_of(m.at)
            pen = QPen(QColor(style.TEXT), 1.5)
            pen.setDashPattern([2.0, 1.5])
            p.setPen(pen)
            p.drawLine(QPointF(x, top + 6), QPointF(x, top + ROW_H - 8))
            w = nfm.horizontalAdvance(m.name) + 6
            box = QRectF(x + 3, top + 2, w, 14)
            p.fillRect(box, QColor(style.BG))
            p.setPen(QColor(style.TEXT))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, m.name)
        # end label
        total, skips = r.end_text()
        x = self.x_of(r.total) + 10
        bold = mono()
        bold.setBold(True)
        plain = mono()
        parts = [(total, bold, style.TEXT), (" · ", plain, style.TEXT), (skips, plain, r.skips_color)]
        for text, f, color in parts:
            p.setFont(f)
            p.setPen(QColor(color))
            w = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRectF(x, seg_y - 2, w + 2, SEG_H + 4), Qt.AlignmentFlag.AlignVCenter, text)
            x += w

    def _paint_legend(self, p: QPainter) -> None:
        y0 = self._body_h() + 12
        x0 = 2.0
        items, _ = self._legend_layout(self.width() - 4)
        p.setFont(_font(13))
        for x, y, k in items:
            bx, by = x0 + x, y0 + y
            if k < 0:
                p.setPen(QColor(style.TEXT2))
                p.drawText(QRectF(bx, by, self.width(), LEGEND_LINE), Qt.AlignmentFlag.AlignVCenter, END_NOTE)
                continue
            kind, text, color = self._legend[k]
            mid = by + LEGEND_LINE / 2
            if kind == "swatch":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(bx, mid - 5, 16, 10), 2, 2)
                p.setBrush(Qt.BrushStyle.NoBrush)
            elif kind == "zero":
                p.fillRect(QRectF(bx + 7, mid - 7, 2, 14), QColor(style.TEXT))
            elif kind == "check":
                p.setPen(QColor(style.TEXT))
                p.drawText(QRectF(bx, by, 16, LEGEND_LINE), Qt.AlignmentFlag.AlignCenter, CHECK)
            else:
                pen = QPen(QColor(style.TEXT), 1.5)
                pen.setDashPattern([2.0, 1.5])
                p.setPen(pen)
                p.drawLine(QPointF(bx + 8, mid - 7), QPointF(bx + 8, mid + 7))
            p.setPen(QColor(style.TEXT2))
            p.drawText(QRectF(bx + 21, by, self.width(), LEGEND_LINE), Qt.AlignmentFlag.AlignVCenter, text)
