"""Main dashboard screen for Token-Jet TUI — vertical stack layout."""

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Static

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, and quick chat."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "switch_model", "Switch Model"),
        ("ctrl+d", "download", "Download Models"),
        ("ctrl+x", "remove_model", "Remove Model"),
        ("ctrl+c", "focus_chat", "Focus Chat"),
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
        yield Static(" Ctrl+Q:quit  Ctrl+S:switch model  Ctrl+D:download  Ctrl+X:remove  Ctrl+C:chat input", id="hotkey-bar")
        yield Footer()

    def action_switch_model(self) -> None:
        self.notify("Switch model — coming soon", timeout=3)

    def action_download(self) -> None:
        self.notify("Download models — coming soon", timeout=3)

    def action_remove_model(self) -> None:
        self.notify("Remove model — coming soon", timeout=3)

    def action_focus_chat(self) -> None:
        self.query_one(ChatPanel).query_one("#chat-input").focus()
