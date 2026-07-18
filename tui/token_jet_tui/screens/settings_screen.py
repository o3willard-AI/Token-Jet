"""Settings screen — theme picker and screenshot, no nested command palettes."""

from __future__ import annotations

from textual import events
from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem
from textual.containers import Container
from textual.theme import BUILTIN_THEMES

_THEMES = sorted(BUILTIN_THEMES.keys())


class _SilentListView(ListView):
    def action_select_cursor(self) -> None:
        pass


_OPTIONS = [
    ("Theme",      "Switch the application colour theme"),
    ("Screenshot", "Save SVG screenshot to ~/Token-Jet_<timestamp>.svg"),
]


class ThemeScreen(ModalScreen):
    """Modal: pick a theme from the full built-in list."""

    DEFAULT_CSS = """
    ThemeScreen {
        align: center middle;
    }
    #theme-dialog {
        border: solid $primary;
        background: $surface;
        padding: 1 2;
        width: 40;
        height: auto;
        max-height: 28;
    }
    #theme-title {
        text-style: bold;
        padding-bottom: 1;
    }
    #theme-list {
        height: auto;
        max-height: 20;
    }
    #theme-hint {
        color: $text-muted;
        padding-top: 1;
    }
    """

    def compose(self):
        with Container(id="theme-dialog"):
            yield Static("Select Theme", id="theme-title")
            yield _SilentListView(
                *[ListItem(Static(name)) for name in _THEMES],
                id="theme-list",
            )
            yield Static("↑↓ navigate · Enter: apply · Esc: back", id="theme-hint")

    def on_mount(self) -> None:
        lv = self.query_one("#theme-list", _SilentListView)
        # Highlight the currently active theme
        try:
            idx = _THEMES.index(self.app.theme)
            lv.index = idx
        except ValueError:
            pass
        lv.focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
        elif event.key == "enter":
            try:
                lv = self.query_one("#theme-list", _SilentListView)
            except Exception:
                return
            idx = lv.index
            if idx is not None and 0 <= idx < len(_THEMES):
                self.app.theme = _THEMES[idx]
            self.dismiss()


class SettingsScreen(ModalScreen):
    """Modal settings panel — theme and screenshot."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        border: solid $primary;
        background: $surface;
        padding: 1 2;
        width: 52;
        height: auto;
    }
    #settings-title {
        text-style: bold;
        padding-bottom: 1;
    }
    #settings-list {
        height: auto;
    }
    #settings-hint {
        color: $text-muted;
        padding-top: 1;
    }
    """

    def compose(self):
        with Container(id="settings-dialog"):
            yield Static("Palette & Settings", id="settings-title")
            yield _SilentListView(
                *[ListItem(Static(f"{label}  —  {desc}")) for label, desc in _OPTIONS],
                id="settings-list",
            )
            yield Static("↑↓ navigate · Enter: select · Esc: close", id="settings-hint")

    def on_mount(self) -> None:
        self.query_one("#settings-list", _SilentListView).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
        elif event.key == "enter":
            try:
                lv = self.query_one("#settings-list", _SilentListView)
            except Exception:
                return
            idx = lv.index
            if idx is None:
                return
            label = _OPTIONS[idx][0]
            self.dismiss()
            if label == "Theme":
                self.app.push_screen(ThemeScreen())
            elif label == "Screenshot":
                self.app.set_timer(0.1, self.app.deliver_screenshot)
