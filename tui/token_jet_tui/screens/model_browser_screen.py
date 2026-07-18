"""Model browser — search Hugging Face and download GGUF files to ~/models/."""

from __future__ import annotations

import logging

from textual import events
from textual.screen import ModalScreen
from textual.widgets import Static, ListView, ListItem, Input
from textual.containers import Container
from textual import work

from token_jet_tui.store import RootStore, DownloadProgress
from token_jet_tui import downloader

log = logging.getLogger(__name__)


class _SilentListView(ListView):
    """ListView with Enter suppressed — parent Screen handles selection."""

    def action_select_cursor(self) -> None:
        pass


class ModelBrowserScreen(ModalScreen):
    """Two-step flow: search HF repos → pick a GGUF variant → download."""

    DEFAULT_CSS = """
    ModelBrowserScreen {
        align: center middle;
    }
    #browser-dialog {
        border: solid $primary;
        background: $surface;
        padding: 1 2;
        width: 74;
        height: 26;
    }
    #browser-title {
        text-style: bold;
        padding-bottom: 1;
    }
    #search-input {
        width: 100%;
        margin-bottom: 1;
    }
    #result-list {
        height: 1fr;
    }
    #browser-status {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    #dl-progress {
        color: $success;
        height: 1;
    }
    #browser-hint {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._store = RootStore()
        self._mode = "search"
        self._repos: list[dict] = []
        self._files: list[dict] = []
        self._selected_repo = ""
        self._downloading = False
        self._progress_watcher = self._on_progress

    def compose(self):
        with Container(id="browser-dialog"):
            yield Static("Model Browser — Search Hugging Face", id="browser-title")
            yield Input(
                placeholder='Search: e.g. "bartowski qwen"  or  "org/repo-id"',
                id="search-input",
            )
            yield _SilentListView(id="result-list")
            yield Static("", id="browser-status")
            yield Static("", id="dl-progress")
            yield Static(
                "Type a query and press Enter to search",
                id="browser-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#search-input").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        log.debug("ModelBrowserScreen: input submitted %r (downloading=%s)",
                  query, self._downloading)
        if not query or self._downloading:
            return
        if "/" in query:
            self._load_repo_files(query)
        else:
            self._do_search(query)

    # ── Search ────────────────────────────────────────────────────────────────

    @work(thread=True, name="browser_search", exit_on_error=False)
    def _do_search(self, query: str) -> None:
        log.debug("_do_search: %r", query)
        self.app.call_from_thread(
            lambda: self.query_one("#browser-status").update(f"Searching for '{query}'...")
        )
        try:
            results = downloader.search_hf_models(query)
            self._repos = results
            log.debug("_do_search: %d results", len(results))
            self.app.call_from_thread(self._populate_repos)
        except Exception:
            log.exception("_do_search: failed")
            self.app.call_from_thread(
                lambda: self.query_one("#browser-status").update("Search failed — check network")
            )

    def _populate_repos(self) -> None:
        lv = self.query_one("#result-list", _SilentListView)
        lv.clear()
        if not self._repos:
            self.query_one("#browser-status").update("No results — try a different query")
            return
        for r in self._repos:
            dl = r.get("downloads", 0)
            dl_str = f"{dl // 1000}k" if dl >= 1000 else str(dl)
            lv.append(ListItem(Static(f"{r['id']}  ↓{dl_str}")))
        self._mode = "search"
        self.query_one("#browser-status").update(
            f"{len(self._repos)} repos found"
        )
        self.query_one("#browser-hint").update("↑↓ to navigate · Enter: browse files · Esc: cancel")
        lv.focus()

    # ── File listing ──────────────────────────────────────────────────────────

    @work(thread=True, name="browser_files", exit_on_error=False)
    def _load_repo_files(self, repo_id: str) -> None:
        log.debug("_load_repo_files: %r", repo_id)
        self._selected_repo = repo_id
        self.app.call_from_thread(
            lambda: self.query_one("#browser-status").update(f"Loading files from {repo_id}...")
        )
        try:
            files = downloader.fetch_gguf_files(repo_id)
            self._files = files
            log.debug("_load_repo_files: %d files", len(files))
            self.app.call_from_thread(self._populate_files)
        except Exception:
            log.exception("_load_repo_files: failed")
            self.app.call_from_thread(
                lambda: self.query_one("#browser-status").update(f"Error loading {repo_id}")
            )

    def _populate_files(self) -> None:
        lv = self.query_one("#result-list", _SilentListView)
        lv.clear()
        if not self._files:
            self.query_one("#browser-status").update("No GGUF files found in this repo")
            return
        for f in self._files:
            size_gb = f["size"] / (1024 ** 3) if f["size"] else 0
            size_str = (
                f"{size_gb:.1f} GB" if size_gb >= 0.1
                else f"{f['size'] // 1024 // 1024} MB"
            )
            lv.append(ListItem(Static(f"{f['name']}  ({size_str})")))
        self._mode = "files"
        self.query_one("#browser-status").update(
            f"{len(self._files)} GGUF files in {self._selected_repo}"
        )
        self.query_one("#browser-hint").update("↑↓ to navigate · Enter: download · Esc: back")
        lv.focus()

    # ── Download ──────────────────────────────────────────────────────────────

    def _begin_download(self, filename: str) -> None:
        log.debug("_begin_download: %r", filename)
        self._downloading = True
        self._store.download_progress.watch(self._progress_watcher)
        self.query_one("#browser-status").update(f"Starting: {filename}")
        self.query_one("#browser-hint").update("Downloading… Esc to cancel")
        self._run_download(filename)

    @work(thread=True, name="browser_download", exit_on_error=False)
    def _run_download(self, filename: str) -> None:
        try:
            downloader.stream_download(
                self._selected_repo, filename, self._store.config.model_dir
            )
        except Exception:
            log.exception("_run_download: failed")

    def _on_progress(self, progress: DownloadProgress | None) -> None:
        if progress is None:
            return
        try:
            self.app.call_from_thread(self._render_progress, progress)
        except Exception:
            log.exception("_on_progress: call_from_thread failed")

    def _render_progress(self, p: DownloadProgress) -> None:
        if not self.is_mounted:
            return
        if p.error:
            self.query_one("#dl-progress").update(f"[red]Error: {p.error}[/red]")
            self._finish_download()
            return
        if p.cancelled:
            self.query_one("#dl-progress").update("[yellow]Cancelled[/yellow]")
            self._finish_download()
            return
        if p.done:
            mb = p.total_bytes / (1024 * 1024)
            self.query_one("#dl-progress").update(
                f"[green]Done! {mb:.0f} MB — model ready[/green]"
            )
            self.query_one("#browser-status").update(
                "Model saved to ~/models/  — Esc to close"
            )
            self._finish_download()
            return

        bar_len = 28
        filled = int(bar_len * p.pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        mb_r = p.bytes_received / (1024 * 1024)
        mb_t = p.total_bytes / (1024 * 1024)
        self.query_one("#dl-progress").update(
            f"{bar} {p.pct:.0f}%  {mb_r:.0f}/{mb_t:.0f} MB  {p.speed_mb:.1f} MB/s"
        )

    def _finish_download(self) -> None:
        self._downloading = False
        self._store.download_progress.unwatch(self._progress_watcher)

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        log.debug("ModelBrowserScreen.on_key: key=%r mode=%s downloading=%s",
                  event.key, self._mode, self._downloading)
        if event.key == "escape":
            if self._downloading:
                self._store.cancel_download()
            elif self._mode == "files":
                self._mode = "search"
                self._populate_repos()
                self.query_one("#search-input").focus()
            else:
                self.dismiss(None)
        elif event.key == "enter" and not self._downloading:
            try:
                lv = self.query_one("#result-list", _SilentListView)
            except Exception:
                return
            idx = lv.index
            log.debug("ModelBrowserScreen Enter: mode=%s idx=%s", self._mode, idx)
            if idx is None:
                return
            if self._mode == "search" and idx < len(self._repos):
                self._load_repo_files(self._repos[idx]["id"])
            elif self._mode == "files" and idx < len(self._files):
                self._begin_download(self._files[idx]["name"])
