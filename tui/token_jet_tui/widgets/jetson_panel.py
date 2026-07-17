"""Jetson status panel — unified memory, CPU utilization, GPU, and temperature."""

from __future__ import annotations

import re
import subprocess

from textual.widgets import Static
from textual.containers import Container

from token_jet_tui.store import RootStore


class JetsonPanel(Container):
    """Displays live Jetson hardware stats in a compact single-line format."""

    DEFAULT_CSS = """
    JetsonPanel {
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._store = RootStore()
        self._cpu_prev: tuple[int, int] | None = None  # (idle, total)

    def compose(self):
        yield Static("JETSON STATUS", classes="panel-title")
        yield Static("Loading...", id="jetson-stats")

    def on_mount(self) -> None:
        self.set_interval(3, self._refresh)

    def _refresh(self) -> None:
        try:
            ram_used, ram_total = self._read_ram()
            temp = self._read_temp()
            cpu_pct = self._read_cpu()
            gpu_pct = self._read_gpu()

            self.query_one("#jetson-stats").update(
                f"  RAM: {ram_used} / {ram_total} MB  |  "
                f"CPU: {cpu_pct}%  |  "
                f"GPU: {gpu_pct}%  |  "
                f"Temp: {temp:.0f}°C"
            )
        except Exception as e:
            self.query_one("#jetson-stats").update(f"  Error: {e}")

    def _read_ram(self) -> tuple[int, int]:
        with open("/proc/meminfo") as f:
            mem = f.read()
        total = int(re.search(r"MemTotal:\s+(\d+)", mem).group(1)) // 1024
        avail = int(re.search(r"MemAvailable:\s+(\d+)", mem).group(1)) // 1024
        return total - avail, total

    def _read_temp(self) -> float:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000
        except OSError:
            return 0.0

    def _read_cpu(self) -> int:
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            idle = int(parts[4])
            total = sum(int(x) for x in parts[1:])
            if self._cpu_prev is not None:
                prev_idle, prev_total = self._cpu_prev
                delta_idle = idle - prev_idle
                delta_total = total - prev_total
                pct = 100 - (delta_idle * 100 // delta_total) if delta_total else 0
            else:
                pct = 0
            self._cpu_prev = (idle, total)
            return max(0, min(100, pct))
        except OSError:
            return 0

    def _read_gpu(self) -> int:
        try:
            result = subprocess.run(
                ["tegrastats", "--interval", "100", "--count", "1"],
                capture_output=True, text=True, timeout=2,
            )
            m = re.search(r"GR3D_FREQ\s+(\d+)%", result.stdout)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0
