"""Models panel — active model display, switch, download."""

from textual.widgets import Static, Button
from textual.containers import Container, Horizontal


class ModelsPanel(Container):
    """Model management: view active model, switch, download new."""

    def compose(self):
        yield Static("MODELS", classes="panel-title")
        yield Static("Loading...", id="active-model-info")
        yield Horizontal(
            Button("Switch Model", id="btn-switch", variant="primary"),
            Button("Download Models", id="btn-download", variant="default"),
            Button("Refresh", id="btn-refresh", variant="default"),
            id="model-buttons"
        )

    def on_mount(self) -> None:
        self.refresh_model_info()

    def refresh_model_info(self) -> None:
        """Query the inference server for active model info."""
        try:
            import urllib.request, json
            resp = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:1234/v1/models", timeout=5).read())
            if resp.get("data"):
                model = resp["data"][0]
                meta = model.get("meta", {})
                info = (
                    f"  Active: {model['id']}\n"
                    f"  Size:   {meta.get('size', 0) / (1024**3):.1f} GB\n"
                    f"  Params: {meta.get('n_params', 0) / 1e9:.1f}B\n"
                    f"  Ctx:    {meta.get('n_ctx', '?')} tokens"
                )
            else:
                info = "  No model loaded"
            self.query_one("#active-model-info").update(info)
        except:
            self.query_one("#active-model-info").update("  Server unreachable")


CSS = """
ModelsPanel {
    border: solid $primary;
    padding: 1;
    height: 100%;
}
.panel-title {
    text-style: bold;
    color: $text-muted;
    padding-bottom: 1;
}
#model-buttons {
    margin-top: 1;
    height: auto;
}
#btn-switch, #btn-download, #btn-refresh {
    margin-right: 1;
}
"""
