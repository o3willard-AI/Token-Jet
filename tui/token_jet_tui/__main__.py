"""Entry point for Token-Jet TUI — runs pre-flight checks then launches."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from token_jet_tui.tui_logging import setup_logging
setup_logging()

import logging
log = logging.getLogger(__name__)

from token_jet_tui.config import load_config


def _server_health(host: str, port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://{host}:{port}/health", timeout=3)
        return True
    except Exception:
        return False


def _has_models(model_dir: str) -> bool:
    try:
        return any(Path(model_dir).expanduser().glob("*.gguf"))
    except Exception:
        return False


def main() -> None:
    cfg = load_config()

    if not _has_models(cfg.model_dir):
        # First run — no models yet. Skip the server check entirely.
        # The TUI will show a welcome message guiding the user to Ctrl+D.
        pass
    elif not _server_health(cfg.server_host, cfg.server_port):
        print(f"\nInference server not running on {cfg.server_host}:{cfg.server_port}")
        print("  → Press Ctrl+S inside the TUI to start it.")

    from token_jet_tui.app import TokenJetApp
    app = TokenJetApp()
    app.run()


if __name__ == "__main__":
    main()
