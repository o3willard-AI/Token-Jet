"""Jetson status panel — unified memory, CPU, temperature, power."""

from textual.widgets import Static
from textual.containers import Container


class JetsonPanel(Container):
    """Displays Jetson hardware status: memory, CPU, temperature, power."""

    def compose(self):
        yield Static("JETSON STATUS", classes="panel-title")
        yield Static("Loading...", id="jetson-stats")

    def on_mount(self) -> None:
        self.set_interval(5, self.refresh_stats)

    def refresh_stats(self) -> None:
        """Refresh Jetson stats from /proc and tegrastats."""
        try:
            import subprocess, re
            
            # Memory from /proc/meminfo
            with open("/proc/meminfo") as f:
                mem = f.read()
            total = int(re.search(r"MemTotal:\s+(\d+)", mem).group(1)) // 1024
            avail = int(re.search(r"MemAvailable:\s+(\d+)", mem).group(1)) // 1024
            used = total - avail
            
            # CPU temp
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    temp = int(f.read().strip()) / 1000
            except:
                temp = 0
            
            # CPU usage
            try:
                with open("/proc/stat") as f:
                    stat = f.readline().split()
                idle = int(stat[4])
                total_cpu = sum(int(x) for x in stat[1:])
            except:
                idle = total_cpu = 1
            cpu_pct = 100 - (idle * 100 // total_cpu) if total_cpu else 0
            
            # GPU info from CUDA
            try:
                import subprocess
                result = subprocess.run(
                    ["/home/sblanken/llama.cpp/build/bin/llama-bench", "--list-devices"],
                    capture_output=True, text=True, timeout=5,
                    env={"LD_LIBRARY_PATH": "/usr/local/cuda-13.2/targets/sbsa-linux/lib"}
                )
                gpu_info = "CUDA available" if "CUDA" in result.stderr + result.stdout else "GPU unknown"
            except:
                gpu_info = "GPU detect failed"
            
            self.query_one("#jetson-stats").update(
                f"  Memory: {used}M / {total}M used ({avail}M free)\n"
                f"  CPU:    {cpu_pct}% utilized\n"
                f"  Temp:   {temp:.1f}°C\n"
                f"  GPU:    {gpu_info}"
            )
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
