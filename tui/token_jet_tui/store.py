"""Central application state for Token-Jet TUI."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

from token_jet_tui.config import AppConfig, load_config

T = TypeVar("T")


class ReactiveVar(Generic[T]):
    """Thread-safe observable value — notifies watchers on every write."""

    def __init__(self, initial: T) -> None:
        self._value = initial
        self._lock = threading.Lock()
        self._watchers: list[Callable[[T], None]] = []

    @property
    def value(self) -> T:
        with self._lock:
            return self._value

    @value.setter
    def value(self, new: T) -> None:
        with self._lock:
            self._value = new
            watchers = list(self._watchers)
        for cb in watchers:
            try:
                cb(new)
            except Exception:
                pass

    def watch(self, callback: Callable[[T], None]) -> None:
        with self._lock:
            if callback not in self._watchers:
                self._watchers.append(callback)

    def unwatch(self, callback: Callable[[T], None]) -> None:
        with self._lock:
            self._watchers = [w for w in self._watchers if w is not callback]


@dataclass
class DownloadProgress:
    filename: str
    bytes_received: int
    total_bytes: int
    speed_bps: float
    elapsed: float
    cancelled: bool = False
    verifying: bool = False
    error: Optional[str] = None

    @property
    def pct(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return 100.0 * self.bytes_received / self.total_bytes

    @property
    def speed_mb(self) -> float:
        return self.speed_bps / (1024 * 1024)

    @property
    def done(self) -> bool:
        return (
            not self.cancelled
            and not self.verifying
            and self.error is None
            and self.total_bytes > 0
            and self.bytes_received >= self.total_bytes
        )


class RootStore:
    """Singleton holding all shared TUI state."""

    _instance: Optional["RootStore"] = None

    def __new__(cls) -> "RootStore":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._init()
            cls._instance = inst
        return cls._instance

    def _init(self) -> None:
        self.config: AppConfig = load_config()
        self.download_progress: ReactiveVar[Optional[DownloadProgress]] = ReactiveVar(None)
        self.server_tps: ReactiveVar[float] = ReactiveVar(0.0)
        self.server_tokens_total: ReactiveVar[int] = ReactiveVar(0)
        self.server_requests: ReactiveVar[int] = ReactiveVar(0)
        self.server_healthy: ReactiveVar[bool] = ReactiveVar(False)
        self._cancel_event = threading.Event()

    def cancel_download(self) -> None:
        self._cancel_event.set()

    def reset_download_cancel(self) -> None:
        self._cancel_event.clear()

    @property
    def download_cancelled(self) -> bool:
        return self._cancel_event.is_set()
