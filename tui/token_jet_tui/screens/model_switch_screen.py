"""Model switch screen — pick a standby model to activate."""

import os, glob

from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem
from textual.containers import Container


class ModelSwitchScreen(ModalScreen):
    """Modal screen to select a standby model to switch to."""

    DEFAULT_CSS = """
    ModelSwitchScreen {
        align: center middle;
    }
    #switch-dialog {
        border: solid $primary;
        background: $surface;
        padding: 1 2;
        width: 50;
        height: auto;
        max-height: 20;
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

    def __init__(self):
        super().__init__()
        self._model_names = []

    def compose(self):
        items = []
        model_dir = "/home/sblanken/models"
        for g in sorted(glob.glob(os.path.join(model_dir, "*.gguf"))):
            name = os.path.basename(g).replace(".gguf", "")
            size_gb = os.path.getsize(g) / (1024**3)
            self._model_names.append(name)
            items.append(ListItem(Static(f"{name}  ({size_gb:.1f} GB)")))

        with Container(id="switch-dialog"):
            yield Static("Switch Model — select one:", id="switch-title")
            if items:
                yield ListView(*items, id="switch-list")
            else:
                yield Static("No models found on disk.", id="switch-list")
            yield Static("Enter: select  Esc: cancel", id="switch-hint")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and self._model_names:
            try:
                idx = self.query_one("#switch-list", ListView).index
                if idx is not None and idx < len(self._model_names):
                    self.dismiss(self._model_names[idx])
            except:
                pass

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            lv = self.query_one("#switch-list", ListView)
            if lv.index is not None and lv.index < len(self._model_names):
                self.dismiss(self._model_names[lv.index])
