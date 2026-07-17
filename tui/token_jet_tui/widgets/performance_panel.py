"""Performance panel — live TPS and token counters from llama-server /metrics."""

from __future__ import annotations

import re
import time
import urllib.request

from textual.widgets import Static
from textual.containers import Container

from token_jet_tui.store import RootStore


class PerformancePanel(Container):
    """Shows tokens/sec, peak TPS, and session totals from the inference server."""

    DEFAULT_CSS = """
    PerformancePanel {
        border: solid $warning;
        padding: 1;
        height: auto;
    }
    """

    def compose(self):
        yield Static("PERFORMANCE", classes="panel-title")
        yield Static("Waiting for server...", id="perf-stats")

    def on_mount(self) -> None:
        self._store = RootStore()
        self._prev_tokens: float = 0.0
        self._prev_time: float = time.monotonic()
        self._peak_tps: float = 0.0
        self._tps_window: list[float] = []
        self._metrics_disabled = False
        self.set_interval(2, self._refresh)

    def _refresh(self) -> None:
        host = self._store.config.server_host
        port = self._store.config.server_port

        if self._metrics_disabled:
            self.query_one("#perf-stats").update(
                "  Metrics not enabled — restart jetson-infer to activate"
            )
            return

        try:
            raw = urllib.request.urlopen(
                f"http://{host}:{port}/metrics", timeout=3
            ).read().decode()
        except Exception:
            self.query_one("#perf-stats").update("  Server unreachable")
            self._store.server_healthy.value = False
            return

        self._store.server_healthy.value = True

        if '"not_supported_error"' in raw or "not_supported" in raw.lower():
            self._metrics_disabled = True
            return

        tokens = self._metric(raw, "llamacpp:tokens_predicted_total")
        requests = int(self._metric(raw, "llamacpp:requests_processed_total") or 0)

        now = time.monotonic()
        elapsed = now - self._prev_time

        if tokens is not None and elapsed > 0:
            delta = tokens - self._prev_tokens
            tps = max(0.0, delta / elapsed) if delta > 0 else 0.0

            self._tps_window.append(tps)
            if len(self._tps_window) > 15:
                self._tps_window.pop(0)
            if tps > self._peak_tps:
                self._peak_tps = tps

            self._prev_tokens = tokens
            self._prev_time = now

            self._store.server_tps.value = tps
            self._store.server_tokens_total.value = int(tokens)
            self._store.server_requests.value = requests

            current = self._tps_window[-1]
            avg = sum(self._tps_window) / len(self._tps_window) if self._tps_window else 0.0

            self.query_one("#perf-stats").update(
                f"  TPS now: {current:.1f}  |  peak: {self._peak_tps:.1f}  |  "
                f"avg: {avg:.1f}  |  tokens out: {int(tokens):,}  |  requests: {requests:,}"
            )

    def _metric(self, text: str, name: str) -> float | None:
        m = re.search(rf"^{re.escape(name)}\s+([\d.eE+\-]+)", text, re.MULTILINE)
        return float(m.group(1)) if m else None
