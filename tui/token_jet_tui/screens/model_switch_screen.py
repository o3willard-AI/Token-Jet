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

    def compose(self):
        items = []
        model_dir = "/home/sblanken/models"
        for g in sorted(glob.glob(os.path.join(model_dir, "*.gguf"))):
            name = os.path.basename(g).replace(".gguf", "")
            size_gb = os.path.getsize(g) / (1024**3)
            items.append(ListItem(Static(f"{name}  ({size_gb:.1f} GB)")))

        with Container(id="switch-dialog"):
            yield Static("Switch Model — select one:", id="switch-title")
            if items:
                yield ListView(*items, id="switch-list")
            else:
                yield Static("No models found on disk.", id="switch-list")
            yield Static("Enter: select  Esc: cancel", id="switch-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.children:
            label = event.item.children[0]
            if hasattr(label, 'renderable'):
                self.dismiss(str(label.renderable).split("  (")[0])

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)
