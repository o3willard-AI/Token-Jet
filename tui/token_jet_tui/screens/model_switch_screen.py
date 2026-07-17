"""Model switch screen — pick a model from disk to activate."""

from __future__ import annotations

import glob
import os

from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem
from textual.containers import Container

from token_jet_tui.store import RootStore


class ModelSwitchScreen(ModalScreen):
    """Modal: choose a GGUF from ~/models/ to switch to."""

    DEFAULT_CSS = """
    ModelSwitchScreen {
        align: center middle;
    }
    #switch-dialog {
        border: solid $primary;
        background: $surface;
        padding: 1 2;
        width: 60;
        height: auto;
        max-height: 22;
    }
    #switch-title {
        text-style: bold;
        padding-bottom: 1;
    }
    #switch-list {
        height: auto;
        max-height: 14;
    }
    #switch-hint {
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._store = RootStore()
        self._model_names: list[str] = []

    def compose(self):
        model_dir = self._store.config.model_dir
        items = []
        for path in sorted(glob.glob(os.path.join(model_dir, "*.gguf"))):
            name = os.path.basename(path).replace(".gguf", "")
            size_gb = os.path.getsize(path) / (1024 ** 3)
            self._model_names.append(name)
            items.append(ListItem(Static(f"{name}  ({size_gb:.1f} GB)")))

        with Container(id="switch-dialog"):
            yield Static("Switch Model", id="switch-title")
            if items:
                yield ListView(*items, id="switch-list")
            else:
                yield Static("No models found in ~/models/", id="switch-list")
            yield Static("Enter: load   Esc: cancel", id="switch-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#switch-list", ListView)
        idx = lv.index
        if idx is not None and idx < len(self._model_names):
            self.dismiss(self._model_names[idx])

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
