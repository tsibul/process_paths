"""Menus and popup lists: opaque, framed, with their own colours, inside the window."""

import os
from collections import Counter

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
    style.use(False)


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


def _open_forms(w: MainWindow) -> None:
    """Open the lists that live in cells and forms: the input row and the dictionary editors."""
    w.tabs.setCurrentWidget(w.chains)
    w.chains.table.open_input(("call", 1))
    QApplication.processEvents()
    w.tabs.setCurrentWidget(w.dictionary)
    for table in w.dictionary.tables():
        for kind, owner in list(table._adds):
            if kind in ("variant_param", "executor"):
                table.open_add(kind, owner)
                QApplication.processEvents()
                break


def _popups(w: MainWindow) -> list[QWidget]:
    """Every menu of the window and the popup frame of every list in it."""
    _open_forms(w)
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


def _most_common(img) -> str:
    """The ground of a popup: its commonest colour, the tint of the chosen item aside."""
    seen = Counter(img.pixelColor(x, y).name()
                   for y in range(0, img.height(), 2) for x in range(0, img.width(), 2))
    del seen[style.TINT.lower()]
    del seen[style.SELECT_BG.lower()]
    return seen.most_common(1)[0][0]


def test_popup_tokens_of_variant_3():
    assert style.LIGHT["POPUP_BG"] == "#F5F6FF"
    assert style.LIGHT["POPUP_BORDER"] == "#C7CBF5"


def test_menu_background_explicit(system, store, tmp_path):
    w = _window(system, store, tmp_path, dark_palette())
    try:
        for m in (w.new_menu, w.more_menu, w.language_menu):
            img = _shown(m).grab().toImage()
            assert img.pixelColor(img.width() // 2, 3).name() == style.POPUP_BG.lower(), m
    finally:
        w.close()


@pytest.mark.parametrize("dark", [False, True])
def test_every_popup_tinted(system, store, tmp_path, dark):
    w = _window(system, store, tmp_path, dark_palette() if dark else None)
    try:
        _open_forms(w)
        for m in w.findChildren(QMenu):
            assert _most_common(_shown(m).grab().toImage()) == style.POPUP_BG.lower(), m
        boxes = w.findChildren(QComboBox)
        assert len(boxes) >= 4  # the projects, the input row and a dictionary form
        for c in boxes:
            c.showPopup()
            QApplication.processEvents()
            img = c.view().window().grab().toImage()
            c.hidePopup()
            if c.count() > 1:  # a list of one shows only its chosen item
                assert _most_common(img) == style.POPUP_BG.lower(), c
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
