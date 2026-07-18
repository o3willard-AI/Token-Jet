"""Main dashboard screen — Jetson status, models, performance, and quick chat."""

import logging
import os
import subprocess
import time
import urllib.request

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

# Exact filenames (without .gguf) for models registered in jetson-infer.
# Only these get routed through jetson-infer; everything else starts directly.
_JETSON_INFER_KEYS = {
    "MiniCPM5-1B-Claude-Opus-Fable5-Thinking-Q8_0": "MiniCPM5",
    "qwen3.5-4B-super-coder.Q4_0": "qwen3.5",
    "Ternary-Bonsai-8B-Q2_0": "8B",
}


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
        key = _JETSON_INFER_KEYS.get(model_name)
        jetson_infer = self._store.config.jetson_infer_bin
        env = {
            "LD_LIBRARY_PATH": self._store.config.ld_library_path,
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(__import__("pathlib").Path.home()),
        }
        log.debug("_switch_worker: model=%r key=%r", model_name, key)
        try:
            # Always stop the running server first
            stop = subprocess.run(
                ["python3", jetson_infer, "stop"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            log.debug("stop: rc=%d stdout=%r", stop.returncode, stop.stdout.strip())

            self.app.call_from_thread(
                lambda: self._set_switch_status(f"  [yellow]⟳ Loading {model_name}…[/yellow]")
            )

            if key:
                # Registered model — delegate entirely to jetson-infer
                start = subprocess.run(
                    ["python3", jetson_infer, "start", "--model", key],
                    capture_output=True, text=True, timeout=300, env=env,
                )
                log.debug("start (jetson-infer): rc=%d stdout=%r", start.returncode, start.stdout.strip())
                ok = start.returncode == 0
                err = start.stderr.strip() or start.stdout.strip() or "unknown error"
            else:
                # Unregistered model — start llama-server directly
                ok, err = self._start_direct(model_name, env)

            if ok:
                self.app.call_from_thread(lambda: self._set_switch_status(""))
                self.app.call_from_thread(
                    lambda: self.notify(f"Switched to {model_name}", timeout=4)
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

    def _start_direct(self, model_name: str, env: dict) -> tuple[bool, str]:
        """Launch llama-server directly for models not registered in jetson-infer."""
        model_dir = self._store.config.model_dir
        port = self._store.config.server_port
        llama_bin = os.path.join(self._store.config.llama_cpp_bin, "llama-server")
        model_path = os.path.join(model_dir, f"{model_name}.gguf")

        if not os.path.exists(model_path):
            return False, f"Model file not found: {model_path}"
        if not os.path.exists(llama_bin):
            return False, f"llama-server not found: {llama_bin}"

        cmd = [
            llama_bin, "-m", model_path,
            "--host", "0.0.0.0",
            "--port", str(port),
            "--n-gpu-layers", "99",
            "--ctx-size", "4096",
            "--metrics",
        ]
        log.debug("_start_direct: %s", " ".join(cmd))

        with open("/tmp/jetson-infer.log", "w") as logfile:
            proc = subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT, env=env)

        with open("/tmp/jetson-infer.pid", "w") as pidf:
            pidf.write(str(proc.pid))

        # Poll health endpoint until ready (up to 5 minutes)
        health_url = f"http://127.0.0.1:{port}/health"
        for i in range(150):
            time.sleep(2)
            try:
                resp = urllib.request.urlopen(health_url, timeout=2).read()
                if b'"status":"ok"' in resp:
                    log.debug("_start_direct: server healthy after %ds", i * 2)
                    return True, ""
            except Exception:
                pass
            # Check if process died
            if proc.poll() is not None:
                return False, f"llama-server exited early (rc={proc.returncode}) — check /tmp/jetson-infer.log"

        return False, "Server did not become healthy within 5 minutes"

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
