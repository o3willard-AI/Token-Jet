"""Models panel — active model display."""

from textual.widgets import Static
from textual.containers import Container
import os


class ModelsPanel(Container):
    """Shows the currently loaded model."""

    def compose(self):
        yield Static("ACTIVE MODEL", classes="panel-title")
        yield Static("Loading...", id="active-model-info")

    def on_mount(self) -> None:
        self.set_interval(5, self.refresh_model_info)

    def refresh_model_info(self) -> None:
        try:
            import urllib.request, json
            resp = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:1234/v1/models", timeout=5).read())
            if resp.get("data"):
                model = resp["data"][0]
                meta = model.get("meta", {})
                name = os.path.basename(model["id"]).replace(".gguf", "")
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
"""
