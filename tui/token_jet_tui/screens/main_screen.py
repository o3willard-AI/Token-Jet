"""Main dashboard screen — Jetson status, models, performance, and quick chat."""

import subprocess

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer
from textual import work

from token_jet_tui.store import RootStore
from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.performance_panel import PerformancePanel
from token_jet_tui.widgets.chat_panel import ChatPanel
from token_jet_tui.screens.model_switch_screen import ModelSwitchScreen
from token_jet_tui.screens.model_browser_screen import ModelBrowserScreen
from token_jet_tui.screens.delete_model_screen import DeleteModelScreen


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, performance, and quick chat."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "switch_model", "Switch Model"),
        ("ctrl+d", "download_model", "Download"),
        ("ctrl+x", "remove_model", "Remove"),
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
    #perf-panel {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #chat-panel {
        width: 100%;
        height: 1fr;
        min-height: 12;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._store = RootStore()

    def compose(self):
        yield Container(AsciiLogo(), id="logo-container")
        yield JetsonPanel(id="jetson-panel")
        yield ModelsPanel(id="models-panel")
        yield PerformancePanel(id="perf-panel")
        yield ChatPanel(id="chat-panel")
        yield Footer()

    # ── Model switching ───────────────────────────────────────────────────────

    def action_switch_model(self) -> None:
        self.app.push_screen(ModelSwitchScreen(), callback=self._on_model_selected)

    def _on_model_selected(self, model_name: str | None) -> None:
        if not model_name:
            return
        self.notify(f"Switching to {model_name}...", timeout=2)
        self._switch_worker(model_name)

    @work(thread=True)
    def _switch_worker(self, model_name: str) -> None:
        jetson_infer = self._store.config.jetson_infer_bin
        key = self._model_name_to_key(model_name)
        try:
            if key:
                subprocess.run(
                    ["python3", jetson_infer, "start", "--model", key],
                    capture_output=True, text=True, timeout=180,
                    env={
                        "LD_LIBRARY_PATH": self._store.config.ld_library_path,
                        "PATH": "/usr/bin:/bin:/usr/local/bin",
                        "HOME": str(__import__("pathlib").Path.home()),
                    },
                )
                self.app.call_from_thread(
                    lambda: self.notify(f"Switched to {model_name}", timeout=3)
                )
            else:
                # Unknown model — pass filename directly
                subprocess.run(
                    ["python3", jetson_infer, "start", "--model", model_name],
                    capture_output=True, text=True, timeout=180,
                    env={
                        "LD_LIBRARY_PATH": self._store.config.ld_library_path,
                        "PATH": "/usr/bin:/bin:/usr/local/bin",
                        "HOME": str(__import__("pathlib").Path.home()),
                    },
                )
                self.app.call_from_thread(
                    lambda: self.notify(f"Switched to {model_name}", timeout=3)
                )
        except Exception as e:
            self.app.call_from_thread(
                lambda msg=str(e): self.notify(f"Switch failed: {msg}", timeout=5, severity="error")
            )

    @staticmethod
    def _model_name_to_key(name: str) -> str | None:
        n = name.lower()
        if "minicpm" in n:
            return "MiniCPM5"
        if "bonsai" in n:
            return "8B"
        if "qwen" in n:
            return "qwen3.5"
        return None

    # ── Download ──────────────────────────────────────────────────────────────

    def action_download_model(self) -> None:
        self.app.push_screen(ModelBrowserScreen())

    # ── Remove ────────────────────────────────────────────────────────────────

    def action_remove_model(self) -> None:
        self.app.push_screen(DeleteModelScreen())

    # ── Chat focus ────────────────────────────────────────────────────────────

    def action_focus_chat(self) -> None:
        try:
            self.query_one("#chat-input-area").focus()
        except Exception:
            pass
