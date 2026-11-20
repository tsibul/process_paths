# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The colours of the window in one place: a light and a dark set of tokens, the Qt stylesheet
and the palette made of them, the stored theme.

Every colour of the window is a token here; a change of the look is a change of values in
``LIGHT`` and ``DARK``. The module names of the tokens (``style.TEXT`` and so on) hold the set in
use; :func:`use` switches them. Code reads them when it draws, so it takes ``style.TEXT``, never a
copy made at import.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QToolTip

# The light set: the palette of the mockup of version 1.
LIGHT = {
    "BG": "#FFFFFF",  # the window
    "FIELD": "#FFFFFF",  # fields, buttons, tables, lists
    "SUB": "#FAFAFB",  # a quiet ground: disabled buttons, grey groups, empty cells
    "HEAD": "#FAFAFB",  # table headers
    "HOVER": "#FAFAFB",  # a row under the pointer
    "PANEL": "#F4F4F6",
    "BORDER": "#E4E4E7",
    "TEXT": "#18181B",
    "TEXT2": "#52525B",
    "ERR": "#B91C1C",
    "OK": "#15803D",
    "WARN": "#B45309",
    "ACCENT": "#4F46E5",  # the accent as a fill only: primary buttons, ticks
    "ON_ACCENT": "#FFFFFF",  # text on the accent fill
    "ACCENT_FG": "#4F46E5",  # the accent as text, marks and lines on a ground
    "TINT": "#EEF2FF",
    "STEP_BG": "#F7F8FF",  # a step row of a chain
    "SELECT_BG": "#EEF2FF",  # the chosen item of a menu, list or table
    "SELECT_TEXT": "#18181B",
    "MISSING_BG": "#FEF3C7",  # a number cell not set
    "OFF": "#D4D4D8",  # an arrow that cannot move its word
    "NOT_ALLOWED": "#6B6F80",  # disabled items; a kind not allowed here and its reason
    # The amber line about variants that got errors after a dictionary edit: text, fill, edge.
    "AMBER_TEXT": "#92400E",
    "AMBER_BG": "#FFFBEB",
    "AMBER_EDGE": "#D97706",
    # Every menu and popup list: a tinted opaque ground and a frame.
    # Qt draws no shadow under an opaque popup, so the look rests on these two.
    "POPUP_BG": "#F5F6FF",
    "POPUP_BORDER": "#C7CBF5",
    # Labour scale: (fill, text) of a step by the executor's place in the dictionary; status
    # strip; grid.
    "SCALE_STEPS": (
        ("#6366F1", "#FFFFFF"),
        ("#A5B4FC", "#18181B"),
        ("#4338CA", "#FFFFFF"),
        ("#C7D2FE", "#18181B"),
        ("#818CF8", "#18181B"),
    ),
    "SCALE_OPEN": "#F2B8B8",
    "SCALE_DONE": "#BBE5C8",
    "SCALE_GRID": "#F0F0F4",
    # Line colours of the variants: neutral, without the green and red that mean good and bad.
    "SERIES": ("#4F46E5", "#0284C7", "#9333EA", "#D97706", "#475569", "#0891B2", "#C026D3"),
}

# The dark set: the mockup ``dark_theme.html`` of pp-marketing, a neutral dark blue. Window,
# fields and menus differ in steps of lightness, so a menu stands out of a table without a shadow.
DARK = {
    "BG": "#14161F",
    "FIELD": "#1B1E2B",
    "SUB": "#222637",
    "HEAD": "#262B40",
    "HOVER": "#2A3050",
    "PANEL": "#262B40",
    "BORDER": "#3A405A",
    "TEXT": "#E6E8F2",
    "TEXT2": "#A3A9C2",
    "ERR": "#F87171",
    "OK": "#4ADE80",
    "WARN": "#FBBF24",
    "ACCENT": "#4F46E5",
    "ON_ACCENT": "#FFFFFF",
    "ACCENT_FG": "#A5B4FC",
    "TINT": "#242A4D",
    "STEP_BG": "#242A4D",
    "SELECT_BG": "#3A4291",
    "SELECT_TEXT": "#FFFFFF",
    "MISSING_BG": "#3A2F14",
    "OFF": "#4B5272",
    "NOT_ALLOWED": "#959CB8",
    "AMBER_TEXT": "#FCD34D",
    "AMBER_BG": "#2E2614",
    "AMBER_EDGE": "#D97706",
    "POPUP_BG": "#2D3350",
    "POPUP_BORDER": "#5A63A8",
    "SCALE_STEPS": (
        ("#4F46E5", "#FFFFFF"),
        ("#A5B4FC", "#14161F"),
        ("#3730A3", "#FFFFFF"),
        ("#C7D2FE", "#14161F"),
        ("#818CF8", "#14161F"),
    ),
    "SCALE_OPEN": "#9F4A4A",
    "SCALE_DONE": "#2F7A4B",
    "SCALE_GRID": "#262B40",
    "SERIES": ("#A5B4FC", "#38BDF8", "#C084FC", "#F59E0B", "#94A3B8", "#22D3EE", "#E879F9"),
}

# The names of the set in use; :func:`use` fills them in.
BG = FIELD = SUB = HEAD = HOVER = PANEL = BORDER = TEXT = TEXT2 = ""
ERR = OK = WARN = ACCENT = ON_ACCENT = ACCENT_FG = TINT = STEP_BG = ""
SELECT_BG = SELECT_TEXT = MISSING_BG = OFF = NOT_ALLOWED = ""
AMBER_TEXT = AMBER_BG = AMBER_EDGE = POPUP_BG = POPUP_BORDER = ""
SCALE_STEPS: tuple[tuple[str, str], ...] = ()
SCALE_OPEN = SCALE_DONE = SCALE_GRID = ""
SERIES: tuple[str, ...] = ()

RADIUS = "8px"
SIDE_MARK = {"own": "●", "other": "○"}

THEME_KEY = "theme"
# The stored choice, in the order of the switch.
THEMES = ("system", "light", "dark")
SYSTEM = "system"

_dark = False
_system: QPalette | None = None  # the palette of the system, as it was before ours
_ours: QPalette | None = None  # the palette this module gave the application


def use(dark: bool) -> None:
    """Make the dark or the light set the tokens in use."""
    global _dark
    _dark = dark
    globals().update(DARK if dark else LIGHT)


use(False)


def is_dark() -> bool:
    """Whether the dark set is in use."""
    return _dark


@contextmanager
def light() -> Iterator[None]:
    """The light set for a while, whatever the window shows: for paper, such as the PDF report."""
    was = _dark
    use(False)
    try:
        yield
    finally:
        use(was)


def read_theme(settings: QSettings | None) -> str:
    """The stored theme: ``system``, ``light`` or ``dark``; ``system`` when none or unknown."""
    stored = settings.value(THEME_KEY) if settings is not None else None
    return stored if stored in THEMES else SYSTEM


def write_theme(settings: QSettings, theme: str) -> None:
    """Keep the chosen theme for the next start."""
    settings.setValue(THEME_KEY, theme)


def _system_palette(app: QGuiApplication) -> QPalette:
    """The palette of the system: the one of the application, unless it is the one set here."""
    global _system
    now = app.palette()
    if _ours is None or _system is None or now != _ours:
        _system = QPalette(now)
    return _system


def system_dark(app: QGuiApplication) -> bool:
    """Whether the system shows a dark theme.

    The colour scheme of the system when Qt knows it, else the system palette: dark when its
    window is darker than its text.
    """
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    p = _system_palette(app)
    window = p.color(QPalette.ColorRole.Window).lightness()
    return window < p.color(QPalette.ColorRole.WindowText).lightness()


def palette() -> QPalette:
    """The palette of the tokens in use, every role set, so nothing of the system shows through."""
    roles = QPalette.ColorRole
    colours = {
        roles.Window: BG,
        roles.WindowText: TEXT,
        roles.Base: FIELD,
        roles.AlternateBase: SUB,
        roles.Text: TEXT,
        roles.Button: FIELD,
        roles.ButtonText: TEXT,
        roles.BrightText: ON_ACCENT,
        roles.ToolTipBase: POPUP_BG,
        roles.ToolTipText: TEXT,
        roles.Highlight: SELECT_BG,
        roles.HighlightedText: SELECT_TEXT,
        roles.PlaceholderText: TEXT2,
        roles.Link: ACCENT_FG,
        roles.LinkVisited: ACCENT_FG,
        roles.Light: FIELD,
        roles.Midlight: SUB,
        roles.Mid: BORDER,
        roles.Dark: BORDER,
        roles.Shadow: BORDER,
        roles.Accent: ACCENT,
    }
    out = QPalette()
    for role, colour in colours.items():
        out.setColor(role, QColor(colour))
    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        out.setColor(QPalette.ColorGroup.Disabled, role, QColor(NOT_ALLOWED))
    return out


def apply(app: QGuiApplication, theme: str) -> bool:
    """Make a theme the look of the application: the tokens, its palette and the tooltips'.

    :param app: the application.
    :param theme: ``system``, ``light`` or ``dark``.
    :return: whether the window is dark now.
    :rtype: bool
    """
    global _ours
    hints = app.styleHints()
    if theme == SYSTEM:
        hints.unsetColorScheme()
        dark = system_dark(app)
    else:
        dark = theme == "dark"
        # The system then draws its own parts, such as the window frame, in the same scheme.
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        _system_palette(app)  # kept for a later return to the system theme
    use(dark)
    ours = palette()
    app.setPalette(ours)
    QToolTip.setPalette(ours)
    _ours = QPalette(app.palette())
    return dark



def side_name(side: str) -> str:
    """``Ours`` or ``Theirs`` in the language of the window; an unknown side as it is."""
    if side == "own":
        return QCoreApplication.translate("Side", "Ours")
    if side == "other":
        return QCoreApplication.translate("Side", "Theirs")
    return side


def side_word(side: str) -> str:
    """The stored word ``own`` or ``other`` as the Variants table shows it, in the language of the
    window; an unknown side as it is."""
    if side == "own":
        return QCoreApplication.translate("Side", "own")
    if side == "other":
        return QCoreApplication.translate("Side", "other")
    return side


def side_text(side: str) -> str:
    """The side with its mark: ``● Ours`` or ``○ Theirs``."""
    return f"{SIDE_MARK[side]} {side_name(side)}" if side in SIDE_MARK else side


def stylesheet() -> str:
    """The Qt stylesheet of the tokens in use."""
    return f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 15px; }}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QLabel {{ background: transparent; }}

QLineEdit,
QPlainTextEdit,
QTextEdit {{
  background: {FIELD};
  color: {TEXT};
  selection-background-color: {SELECT_BG};
  selection-color: {SELECT_TEXT};
}}

QToolTip {{
  background: {POPUP_BG};
  color: {TEXT};
  border: 1px solid {POPUP_BORDER};
}}

QLabel#title {{ font-size: 18px; font-weight: 700; }}
QLabel#h2 {{ font-size: 17px; font-weight: 700; }}
QLabel#h3 {{ font-size: 13px; font-weight: 600; color: {TEXT2}; padding-top: 14px; }}
QLabel#note {{ font-size: 13px; color: {TEXT2}; }}
QLabel#err {{ color: {ERR}; font-weight: 600; }}
QFrame#bar {{ background: {BG}; }}
QPushButton {{ background: {FIELD}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px;
              padding: 5px 12px; }}
QPushButton:hover {{ border-color: {ACCENT_FG}; }}
QPushButton:disabled {{ color: {TEXT2}; background: {SUB}; }}
QPushButton[primary="true"] {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}

QPushButton[primary="true"]:disabled {{
  background: {SUB};
  color: {TEXT2};
  border-color: {BORDER};
}}

QPushButton:checked {{ border-color: {ACCENT_FG}; color: {ACCENT_FG}; font-weight: 600; }}

QPushButton#menuButton::menu-indicator {{
  image: none;
  width: 0px;
}}

QMenu {{
  background: {POPUP_BG};
  color: {TEXT};
  border: 1px solid {POPUP_BORDER};
  padding: 4px 0;
}}

QMenu::item {{
  padding: 6px 24px 6px 16px;
}}

QMenu::item:selected {{
  background: {SELECT_BG};
  color: {SELECT_TEXT};
}}

QMenu::item:disabled {{
  color: {NOT_ALLOWED};
}}

QLabel#menuHint {{
  font-size: 13px;
  color: {TEXT2};
  padding: 0 24px 6px 16px;
}}

QComboBox {{
  background: {FIELD};
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 5px 12px;
  min-width: 240px;
  selection-background-color: {SELECT_BG};
  selection-color: {SELECT_TEXT};
}}

QComboBox QAbstractItemView {{
  background: {POPUP_BG};
  color: {TEXT};
  border: 1px solid {POPUP_BORDER};
  selection-background-color: {SELECT_BG};
  selection-color: {SELECT_TEXT};
}}

QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {TEXT2}; padding: 8px 12px;
               border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{
  color: {ACCENT_FG};
  border-bottom: 2px solid {ACCENT_FG};
  font-weight: 600;
}}
QTableWidget {{ background: {FIELD}; border: 1px solid {BORDER}; border-radius: {RADIUS};
               gridline-color: {BORDER}; selection-background-color: {SELECT_BG};
               selection-color: {SELECT_TEXT}; outline: 0; }}
QTableWidget::item {{ padding: 2px 8px; border-bottom: 1px solid {BORDER}; }}
QHeaderView {{ background: {HEAD}; border: none; border-top-left-radius: {RADIUS};
              border-top-right-radius: {RADIUS}; }}
QHeaderView::section {{ background: {HEAD}; color: {TEXT2}; font-size: 13px; font-weight: 600;
                       padding: 6px 8px; border: none; border-bottom: 1px solid {BORDER}; }}
QTreeWidget {{
  background: {FIELD};
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  outline: 0;
}}
QTreeWidget::item {{ padding: 8px 8px; border-bottom: 1px solid {BORDER}; }}
QTreeWidget::item:hover {{ background: {HOVER}; }}
QFrame#group {{ background: {TINT}; border: none; border-bottom: 1px solid {BORDER}; }}
QFrame#group[grey="true"] {{ background: {SUB}; }}
QLabel#groupTitle {{ font-size: 14px; font-weight: 700; }}
QFrame#group[grey="true"] QLabel#groupTitle {{ color: {TEXT2}; }}
QLabel#groupNote {{ font-size: 13px; color: {TEXT2}; }}
QFrame#steps {{ background: {SUB}; border: none; border-bottom: 1px solid {BORDER}; }}
QLabel#skipped {{ font-size: 13px; color: {TEXT}; }}
QPushButton#small {{ font-size: 13px; padding: 3px 10px; }}
QPushButton#icon {{ font-size: 13px; padding: 0; min-width: 26px; max-width: 26px; min-height: 22px;
                   max-height: 22px; }}
QComboBox#pick {{ font-size: 13px; padding: 2px 6px; min-width: 0; }}
QFrame#viewHead {{ background: {TINT}; border: 1px solid {BORDER}; border-bottom: none;
                  border-top-left-radius: {RADIUS}; border-top-right-radius: {RADIUS}; }}
QFrame#grid {{ background: {FIELD}; border: 1px solid {BORDER}; }}
QFrame#hc {{ background: {HEAD}; border: none; border-bottom: 1px solid {BORDER};
            border-left: 1px solid {BORDER}; }}
QFrame#hc[own="true"], QFrame#cell[own="true"] {{ border-left: 3px solid {ACCENT_FG}; }}
QFrame#cell {{ background: {FIELD}; border: none; border-bottom: 1px solid {BORDER};
              border-left: 1px solid {BORDER}; }}
QFrame#empty {{ background: {SUB}; border: none; border-bottom: 1px solid {BORDER};
               border-left: 1px solid {BORDER}; }}
QLabel#sn {{ color: {TEXT2}; padding-top: 8px; border-bottom: 1px solid {BORDER}; }}
QLabel#colCode {{ font-weight: 700; }}
QLabel#cellKind {{ font-size: 13px; color: {TEXT2}; }}
QLabel#pill {{
  font-size: 11px;
  color: {ACCENT_FG};
  background: {TINT};
  border-radius: 8px;
  padding: 0 6px;
}}
QFrame#pathList {{ background: {FIELD}; border: 1px solid {BORDER}; border-radius: {RADIUS}; }}
QLabel#listHead {{ background: {HEAD}; font-size: 13px; font-weight: 700; padding: 6px 10px;
                  border-bottom: 1px solid {BORDER}; border-top-left-radius: {RADIUS};
                  border-top-right-radius: {RADIUS}; }}
QFrame#path {{ background: {FIELD}; border: none; border-bottom: 1px solid {BORDER}; }}
QFrame#path[own="true"] {{ border-left: 3px solid {ACCENT_FG}; }}
QFrame#path[cur="true"] {{ background: {TINT}; }}
QFrame#path[grey="true"] QLabel#pathTitle {{ color: {TEXT2}; }}
QLabel#warn {{ font-size: 13px; color: {WARN}; }}
QLineEdit#chainCode, QLineEdit#chainTitle {{ font-size: 16px; border: 1px solid transparent; background: transparent; padding: 2px 4px; }}
QLineEdit#chainCode {{ font-weight: 700; }}
QLineEdit#chainCode:hover,
QLineEdit#chainTitle:hover,
QLineEdit#chainCode:focus,
QLineEdit#chainTitle:focus {{
  border-color: {BORDER};
  background: {FIELD};
}}
QFrame#offer {{ background: {TINT}; border: none; border-left: 3px solid {ACCENT_FG}; }}
QFrame#remarks {{ background: {FIELD}; border: 1px solid {ERR}; border-radius: {RADIUS}; }}
QFrame#remarks QPlainTextEdit {{ border: 1px solid {BORDER}; border-radius: 6px; background: {SUB}; }}
QStatusBar {{ background: {BG}; color: {TEXT2}; font-size: 13px; border-top: 1px solid {BORDER}; }}
QScrollBar {{ background: {SUB}; }}

QFrame#aiTop {{
  border: none;
  border-bottom: 1px solid {BORDER};
}}

QLabel#aiTopTitle {{
  font-size: 15px;
  font-weight: 700;
}}

QPushButton#aiLink {{
  background: transparent;
  border: none;
  color: {ACCENT_FG};
  font-size: 13px;
  padding: 0;
}}

QFrame#aiStep {{
  background: {FIELD};
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
}}

QFrame#aiStep[state="current"] {{
  border-color: {ACCENT_FG};
}}

QFrame#aiStepHead {{
  background: transparent;
  border: none;
  border-top-left-radius: {RADIUS};
  border-top-right-radius: {RADIUS};
}}

QFrame#aiStepHead[state="current"] {{
  background: {TINT};
}}

QWidget#aiStepBody {{
  background: transparent;
}}

QLabel#aiStepTitle {{
  color: {TEXT2};
}}

QLabel#aiStepTitle[state="current"] {{
  color: {ACCENT_FG};
  font-weight: 700;
}}

QLabel#aiStepTitle[state="future"] {{
  color: {NOT_ALLOWED};
}}

QLabel#aiMark {{
  color: {OK};
  font-weight: 700;
}}

QLabel#aiSummary {{
  color: {TEXT2};
  font-size: 13px;
}}

QLabel#aiCaption {{
  color: {ACCENT_FG};
  font-size: 13px;
  font-weight: 700;
}}

QPlainTextEdit#aiPrompt,
QPlainTextEdit#aiAnswer,
QPlainTextEdit#aiTask {{
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  background: {FIELD};
}}

QPlainTextEdit#aiPrompt,
QPlainTextEdit#aiAnswer {{
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 13px;
}}

QPlainTextEdit#aiPrompt {{
  background: {SUB};
}}

QPlainTextEdit#aiTask {{
  border-color: {ACCENT_FG};
}}

QPushButton#icon:disabled {{
    color: {OFF};
    background: transparent;
    border-color: transparent;
}}

QFrame#special {{
    background: {SUB};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
}}

QLabel#specialLabel {{
    font-size: 13px;
    font-weight: 700;
}}

QLineEdit#specialField,
QLineEdit#addField {{
    font-size: 13px;
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
}}

QLineEdit#specialField:focus,
QLineEdit#addField:focus {{
    border-color: {ACCENT_FG};
}}

QLabel#tag {{
    font-size: 12px;
    color: {TEXT2};
}}

QFrame#kindForm {{
    background: {FIELD};
    border: 1px solid {ACCENT_FG};
    border-radius: {RADIUS};
}}

QFrame#sliceForm {{
    background: {FIELD};
    border: 1px solid {ACCENT_FG};
    border-radius: {RADIUS};
}}

QFrame#sliceGroup {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
}}

QLabel#groupTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}

QLabel#orLine {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT2};
}}

QLabel#formLabel {{
    font-size: 13px;
    color: {TEXT2};
}}

QFrame#kindForm QCheckBox {{
    font-size: 13px;
    background: transparent;
}}

QFrame#kindForm QCheckBox::indicator {{
    width: 12px;
    height: 12px;
    background: {FIELD};
    border: 1px solid {TEXT2};
    border-radius: 3px;
}}

QFrame#kindForm QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton#addLink {{
    font-size: 13px;
    color: {ACCENT_FG};
    background: transparent;
    border: none;
    padding: 2px 0;
    text-align: left;
}}

QLabel#fieldLabel {{
    font-size: 13px;
    font-weight: 700;
}}

QWidget#chainFields QLineEdit {{
    font-size: 13px;
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
}}

QWidget#chainFields QLineEdit:focus {{
    border-color: {ACCENT_FG};
}}

QWidget#chainFields QLineEdit:disabled {{
    background: {SUB};
}}

QWidget#chainFields QRadioButton,
QWidget#chainFields QCheckBox {{
    font-size: 13px;
    background: transparent;
}}

QWidget#chainFields QCheckBox::indicator {{
    width: 12px;
    height: 12px;
    background: {FIELD};
    border: 1px solid {TEXT2};
    border-radius: 3px;
}}

QWidget#chainFields QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QWidget#chainFields QRadioButton::indicator {{
    width: 10px;
    height: 10px;
    background: {FIELD};
    border: 1px solid {TEXT2};
    border-radius: 6px;
}}

QWidget#chainFields QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QFrame#fold {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
}}

QPushButton#foldButton {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
    background: transparent;
    border: none;
    padding: 2px 0;
    text-align: left;
}}

QFrame#stateHere {{
    background: {PANEL};
    border-radius: 6px;
}}

QLabel#stateHead {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT2};
}}

QLabel#stateLines {{
    font-size: 13px;
}}

QLabel#amber {{
    font-size: 13px;
    color: {AMBER_TEXT};
    background: {AMBER_BG};
    border-left: 3px solid {AMBER_EDGE};
    padding: 7px 12px;
}}
"""
