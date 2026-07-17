"""Entry point for Token-Jet TUI."""

import sys
from token_jet_tui.app import TokenJetApp


def main():
    app = TokenJetApp()
    app.run()


if __name__ == "__main__":
    main()
