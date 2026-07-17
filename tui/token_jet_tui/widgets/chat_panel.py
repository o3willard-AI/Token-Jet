"""Quick chat panel — type messages to test the loaded model."""

import urllib.request
import json

from textual.widgets import Static
from textual.containers import Container
from textual import events
from textual import work
from textual.worker import WorkerState


class ChatInput(Static):
    """A focusable text input area — plain Static, no built-in styling."""

    can_focus = True
    BINDINGS = [("escape", "blur", "Done")]

    def __init__(self):
        super().__init__("", id="chat-input-area")
        self._buffer = ""

    def on_mount(self) -> None:
        self.update("")

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            panel = self.parent
            if hasattr(panel, "send_message"):
                panel.send_message()
        elif event.key == "backspace":
            self._buffer = self._buffer[:-1]
        elif event.key == "escape":
            self.blur()
            return
        elif event.key == "space":
            self._buffer += " "
        elif event.is_printable and event.character:
            self._buffer += event.character
        else:
            return
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
    """Quick chat for testing. Ctrl+C to focus, type, Enter to send."""

    SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield Static("", id="chat-response")
        yield Static("  Ctrl+C to type, Enter to send", id="chat-input-hint")
        yield ChatInput()

    def on_mount(self) -> None:
        self._chat_input = self.query_one(ChatInput)
        self._spinner_idx = 0
        self._spinning = False

    def send_message(self) -> None:
        msg = self._chat_input.value.strip()
        if not msg:
            return
        self._chat_input.clear()
        self._spinner_idx = 0
        self._spinning = True
        self._spin_timer = self.set_interval(0.15, self._tick_spinner)
        self.run_worker(self._do_request(msg), exclusive=False)

    def _tick_spinner(self) -> None:
        if self._spinning:
            area = self.query_one("#chat-response", Static)
            area.update(f"  {self.SPINNER[self._spinner_idx]} thinking...")
            self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER)

    @work(thread=True)
    def _do_request(self, msg: str) -> str:
        try:
            body = {
                "messages": [{"role": "user", "content": msg}],
                "max_tokens": 300,
                "temperature": 0,
            }
            resp = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}),
                timeout=120).read())
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {e}"

    def on_worker_state_changed(self, event) -> None:
        if event.state == WorkerState.SUCCESS and event.worker.name == "_do_request":
            self._spinning = False
            if hasattr(self, '_spin_timer'):
                self._spin_timer.stop()
            content = event.worker.result
            if content:
                self.query_one("#chat-response", Static).update(content)


CSS = """
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
