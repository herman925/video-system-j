"""Shared ref lifecycle cleanup helpers.

The tracker and downloader both reference the same JAV ref IDs. Covers and
cached metadata should persist while either module still references a ref, and
should be removed only after the last reference disappears.
"""

from __future__ import annotations

from tracker.store import delete_shared_video_refs, load_tracker
from utils.covers import delete_cover
from utils.downloader_store import load_downloader_queue, remove_downloader_refs


def _normalize_refs(refs: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    return {str(ref).strip().upper() for ref in refs if str(ref).strip()}


def get_tracker_refs() -> set[str]:
    data = load_tracker()
    out: set[str] = set()
    for actress in data.get("actresses", {}).values():
        for video in actress.get("videos", []):
            ref = str(video.get("ref", "")).strip().upper()
            if ref:
                out.add(ref)
    return out


def get_downloader_refs(user_storage) -> set[str]:
    out: set[str] = set()
    for item in load_downloader_queue():
        ref = str(item.get("kw", "")).strip().upper()
        if ref:
            out.add(ref)
    return out


def prune_orphaned_refs(user_storage, refs: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    """Remove shared cache artifacts for refs no longer referenced anywhere."""
    refs_to_check = _normalize_refs(refs)
    if not refs_to_check:
        return set()

    live_refs = get_tracker_refs() | get_downloader_refs(user_storage)
    removed: set[str] = set()
    for ref in refs_to_check:
        if ref in live_refs:
            continue
        delete_cover(ref)
        removed.add(ref)

    if removed:
        delete_shared_video_refs(removed)
        remove_downloader_refs(removed)

    return removed