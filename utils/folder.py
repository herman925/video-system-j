"""
Folder creation and cover image download utilities.
"""
import re
import requests
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional


# Windows-illegal filename characters
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(name: str) -> str:
    """Strip characters that Windows forbids in folder/file names."""
    return _ILLEGAL.sub("", name).strip(". ")


def _cover_ext(cover_url: str) -> str:
    ext = Path(urlparse(cover_url).path).suffix
    return ext if ext else ".jpg"


def create_video_folder(base_folder: str, folder_name: str) -> Path:
    """
    Create  <base_folder>/<folder_name>/  and return the Path.
    Raises OSError on permission / disk errors.
    """
    folder_path = Path(base_folder) / _safe_name(folder_name)
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path


def download_cover(
    folder_path: Path,
    ref_id: str,
    cover_url: str = "",
) -> Path:
    """
    Save the cover image into *folder_path* as  '<REF> Cover.<ext>'.
    Copies from the shared COVERS_DIR cache when available (no network call).
    Falls back to fetching cover_url if not cached.
    Returns the saved file Path.
    Raises RuntimeError if neither the cache nor a URL is available.
    """
    import shutil
    from utils.covers import cover_path as _cover_path, save_cover_bytes

    # ── Fast path: copy from shared cache ────────────────────────────────────
    cached = _cover_path(ref_id)
    if cached is not None:
        dest = folder_path / f"{ref_id.upper()} Cover{cached.suffix}"
        shutil.copy2(cached, dest)
        print(f"[COVER][folder] ✓ {ref_id} — copied from cache → {dest.name}", flush=True)
        return dest

    # ── Slow path: fetch from URL and populate the cache ─────────────────────
    print(f"[COVER][folder] {ref_id} — cache miss, fetching from URL …", flush=True)
    if not cover_url:
        print(f"[COVER][folder] ✗ {ref_id} — no URL available", flush=True)
        raise RuntimeError(f"No cached cover and no URL for {ref_id}")

    ext  = _cover_ext(cover_url)
    dest = folder_path / f"{ref_id.upper()} Cover{ext}"

    resp = requests.get(
        cover_url,
        headers={
            "Referer":    "https://www.javlibrary.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.content
    dest.write_bytes(raw)
    print(f"[COVER][folder] ✓ {ref_id} — fetched from URL → {dest.name} ({len(raw):,} bytes)", flush=True)

    # Mirror to shared cache so future copies skip the network
    try:
        save_cover_bytes(ref_id, raw, ext)
    except Exception:
        pass

    return dest
