"""
Shared cover image cache.

Covers are stored at COVERS_DIR/{REF} Cover{ext} and shared between the
JAV Video System (main queue) and the Actress Tracker.  The extension is
preserved from the source (e.g. .jpg, .webp, .png).

Public API
----------
cover_path(ref)                   -> Path | None   (None = not cached)
cover_exists(ref)                 -> bool
save_cover_bytes(ref, data, ext)  -> Path  (creates COVERS_DIR if needed)
fetch_and_cache_cover(ref)        -> bool  (async; uses configured scraper)
"""

from pathlib import Path
from typing import Optional

from utils.paths import COVERS_DIR
from utils.metadata import fetch_jav_metadata, resolve_metadata_source


def cover_path(ref: str) -> Optional[Path]:
    """
    Return the Path to the cached cover for *ref*, or None if not cached.
    Uses a glob so the extension doesn't need to be known in advance.
    """
    if not COVERS_DIR.exists():
        return None
    matches = list(COVERS_DIR.glob(f"{ref.upper()} Cover.*"))
    return matches[0] if matches else None


def cover_exists(ref: str) -> bool:
    return cover_path(ref) is not None


def delete_cover(ref: str) -> bool:
    """
    Delete any cached cover file(s) for *ref* (all extensions).
    Returns True if at least one file was removed.
    Used by deep-fetch so stale covers with a different extension don't persist.
    """
    if not COVERS_DIR.exists():
        return False
    deleted = False
    for p in list(COVERS_DIR.glob(f"{ref.upper()} Cover.*")):
        try:
            p.unlink()
            deleted = True
            print(f"[COVER] Deleted stale cover: {p.name}", flush=True)
        except Exception as _e:
            print(f"[COVER] Could not delete {p.name}: {_e}", flush=True)
    return deleted


def keep_latest_cover(ref: str) -> None:
    """
    If more than one cover file exists for *ref*, delete all but the
    most recently modified one.  Called after a deep-fetch scrape to
    handle races where both primary and fallback scrapers (or a
    background cover-queue task) each wrote a file with a different
    extension before the other could finish.
    """
    if not COVERS_DIR.exists():
        return
    matches = list(COVERS_DIR.glob(f"{ref.upper()} Cover.*"))
    if len(matches) <= 1:
        return
    # Sort newest first (highest mtime)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in matches[1:]:
        try:
            stale.unlink()
            print(f"[COVER] Removed duplicate cover: {stale.name}", flush=True)
        except Exception as _e:
            print(f"[COVER] Could not remove {stale.name}: {_e}", flush=True)


def save_cover_bytes(ref: str, data: bytes, ext: str = ".jpg") -> Path:
    """Write raw image bytes to the shared cache with the given extension."""
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    p = COVERS_DIR / f"{ref.upper()} Cover{ext}"
    p.write_bytes(data)
    return p


async def fetch_and_cache_cover(ref: str, source: str | None = None) -> tuple[bool, dict | None]:
    """
    Fetch a cover for *ref* using the currently configured metadata source,
    then save it to the shared cache.

    The scraper itself writes to COVERS_DIR directly during the search, so
    after the scrape we simply check whether the file landed there.

    Returns (cover_ok, meta):
        cover_ok – True if a cover is now cached, False on failure.
                   Skips the network call if the cover is already cached
                   (returns True, None in that case).
        meta     – full metadata dict from the scraper if available,
                   None if the cover was already cached or scrape failed.
    """
    if cover_exists(ref):
        return True, None

    source = resolve_metadata_source(source)

    print(f"[COVER][tracker] Fetching cover for {ref} via {source} …", flush=True)
    meta: dict | None = None
    try:
        meta = await fetch_jav_metadata(ref, source=source)
    except Exception as _e:
        print(f"[COVER][tracker] ✗ Scrape failed for {ref}: {_e}", flush=True)
        meta = None

    result = cover_exists(ref)
    if result:
        p = cover_path(ref)
        print(f"[COVER][tracker] ✓ {ref} cached → {p.name if p else '?'}", flush=True)
    else:
        print(f"[COVER][tracker] ✗ {ref} — no cover after scrape", flush=True)
    return result, (meta if isinstance(meta, dict) and meta else None)


def get_cover_source() -> str:
    """Return the configured metadata source used for cover fetching ('javdb' or 'javlibrary')."""
    try:
        return resolve_metadata_source()
    except Exception:
        return "javdb"
