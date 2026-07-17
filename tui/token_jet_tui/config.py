"""Token-Jet configuration — loads ~/.config/token-jet/config.toml."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

CONFIG_DIR = Path("~/.config/token-jet").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class AppConfig:
    model_dir: str = field(default_factory=lambda: str(Path("~/models").expanduser()))
    llama_cpp_bin: str = field(
        default_factory=lambda: str(Path("~/llama.cpp/build/bin").expanduser())
    )
    server_host: str = "127.0.0.1"
    server_port: int = 1234
    ld_library_path: str = "/usr/local/cuda-13.2/targets/sbsa-linux/lib"
    jetson_infer_bin: str = field(
        default_factory=lambda: str(Path("~/bin/jetson-infer").expanduser())
    )
    hf_download_timeout: int = 300


def load_config() -> AppConfig:
    """Load config from disk, falling back to safe defaults."""
    if not CONFIG_PATH.exists() or tomllib is None:
        return AppConfig()
    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        cfg = AppConfig()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
    except Exception:
        return AppConfig()


def save_default_config() -> None:
    """Write a starter config.toml if none exists yet."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        return
    cfg = AppConfig()
    CONFIG_PATH.write_text(
        f"""# Token-Jet configuration
# Edit paths to match your Jetson setup.

model_dir = "{cfg.model_dir}"
llama_cpp_bin = "{cfg.llama_cpp_bin}"
server_host = "{cfg.server_host}"
server_port = {cfg.server_port}
ld_library_path = "{cfg.ld_library_path}"
jetson_infer_bin = "{cfg.jetson_infer_bin}"
hf_download_timeout = {cfg.hf_download_timeout}
"""
    )
