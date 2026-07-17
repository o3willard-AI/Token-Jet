"""Main dashboard screen for Token-Jet TUI — vertical stack layout."""

from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, and quick chat — stacked vertically."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("s", "switch", "Switch Model"),
        ("d", "download", "Download Models"),
        ("c", "focus_chat", "Focus Chat"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #logo-container {
        height: auto;
        content-align: center middle;
        margin-bottom: 1;
    }
    #jetson-panel {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #models-panel {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #chat-panel {
        width: 100%;
        height: 14;
    }
    #hotkey-bar {
        width: 100%;
        height: 1;
        color: $text-muted;
        content-align: center middle;
    }
    """

    def compose(self):
        yield Container(AsciiLogo(), id="logo-container")
        yield JetsonPanel(id="jetson-panel")
        yield ModelsPanel(id="models-panel")
        yield ChatPanel(id="chat-panel")
        yield Static(" q:quit  r:refresh  s:switch model  d:download  c:chat input  tab:next field", id="hotkey-bar")
        yield Footer()

    def action_refresh(self) -> None:
        self.query_one(JetsonPanel).refresh_stats()
        self.query_one(ModelsPanel).refresh_model_info()

    def action_switch(self) -> None:
        self.query_one(ModelsPanel).query_one("#btn-switch").press()

    def action_download(self) -> None:
        self.query_one(ModelsPanel).query_one("#btn-download").press()

    def action_focus_chat(self) -> None:
        self.query_one(ChatPanel).query_one("#chat-input").focus()
