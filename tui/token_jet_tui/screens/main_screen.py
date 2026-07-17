"""Main dashboard screen for Token-Jet TUI."""

from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, and quick chat."""

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #logo-container {
        height: auto;
        content-align: center middle;
    }
    #content-row {
        width: 100%;
        height: 1fr;
    }
    #left-column {
        width: 45%;
        height: 100%;
        layout: vertical;
    }
    #jetson-panel {
        width: 100%;
        height: auto;
    }
    #chat-panel {
        width: 100%;
        height: 1fr;
    }
    #models-panel {
        width: 55%;
        height: 100%;
    }
    """

    def compose(self):
        yield Vertical(
            Container(AsciiLogo(), id="logo-container"),
            Horizontal(
                Vertical(
                    JetsonPanel(id="jetson-panel"),
                    ChatPanel(id="chat-panel"),
                    id="left-column"
                ),
                ModelsPanel(id="models-panel"),
                id="content-row"
            ),
            id="main-content"
        )
        yield Footer()
