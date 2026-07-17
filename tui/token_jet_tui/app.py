"""Token-Jet Terminal UI — manage your Jetson inference server."""

from textual.app import App

from token_jet_tui.store import RootStore
from token_jet_tui.config import save_default_config
from token_jet_tui.screens.main_screen import MainScreen


class TokenJetApp(App):
    """Token-Jet TUI application."""

    TITLE = "Token-Jet"
    SUB_TITLE = "Jetson Inference Manager"

    def on_mount(self) -> None:
        save_default_config()
        self.push_screen(MainScreen())
