"""Jetson status panel — unified memory, CPU, temperature, GPU utilization."""

from textual.widgets import Static
from textual.containers import Container


class JetsonPanel(Container):
    """Displays Jetson hardware stats in a compact single line."""

    def compose(self):
        yield Static("JETSON STATUS", classes="panel-title")
        yield Static("Loading...", id="jetson-stats")

    def on_mount(self) -> None:
        self.set_interval(3, self.refresh_stats)

    def refresh_stats(self) -> None:
        try:
            import re, subprocess

            with open("/proc/meminfo") as f:
                mem = f.read()
            total = int(re.search(r"MemTotal:\s+(\d+)", mem).group(1)) // 1024
            avail = int(re.search(r"MemAvailable:\s+(\d+)", mem).group(1)) // 1024
            used = total - avail
            
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    temp = int(f.read().strip()) / 1000
            except:
                temp = 0
            
            try:
                with open("/proc/stat") as f:
                    stat = f.readline().split()
                idle = int(stat[4])
                total_cpu = sum(int(x) for x in stat[1:])
                cpu_pct = 100 - (idle * 100 // total_cpu) if total_cpu else 0
            except:
                cpu_pct = 0
            
            # GPU utilization from tegrastats
            gpu_pct = 0
            try:
                result = subprocess.run(
                    ["tegrastats", "--interval", "100", "--count", "1"],
                    capture_output=True, text=True, timeout=2
                )
                m = re.search(r"GR3D_FREQ (\d+)%", result.stdout)
                if m:
                    gpu_pct = int(m.group(1))
            except:
                pass
            
            line = (
                f"  RAM: {used}M / {total}M  |  "
                f"CPU: {cpu_pct}%  |  "
                f"GPU: {gpu_pct}%  |  "
                f"Temp: {temp:.0f}°C"
            )
            self.query_one("#jetson-stats").update(line)
        except Exception as e:
            self.query_one("#jetson-stats").update(f"Error: {e}")


CSS = """
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
