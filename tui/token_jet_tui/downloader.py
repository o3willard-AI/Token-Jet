"""Direct Hugging Face GGUF streaming downloader."""

from __future__ import annotations

import time
import urllib.request
import urllib.error
import urllib.parse
import json
from pathlib import Path

from token_jet_tui.store import RootStore, DownloadProgress

_HEADERS = {"User-Agent": "token-jet-tui/1.0"}


def search_hf_models(query: str) -> list[dict]:
    """Return up to 20 HF repos matching query, sorted by downloads."""
    url = (
        "https://huggingface.co/api/models"
        f"?search={urllib.parse.quote(query)}&filter=gguf&sort=downloads&limit=20"
    )
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        return [{"id": m["modelId"], "downloads": m.get("downloads", 0)} for m in data]
    except Exception as e:
        raise RuntimeError(f"Search failed: {e}") from e


def fetch_gguf_files(repo_id: str) -> list[dict]:
    """Return all GGUF files in a HF repo as [{name, size}], sorted by name."""
    url = f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id, safe='/')}?blobs=true"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        siblings = data.get("siblings", [])
        return sorted(
            [{"name": s["rfilename"], "size": s.get("size", 0)}
             for s in siblings if s["rfilename"].endswith(".gguf")],
            key=lambda x: x["name"],
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {repo_id}: {e}") from e


def stream_download(repo_id: str, filename: str, dest_dir: str) -> None:
    """Stream a GGUF file from HF to dest_dir, writing progress to RootStore."""
    store = RootStore()
    store.reset_download_cancel()

    dest = Path(dest_dir) / Path(filename).name
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    url = (
        f"https://huggingface.co/{urllib.parse.quote(repo_id, safe='/')}"
        f"/resolve/main/{urllib.parse.quote(filename, safe='/')}"
    )
    req = urllib.request.Request(url, headers=_HEADERS)

    try:
        resp = urllib.request.urlopen(req, timeout=store.config.hf_download_timeout)
        total = int(resp.headers.get("Content-Length", 0))
        received = 0
        start = time.monotonic()
        last_update = start
        chunk_size = 512 * 1024  # 512 KB

        with open(dest, "wb") as f:
            while True:
                if store.download_cancelled:
                    dest.unlink(missing_ok=True)
                    store.download_progress.value = DownloadProgress(
                        filename=filename, bytes_received=received,
                        total_bytes=total, speed_bps=0,
                        elapsed=time.monotonic() - start, cancelled=True,
                    )
                    return

                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)

                now = time.monotonic()
                if now - last_update >= 0.5:
                    elapsed = now - start
                    speed = received / elapsed if elapsed > 0 else 0
                    store.download_progress.value = DownloadProgress(
                        filename=filename, bytes_received=received,
                        total_bytes=total, speed_bps=speed, elapsed=elapsed,
                    )
                    last_update = now

        elapsed = time.monotonic() - start
        store.download_progress.value = DownloadProgress(
            filename=filename, bytes_received=received,
            total_bytes=total,
            speed_bps=received / elapsed if elapsed > 0 else 0,
            elapsed=elapsed,
        )

    except Exception as e:
        dest.unlink(missing_ok=True)
        store.download_progress.value = DownloadProgress(
            filename=filename, bytes_received=0, total_bytes=0,
            speed_bps=0, elapsed=0, error=str(e),
        )
        raise
