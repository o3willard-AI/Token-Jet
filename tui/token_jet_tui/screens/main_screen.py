"""Main dashboard screen for Token-Jet TUI — vertical stack layout."""

from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Footer

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, and quick chat — stacked vertically."""

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #logo-container {
        height: auto;
        content-align: center middle;
    }
    #jetson-panel {
        width: 100%;
        height: auto;
    }
    #models-panel {
        width: 100%;
        height: auto;
    }
    #chat-panel {
        width: 100%;
        height: 1fr;
    }
    """

    def compose(self):
        yield Container(AsciiLogo(), id="logo-container")
        yield JetsonPanel(id="jetson-panel")
        yield ModelsPanel(id="models-panel")
        yield ChatPanel(id="chat-panel")
        yield Footer()
