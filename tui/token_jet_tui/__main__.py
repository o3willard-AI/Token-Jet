"""Entry point for Token-Jet TUI — runs pre-flight checks then launches."""

from __future__ import annotations

import sys
import urllib.request

from token_jet_tui.config import load_config


def _server_health(host: str, port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://{host}:{port}/health", timeout=3)
        return True
    except Exception:
        return False


def main() -> None:
    cfg = load_config()

    if not _server_health(cfg.server_host, cfg.server_port):
        print(f"\nInference server not responding on {cfg.server_host}:{cfg.server_port}")
        print("  Start it with:  jetson-infer start")
        ans = input("Launch TUI anyway? [Y/n] ").strip().lower()
        if ans == "n":
            sys.exit(0)

    from token_jet_tui.app import TokenJetApp
    app = TokenJetApp()
    app.run()


if __name__ == "__main__":
    main()
