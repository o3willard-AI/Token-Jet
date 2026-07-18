"""Quick chat panel — multi-turn conversation with the loaded model."""

from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.request

from rich.markup import escape as markup_escape
from textual.widgets import Static, RichLog
from textual.containers import Container
from textual import events, work
from textual.worker import WorkerState

from token_jet_tui.store import RootStore

log = logging.getLogger(__name__)

SLASH_HELP = """\
[bold]/clear[/bold]   — clear chat history
[bold]/help[/bold]    — show this list
[bold]/model[/bold]   — show loaded model name
[bold]Ctrl+S[/bold]   — switch loaded model
[bold]Ctrl+D[/bold]   — download model from Hugging Face
[bold]Ctrl+X[/bold]   — remove a local model
[bold]Ctrl+R[/bold]   — reset performance counters
[bold]Ctrl+Q[/bold]   — quit
[bold]Ctrl+V[/bold]   — paste clipboard  (or Shift+Insert / Ctrl+Shift+V)\
"""


class ChatInput(Static):
    """Focusable single-line text input.

    Uses render() + refresh() so the cursor indicator always reflects the
    live has_focus state — no timing race with on_focus callbacks.
    """

    can_focus = True

    def __init__(self) -> None:
        super().__init__("", id="chat-input-area")
        self._buffer = ""

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self):
        if self.has_focus:
            return f"  > {self._buffer}_"
        return f"  {self._buffer}" if self._buffer else ""

    # ── Focus events ──────────────────────────────────────────────────────────

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    # ── Paste handling ────────────────────────────────────────────────────────

    def on_paste(self, event: events.Paste) -> None:
        """Handle bracketed paste from the terminal (Shift+Insert, Ctrl+Shift+V, etc.)."""
        text = event.text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        self._buffer += text
        self.refresh()

    def _paste_from_clipboard(self) -> None:
        """Try subprocess clipboard tools for Ctrl+V (headless fallback)."""
        for cmd in [
            ["xclip", "-o", "-sel", "clipboard"],
            ["xsel", "--clipboard", "--output"],
            ["wl-paste", "--no-newline"],
            ["pbpaste"],
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout:
                    text = result.stdout.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
                    self._buffer += text
                    self.refresh()
                    return
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

    # ── Key handling ──────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        log.debug("ChatInput.on_key: key=%r", event.key)
        try:
            if event.key == "enter":
                panel = self.parent
                log.debug("ChatInput Enter — parent=%s", type(panel).__name__)
                if hasattr(panel, "send_message"):
                    panel.send_message()
            elif event.key == "ctrl+v":
                self._paste_from_clipboard()
                event.stop()
            elif event.key == "backspace":
                self._buffer = self._buffer[:-1]
                self.refresh()
            elif event.key == "space":
                self._buffer += " "
                self.refresh()
            elif event.is_printable and event.character:
                self._buffer += event.character
                self.refresh()
        except Exception:
            log.exception("ChatInput.on_key raised")

    @property
    def value(self) -> str:
        return self._buffer

    def clear(self) -> None:
        self._buffer = ""
        self.refresh()


class ChatPanel(Container):
    """Scrollable chat log with multi-turn history. Ctrl+F to focus input."""

    SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    DEFAULT_CSS = """
    ChatPanel {
        border: solid $primary;
        padding: 1;
        layout: vertical;
    }
    .panel-title {
        text-style: bold;
        color: $text-muted;
        padding-bottom: 1;
    }
    #chat-log {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    #chat-status {
        color: $warning;
        height: 1;
    }
    #chat-input-hint {
        color: $text-muted;
        height: 1;
    }
    #chat-input-area {
        height: 1;
    }
    #chat-input-area:focus {
        background: $surface;
        color: $text;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._store = RootStore()
        self._history: list[dict] = []
        self._spinner_idx = 0
        self._spinning = False
        self._spin_timer = None
        self._request_start: float = 0.0
        self._request_timeout: int = 600

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield RichLog(id="chat-log", markup=True, highlight=False, wrap=True)
        yield Static("", id="chat-status")
        yield Static("  Enter to send · Ctrl+V / Shift+Insert to paste · /help for commands",
                     id="chat-input-hint")
        yield ChatInput()

    def on_mount(self) -> None:
        self._chat_input = self.query_one(ChatInput)
        self._chat_log = self.query_one("#chat-log", RichLog)
        self._chat_status = self.query_one("#chat-status", Static)
        log.debug("ChatPanel mounted")

    def send_message(self) -> None:
        log.debug("send_message called")
        try:
            msg = self._chat_input.value.strip()
            if not msg:
                return
            self._chat_input.clear()
            log.debug("send_message: msg=%r", msg)

            if msg.startswith("/"):
                self._handle_slash(msg)
                return

            self._chat_log.write(f"[bold cyan]You:[/bold cyan] {msg}")
            self._history.append({"role": "user", "content": msg})
            tps = self._store.server_tps.value
            if tps and tps > 0:
                req_timeout = max(60, min(900, int(8192 / tps * 1.5)))
            else:
                req_timeout = 900
            log.debug("send_message: tps=%.1f computed timeout=%ds", tps or 0, req_timeout)
            self._start_spinner(req_timeout)
            log.debug("send_message: spawning _do_request worker")
            self._do_request(self._history[:], req_timeout)
        except Exception:
            log.exception("send_message raised")

    def _handle_slash(self, cmd: str) -> None:
        log.debug("_handle_slash: %r", cmd)
        verb = cmd.split()[0].lower()
        if verb == "/clear":
            self._history.clear()
            self._chat_log.clear()
            self._chat_status.update("")
            self.notify("Chat cleared", timeout=2)
        elif verb == "/help":
            self._chat_log.write(SLASH_HELP)
        elif verb == "/model":
            self._fetch_model_info()
        else:
            self._chat_log.write(f"[red]Unknown command: {cmd.split()[0]}  (try /help)[/red]")

    @work(thread=True, name="fetch_model_info", exit_on_error=False)
    def _fetch_model_info(self) -> None:
        host = self._store.config.server_host
        port = self._store.config.server_port
        try:
            resp = json.loads(
                urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=3).read()
            )
            data = resp.get("data") or []
            name = data[0]["id"].split("/")[-1] if data else "none"
            msg = f"[dim]Loaded model: {name}[/dim]"
        except Exception:
            log.exception("_fetch_model_info failed")
            msg = "[red]Server unreachable[/red]"
        self.app.call_from_thread(
            lambda m=msg: self._chat_log.write(m)
        )

    def _start_spinner(self, timeout: int) -> None:
        self._spinner_idx = 0
        self._spinning = True
        self._request_start = time.monotonic()
        self._request_timeout = timeout
        self._spin_timer = self.set_interval(0.5, self._tick_spinner)

    def _stop_spinner(self) -> None:
        self._spinning = False
        if self._spin_timer is not None:
            try:
                self._spin_timer.stop()
            except Exception:
                log.exception("_stop_spinner: timer.stop raised")
            self._spin_timer = None
        self._chat_status.update("")

    def _tick_spinner(self) -> None:
        try:
            if self._spinning:
                elapsed = int(time.monotonic() - self._request_start)
                remaining = max(0, self._request_timeout - elapsed)
                self._chat_status.update(
                    f"  {self.SPINNER[self._spinner_idx]} thinking…"
                    f"  {elapsed}s elapsed  ·  timeout in {remaining}s"
                )
                self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER)
        except Exception:
            log.exception("_tick_spinner raised")

    @work(thread=True, name="do_request", exit_on_error=False)
    def _do_request(self, history: list[dict], req_timeout: int) -> tuple:
        log.debug("_do_request: starting, %d messages, timeout=%ds", len(history), req_timeout)
        host = self._store.config.server_host
        port = self._store.config.server_port
        start = time.monotonic()
        try:
            body = {
                "messages": history,
                "max_tokens": 8192,
                "temperature": 0.3,
            }
            req = urllib.request.Request(
                f"http://{host}:{port}/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            log.debug("_do_request: sending HTTP request")
            resp = json.loads(urllib.request.urlopen(req, timeout=req_timeout).read())
            msg = resp["choices"][0]["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            elapsed = time.monotonic() - start
            token_count = resp.get("usage", {}).get("completion_tokens", 0)
            tps = token_count / elapsed if elapsed > 0 and token_count else 0
            stats = (
                f"[dim]{token_count} tok · {tps:.1f} t/s · {elapsed:.1f}s[/dim]"
                if token_count else ""
            )
            log.debug("_do_request: success, %d tokens, content len=%d, reasoning len=%d",
                      token_count, len(content), len(reasoning))
            return content, reasoning, stats
        except Exception as e:
            log.exception("_do_request: failed")
            return None, "", f"[red]Error: {e}[/red]"

    def on_worker_state_changed(self, event) -> None:
        log.debug("on_worker_state_changed: name=%r state=%s",
                  getattr(event.worker, "name", "?"), event.state)
        if event.state != WorkerState.SUCCESS:
            return
        if event.worker.name != "do_request":
            return

        self._stop_spinner()
        result = event.worker.result
        if result is None:
            log.warning("on_worker_state_changed: result is None")
            return

        content, reasoning, stats = result
        log.debug("on_worker_state_changed: content=%s reasoning=%d chars stats=%r",
                  "None" if content is None else f"{len(content)} chars",
                  len(reasoning), stats)

        if content is None:
            # Error path — stats contains the error markup
            self._chat_log.write(stats)
            return

        # Show reasoning block if the model produced one
        if reasoning:
            self._chat_log.write("[bold dim]Reasoning:[/bold dim]")
            self._chat_log.write(f"[dim]{markup_escape(reasoning)}[/dim]")

        # Append assistant turn to the scrollable log
        self._chat_log.write(f"[bold green]Assistant:[/bold green]")
        self._chat_log.write(markup_escape(content))
        if stats:
            self._chat_log.write(stats)
        self._chat_log.write("")  # blank separator

        # Store in history for multi-turn (even if content is empty)
        self._history.append({"role": "assistant", "content": content})
        self._store.server_requests.value = self._store.server_requests.value + 1
