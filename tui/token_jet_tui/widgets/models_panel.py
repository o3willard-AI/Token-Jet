"""Models panel — active model and standby models on disk."""

from textual.widgets import Static
from textual.containers import Container
import os
import glob


class ModelsPanel(Container):
    """Shows the currently loaded model plus standby models available on disk."""

    def compose(self):
        yield Static("ACTIVE MODEL", classes="panel-title")
        yield Static("Loading...", id="active-model-info")
        yield Static("", id="separator")
        yield Static("STANDBY MODELS", classes="panel-title")
        yield Static("", id="standby-models")

    def on_mount(self) -> None:
        self.set_interval(5, self.refresh_model_info)

    def refresh_model_info(self) -> None:
        try:
            import urllib.request, json

            # Get active model from server
            active_name = None
            try:
                resp = json.loads(urllib.request.urlopen(
                    "http://127.0.0.1:1234/v1/models", timeout=5).read())
                if resp.get("data"):
                    model = resp["data"][0]
                    meta = model.get("meta", {})
                    active_name = os.path.basename(model["id"])
                    short = active_name.replace(".gguf", "")
                    size_gb = meta.get("size", 0) / (1024**3)
                    params_b = meta.get("n_params", 0) / 1e9
                    ctx = meta.get("n_ctx", "?")
                    info = f"  {short}  |  {size_gb:.1f} GB  |  {params_b:.1f}B params  |  {ctx} ctx"
                else:
                    info = "  No model loaded"
            except:
                info = "  Server unreachable"
            self.query_one("#active-model-info").update(info)

            # List standby models from disk
            model_dir = "/home/sblanken/models"
            ggufs = sorted(glob.glob(os.path.join(model_dir, "*.gguf")))
            lines = []
            for g in ggufs:
                name = os.path.basename(g).replace(".gguf", "")
                size_gb = os.path.getsize(g) / (1024**3)
                marker = "  (active)" if active_name and os.path.basename(g) == active_name else ""
                if not marker:
                    lines.append(f"  {name}  ({size_gb:.1f} GB)")
            if not lines:
                lines.append("  None")
            self.query_one("#standby-models").update("\n".join(lines))

        except Exception as e:
            self.query_one("#active-model-info").update(f"Error: {e}")


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
#separator {
    height: 1;
}
#standby-models {
    color: $text-muted;
}
"""
