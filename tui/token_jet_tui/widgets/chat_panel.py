"""Quick chat panel — send a message to test the loaded model."""

from textual.widgets import Static, Input
from textual.containers import Container


class ChatPanel(Container):
    """Quick chat for testing. Ctrl+C to focus, Enter to send."""

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield Static("", id="chat-response")
        yield Input(placeholder="Type a message, Enter to send...", id="chat-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.send_message()

    def send_message(self) -> None:
        inp = self.query_one("#chat-input", Input)
        msg = inp.value.strip()
        if not msg:
            return
        inp.value = ""
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
#chat-input {
    height: 3;
    border: none;
}
#chat-input:focus {
    border: none;
}
"""
