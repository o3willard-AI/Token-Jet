"""Quick chat panel — send a message to test the loaded model."""

from textual.widgets import Static
from textual.containers import Container
from textual import events


class ChatInput(Static):
    """A plain text area for typing messages — no Input widget styling."""

    def __init__(self):
        super().__init__("", id="chat-input-area")
        self._buffer = ""

    def on_mount(self) -> None:
        self.update("")

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            self.app.query_one(ChatPanel).send_message()
        elif event.key == "backspace":
            self._buffer = self._buffer[:-1]
            self.update(f"  {self._buffer}")
        elif len(event.key) == 1 and event.is_printable:
            self._buffer += event.key
            self.update(f"  {self._buffer}")

    @property
    def value(self) -> str:
        return self._buffer

    def clear(self) -> None:
        self._buffer = ""
        self.update("")


class ChatPanel(Container):
    """Quick chat for testing. Ctrl+C to focus, Enter to send."""

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield Static("", id="chat-response")
        yield Static("  Type a message, Enter to send...", id="chat-input-hint")
        yield ChatInput()

    def on_mount(self) -> None:
        self._chat_input = self.query_one(ChatInput)

    def send_message(self) -> None:
        msg = self._chat_input.value.strip()
        if not msg:
            return
        self._chat_input.clear()
        self.query_one("#chat-response", Static).update("Thinking...")
        
        try:
            import urllib.request, json
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
            content = resp["choices"][0]["message"]["content"]
            self.query_one("#chat-response", Static).update(content)
        except Exception as e:
            self.query_one("#chat-response", Static).update(f"Error: {e}")


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
#chat-input-area {
    height: 3;
}
"""
