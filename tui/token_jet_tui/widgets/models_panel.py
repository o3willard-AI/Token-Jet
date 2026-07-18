"""Models panel — active model info, standby models, and download progress."""

from __future__ import annotations

import glob
import json
import os
import urllib.request

from textual import work
from textual.widgets import Static
from textual.containers import Container

from token_jet_tui.store import RootStore, DownloadProgress


class ModelsPanel(Container):
    """Shows loaded model plus standby models; overlays download progress."""

    DEFAULT_CSS = """
    ModelsPanel {
        border: solid $primary;
        padding: 1;
        height: auto;
    }
    .panel-title {
        text-style: bold;
        color: $text-muted;
        padding-bottom: 1;
    }
    #separator {
        height: 1;
    }
    #standby-models {
        color: $text-muted;
    }
    #download-overlay {
        color: $success;
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._store = RootStore()
        self._active_name: str | None = None

    def compose(self):
        yield Static("ACTIVE MODEL", classes="panel-title")
        yield Static("Loading...", id="active-model-info")
        yield Static("", id="separator")
        yield Static("STANDBY MODELS", classes="panel-title")
        yield Static("", id="standby-models")
        yield Static("", id="download-overlay")

    def on_mount(self) -> None:
        self._store.download_progress.watch(self._on_download_progress)
        self.set_interval(5, self._schedule_refresh)

    def on_unmount(self) -> None:
        self._store.download_progress.unwatch(self._on_download_progress)

    def _schedule_refresh(self) -> None:
        self._refresh_worker()

    @work(thread=True, exit_on_error=False)
    def _refresh_worker(self) -> None:
        """Fetch data in background thread, then post results to the event loop."""
        host = self._store.config.server_host
        port = self._store.config.server_port
        model_dir = self._store.config.model_dir

        # --- blocking I/O in thread ---
        try:
            resp = json.loads(
                urllib.request.urlopen(
                    f"http://{host}:{port}/v1/models", timeout=5
                ).read()
            )
            data = resp.get("data") or []
            if data:
                model = data[0]
                meta = model.get("meta", {})
                active_name = os.path.basename(model.get("id", ""))
                short = active_name.replace(".gguf", "")
                size_gb = meta.get("size", 0) / (1024 ** 3)
                params_b = meta.get("n_params", 0) / 1e9
                ctx = meta.get("n_ctx", "?")
                ftype = meta.get("ftype", "")
                info = (
                    f"  {short}  |  {size_gb:.1f} GB  |  "
                    f"{params_b:.1f}B params  |  ctx {ctx}  |  {ftype}"
                )
            else:
                active_name = None
                info = "  No model loaded — use Ctrl+S to load one"
        except Exception:
            active_name = None
            info = "  Server unreachable"

        ggufs = sorted(glob.glob(os.path.join(model_dir, "*.gguf")))
        standby_lines = []
        for g in ggufs:
            name = os.path.basename(g)
            base = name.replace(".gguf", "")
            size_gb = os.path.getsize(g) / (1024 ** 3)
            if name != active_name:
                standby_lines.append(f"  {base}  ({size_gb:.1f} GB)")
        standby = "\n".join(standby_lines) if standby_lines else "  None"

        # --- UI updates on event loop ---
        self._active_name = active_name

        def _update(info=info, standby=standby):
            if self.is_mounted:
                self.query_one("#active-model-info").update(info)
                self.query_one("#standby-models").update(standby)

        self.app.call_from_thread(_update)

    def _on_download_progress(self, progress: DownloadProgress | None) -> None:
        try:
            self.app.call_from_thread(self._render_download, progress)
        except Exception:
            pass

    def _render_download(self, p: DownloadProgress | None) -> None:
        if not self.is_mounted:
            return
        overlay = self.query_one("#download-overlay")
        if p is None:
            overlay.update("")
            return
        if p.done:
            overlay.update(f"  [green]Download complete: {p.filename}[/green]")
        elif p.cancelled:
            overlay.update(f"  [yellow]Download cancelled: {p.filename}[/yellow]")
        elif p.error:
            overlay.update(f"  [red]Download error: {p.error}[/red]")
        else:
            bar_len = 20
            filled = int(bar_len * p.pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            overlay.update(
                f"  Downloading {p.filename}  {bar} {p.pct:.0f}%  {p.speed_mb:.1f} MB/s"
            )
