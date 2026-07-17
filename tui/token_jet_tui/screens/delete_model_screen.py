"""Delete model screen — select a local GGUF and remove it from disk."""

from __future__ import annotations

import glob
import json
import os
import urllib.request
from pathlib import Path

from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem
from textual.containers import Container
from textual import work

from token_jet_tui.store import RootStore


class DeleteModelScreen(ModalScreen):
    """Lists models on disk; Enter deletes the selected one."""

    DEFAULT_CSS = """
    DeleteModelScreen {
        align: center middle;
    }
    #delete-dialog {
        border: solid $error;
        background: $surface;
        padding: 1 2;
        width: 64;
        height: auto;
        max-height: 24;
    }
    #delete-title {
        text-style: bold;
        color: $error;
        padding-bottom: 1;
    }
    #delete-list {
        height: auto;
        max-height: 14;
    }
    #delete-status {
        color: $text-muted;
        height: 2;
        padding-top: 1;
    }
    #delete-hint {
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._store = RootStore()
        self._model_paths: list[str] = []
        self._active_name: str | None = None
        self._pending_delete: str | None = None

    def compose(self):
        with Container(id="delete-dialog"):
            yield Static("Remove Model", id="delete-title")
            yield ListView(id="delete-list")
            yield Static("", id="delete-status")
            yield Static("Enter: delete   Esc: cancel", id="delete-hint")

    def on_mount(self) -> None:
        self._load_list()

    def _load_list(self) -> None:
        try:
            resp = json.loads(
                urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=3).read()
            )
            data = resp.get("data") or []
            if data:
                self._active_name = os.path.basename(data[0]["id"])
        except Exception:
            self._active_name = None

        model_dir = self._store.config.model_dir
        self._model_paths = sorted(glob.glob(os.path.join(model_dir, "*.gguf")))
        self._pending_delete = None

        lv = self.query_one("#delete-list", ListView)
        lv.clear()
        if not self._model_paths:
            lv.append(ListItem(Static("No .gguf files found in ~/models/")))
            return
        for path in self._model_paths:
            name = os.path.basename(path)
            size_gb = os.path.getsize(path) / (1024 ** 3)
            loaded = "  [LOADED — stop server first]" if name == self._active_name else ""
            lv.append(ListItem(Static(f"{name}  ({size_gb:.1f} GB){loaded}")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#delete-list", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._model_paths):
            return
        path = self._model_paths[idx]
        name = os.path.basename(path)

        if name == self._active_name:
            self.query_one("#delete-status").update(
                f"[yellow]{name}[/yellow] is loaded — unload or stop the server first."
            )
            return

        if self._pending_delete == path:
            self._do_delete(path, name)
        else:
            self._pending_delete = path
            self.query_one("#delete-status").update(
                f"Press Enter again to confirm deleting [bold]{name}[/bold]"
            )

    @work(thread=True)
    def _do_delete(self, path: str, name: str) -> None:
        self.app.call_from_thread(
            lambda: self.query_one("#delete-status").update(f"Deleting {name}...")
        )
        try:
            os.remove(path)
            self.app.call_from_thread(
                lambda: self.query_one("#delete-status").update(f"[green]Deleted {name}[/green]")
            )
            self.app.call_from_thread(self._load_list)
        except Exception as e:
            self.app.call_from_thread(
                lambda msg=str(e): self.query_one("#delete-status").update(f"[red]Error: {msg}[/red]")
            )

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
