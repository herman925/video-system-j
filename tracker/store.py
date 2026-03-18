"""
Actress Tracker — persistent data layer.

tracker.json lives at DATA_DIR / "tracker.json".
Schema: { "actresses": { "<actress_id>": ActressDict } }

actress_id is the value of the ?s= query parameter from the JAVLibrary actress URL,
e.g. "aadd6" from "https://www.javlibrary.com/tw/vl_star.php?s=aadd6".
"""
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from calendar import monthrange
from datetime import date as _date_cls, datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

from translator.llm import load_config
from utils.paths import TRACKER_FILE
from utils.save_state import tracked_save_state

# ── URL helpers ────────────────────────────────────────────────────────────────

def actress_id_from_url(url: str) -> Optional[str]:
    """Extract the ?s= param from a javlibrary actress URL. Returns None if absent."""
    qs = parse_qs(urlparse(url).query)
    ids = qs.get("s", [])
    return ids[0] if ids else None


# ── Load / Save ────────────────────────────────────────────────────────────────

def _migrate_to_normalized(data: dict) -> bool:
    """
    One-time migration: move shared video fields (title, date, cover_url, _meta)
    from per-actress video entries into the top-level data["videos"] dict.
    Idempotent — safe to call on already-migrated data.
    Returns True if any fields were actually moved.
    """
    if "videos" not in data:
        data["videos"] = {}
    vd = data["videos"]
    migrated = False

    for actress in data.get("actresses", {}).values():
        for v in actress.get("videos", []):
            ref = str(v.get("ref", "")).strip().upper()
            if not ref:
                continue
            ventry = vd.setdefault(ref, {})
            # Move each shared field once; first actress wins on conflicts.
            for field in ("title", "date", "cover_url"):
                if field in v:
                    if not ventry.get(field):
                        ventry[field] = v.pop(field)
                    else:
                        v.pop(field)
                    migrated = True
            if "_meta" in v:
                raw_meta = v.pop("_meta")
                migrated = True
                if raw_meta and not ventry.get("_meta"):
                    ventry["_meta"] = raw_meta
                    # promote title/date from _meta if still missing
                    if raw_meta.get("title") and not ventry.get("title"):
                        ventry["title"] = raw_meta["title"]
                    if raw_meta.get("date") and not ventry.get("date"):
                        ventry["date"] = raw_meta["date"]
    return migrated


_tracker_cache: "dict | None" = None
_tracker_cache_mtime: float = -1.0


def load_tracker() -> dict:
    """Load tracker.json. Returns empty structure on missing or corrupt file.

    Results are cached in-memory and validated against the file's mtime so that
    repeated calls within the same event-loop tick (e.g. _rebuild_left_list +
    _refresh_right_panel) hit RAM instead of disk.
    """
    global _tracker_cache, _tracker_cache_mtime

    try:
        mtime = TRACKER_FILE.stat().st_mtime
    except FileNotFoundError:
        return {"actresses": {}, "videos": {}}

    if _tracker_cache is not None and mtime == _tracker_cache_mtime:
        return _tracker_cache

    last_data_error: json.JSONDecodeError | None = None
    for attempt in range(3):
        try:
            data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
            if _migrate_to_normalized(data):
                try:
                    save_tracker(data)
                    # save_tracker updated the cache; return it directly.
                    return _tracker_cache  # type: ignore[return-value]
                except Exception:
                    pass
            _tracker_cache = data
            _tracker_cache_mtime = mtime
            return data
        except FileNotFoundError:
            return {"actresses": {}, "videos": {}}
        except json.JSONDecodeError as exc:
            last_data_error = exc
            if attempt < 2:
                time.sleep(0.05)
    if last_data_error is not None:
        return {"actresses": {}, "videos": {}}
    return {"actresses": {}, "videos": {}}


def save_tracker(data: dict) -> None:
    """Write tracker.json atomically so readers never see a partial file."""
    global _tracker_cache, _tracker_cache_mtime

    with tracked_save_state("tracker"):
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=f"{TRACKER_FILE.stem}.",
            suffix=".tmp",
            dir=str(TRACKER_FILE.parent),
            text=True,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                # os.fsync omitted intentionally — blocks the asyncio event loop
                # on Windows (100-500 ms per call), causing WebSocket heartbeat
                # failures and page reloads during batch operations.
                # os.replace is already atomic at the OS level.
            os.replace(tmp_path, TRACKER_FILE)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        _tracker_cache = data
        try:
            _tracker_cache_mtime = TRACKER_FILE.stat().st_mtime
        except OSError:
            _tracker_cache_mtime = -1.0


# ── Sort cache ─────────────────────────────────────────────────────────────────

def sort_fingerprint(actresses: dict) -> str:
    """Stable MD5 of all (id, name) pairs — changes only when an actress is added/removed/renamed."""
    pairs = sorted((aid, a.get("name") or aid) for aid, a in actresses.items())
    return hashlib.md5(json.dumps(pairs, ensure_ascii=False).encode()).hexdigest()


# ── Actress management ─────────────────────────────────────────────────────────

def add_actress(url: str) -> Optional[str]:
    """
    Register an actress URL. Idempotent — safe to call twice with the same URL.
    Returns actress_id on success, None if URL has no valid ?s= param.
    """
    actress_id = actress_id_from_url(url)
    if not actress_id:
        return None
    data = load_tracker()
    if actress_id not in data["actresses"]:
        inactive_status = _build_inactive_status([], {})
        data["actresses"][actress_id] = {
            "url": url,
            "name": "",
            "added_at": datetime.now(timezone.utc).isoformat(),
            "last_scraped": None,
            "videos": [],
            "inactive": inactive_status["inactive"],
            "inactive_reason": inactive_status["inactive_reason"],
            "inactive_last_solo": inactive_status["inactive_last_solo"],
        }
        save_tracker(data)
    return actress_id


def delete_actress(actress_id: str) -> set[str]:
    data = load_tracker()
    actress = data["actresses"].pop(actress_id, None)
    save_tracker(data)
    if not actress:
        return set()
    return {
        str(video.get("ref", "")).strip().upper()
        for video in actress.get("videos", [])
        if str(video.get("ref", "")).strip()
    }


def delete_video_from_actress(actress_id: str, ref: str) -> bool:
    """Remove a single ref from one actress entry, preserving shared data until pruned."""
    ref_up = str(ref or "").strip().upper()
    if not ref_up:
        return False

    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if actress is None:
        return False

    videos = actress.get("videos", [])
    kept = [
        video
        for video in videos
        if str(video.get("ref", "")).strip().upper() != ref_up
    ]
    if len(kept) == len(videos):
        return False

    actress["videos"] = kept
    _apply_inactive_status(actress, data.get("videos", {}))
    save_tracker(data)
    return True


def update_actress_rating(actress_id: str, rating: "int | None") -> None:
    """
    Set the 0-100 score for an actress, or None to clear it.
    Clamps the value to [0, 100] if an integer is provided.
    """
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if actress is None:
        return
    if rating is not None:
        rating = max(0, min(100, int(rating)))
    actress["rating"] = rating
    save_tracker(data)


def migrate_ratings_to_score() -> int:
    """
    One-time migration: remove old float star ratings (0.0–5.0) from tracker.json.
    Returns the number of entries cleared.
    """
    data = load_tracker()
    changed = 0
    for actress in data["actresses"].values():
        r = actress.get("rating")
        if r is not None and not isinstance(r, int):
            # Old star rating was a float like 3.5 — remove it entirely
            actress["rating"] = None
            changed += 1
    if changed:
        save_tracker(data)
    return changed


def rename_actress(actress_id: str, new_name: str) -> None:
    """Update the display name for a tracked actress."""
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if actress is None:
        return
    actress["name"] = new_name.strip()
    save_tracker(data)


# ── Video management ───────────────────────────────────────────────────────────

def update_actress_videos(actress_id: str, name: str, videos: list[dict]) -> None:
    """
    Merge a freshly-scraped video list into the stored actress entry.
    Preserves existing 'seen' and 'downloaded' flags by ref.
    Shared fields (title, date, cover_url) from each incoming video are written
    to data["videos"][ref] and stripped from the per-actress entry.
    """
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if actress is None:
        return

    if "videos" not in data:
        data["videos"] = {}
    vd = data["videos"]

    existing_seen: dict[str, bool] = {
        v["ref"].upper(): v.get("seen", False)
        for v in actress.get("videos", [])
    }
    existing_dl: dict[str, bool] = {
        v["ref"].upper(): v.get("downloaded", False)
        for v in actress.get("videos", [])
    }

    merged: list[dict] = []
    for v in videos:
        ref_orig = str(v.get("ref", "")).strip()
        ref_up = ref_orig.upper()
        if not ref_up:
            continue
        # Write shared fields to top-level dict (don't overwrite deep-fetch data)
        ventry = vd.setdefault(ref_up, {})
        if v.get("title") and not (ventry.get("_meta", {}) or {}).get("title"):
            ventry["title"] = v["title"]
        if v.get("date"):
            ventry["date"] = v["date"]
        if v.get("cover_url") and not ventry.get("cover_url"):
            ventry["cover_url"] = v["cover_url"]
        # Per-actress entry: only identity + personal state
        per = {"ref": ref_orig, "seen": existing_seen.get(ref_up, False)}
        if existing_dl.get(ref_up):
            per["downloaded"] = True
        merged.append(per)

    actress["name"] = name or actress.get("name", "")
    actress["videos"] = merged
    actress["last_scraped"] = datetime.now(timezone.utc).isoformat()
    _apply_inactive_status(actress, vd)
    save_tracker(data)


def mark_seen(actress_id: str, refs: list[str]) -> None:
    """Mark specific refs as seen for one actress."""
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if not actress:
        return
    ref_set = {r.upper() for r in refs}
    changed = False
    for v in actress["videos"]:
        if v["ref"].upper() in ref_set and not v.get("seen"):
            v["seen"] = True
            changed = True
    if changed:
        save_tracker(data)


def mark_all_seen(actress_id: str) -> None:
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if not actress:
        return
    for v in actress["videos"]:
        v["seen"] = True
    save_tracker(data)


def save_pagination_state(
    actress_id: str,
    pages_loaded: int,
    next_page: "int | None",
    has_more: bool,
    total_pages: "int | None" = None,
    fetched_pages: "list[int] | None" = None,
) -> None:
    """Persist pagination state to tracker.json so it survives app restarts."""
    data = load_tracker()
    actress = data["actresses"].get(actress_id)
    if actress is None:
        return
    actress["pages_loaded"] = pages_loaded
    actress["next_page"] = next_page
    actress["has_more"] = has_more
    if total_pages is not None:
        actress["total_pages"] = max(1, int(total_pages))
    elif "total_pages" not in actress:
        actress["total_pages"] = None
    if fetched_pages is not None:
        actress["fetched_pages"] = sorted(
            {
                max(1, int(page))
                for page in fetched_pages
                if str(page).strip()
            }
        )
    elif "fetched_pages" not in actress:
        actress["fetched_pages"] = []
    save_tracker(data)


def mark_ref_seen_globally(ref: str) -> None:
    """
    Called when a ref is added to the downloader queue from any source.
    Marks the ref as seen across all tracked actresses.
    """
    ref = ref.upper()
    data = load_tracker()
    changed = False
    for actress in data["actresses"].values():
        for v in actress["videos"]:
            if v["ref"].upper() == ref and not v.get("seen"):
                v["seen"] = True
                changed = True
    if changed:
        save_tracker(data)


def save_video_meta(actress_id: str, ref: str, meta: dict) -> None:
    """
    Persist deep-fetched JAV metadata into the shared top-level videos dict.
    actress_id is kept for API compatibility but is no longer used to target
    a specific actress entry — the data is now stored once, keyed by ref.
    Recalculates inactive status for every actress that has this ref.
    """
    data = load_tracker()
    if "videos" not in data:
        data["videos"] = {}
    ref_up = ref.upper()
    ventry = data["videos"].setdefault(ref_up, {})
    ventry["_meta"] = {
        "actresses": meta.get("actresses", []),
        "studio":    meta.get("studio", ""),
        "genres":    meta.get("genres", []),
        "title":     meta.get("title", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if meta.get("title"):
        ventry["title"] = meta["title"]
    if meta.get("date"):
        ventry["date"] = meta["date"]

    vd = data["videos"]
    for actress in data["actresses"].values():
        if any(v.get("ref", "").upper() == ref_up for v in actress.get("videos", [])):
            _apply_inactive_status(actress, vd)
    save_tracker(data)


def delete_shared_video_refs(refs: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    """Remove orphaned shared video metadata entries from tracker.json."""
    normalized = {
        str(ref).strip().upper()
        for ref in refs
        if str(ref).strip()
    }
    if not normalized:
        return set()

    data = load_tracker()
    videos = data.get("videos", {})
    removed: set[str] = set()
    for ref in normalized:
        if ref in videos:
            videos.pop(ref, None)
            removed.add(ref)

    if removed:
        save_tracker(data)
    return removed


def record_deleted_ref(actress_id: "str | None", ref: str, *, globally: bool = False) -> None:
    """Record a ref as manually deleted so it is skipped in future scrapes."""
    ref_up = str(ref or "").strip().upper()
    if not ref_up:
        return
    data = load_tracker()
    if globally:
        deleted = set(data.get("globally_deleted_refs", []))
        deleted.add(ref_up)
        data["globally_deleted_refs"] = sorted(deleted)
    else:
        if actress_id:
            actress = data["actresses"].get(actress_id)
            if actress is not None:
                deleted = set(actress.get("deleted_refs", []))
                deleted.add(ref_up)
                actress["deleted_refs"] = sorted(deleted)
    save_tracker(data)


def remove_from_deleted_refs(ref: str) -> None:
    """Remove a ref from all deleted lists (per-actress and global) — i.e., reacquire it."""
    ref_up = str(ref or "").strip().upper()
    if not ref_up:
        return
    data = load_tracker()
    changed = False
    global_list = data.get("globally_deleted_refs", [])
    if ref_up in global_list:
        data["globally_deleted_refs"] = [r for r in global_list if r != ref_up]
        changed = True
    for actress in data.get("actresses", {}).values():
        per = actress.get("deleted_refs", [])
        if ref_up in per:
            actress["deleted_refs"] = [r for r in per if r != ref_up]
            changed = True
    if changed:
        save_tracker(data)


def get_deleted_refs_for_actress(actress_id: str) -> set[str]:
    """Return all refs skipped for this actress: per-actress deleted + globally deleted."""
    data = load_tracker()
    actress = data["actresses"].get(actress_id, {})
    return set(actress.get("deleted_refs", [])) | set(data.get("globally_deleted_refs", []))


def get_all_deleted_refs() -> set[str]:
    """Return every deleted ref across all actresses and the global list."""
    data = load_tracker()
    out: set[str] = set(data.get("globally_deleted_refs", []))
    for actress in data.get("actresses", {}).values():
        out.update(actress.get("deleted_refs", []))
    return out


def mark_ref_downloaded_globally(ref: str, downloaded: bool = True) -> None:
    """
    Mark (or unmark) a ref as downloaded across all tracked actresses.
    Called when the downloader toggles the downloaded state for a keyword.
    """
    ref = ref.upper()
    data = load_tracker()
    changed = False
    for actress in data["actresses"].values():
        for v in actress["videos"]:
            if v["ref"].upper() == ref:
                current = v.get("downloaded", False)
                if current != downloaded:
                    v["downloaded"] = downloaded
                    if downloaded:
                        v["seen"] = True  # downloaded implies seen
                    changed = True
    if changed:
        save_tracker(data)


def is_ref_downloaded_globally(ref: str) -> bool:
    """Return True when any tracked instance of ref is marked downloaded."""
    ref_up = str(ref or "").strip().upper()
    if not ref_up:
        return False

    data = load_tracker()
    for actress in data.get("actresses", {}).values():
        for video in actress.get("videos", []):
            if str(video.get("ref", "")).strip().upper() == ref_up:
                return bool(video.get("downloaded", False))
    return False


def _iter_tracker_aliases(actress_id: str, actress: dict, videos_dict: dict | None = None) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    vd = videos_dict or {}

    def _add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        aliases.append(text)

    _add(actress_id)
    _add(actress.get("name", ""))
    for video in actress.get("videos", []):
        ref = str(video.get("ref", "")).upper()
        for actress_name in (vd.get(ref, {}).get("_meta", {}) or {}).get("actresses", []) or []:
            _add(actress_name)

    return aliases


def _iter_tracker_lookup_aliases(
    actress_id: str,
    actress: dict,
    videos_dict: dict | None = None,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    vd = videos_dict or {}

    def _add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        aliases.append(text)

    _add(actress_id)
    _add(actress.get("name", ""))

    # Only treat solo metadata names as stable aliases for this actress.
    # Co-star names from multi-actress videos make ref lookups ambiguous.
    for video in actress.get("videos", []):
        ref = str(video.get("ref", "")).upper()
        meta_actresses = (vd.get(ref, {}).get("_meta", {}) or {}).get("actresses", []) or []
        if len(meta_actresses) == 1:
            _add(meta_actresses[0])

    return aliases


def split_actress_names(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    parts = re.split(r"\s*(?:、|,|，|/|／|&|＆|\||｜|\+|＋|・|･|·|•|\band\b)\s*", text, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part and part.strip()]


def _tracker_inactive_config() -> tuple[bool, int]:
    cfg = load_config()
    enabled = bool(cfg.get("tracker_auto_inactive_enabled", True))
    try:
        months = int(cfg.get("tracker_inactive_months", 6))
    except (TypeError, ValueError):
        months = 6
    return enabled, max(1, months)


def _subtract_months(anchor: _date_cls, months: int) -> _date_cls:
    total_months = (anchor.year * 12 + (anchor.month - 1)) - max(0, int(months))
    year = total_months // 12
    month = total_months % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return _date_cls(year, month, day)


def _parse_tracker_date(value: str) -> Optional[_date_cls]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _date_cls.fromisoformat(text[:10])
    except ValueError:
        return None


def _is_fetched_solo_video(ref: str, videos_dict: dict) -> bool:
    actresses = (videos_dict.get(str(ref or "").upper()) or {}).get("_meta", {}).get("actresses") or []
    return len(actresses) == 1


def _build_inactive_status(
    videos: list[dict],
    videos_dict: dict,
    *,
    enabled: Optional[bool] = None,
    months: Optional[int] = None,
    today: Optional[_date_cls] = None,
) -> dict:
    if enabled is None or months is None:
        enabled, months = _tracker_inactive_config()

    months = max(1, int(months))
    if not enabled:
        return {
            "inactive": False,
            "inactive_reason": "",
            "inactive_last_solo": None,
        }

    if today is None:
        today = _date_cls.today()

    fetched_solo_videos = [
        v for v in videos if _is_fetched_solo_video(v.get("ref", ""), videos_dict)
    ]
    if not fetched_solo_videos:
        return {
            "inactive": True,
            "inactive_reason": "No fetched solo releases in the tracker list.",
            "inactive_last_solo": None,
        }

    solo_dates = [
        parsed_date
        for parsed_date in (
            _parse_tracker_date(
                (videos_dict.get(v.get("ref", "").upper()) or {}).get("date", "")
            )
            for v in fetched_solo_videos
        )
        if parsed_date is not None
    ]
    if not solo_dates:
        return {
            "inactive": True,
            "inactive_reason": "Solo releases exist, but none have a usable release date yet.",
            "inactive_last_solo": None,
        }

    latest_solo = max(solo_dates)
    cutoff = _subtract_months(today, months)
    is_inactive = latest_solo < cutoff
    month_word = "month" if months == 1 else "months"
    return {
        "inactive": is_inactive,
        "inactive_reason": (
            f"Latest solo release was {latest_solo.isoformat()}, older than the {months}-{month_word} window."
            if is_inactive
            else ""
        ),
        "inactive_last_solo": latest_solo.isoformat(),
    }


def _apply_inactive_status(
    actress: dict,
    videos_dict: dict,
    *,
    enabled: Optional[bool] = None,
    months: Optional[int] = None,
    today: Optional[_date_cls] = None,
) -> bool:
    status = _build_inactive_status(
        actress.get("videos", []),
        videos_dict,
        enabled=enabled,
        months=months,
        today=today,
    )
    changed = False
    for key, value in status.items():
        if actress.get(key) != value:
            actress[key] = value
            changed = True
    return changed


def recalculate_all_inactive_statuses() -> int:
    data = load_tracker()
    actresses = data.get("actresses", {})
    videos_dict = data.get("videos", {})
    enabled, months = _tracker_inactive_config()
    today = _date_cls.today()
    changed = 0

    for actress in actresses.values():
        if _apply_inactive_status(actress, videos_dict, enabled=enabled, months=months, today=today):
            changed += 1

    if changed:
        save_tracker(data)
    return changed


def normalize_tracker_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "").strip()).casefold()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[·・･•‧﹒．。｡]", "", text)
    return text


def get_preferred_actress_name(actress_id: str, actress: dict) -> str:
    preferred = str((actress or {}).get("name", "") or "").strip()
    if preferred:
        return preferred

    for alias in _iter_tracker_aliases(actress_id, actress or {}):
        if alias != actress_id:
            return alias
    return actress_id


def _build_tracker_name_indexes(
    data: dict,
    ref: str = "",
) -> tuple[
    dict[str, list[tuple[Optional[int], str, str]]],
    dict[str, list[tuple[Optional[int], str, str]]],
    dict[str, list[tuple[Optional[int], str, str]]],
    dict[str, list[tuple[Optional[int], str, str]]],
    list[tuple[Optional[int], str, str]],
]:
    global_exact: dict[str, list[tuple[Optional[int], str, str]]] = {}
    global_normalized: dict[str, list[tuple[Optional[int], str, str]]] = {}
    ref_exact: dict[str, list[tuple[Optional[int], str, str]]] = {}
    ref_normalized: dict[str, list[tuple[Optional[int], str, str]]] = {}
    matched_ref_actresses: list[tuple[Optional[int], str, str]] = []

    actresses = (data or {}).get("actresses", {})
    videos_dict = (data or {}).get("videos", {})
    ref_up = str(ref or "").strip().upper()

    for actress_id, actress in actresses.items():
        rating = actress.get("rating")
        preferred_name = get_preferred_actress_name(actress_id, actress)
        aliases = _iter_tracker_lookup_aliases(actress_id, actress, videos_dict)
        entry = (rating, actress_id, preferred_name)

        for alias in aliases:
            global_exact.setdefault(alias, []).append(entry)
            normalized_alias = normalize_tracker_name(alias)
            if normalized_alias:
                global_normalized.setdefault(normalized_alias, []).append(entry)

        if not ref_up:
            continue

        matched_video = any(
            str(video.get("ref", "")).strip().upper() == ref_up
            for video in actress.get("videos", []) or []
        )
        if not matched_video:
            continue

        matched_ref_actresses.append(entry)
        for alias in aliases:
            ref_exact.setdefault(alias, []).append(entry)
            normalized_alias = normalize_tracker_name(alias)
            if normalized_alias:
                ref_normalized.setdefault(normalized_alias, []).append(entry)

    return (
        global_exact,
        global_normalized,
        ref_exact,
        ref_normalized,
        matched_ref_actresses,
    )


def _pick_unique_tracker_match(
    candidates: list[tuple[Optional[int], str, str]] | None,
) -> tuple[Optional[int], Optional[str], Optional[str]]:
    if not candidates:
        return None, None, None

    unique = {(rating, actress_id, preferred_name) for rating, actress_id, preferred_name in candidates}
    if len(unique) != 1:
        return None, None, None

    rating, actress_id, preferred_name = next(iter(unique))
    return rating, actress_id, preferred_name


def get_video(data: dict, ref: str) -> dict:
    """Return the shared video entry for a ref, or empty dict if not found."""
    return (data.get("videos") or {}).get(str(ref or "").strip().upper(), {})


def build_name_to_rating(data: dict) -> dict:
    name_to_rating = {}
    if not data or "actresses" not in data:
        return name_to_rating

    vd = data.get("videos", {})
    for a_id, a_data in data["actresses"].items():
        r = a_data.get("rating")
        if r is not None:
            for alias in _iter_tracker_aliases(a_id, a_data, vd):
                name_to_rating[alias] = r
    return name_to_rating


def resolve_ref_actress_lookup(
    data: dict,
    ref: str,
    actress_names: list[str] | None = None,
) -> dict[str, tuple[Optional[int], Optional[str]]]:
    details = resolve_ref_actress_details(data, ref, actress_names)
    lookup: dict[str, tuple[Optional[int], Optional[str]]] = {}
    for name, detail in details.items():
        lookup[name] = (detail.get("rating"), detail.get("actress_id"))
    return lookup


def resolve_ref_actress_details(
    data: dict,
    ref: str,
    actress_names: list[str] | None = None,
) -> dict[str, dict[str, Optional[str] | Optional[int]]]:
    lookup: dict[str, dict[str, Optional[str] | Optional[int]]] = {}
    requested = [str(name or "").strip() for name in (actress_names or []) if str(name or "").strip()]
    for name in requested:
        lookup[name] = {
            "rating": None,
            "actress_id": None,
            "canonical_name": None,
            "matched_by": None,
        }

    actresses = (data or {}).get("actresses", {})
    if not actresses:
        return lookup

    (
        global_exact,
        global_normalized,
        ref_exact,
        ref_normalized,
        matched_ref_actresses,
    ) = _build_tracker_name_indexes(data, ref)

    if not requested:
        for alias, candidates in ref_exact.items():
            rating, actress_id, preferred_name = _pick_unique_tracker_match(candidates)
            lookup[alias] = {
                "rating": rating,
                "actress_id": actress_id,
                "canonical_name": preferred_name,
                "matched_by": "ref-exact" if actress_id else None,
            }
        return lookup

    for name in requested:
        normalized_name = normalize_tracker_name(name)
        rating = actress_id = preferred_name = matched_by = None

        for candidate_map, candidate_kind in (
            (ref_exact, "ref-exact"),
            (ref_normalized, "ref-normalized"),
            (global_exact, "global-exact"),
            (global_normalized, "global-normalized"),
        ):
            key = name if candidate_kind.endswith("exact") else normalized_name
            if not key:
                continue
            rating, actress_id, preferred_name = _pick_unique_tracker_match(candidate_map.get(key))
            if actress_id:
                matched_by = candidate_kind
                break

        lookup[name] = {
            "rating": rating,
            "actress_id": actress_id,
            "canonical_name": preferred_name,
            "matched_by": matched_by,
        }

    if ref and requested:
        used_ids = {
            str(detail.get("actress_id") or "")
            for detail in lookup.values()
            if detail.get("actress_id")
        }
        unmatched_requested = [
            name for name in requested if not lookup.get(name, {}).get("actress_id")
        ]
        remaining_ref_entries = [
            (rating, actress_id, preferred_name)
            for rating, actress_id, preferred_name in matched_ref_actresses
            if actress_id and actress_id not in used_ids
        ]

        # If the ref already identified all but a small remainder, pair the
        # leftover requested names with the leftover ref actresses by position.
        # This preserves multi-actress names when one alias drifts but the ref
        # still points to the correct cast set.
        if unmatched_requested and len(unmatched_requested) == len(remaining_ref_entries):
            for name, (rating, actress_id, preferred_name) in zip(
                unmatched_requested,
                remaining_ref_entries,
            ):
                lookup[name] = {
                    "rating": rating,
                    "actress_id": actress_id,
                    "canonical_name": preferred_name,
                    "matched_by": "ref-remaining",
                }

    return lookup
