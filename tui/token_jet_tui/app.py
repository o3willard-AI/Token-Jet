"""Token-Jet Terminal UI — manage your Jetson inference server."""

from textual.app import App

from token_jet_tui.screens.main_screen import MainScreen


class TokenJetApp(App):
    """Token-Jet TUI application."""

    TITLE = "Token-Jet"
    SUB_TITLE = "Jetson Inference Manager"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())
