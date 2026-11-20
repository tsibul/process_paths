"""The dark theme (piece 43): tokens, contrast, opaque popups, the switch ``More → Theme``."""

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTabBar,
                               QTextEdit, QToolTip, QWidget)

from measure_twice import i18n
from measure_twice.example import add_example
from measure_twice.store import Store
from measure_twice.ui import style
from measure_twice.ui.ai_scenario import AiScenarioDialog
from measure_twice.ui.app import MainWindow
from measure_twice.ui.guide import GuideDialog
from measure_twice.ui.paste import PasteDialog
from measure_twice.ui.report_dialog import ReportDialog

UI = Path(style.__file__).parent
LEAST = 4.5

# The system palettes Qt reads on GNOME: light (Yaru) and dark (Yaru-dark).
SYSTEM = {
    "light": {"Window": "#fafafa", "WindowText": "#000000", "Base": "#ffffff",
              "Text": "#000000", "Button": "#f0f0f0", "ButtonText": "#000000",
              "ToolTipBase": "#ffffdc", "ToolTipText": "#000000", "Highlight": "#e95420",
              "HighlightedText": "#ffffff", "AlternateBase": "#f5f5f5"},
    "dark": {"Window": "#2a2a2a", "WindowText": "#ffffff", "Base": "#2a2a2a",
             "Text": "#ffffff", "Button": "#2a2a2a", "ButtonText": "#ffffff",
             "ToolTipBase": "#333333", "ToolTipText": "#ffffff", "Highlight": "#e95420",
             "HighlightedText": "#ffffff", "AlternateBase": "#333333"},
}


def system_palette(kind: str) -> QPalette:
    p = QPalette()
    for role, colour in SYSTEM[kind].items():
        p.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    return p


def luminance(c: QColor) -> float:
    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF())


def contrast(a, b) -> float:
    x, y = sorted((luminance(QColor(a)), luminance(QColor(b))), reverse=True)
    return (x + 0.05) / (y + 0.05)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def system(app):
    """Puts back the palette, the language and the light tokens after a test."""
    palette = QPalette(app.palette())
    yield app
    app.setPalette(palette)
    i18n.apply_language(app, "en")
    style.use(False)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "p.db")
    add_example(s, "en")
    yield s
    s.close()


def _settings(tmp_path, theme: str | None = None) -> QSettings:
    s = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    s.setValue(i18n.KEY, "en")
    if theme is not None:
        s.setValue(style.THEME_KEY, theme)
    return s


def _window(app, store, tmp_path, theme: str | None, sys_kind: str = "light") -> MainWindow:
    app.setPalette(system_palette(sys_kind))
    w = MainWindow(store, _settings(tmp_path, theme))
    w.resize(1100, 700)
    w.show()
    QApplication.processEvents()
    return w


THEMES = [(t, s) for t in ("light", "dark") for s in ("light", "dark")]


# ---------- tokens in one place ----------

HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
NAMED = re.compile(r"Qt\.GlobalColor\.(?!transparent\b)\w+"
                   r"|QColor\(\s*['\"\d]"
                   r"|\brgba?\(|\bhsla?\("
                   r"|[\"';{]\s*(?:color|background|background-color)\s*:\s*"
                   r"(?!transparent|none)[a-z]+\b")


def test_no_colours_outside_tokens():
    found = []
    for path in sorted(UI.glob("*.py")):
        if path.name == "style.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HEX.search(line) or NAMED.search(line):
                found.append(f"{path.name}:{n}: {line.strip()}")
    assert found == []


def test_stylesheet_only_from_tokens():
    source = Path(style.__file__).read_text(encoding="utf-8")
    template = source[source.index("def stylesheet"):]
    assert HEX.findall(template) == []


def test_light_and_dark_sets_alike():
    assert set(style.LIGHT) == set(style.DARK)
    for name, value in list(style.LIGHT.items()) + list(style.DARK.items()):
        values = value if isinstance(value, tuple) else (value,)
        for v in values:
            for one in v if isinstance(v, tuple) else (v,):
                assert QColor(one).isValid(), (name, one)


def test_dark_tokens_of_mockup():
    d = style.DARK
    assert d["BG"] == "#14161F" and d["FIELD"] == "#1B1E2B" and d["POPUP_BG"] == "#2D3350"
    assert d["TEXT"] == "#E6E8F2" and d["TEXT2"] == "#A3A9C2" and d["BORDER"] == "#3A405A"
    assert d["ACCENT"] == "#4F46E5" and d["ACCENT_FG"] == "#A5B4FC"
    assert d["SELECT_BG"] == "#3A4291" and d["SELECT_TEXT"] == "#FFFFFF"
    assert d["POPUP_BORDER"] == "#5A63A8" and d["TINT"] == "#242A4D"


def test_use_switches_tokens():
    try:
        style.use(True)
        assert style.BG == style.DARK["BG"] and style.DARK["BG"] in style.stylesheet()
        style.use(False)
        assert style.BG == style.LIGHT["BG"] and style.DARK["BG"] not in style.stylesheet()
    finally:
        style.use(False)


# The text on its ground, as the stylesheet and the drawing put them together.
PAIRS = [("TEXT", "BG"), ("TEXT", "FIELD"), ("TEXT", "SUB"), ("TEXT", "HEAD"), ("TEXT", "TINT"),
         ("TEXT", "STEP_BG"), ("TEXT", "HOVER"), ("TEXT", "PANEL"), ("TEXT", "POPUP_BG"),
         ("TEXT2", "BG"), ("TEXT2", "FIELD"), ("TEXT2", "SUB"), ("TEXT2", "HEAD"),
         ("TEXT2", "TINT"), ("TEXT2", "POPUP_BG"), ("TEXT2", "PANEL"),
         ("SELECT_TEXT", "SELECT_BG"), ("ON_ACCENT", "ACCENT"),
         ("ACCENT_FG", "BG"), ("ACCENT_FG", "FIELD"), ("ACCENT_FG", "TINT"),
         ("ACCENT_FG", "STEP_BG"), ("ERR", "BG"), ("ERR", "FIELD"), ("OK", "FIELD"),
         ("WARN", "FIELD"), ("WARN", "MISSING_BG"), ("AMBER_TEXT", "AMBER_BG"),
         ("NOT_ALLOWED", "FIELD"), ("NOT_ALLOWED", "POPUP_BG"), ("NOT_ALLOWED", "PANEL")]


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("fg, bg", PAIRS)
def test_token_pairs_contrast(dark, fg, bg):
    tokens = style.DARK if dark else style.LIGHT
    assert contrast(tokens[fg], tokens[bg]) >= LEAST, (fg, bg)


def test_dark_scale_labels_readable():
    for fill, text in style.DARK["SCALE_STEPS"]:
        assert contrast(fill, text) >= LEAST, fill


# ---------- what the window shows ----------

def _ground(w: QWidget) -> QColor:
    """The colour a widget stands on: its own ground, else the first opaque one above it."""
    while w is not None:
        c = w.palette().color(w.backgroundRole())
        if c.alpha() == 255:
            return c
        w = w.parentWidget()
    return QColor(style.BG)


TEXTED = (QLabel, QPushButton, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QTabBar, QMenu)


def _bad_pairs(root: QWidget) -> list[str]:
    """Visible enabled text whose contrast to its ground is below ``LEAST``."""
    bad = []
    for w in [root] + root.findChildren(QWidget):
        if not w.isVisibleTo(root.window()) or not w.isEnabled():
            continue
        p = w.palette()
        if isinstance(w, QAbstractItemView):
            pairs = [(p.color(QPalette.ColorRole.Text), p.color(QPalette.ColorRole.Base))]
            pairs += _item_pairs(w)
        elif isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit)):
            base = p.color(QPalette.ColorRole.Base)
            ground = base if base.alpha() == 255 else _ground(w)
            pairs = [(p.color(QPalette.ColorRole.Text), ground)]
        elif isinstance(w, TEXTED):
            pairs = [(p.color(w.foregroundRole()), _ground(w))]
        else:
            continue
        for fg, bg in pairs:
            if contrast(fg, bg) < LEAST:
                bad.append(f"{type(w).__name__}#{w.objectName()} {fg.name()} on {bg.name()}")
    return bad


def _item_pairs(view: QAbstractItemView) -> list[tuple[QColor, QColor]]:
    """The colours set on items: their text and ground, the view's where an item sets none."""
    model = view.model()
    if model is None:
        return []
    base = view.palette().color(QPalette.ColorRole.Base)
    text = view.palette().color(QPalette.ColorRole.Text)
    out = []
    for r in range(60):
        for c in range(20):
            i = model.index(r, c)
            if not i.isValid():
                break
            fg = i.data(Qt.ItemDataRole.ForegroundRole)
            bg = i.data(Qt.ItemDataRole.BackgroundRole)
            if fg is None and bg is None:
                continue
            fg = fg.color() if hasattr(fg, "color") else QColor(fg) if fg is not None else text
            bg = bg.color() if hasattr(bg, "color") else QColor(bg) if bg is not None else base
            out.append((fg, bg))
    return out


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_window_contrast_on_every_tab(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        bad = []
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            QApplication.processEvents()
            bad += _bad_pairs(w)
        assert bad == []
    finally:
        w.close()


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_system_palette_not_mixed(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        tokens = style.DARK if theme == "dark" else style.LIGHT
        p = QApplication.palette()
        assert p.color(QPalette.ColorRole.Window).name() == tokens["BG"].lower()
        assert p.color(QPalette.ColorRole.Base).name() == tokens["FIELD"].lower()
        assert p.color(QPalette.ColorRole.Text).name() == tokens["TEXT"].lower()
        assert p.color(QPalette.ColorRole.Highlight).name() == tokens["SELECT_BG"].lower()
        assert p.color(QPalette.ColorRole.ToolTipBase).name() == tokens["POPUP_BG"].lower()
        assert w.palette().color(QPalette.ColorRole.Window).name() == tokens["BG"].lower()
    finally:
        w.close()


def _menus(w: MainWindow) -> list[QMenu]:
    return [w.new_menu, w.more_menu, w.language_menu, w.theme_menu]


def _shown(menu: QMenu) -> QMenu:
    menu.ensurePolished()
    menu.adjustSize()
    return menu


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_menus_contrast(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        for m in _menus(w):
            p = _shown(m).palette()
            fg, bg = p.color(QPalette.ColorRole.WindowText), p.color(QPalette.ColorRole.Window)
            assert bg.name() == style.POPUP_BG.lower(), m
            assert contrast(fg, bg) >= LEAST, m
        assert _bad_pairs(w.export_hint.defaultWidget()) == []
    finally:
        w.close()


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_lists_contrast_and_opaque(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        w.tabs.setCurrentWidget(w.chains)
        w.chains.table.open_input(("call", 1))
        QApplication.processEvents()
        boxes = w.findChildren(QComboBox)
        assert len(boxes) >= 2
        for c in boxes:
            c.showPopup()
            QApplication.processEvents()
            view = c.view()
            p = view.palette()
            assert contrast(p.color(QPalette.ColorRole.Text),
                            p.color(QPalette.ColorRole.Base)) >= LEAST, c
            img = view.window().grab().toImage()
            c.hidePopup()
            assert {img.pixelColor(x, y).alpha() for y in range(0, img.height(), 3)
                    for x in range(0, img.width(), 3)} == {255}, c
    finally:
        w.close()


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_menus_opaque_and_framed(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        for m in _menus(w):
            img = _shown(m).grab().toImage()
            alpha = {img.pixelColor(x, y).alpha()
                     for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)}
            assert alpha == {255}, m
            assert img.pixelColor(0, img.height() // 2).name() == style.POPUP_BORDER.lower()
            assert img.pixelColor(img.width() // 2, 3).name() == style.POPUP_BG.lower()
    finally:
        w.close()


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_tooltip_contrast(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        QToolTip.showText(w.mapToGlobal(QPoint(40, 40)), "A tip", w.projects)
        QApplication.processEvents()
        tips = [t for t in QApplication.topLevelWidgets()
                if t.inherits("QTipLabel") and t.isVisible()]
        assert tips
        p = tips[0].palette()
        fg, bg = p.color(QPalette.ColorRole.ToolTipText), p.color(QPalette.ColorRole.ToolTipBase)
        assert bg.name() == style.POPUP_BG.lower()
        assert contrast(fg, bg) >= LEAST
        QToolTip.hideText()
    finally:
        w.close()


@pytest.mark.parametrize("theme, sys_kind", THEMES)
def test_dialogs_and_guide_contrast(system, store, tmp_path, theme, sys_kind):
    w = _window(system, store, tmp_path, theme, sys_kind)
    try:
        project = w.store.get(w.current_id)
        dialogs = [GuideDialog("Guide", w), PasteDialog(lambda text: True, w),
                   AiScenarioDialog(lambda text: True, w),
                   ReportDialog(project, lambda pages, ways: True, w),
                   QMessageBox(QMessageBox.Icon.Warning, "Measure Twice", "Text",
                               QMessageBox.StandardButton.Ok, w)]
        for d in dialogs:
            d.show()
            QApplication.processEvents()
            assert d.palette().color(QPalette.ColorRole.Window).name() == style.BG.lower(), d
            assert _bad_pairs(d) == [], d
            d.close()
        guide = dialogs[0].browser
        p = guide.palette()
        assert p.color(QPalette.ColorRole.Base).name() == style.FIELD.lower()
        assert contrast(p.color(QPalette.ColorRole.Link), p.color(QPalette.ColorRole.Base)) >= LEAST
    finally:
        w.close()


# ---------- the switch ----------

def _theme_actions(w: MainWindow) -> dict[str, object]:
    return {a.data(): a for a in w.theme_menu.actions()}


def test_switch_in_more_menu(system, store, tmp_path):
    w = _window(system, store, tmp_path, None)
    try:
        theme = [a for a in w.more_menu.actions() if a.menu() is w.theme_menu]
        assert len(theme) == 1 and theme[0].text() == "Theme"
        acts = _theme_actions(w)
        assert list(acts) == ["system", "light", "dark"]
        assert [a.text() for a in acts.values()] == ["As in the system", "Light", "Dark"]
        assert all(a.isCheckable() for a in acts.values())
        assert acts["system"].isChecked()  # the default
    finally:
        w.close()


WORDS = {"ru": ["Тема", "Как в системе", "Светлая", "Тёмная"],
         "el": ["Θέμα", "Όπως στο σύστημα", "Ανοιχτό", "Σκούρο"]}


@pytest.mark.parametrize("lang", ["ru", "el"])
def test_switch_translated(system, store, tmp_path, lang):
    out = tmp_path / "qm"
    assert i18n.build_qm(i18n.SOURCES, out, frozen=False)
    i18n.apply_language(system, lang, out)
    w = _window(system, store, tmp_path, None)
    try:
        theme = next(a for a in w.more_menu.actions() if a.menu() is w.theme_menu)
        got = [theme.text()] + [a.text() for a in w.theme_menu.actions()]
        assert got == WORDS[lang]
    finally:
        w.close()


@pytest.mark.parametrize("sys_kind", ["light", "dark"])
def test_system_follows_system_palette(system, store, tmp_path, sys_kind):
    w = _window(system, store, tmp_path, None, sys_kind)
    try:
        tokens = style.DARK if sys_kind == "dark" else style.LIGHT
        assert style.BG == tokens["BG"]
        assert w.palette().color(QPalette.ColorRole.Window).name() == tokens["BG"].lower()
    finally:
        w.close()


def test_choice_applies_at_once_and_is_kept(system, store, tmp_path):
    w = _window(system, store, tmp_path, None, "light")
    tab = w.tabs.currentIndex()
    new = w.choose_theme("dark")
    try:
        assert new is not w and new.isVisible() and not w.isVisible()
        assert new.tabs.currentIndex() == tab and new.current_id == w.current_id
        assert new.palette().color(QPalette.ColorRole.Window).name() == style.DARK["BG"].lower()
        assert _theme_actions(new)["dark"].isChecked()
        assert QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat).value(
            style.THEME_KEY) == "dark"
        again = MainWindow(store, _settings(tmp_path))
        assert style.BG == style.DARK["BG"]
        assert _theme_actions(again)["dark"].isChecked()
        again.close()
        back = new.choose_theme("system")
        assert style.BG == style.LIGHT["BG"]
        assert _theme_actions(back)["system"].isChecked()
        back.close()
    finally:
        new.close()


def test_same_look_keeps_the_window(system, store, tmp_path):
    w = _window(system, store, tmp_path, None, "light")
    try:
        assert w.choose_theme("light") is w
        assert _theme_actions(w)["light"].isChecked()
    finally:
        w.close()


def test_unknown_stored_theme_is_system(tmp_path):
    s = _settings(tmp_path, "purple")
    assert style.read_theme(s) == "system"
    assert style.read_theme(_settings(tmp_path / "x")) == "system"


# ---------- paper stays light ----------

def test_report_charts_light_in_dark_theme(app, store):
    from PySide6.QtGui import QImage, QPainter

    from measure_twice import report

    project = store.get(store.list()[0].id)
    charts = [c for page in report.pages(project) for c in page.charts]
    assert charts
    try:
        style.use(True)
        for c in charts:
            size = (int(c.x + c.width) + 2, int(c.y + c.height) + 2)
            img = QImage(*size, QImage.Format.Format_RGB32)
            img.fill(QColor("#808080"))
            painter = QPainter(img)
            report._draw_chart(painter, c)
            painter.end()
            seen = {img.pixelColor(x, y).name() for y in range(int(c.y), img.height(), 4)
                    for x in range(int(c.x), img.width(), 4)}
            assert style.LIGHT["BG"].lower() in seen, c.kind
            assert style.DARK["BG"].lower() not in seen, c.kind
        assert style.is_dark()  # the window keeps its theme
    finally:
        style.use(False)
