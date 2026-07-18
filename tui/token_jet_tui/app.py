"""Token-Jet Terminal UI — manage your Jetson inference server."""

from textual.app import App
from textual.binding import Binding

from token_jet_tui.config import save_default_config
from token_jet_tui.screens.main_screen import MainScreen
from token_jet_tui.screens.settings_screen import SettingsScreen


class TokenJetApp(App):
    """Token-Jet TUI application."""

    TITLE = "Token-Jet"
    SUB_TITLE = "Jetson Inference Manager"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+p", "settings", "Palette & Settings"),
    ]

    def action_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def on_mount(self) -> None:
        save_default_config()
        self.push_screen(MainScreen())
