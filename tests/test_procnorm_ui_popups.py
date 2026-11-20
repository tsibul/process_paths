"""Menus and popup lists: opaque, framed, with their own colours, inside the window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QWidget

from measure_twice import i18n
from measure_twice.example import add_example
from measure_twice.store import Store
from measure_twice.ui import style
from measure_twice.ui.app import MainWindow

# The system palette of GNOME with a dark theme (Yaru-dark), as Qt reads it.
DARK = {
    QPalette.ColorRole.Window: "#2a2a2a",
    QPalette.ColorRole.WindowText: "#ffffff",
    QPalette.ColorRole.Base: "#2a2a2a",
    QPalette.ColorRole.AlternateBase: "#333333",
    QPalette.ColorRole.Text: "#ffffff",
    QPalette.ColorRole.Button: "#2a2a2a",
    QPalette.ColorRole.ButtonText: "#ffffff",
    QPalette.ColorRole.ToolTipBase: "#333333",
    QPalette.ColorRole.ToolTipText: "#ffffff",
    QPalette.ColorRole.Highlight: "#e95420",
    QPalette.ColorRole.HighlightedText: "#ffffff",
    QPalette.ColorRole.PlaceholderText: "#888888",
    QPalette.ColorRole.Light: "#444444",
    QPalette.ColorRole.Midlight: "#3a3a3a",
    QPalette.ColorRole.Mid: "#202020",
    QPalette.ColorRole.Dark: "#101010",
    QPalette.ColorRole.Shadow: "#000000",
    QPalette.ColorRole.BrightText: "#ffffff",
}


def dark_palette() -> QPalette:
    p = QPalette()
    for role, colour in DARK.items():
        p.setColor(role, QColor(colour))
    return p


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def system(app):
    """Puts the app back as it was: palette, language."""
    palette = QPalette(app.palette())
    yield app
    app.setPalette(palette)
    i18n.apply_language(app, "en")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    first = add_example(s, "en")
    s.copy(first)
    yield s
    s.close()


def _window(app, store, tmp_path, palette: QPalette | None = None, width: int = 1100):
    """The window over a given system palette."""
    if palette is not None:
        app.setPalette(palette)
    w = MainWindow(store, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w.resize(width, 700)
    w.show()
    QApplication.processEvents()
    return w


def _popups(w: MainWindow) -> list[QWidget]:
    """Every menu of the window and the popup frame of every list in it."""
    out: list[QWidget] = list(w.findChildren(QMenu))
    for c in w.findChildren(QComboBox):
        c.showPopup()
        QApplication.processEvents()
        out.append(c.view().window())
        c.hidePopup()
    return out


def _shown(menu: QMenu) -> QMenu:
    menu.ensurePolished()
    menu.adjustSize()
    return menu


# ---------- opaque ----------

def test_menus_and_lists_opaque(system, store, tmp_path):
    w = _window(system, store, tmp_path)
    try:
        for p in _popups(w):
            assert not p.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), p
            assert not p.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground), p
            if isinstance(p, QMenu):
                _shown(p)
            img = p.grab().toImage()
            alpha = {img.pixelColor(x, y).alpha()
                     for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)}
            assert alpha == {255}, p
    finally:
        w.close()


def test_menu_background_explicit(system, store, tmp_path):
    w = _window(system, store, tmp_path, dark_palette())
    try:
        for m in (w.new_menu, w.more_menu, w.language_menu):
            img = _shown(m).grab().toImage()
            assert img.pixelColor(img.width() // 2, 3).name() == style.BG.lower(), m
    finally:
        w.close()


# ---------- frame ----------

def test_every_popup_has_border(system, store, tmp_path):
    w = _window(system, store, tmp_path)
    try:
        for p in _popups(w):
            if isinstance(p, QMenu):
                _shown(p)
            img = p.grab().toImage()
            edge = img.pixelColor(0, img.height() // 2).name()
            assert edge == style.POPUP_BORDER.lower(), (p, edge)
    finally:
        w.close()


# ---------- menus of the top row inside the window ----------

def _open(button) -> QRect:
    """Open the menu of a button as a press does and read where it opened.

    Without a display the menu closes at once, keeping the place it was shown at.
    """
    menu = button.menu()
    menu.move(-9999, -9999)
    button.showMenu()
    QApplication.processEvents()
    if menu.isVisible():
        menu.close()
    return menu.geometry()


@pytest.mark.parametrize("lang", ["en", "ru", "el"])
def test_top_menus_inside_narrow_window(system, store, tmp_path, lang):
    i18n.apply_language(system, lang)
    w = _window(system, store, tmp_path, width=640)
    try:
        frame = QRect(w.mapToGlobal(QPoint(0, 0)), w.size())
        for b in (w.new_menu_button, w.more_menu_button, w.language_button):
            got = _open(b)
            assert frame.left() <= got.left() and got.right() <= frame.right(), (b.text(), got)
    finally:
        w.close()


@pytest.mark.parametrize("lang", ["en", "ru", "el"])
def test_export_hint_wraps_to_menu(system, store, tmp_path, lang):
    i18n.apply_language(system, lang)
    w = _window(system, store, tmp_path)
    try:
        menu = _shown(w.more_menu)
        hint = w.export_hint.defaultWidget()
        assert hint.wordWrap()
        items = [a.text() for a in menu.actions() if not a.isSeparator() and a.text()]
        widest = max(menu.fontMetrics().horizontalAdvance(t) for t in items)
        assert hint.width() <= widest + 80
        assert hint.height() > hint.fontMetrics().height() * 1.5  # two lines at least
    finally:
        w.close()
