"""Direct Hugging Face GGUF streaming downloader."""

from __future__ import annotations

import hashlib
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
    """Return all GGUF files in a HF repo as [{name, size, sha256}], sorted by name.

    sha256 is the Git LFS SHA-256 from HuggingFace metadata, or None if unavailable.
    """
    url = f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id, safe='/')}?blobs=true"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        siblings = data.get("siblings", [])
        files = []
        for s in siblings:
            if not s["rfilename"].endswith(".gguf"):
                continue
            sha256 = None
            lfs = s.get("lfs")
            if lfs:
                sha256 = lfs.get("sha256")
            if not sha256:
                oid = s.get("oid", "")
                if oid.startswith("sha256:"):
                    sha256 = oid[7:]
            size = s.get("size") or (lfs.get("size") if lfs else None) or 0
            files.append({"name": s["rfilename"], "size": size, "sha256": sha256})
        return sorted(files, key=lambda x: x["name"])
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {repo_id}: {e}") from e


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file, reading in 1 MB chunks to limit memory use."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stream_download(
    repo_id: str,
    filename: str,
    dest_dir: str,
    expected_sha256: str | None = None,
) -> None:
    """Stream a GGUF file from HF to dest_dir, writing progress to RootStore.

    Validates that the received byte count matches Content-Length, then verifies
    the SHA-256 hash against expected_sha256 (from HuggingFace LFS metadata) when
    available. Deletes the destination file and raises on any failure.
    """
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
        speed = received / elapsed if elapsed > 0 else 0

        # Validate completeness before touching the file further.
        if total > 0 and received < total:
            dest.unlink(missing_ok=True)
            err = f"Incomplete download: received {received:,} of {total:,} bytes"
            store.download_progress.value = DownloadProgress(
                filename=filename, bytes_received=received, total_bytes=total,
                speed_bps=0, elapsed=elapsed, error=err,
            )
            raise RuntimeError(err)

        # SHA-256 integrity check.
        if expected_sha256:
            store.download_progress.value = DownloadProgress(
                filename=filename, bytes_received=received, total_bytes=total,
                speed_bps=speed, elapsed=elapsed, verifying=True,
            )
            actual = _sha256_file(dest)
            if actual != expected_sha256.lower():
                dest.unlink(missing_ok=True)
                err = "Checksum mismatch — file may be corrupt or tampered with"
                store.download_progress.value = DownloadProgress(
                    filename=filename, bytes_received=received, total_bytes=total,
                    speed_bps=0, elapsed=elapsed, error=err,
                )
                raise RuntimeError(err)

        store.download_progress.value = DownloadProgress(
            filename=filename, bytes_received=received,
            total_bytes=total,
            speed_bps=speed,
            elapsed=elapsed,
        )

    except Exception as e:
        dest.unlink(missing_ok=True)
        # Only overwrite progress if no specific error was already recorded above.
        current = store.download_progress.value
        if not (current and current.error):
            store.download_progress.value = DownloadProgress(
                filename=filename, bytes_received=0, total_bytes=0,
                speed_bps=0, elapsed=0, error=str(e),
            )
        raise
