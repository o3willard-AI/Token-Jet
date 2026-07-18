"""Performance panel — live TPS (in & out), peaks, and session totals."""

from __future__ import annotations

import re
import urllib.request

from textual import work
from textual.widgets import Static
from textual.containers import Container

from token_jet_tui.store import RootStore


class PerformancePanel(Container):
    """Shows prompt-in TPS, generation-out TPS, peaks, and token totals."""

    DEFAULT_CSS = """
    PerformancePanel {
        border: solid $primary;
        padding: 1;
        height: auto;
    }
    """

    def compose(self):
        yield Static("PERFORMANCE", classes="panel-title")
        yield Static("Waiting for server...", id="perf-stats")

    def on_mount(self) -> None:
        self._store = RootStore()
        self._metrics_disabled = False

        # Peak tracking (reset-able)
        self._peak_in_tps: float = 0.0
        self._peak_out_tps: float = 0.0

        # Baselines stored at last reset so displayed totals start from 0
        self._baseline_out: int = 0
        self._baseline_in: int = 0

        # Last observed absolute totals (used to set baselines on reset)
        self._last_tokens_out: int = 0
        self._last_tokens_in: int = 0

        self.set_interval(2, self._schedule_refresh)

    def reset_counters(self) -> None:
        """Reset peaks, rolling window, request count, and token-display baselines."""
        self._peak_in_tps = 0.0
        self._peak_out_tps = 0.0
        self._baseline_out = self._last_tokens_out
        self._baseline_in = self._last_tokens_in
        self._store.server_requests.value = 0
        self._store.server_tps.value = 0.0
        self.query_one("#perf-stats").update(
            "  In:      0.0 avg t/s  peak 0.0"
            "  |  Out:      0.0 avg t/s  peak 0.0"
            "  |  tok in: 0  out: 0"
            "  |  reqs: 0"
        )

    def _schedule_refresh(self) -> None:
        self._refresh_worker()

    @work(thread=True, exit_on_error=False)
    def _refresh_worker(self) -> None:
        """Fetch /metrics in a background thread; push UI update to event loop."""
        host = self._store.config.server_host
        port = self._store.config.server_port

        if self._metrics_disabled:
            self.app.call_from_thread(
                lambda: self.query_one("#perf-stats").update(
                    "  Metrics not enabled — restart jetson-infer to activate"
                )
            )
            return

        try:
            raw = urllib.request.urlopen(
                f"http://{host}:{port}/metrics", timeout=3
            ).read().decode()
        except Exception:
            self._store.server_healthy.value = False
            self.app.call_from_thread(
                lambda: self.query_one("#perf-stats").update("  Server unreachable")
            )
            return

        self._store.server_healthy.value = True

        if '"not_supported_error"' in raw or "not_supported" in raw.lower():
            self._metrics_disabled = True
            return

        # Throughput — llama-server computes these as rolling averages
        tps_out = self._metric(raw, "llamacpp:predicted_tokens_seconds") or 0.0
        tps_in  = self._metric(raw, "llamacpp:prompt_tokens_seconds") or 0.0

        # Cumulative totals
        tokens_out_abs = int(self._metric(raw, "llamacpp:tokens_predicted_total") or 0)
        tokens_in_abs  = int(self._metric(raw, "llamacpp:prompt_tokens_total") or 0)

        # Save for baseline-setting on next reset
        self._last_tokens_out = tokens_out_abs
        self._last_tokens_in  = tokens_in_abs

        # Update peaks
        if tps_out > self._peak_out_tps:
            self._peak_out_tps = tps_out
        if tps_in > self._peak_in_tps:
            self._peak_in_tps = tps_in

        self._store.server_tps.value = tps_out
        self._store.server_tokens_total.value = tokens_out_abs

        requests = self._store.server_requests.value

        # Display relative to last reset
        out_since = tokens_out_abs - self._baseline_out
        in_since  = tokens_in_abs  - self._baseline_in

        line = (
            f"  In:  {tps_in:>7.1f} avg t/s  peak {self._peak_in_tps:.1f}"
            f"  |  Out: {tps_out:>7.1f} avg t/s  peak {self._peak_out_tps:.1f}"
            f"  |  tok in: {in_since:,}  out: {out_since:,}"
            f"  |  reqs: {requests:,}"
        )
        self.app.call_from_thread(
            lambda l=line: self.query_one("#perf-stats").update(l)
        )

    def _metric(self, text: str, name: str) -> float | None:
        m = re.search(rf"^{re.escape(name)}\s+([\d.eE+\-]+)", text, re.MULTILINE)
        return float(m.group(1)) if m else None
