"""Models panel — active model display and actions."""

from textual.widgets import Static, Button
from textual.containers import Container, Horizontal
import os


class ModelsPanel(Container):
    """Model management: view active model, switch, download."""

    def compose(self):
        yield Static("ACTIVE MODEL", classes="panel-title")
        yield Static("Loading...", id="active-model-info")
        yield Horizontal(
            Button("Switch", id="btn-switch", variant="primary"),
            Button("Download", id="btn-download", variant="default"),
            Button("Refresh", id="btn-refresh", variant="default"),
            id="model-buttons"
        )

    def on_mount(self) -> None:
        self.refresh_model_info()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
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
                name = os.path.basename(model["id"].replace(".gguf", ""))
                size_gb = meta.get("size", 0) / (1024**3)
                params_b = meta.get("n_params", 0) / 1e9
                ctx = meta.get("n_ctx", "?")
                info = f"  {name}  |  {size_gb:.1f} GB  |  {params_b:.1f}B params  |  {ctx} ctx"
            else:
                info = "  No model loaded"
            self.query_one("#active-model-info").update(info)
        except:
            self.query_one("#active-model-info").update("  Server unreachable")


CSS = """
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
#model-buttons {
    margin-top: 1;
    height: auto;
}
#btn-switch, #btn-download, #btn-refresh {
    margin-right: 1;
}
"""
