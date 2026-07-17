"""Main dashboard screen for Token-Jet TUI — clean vertical stack."""

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel, ChatInput


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, and quick chat."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "switch_model", "Switch Model"),
        ("ctrl+d", "download", "Download"),
        ("ctrl+x", "remove_model", "Remove Model"),
        ("ctrl+c", "focus_chat", "Focus Chat"),
        ("ctrl+p", "noop", ""),
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
    """

    def compose(self):
        yield Container(AsciiLogo(), id="logo-container")
        yield JetsonPanel(id="jetson-panel")
        yield ModelsPanel(id="models-panel")
        yield ChatPanel(id="chat-panel")
        yield Footer()

    def action_noop(self) -> None:
        pass

    def action_switch_model(self) -> None:
        self.notify("Switch model — coming soon", timeout=3)

    def action_download(self) -> None:
        self.notify("Download models — coming soon", timeout=3)

    def action_remove_model(self) -> None:
        self.notify("Remove model — coming soon", timeout=3)

    def action_focus_chat(self) -> None:
        self.query_one("#chat-input-area").focus()
