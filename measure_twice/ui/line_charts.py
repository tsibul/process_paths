# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Two line charts of the comparison: labour and price of checks done, by step."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCharts import QChart, QChartView, QLegend, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from measure_twice.calc import Point, Row, series, start_point
from measure_twice.export import SIDES
from measure_twice.project import Project
from measure_twice.ui import style


def _view(title: str, y_title: str) -> QChartView:
    """An empty chart with integer step axis and a value axis."""
    chart = QChart()
    chart.setTitle(title)
    font = QFont()
    font.setPixelSize(15)
    font.setBold(True)
    chart.setTitleFont(font)
    chart.setTitleBrush(QColor(style.TEXT))
    chart.setBackgroundBrush(QColor(style.BG))
    chart.setMargins(QMargins(4, 4, 4, 4))
    chart.legend().setAlignment(Qt.AlignRight)
    chart.legend().setLabelColor(QColor(style.TEXT))
    chart.legend().setMarkerShape(QLegend.MarkerShapeFromSeries)
    for title_, align, fmt in (("Step", Qt.AlignBottom, "%d"), (y_title, Qt.AlignLeft, "%g")):
        axis = QValueAxis()
        axis.setTitleText(title_)
        axis.setLabelFormat(fmt)
        axis.setLabelsColor(QColor(style.TEXT2))
        axis.setTitleBrush(QColor(style.TEXT2))
        axis.setGridLineColor(QColor(style.BORDER))
        axis.setLinePenColor(QColor(style.BORDER))
        axis.setRange(0, 1)
        chart.addAxis(axis, align)
    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(260)
    return view


class LineCharts(QWidget):
    """``Labour by step`` above ``Checks done by step``; one line per given variant.

    A line goes from point 0 (the initial slice) to the last step of its path. Own variants
    are drawn solid, other variants dashed; the colour of a line is fixed by the place of its
    variant in the project; a line is named by the variant code and side, as ``T1 · Ours``.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.labour = _view("Labour by step", "Labour")
        self.checks = _view("Checks done by step", "Price of checks done")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.labour)
        lay.addWidget(self.checks)

    def set_rows(self, project: Project | None, rows: Sequence[Row]) -> None:
        """Replace the lines by those of ``rows``, in their order.

        :param project: a checked project; ``None`` clears the lines.
        :param rows: variants to draw; a variant with a number not set or a run error is not drawn.
        """
        rows = [r for r in rows if not (r.missing or r.error)] if project is not None else []
        order = [v.code for v in project.model.variants] if project else []
        pts = {r.code: [start_point(project, r.code)] + series(project, r.code) for r in rows}
        self._fill(self.labour, rows, pts, order, lambda p: p.labour)
        self._fill(self.checks, rows, pts, order, lambda p: p.done_total)

    @staticmethod
    def _fill(view: QChartView, rows: Sequence[Row], pts: dict[str, list[Point]],
              order: list[str], value: Callable[[Point], object]) -> None:
        chart = view.chart()
        chart.removeAllSeries()
        x_axis = chart.axes(Qt.Horizontal)[0]
        y_axis = chart.axes(Qt.Vertical)[0]
        x_max, y_max = 1, 0.0
        for r in rows:
            s = QLineSeries()
            s.setName(f"{r.code} · {SIDES.get(r.side, r.side)}")
            pen = QPen(QColor(style.SERIES[order.index(r.code) % len(style.SERIES)]))
            pen.setWidth(2)
            pen.setStyle(Qt.SolidLine if r.side == "own" else Qt.DashLine)
            s.setPen(pen)
            for p in pts[r.code]:
                y = float(value(p))
                s.append(p.number, y)
                y_max = max(y_max, y)
            x_max = max(x_max, pts[r.code][-1].number)
            chart.addSeries(s)
            s.attachAxis(x_axis)
            s.attachAxis(y_axis)
        x_axis.setRange(0, x_max)
        x_axis.setTickType(QValueAxis.TicksDynamic)
        x_axis.setTickAnchor(0)
        x_axis.setTickInterval(1)
        y_axis.setRange(0, y_max * 1.1 or 1)
        y_axis.applyNiceNumbers()
