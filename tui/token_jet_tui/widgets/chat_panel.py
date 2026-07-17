"""Quick chat panel — send a message to the loaded model for testing."""

from textual.widgets import Static, Input, Button
from textual.containers import Container, Horizontal, Vertical


class ChatPanel(Container):
    """Quick chat for testing the loaded model."""

    def compose(self):
        yield Static("QUICK CHAT", classes="panel-title")
        yield Static("Send a message to test the active model.", id="chat-response")
        yield Horizontal(
            Input(placeholder="Type a message...", id="chat-input"),
            Button("Send", id="btn-send", variant="primary"),
            id="chat-row"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-send":
            self.send_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.send_message()

    def send_message(self) -> None:
        """Send the input text to the inference server and display response."""
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
                "max_tokens": 200,
                "temperature": 0,
            }
            resp = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}),
                timeout=60).read())
            content = resp["choices"][0]["message"]["content"]
            self.query_one("#chat-response", Static).update(content)
        except Exception as e:
            self.query_one("#chat-response", Static).update(f"Error: {e}")


CSS = """
ChatPanel {
    border: solid $success;
    padding: 1;
    height: 1fr;
}
.panel-title {
    text-style: bold;
    color: $text-muted;
    padding-bottom: 1;
}
#chat-response {
    height: 1fr;
    margin-bottom: 1;
}
#chat-row {
    height: auto;
}
#chat-input {
    width: 1fr;
}
"""
