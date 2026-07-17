"""Token-Jet ASCII logo widget."""

from textual.widgets import Static

LOGO = """
 ████████╗ ██████╗ ██╗  ██╗ ███████╗ ███╗   ██╗       ██╗███████╗████████╗
 ╚══██╔══╝██╔═══██╗██║ ██╔╝ ██╔════╝ ████╗  ██║       ██║██╔════╝╚══██╔══╝
    ██║   ██║   ██║█████╔╝  █████╗   ██╔██╗ ██║       ██║█████╗     ██║
    ██║   ██║   ██║██╔═██╗  ██╔══╝   ██║╚██╗██║  ██   ██║██╔══╝     ██║
    ██║   ╚██████╔╝██║  ██╗ ███████╗ ██║ ╚████║  ╚█████╔╝███████╗   ██║
    ╚═╝    ╚═════╝ ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═══╝   ╚════╝ ╚══════╝   ╚═╝
                      NVIDIA Jetson Orin Nano — Local Inference
""".strip()


class AsciiLogo(Static):
    """Displays the Token-Jet ASCII logo."""

    def on_mount(self) -> None:
        self.update(LOGO)
