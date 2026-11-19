# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light indigo palette of the mockup as a Qt stylesheet."""

from PySide6.QtCore import QCoreApplication

BG = "#FFFFFF"
SUB = "#FAFAFB"
PANEL = "#F4F4F6"
BORDER = "#E4E4E7"
TEXT = "#18181B"
TEXT2 = "#52525B"
ERR = "#B91C1C"
OK = "#15803D"
ACCENT = "#4F46E5"
ON_ACCENT = "#FFFFFF"
TINT = "#EEF2FF"
STEP_BG = "#F7F8FF"
WARN = "#B45309"
MISSING_BG = "#FEF3C7"  # a number cell not set
OFF = "#D4D4D8"  # an arrow that cannot move its word
NOT_ALLOWED = "#9CA3AF"  # a kind not allowed at a place and its reason, in the list Kind
# The amber line about variants that got errors after a dictionary edit: text, fill, left edge.
AMBER_TEXT = "#92400E"
AMBER_BG = "#FFFBEB"
AMBER_EDGE = "#D97706"
RADIUS = "8px"
# Labour scale: (fill, text) of a step by the executor's place in the dictionary; status strip; grid.
SCALE_STEPS = (("#6366F1", "#FFFFFF"), ("#A5B4FC", TEXT), ("#4338CA", "#FFFFFF"), ("#C7D2FE", TEXT),
               ("#818CF8", TEXT))
SCALE_OPEN = "#F2B8B8"
SCALE_DONE = "#BBE5C8"
SCALE_GRID = "#F0F0F4"
# Line colours of the variants: neutral, without the green and red that mean good and bad elsewhere.
SERIES = ("#4F46E5", "#0284C7", "#9333EA", "#D97706", "#475569", "#0891B2", "#C026D3")
SIDE_MARK = {"own": "●", "other": "○"}


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


STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 15px; }}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 18px; font-weight: 700; }}
QLabel#h2 {{ font-size: 17px; font-weight: 700; }}
QLabel#h3 {{ font-size: 13px; font-weight: 600; color: {TEXT2}; padding-top: 14px; }}
QLabel#note {{ font-size: 13px; color: {TEXT2}; }}
QLabel#err {{ color: {ERR}; font-weight: 600; }}
QFrame#bar {{ background: {BG}; }}
QPushButton {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px;
              padding: 5px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {TEXT2}; background: {SUB}; }}
QPushButton[primary="true"] {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}

QPushButton[primary="true"]:disabled {{
  background: {SUB};
  color: {TEXT2};
  border-color: {BORDER};
}}

QPushButton:checked {{ border-color: {ACCENT}; color: {ACCENT}; font-weight: 600; }}

QPushButton#menuButton::menu-indicator {{
  image: none;
  width: 0px;
}}

QMenu {{
  background: {BG};
  border: 1px solid {BORDER};
  padding: 4px 0;
}}

QMenu::item {{
  padding: 6px 24px 6px 16px;
}}

QMenu::item:selected {{
  background: {TINT};
  color: {TEXT};
}}

QMenu::item:disabled {{
  color: {NOT_ALLOWED};
}}

QLabel#menuHint {{
  font-size: 13px;
  color: {TEXT2};
  padding: 0 24px 6px 16px;
}}
QComboBox {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 12px;
            min-width: 240px; }}
QComboBox QAbstractItemView {{ background: {BG}; border: 1px solid {BORDER};
                              selection-background-color: {TINT}; selection-color: {TEXT}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {TEXT2}; padding: 8px 12px;
               border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTableWidget {{ background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS};
               gridline-color: {BORDER}; selection-background-color: {TINT};
               selection-color: {TEXT}; outline: 0; }}
QTableWidget::item {{ padding: 2px 8px; border-bottom: 1px solid {BORDER}; }}
QHeaderView {{ background: {SUB}; border: none; border-top-left-radius: {RADIUS};
              border-top-right-radius: {RADIUS}; }}
QHeaderView::section {{ background: {SUB}; color: {TEXT2}; font-size: 13px; font-weight: 600;
                       padding: 6px 8px; border: none; border-bottom: 1px solid {BORDER}; }}
QTreeWidget {{ background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS}; outline: 0; }}
QTreeWidget::item {{ padding: 8px 8px; border-bottom: 1px solid {BORDER}; }}
QTreeWidget::item:hover {{ background: {SUB}; }}
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
QFrame#grid {{ background: {BG}; border: 1px solid {BORDER}; }}
QFrame#hc {{ background: {SUB}; border: none; border-bottom: 1px solid {BORDER};
            border-left: 1px solid {BORDER}; }}
QFrame#hc[own="true"], QFrame#cell[own="true"] {{ border-left: 3px solid {ACCENT}; }}
QFrame#cell {{ background: {BG}; border: none; border-bottom: 1px solid {BORDER};
              border-left: 1px solid {BORDER}; }}
QFrame#empty {{ background: {SUB}; border: none; border-bottom: 1px solid {BORDER};
               border-left: 1px solid {BORDER}; }}
QLabel#sn {{ color: {TEXT2}; padding-top: 8px; border-bottom: 1px solid {BORDER}; }}
QLabel#colCode {{ font-weight: 700; }}
QLabel#cellKind {{ font-size: 13px; color: {TEXT2}; }}
QLabel#pill {{ font-size: 11px; color: {ACCENT}; background: {TINT}; border-radius: 8px; padding: 0 6px; }}
QFrame#pathList {{ background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS}; }}
QLabel#listHead {{ background: {SUB}; font-size: 13px; font-weight: 700; padding: 6px 10px;
                  border-bottom: 1px solid {BORDER}; border-top-left-radius: {RADIUS};
                  border-top-right-radius: {RADIUS}; }}
QFrame#path {{ background: {BG}; border: none; border-bottom: 1px solid {BORDER}; }}
QFrame#path[own="true"] {{ border-left: 3px solid {ACCENT}; }}
QFrame#path[cur="true"] {{ background: {TINT}; }}
QFrame#path[grey="true"] QLabel#pathTitle {{ color: {TEXT2}; }}
QLabel#warn {{ font-size: 13px; color: {WARN}; }}
QLineEdit#chainCode, QLineEdit#chainTitle {{ font-size: 16px; border: 1px solid transparent; background: transparent; padding: 2px 4px; }}
QLineEdit#chainCode {{ font-weight: 700; }}
QLineEdit#chainCode:hover, QLineEdit#chainTitle:hover, QLineEdit#chainCode:focus, QLineEdit#chainTitle:focus {{ border-color: {BORDER}; background: {BG}; }}
QFrame#offer {{ background: {TINT}; border: none; border-left: 3px solid {ACCENT}; }}
QFrame#remarks {{ background: {BG}; border: 1px solid {ERR}; border-radius: {RADIUS}; }}
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
  color: {ACCENT};
  font-size: 13px;
  padding: 0;
}}

QFrame#aiStep {{
  background: {BG};
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
}}

QFrame#aiStep[state="current"] {{
  border-color: {ACCENT};
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
  color: {ACCENT};
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
  color: {ACCENT};
  font-size: 13px;
  font-weight: 700;
}}

QPlainTextEdit#aiPrompt,
QPlainTextEdit#aiAnswer,
QPlainTextEdit#aiTask {{
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  background: {BG};
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
  border-color: {ACCENT};
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
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
}}

QLineEdit#specialField:focus,
QLineEdit#addField:focus {{
    border-color: {ACCENT};
}}

QLabel#tag {{
    font-size: 12px;
    color: {TEXT2};
}}

QFrame#kindForm {{
    background: {BG};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS};
}}

QFrame#sliceForm {{
    background: {BG};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS};
}}

QFrame#sliceGroup {{
    background: {BG};
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
    background: {BG};
    border: 1px solid {TEXT2};
    border-radius: 3px;
}}

QFrame#kindForm QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton#addLink {{
    font-size: 13px;
    color: {ACCENT};
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
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
}}

QWidget#chainFields QLineEdit:focus {{
    border-color: {ACCENT};
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
    background: {BG};
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
    background: {BG};
    border: 1px solid {TEXT2};
    border-radius: 6px;
}}

QWidget#chainFields QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QFrame#fold {{
    background: {BG};
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
