"""Model switch screen — pick a model from disk to activate."""

from __future__ import annotations

import glob
import logging
import os

from textual import events
from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem
from textual.containers import Container

from token_jet_tui.store import RootStore

log = logging.getLogger(__name__)


class _SilentListView(ListView):
    """ListView that suppresses the built-in Enter→Selected action.

    Selection is handled by the parent Screen's on_key so we never get
    a spurious Selected event on mount or focus.
    """

    def action_select_cursor(self) -> None:
        pass  # intentionally silent — Screen handles Enter


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
        log.debug("ModelSwitchScreen compose: model_dir=%s", model_dir)
        items = []
        for path in sorted(glob.glob(os.path.join(model_dir, "*.gguf"))):
            name = os.path.basename(path).replace(".gguf", "")
            size_gb = os.path.getsize(path) / (1024 ** 3)
            self._model_names.append(name)
            items.append(ListItem(Static(f"{name}  ({size_gb:.1f} GB)")))

        log.debug("ModelSwitchScreen compose: found %d models", len(items))
        with Container(id="switch-dialog"):
            yield Static("Switch Model", id="switch-title")
            if items:
                yield _SilentListView(*items, id="switch-list")
            else:
                yield Static("No models found in ~/models/", id="switch-list")
            yield Static("↑↓ navigate · Enter: load · Esc: cancel", id="switch-hint")

    def on_key(self, event: events.Key) -> None:
        log.debug("ModelSwitchScreen.on_key: key=%r", event.key)
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            try:
                lv = self.query_one("#switch-list", _SilentListView)
            except Exception:
                log.debug("ModelSwitchScreen: no _SilentListView found")
                return
            idx = lv.index
            log.debug("ModelSwitchScreen Enter: idx=%s names=%s", idx, self._model_names)
            if idx is not None and idx < len(self._model_names):
                selected = self._model_names[idx]
                log.debug("ModelSwitchScreen: dismissing with %r", selected)
                self.dismiss(selected)
