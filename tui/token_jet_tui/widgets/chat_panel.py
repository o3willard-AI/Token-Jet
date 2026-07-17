"""Quick chat panel — multi-turn conversation with the loaded model."""

from __future__ import annotations

import json
import time
import urllib.request

from textual.widgets import Static
from textual.containers import Container
from textual import events, work
from textual.worker import WorkerState

from token_jet_tui.store import RootStore

SLASH_HELP = (
    "/clear  — clear chat history\n"
    "/help   — show this list\n"
    "/model  — show loaded model name\n"
    "Ctrl+S  — switch model"
)


class ChatInput(Static):
    """Focusable single-line text input — plain Static with key handling."""

    can_focus = True
    BINDINGS = [("escape", "blur", "Unfocus")]

    def __init__(self) -> None:
        super().__init__("", id="chat-input-area")
        self._buffer = ""

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            panel = self.parent
            if hasattr(panel, "send_message"):
                panel.send_message()
        elif event.key == "backspace":
            self._buffer = self._buffer[:-1]
            self.update(f"  {self._buffer}")
        elif event.key == "escape":
            self.action_blur()
        elif event.key == "space":
            self._buffer += " "
            self.update(f"  {self._buffer}")
        elif event.is_printable and event.character:
            self._buffer += event.character
            self.update(f"  {self._buffer}")

    def action_blur(self) -> None:
        self.screen.set_focus(None)

    @property
    def value(self) -> str:
        return self._buffer

    def clear(self) -> None:
        self._buffer = ""
        self.update("")


class ChatPanel(Container):
    """Quick chat for testing inference. Ctrl+C to focus, Enter to send."""

    SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    DEFAULT_CSS = """
    ChatPanel {
        border: solid $success;
        padding: 1;
        layout: vertical;
    }
    .panel-title {
        text-style: bold;
        color: $text-muted;
        padding-bottom: 1;
    }
    #chat-response {
        height: 1fr;
        margin-bottom: 1;
        overflow-y: auto;
    }
    #chat-input-hint {
        color: $text-muted;
        height: 1;
    }
    #chat-input-area:focus {
        background: $surface;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._store = RootStore()
        self._history: list[dict] = []
        self._spinner_idx = 0
        self._spinning = False

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield Static("", id="chat-response")
        yield Static("  Ctrl+C to type · Enter to send · /help for commands", id="chat-input-hint")
        yield ChatInput()

    def on_mount(self) -> None:
        self._chat_input = self.query_one(ChatInput)

    def send_message(self) -> None:
        msg = self._chat_input.value.strip()
        if not msg:
            return
        self._chat_input.clear()

        if msg.startswith("/"):
            self._handle_slash(msg)
            return

        self._history.append({"role": "user", "content": msg})
        self._start_spinner()
        self._do_request(self._history[:])

    def _handle_slash(self, cmd: str) -> None:
        parts = cmd.split()
        verb = parts[0].lower()
        if verb == "/clear":
            self._history.clear()
            self.query_one("#chat-response").update("")
            self.notify("Chat cleared", timeout=2)
        elif verb == "/help":
            self.query_one("#chat-response").update(SLASH_HELP)
        elif verb == "/model":
            host = self._store.config.server_host
            port = self._store.config.server_port
            try:
                resp = json.loads(
                    urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=3).read()
                )
                data = resp.get("data") or []
                name = data[0]["id"].split("/")[-1] if data else "none"
                self.query_one("#chat-response").update(f"Loaded: {name}")
            except Exception:
                self.query_one("#chat-response").update("Server unreachable")
        else:
            self.query_one("#chat-response").update(
                f"Unknown command: {parts[0]}  (try /help)"
            )

    def _start_spinner(self) -> None:
        self._spinner_idx = 0
        self._spinning = True
        self._spin_timer = self.set_interval(0.12, self._tick_spinner)

    def _tick_spinner(self) -> None:
        if self._spinning:
            self.query_one("#chat-response", Static).update(
                f"  {self.SPINNER[self._spinner_idx]} thinking..."
            )
            self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER)

    @work(thread=True)
    def _do_request(self, history: list[dict]) -> str:
        host = self._store.config.server_host
        port = self._store.config.server_port
        start = time.monotonic()
        try:
            body = {
                "messages": history,
                "max_tokens": 400,
                "temperature": 0,
            }
            req = urllib.request.Request(
                f"http://{host}:{port}/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
            content = resp["choices"][0]["message"]["content"]
            elapsed = time.monotonic() - start
            token_count = resp.get("usage", {}).get("completion_tokens", 0)
            tps = token_count / elapsed if elapsed > 0 and token_count else 0
            suffix = f"\n\n[dim]{token_count} tokens · {tps:.1f} t/s · {elapsed:.1f}s[/dim]" if token_count else ""
            return content + suffix, content
        except Exception as e:
            return f"Error: {e}", None

    def on_worker_state_changed(self, event) -> None:
        if event.state != WorkerState.SUCCESS:
            return
        if not hasattr(event.worker, "name") or "_do_request" not in str(event.worker.name):
            return
        self._spinning = False
        if hasattr(self, "_spin_timer"):
            self._spin_timer.stop()
        result = event.worker.result
        if result is None:
            return
        display, raw = result if isinstance(result, tuple) else (result, None)
        if display:
            self.query_one("#chat-response", Static).update(display)
        if raw:
            self._history.append({"role": "assistant", "content": raw})
