"""Main dashboard screen — Jetson status, models, performance, and quick chat."""

import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer
from textual import work

from token_jet_tui.store import RootStore
from token_jet_tui.widgets.ascii_logo import AsciiLogo
from token_jet_tui.widgets.chat_panel import ChatPanel
from token_jet_tui.widgets.jetson_panel import JetsonPanel
from token_jet_tui.widgets.models_panel import ModelsPanel
from token_jet_tui.widgets.performance_panel import PerformancePanel
from token_jet_tui.screens.model_switch_screen import ModelSwitchScreen
from token_jet_tui.screens.model_browser_screen import ModelBrowserScreen
from token_jet_tui.screens.delete_model_screen import DeleteModelScreen

log = logging.getLogger(__name__)

_PI_SETTINGS = Path("~/.pi/agent/settings.json").expanduser()


def _update_pi_config(host: str, port: int) -> str:
    """Query the live llama-server and write the active model into pi's settings.json.

    Returns the full 'provider/model-id' string that was written.
    Raises on any failure so the caller can emit a soft warning.
    """
    url = f"http://{host}:{port}/v1/models"
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read())

    model_id: str = data["data"][0]["id"]
    pi_model = f"jetson-local/{model_id}"

    if _PI_SETTINGS.exists():
        settings = json.loads(_PI_SETTINGS.read_text())
    else:
        settings = {}

    settings["model"] = pi_model
    _PI_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _PI_SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    return pi_model


class MainScreen(Screen):
    """Main dashboard: Jetson status, models, performance, and quick chat."""

    BINDINGS = [
        ("ctrl+s", "switch_model", "Switch Model"),
        ("ctrl+d", "download_model", "Download"),
        ("ctrl+x", "remove_model", "Remove"),
        ("ctrl+r", "reset_perf", "Reset Stats"),
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

    def on_mount(self) -> None:
        try:
            self.query_one(ChatPanel).query_one("#chat-input-area").focus()
        except Exception:
            pass

    # ── Model switching ───────────────────────────────────────────────────────

    def action_switch_model(self) -> None:
        self.app.push_screen(ModelSwitchScreen(), callback=self._on_model_selected)

    def _on_model_selected(self, model_name: str | None) -> None:
        log.debug("_on_model_selected: %r", model_name)
        if not model_name:
            return
        self._set_switch_status("  [yellow]⟳ Stopping current model…[/yellow]")
        self.notify(f"Switching to {model_name}…", timeout=5)
        self._switch_worker(model_name)

    def _set_switch_status(self, msg: str) -> None:
        try:
            self.query_one(ModelsPanel).query_one("#download-overlay").update(msg)
        except Exception:
            pass

    @work(thread=True, exit_on_error=False)
    def _switch_worker(self, model_name: str) -> None:
        model_dir = self._store.config.model_dir
        model_path = os.path.join(model_dir, f"{model_name}.gguf")
        jetson_infer = self._store.config.jetson_infer_bin
        env = {
            "LD_LIBRARY_PATH": self._store.config.ld_library_path,
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(__import__("pathlib").Path.home()),
        }
        log.debug("_switch_worker: model=%r path=%r", model_name, model_path)
        try:
            stop = subprocess.run(
                ["python3", jetson_infer, "stop"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            log.debug("stop: rc=%d stdout=%r", stop.returncode, stop.stdout.strip())

            self.app.call_from_thread(
                lambda: self._set_switch_status(f"  [yellow]⟳ Loading {model_name}…[/yellow]")
            )

            start = subprocess.run(
                ["python3", jetson_infer, "start", "--model", model_path],
                capture_output=True, text=True, timeout=300, env=env,
            )
            log.debug("start: rc=%d stdout=%r", start.returncode, start.stdout.strip())
            ok = start.returncode == 0
            err = start.stderr.strip() or start.stdout.strip() or "unknown error"

            if ok:
                self.app.call_from_thread(lambda: self._set_switch_status(""))
                self.app.call_from_thread(
                    lambda: self.notify(f"Switched to {model_name}", timeout=4)
                )
                try:
                    pi_model = _update_pi_config(
                        self._store.config.server_host,
                        self._store.config.server_port,
                    )
                    log.debug("pi config updated: %s", pi_model)
                except Exception as pi_err:
                    log.warning("pi config update failed: %s", pi_err)
                    self.app.call_from_thread(
                        lambda msg=str(pi_err): self.notify(
                            f"Warning: pi agent config not updated — {msg}",
                            timeout=8,
                            severity="warning",
                        )
                    )
            else:
                log.error("switch failed: %s", err)
                self.app.call_from_thread(
                    lambda e=err: self._set_switch_status(f"  [red]Switch failed: {e}[/red]")
                )
                self.app.call_from_thread(
                    lambda e=err: self.notify(f"Switch failed: {e}", timeout=6, severity="error")
                )
        except Exception as e:
            log.exception("_switch_worker raised")
            self.app.call_from_thread(
                lambda msg=str(e): self._set_switch_status(f"  [red]Switch error: {msg}[/red]")
            )
            self.app.call_from_thread(
                lambda msg=str(e): self.notify(f"Switch error: {msg}", timeout=6, severity="error")
            )

    # ── Download ──────────────────────────────────────────────────────────────

    def action_download_model(self) -> None:
        self.app.push_screen(ModelBrowserScreen())

    # ── Remove ────────────────────────────────────────────────────────────────

    def action_remove_model(self) -> None:
        self.app.push_screen(DeleteModelScreen())

    # ── Reset performance counters ────────────────────────────────────────────

    def action_reset_perf(self) -> None:
        try:
            self.query_one(PerformancePanel).reset_counters()
            self.notify("Performance counters reset", timeout=2)
        except Exception:
            pass
