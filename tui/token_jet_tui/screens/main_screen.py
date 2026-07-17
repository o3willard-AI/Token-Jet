"""Main dashboard screen for Token-Jet TUI — clean vertical stack."""

import subprocess

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer
from textual import work

from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.chat_panel import ChatPanel, ChatInput
from token_jet_tui.screens.model_switch_screen import ModelSwitchScreen


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
        height: 12;
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
        self.app.push_screen(ModelSwitchScreen(), callback=self._on_model_selected)

    def _on_model_selected(self, model_name: str | None) -> None:
        if not model_name:
            return
        self.notify(f"Switching to {model_name}...", timeout=2)
        self._switch_worker(model_name)

    @work(thread=True)
    def _switch_worker(self, model_name: str) -> None:
        try:
            # Map model name to jetson-infer key
            key = None
            if "MiniCPM" in model_name:
                key = "MiniCPM5"
            elif "Bonsai-8B" in model_name or "Ternary-Bonsai-8B" in model_name:
                key = "8B"
            elif "qwen3.5" in model_name.lower() or "Qwen" in model_name:
                key = "qwen3.5"

            if key:
                subprocess.run(
                    ["python3", "/home/sblanken/bin/jetson-infer", "start", "--model", key],
                    capture_output=True, text=True, timeout=120,
                    env={"LD_LIBRARY_PATH": "/usr/local/cuda-13.2/targets/sbsa-linux/lib",
                         "PATH": "/usr/bin:/bin"}
                )
                self.app.call_from_thread(
                    lambda: self.notify(f"Switched to {model_name}", timeout=3)
                )
            else:
                self.app.call_from_thread(
                    lambda: self.notify(f"Unknown model: {model_name}", timeout=3, severity="error")
                )
        except Exception as e:
            self.app.call_from_thread(
                lambda: self.notify(f"Switch failed: {e}", timeout=5, severity="error")
            )

    def action_download(self) -> None:
        self.notify("Download models — coming soon", timeout=3)

    def action_remove_model(self) -> None:
        self.notify("Remove model — coming soon", timeout=3)

    def action_focus_chat(self) -> None:
        self.query_one("#chat-input-area").focus()
