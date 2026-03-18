from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable

from utils import paths


_STATE_LOCK = threading.RLock()


def default_downloader_view_state() -> dict:
    return {
        "sort": "default",
        "group": "none",
        "filter": "",
    }


def default_downloader_subtitle_cfg() -> dict:
    return {
        "sort": {
            "default": ["actress"],
            "ref_az": ["actress"],
            "ref_za": ["actress"],
            "date_desc": ["actress", "date"],
            "date_asc": ["actress", "date"],
            "studio_az": ["actress", "studio"],
            "status": ["actress", "status"],
            "badge_m": ["actress"],
            "badge_zh": ["actress"],
            "badge_n": ["actress"],
            "dl_status": ["actress", "dl_status"],
        },
        "group": {
            "none": [],
            "studio": ["studio"],
            "status": ["status"],
            "month": ["date"],
            "actor": [],
            "badge_mt": [],
            "badge_zh": [],
            "dl_status": ["dl_status"],
        },
    }


def _coerce_list(value) -> list:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in ("", None, "none"):
        return []
    return [str(value)]


def _default_state() -> dict:
    return {
        "created_at": "",
        "queue": [],
        "cache": {},
        "view_state": default_downloader_view_state(),
        "subtitle_cfg": default_downloader_subtitle_cfg(),
        "panel_width": 295,
    }


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_queue(items) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        ref = str((item or {}).get("kw", "")).strip().upper()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        normalized.append(
            {
                "kw": ref,
                "title": str((item or {}).get("title", "") or ""),
                "folder_path": str((item or {}).get("folder_path", "") or ""),
                "downloaded": bool((item or {}).get("downloaded")),
                "ever_selected": bool((item or {}).get("ever_selected")),
            }
        )
    return normalized


def _normalize_state(raw: dict | None) -> dict:
    raw = raw or {}
    defaults = _default_state()
    subtitle_defaults = default_downloader_subtitle_cfg()
    legacy_meta_cache = dict(raw.get("meta_cache") or {})
    cache = dict(raw.get("cache") or {})
    for ref, meta in legacy_meta_cache.items():
        ref_up = str(ref or "").strip().upper()
        if not ref_up or not isinstance(meta, dict) or not meta:
            continue
        merged = dict(cache.get(ref_up) or {})
        if not isinstance(merged.get("jav"), dict) or not merged.get("jav"):
            merged["jav"] = dict(meta)
        cache[ref_up] = merged

    raw_view_state = raw.get("view_state") or {}
    view_state = {
        "sort": str(raw_view_state.get("sort", defaults["view_state"]["sort"]) or "default"),
        "group": str(raw_view_state.get("group", defaults["view_state"]["group"]) or "none"),
        "filter": str(raw_view_state.get("filter", defaults["view_state"]["filter"]) or ""),
    }

    raw_subtitle = raw.get("subtitle_cfg") or {}
    subtitle_cfg = {
        "sort": {
            key: _coerce_list((raw_subtitle.get("sort") or {}).get(key, value))
            for key, value in subtitle_defaults["sort"].items()
        },
        "group": {
            key: _coerce_list((raw_subtitle.get("group") or {}).get(key, value))
            for key, value in subtitle_defaults["group"].items()
        },
    }

    normalized = {
        "created_at": str(raw.get("created_at") or ""),
        "queue": _normalize_queue(raw.get("queue") or []),
        "cache": cache,
        "view_state": view_state,
        "subtitle_cfg": subtitle_cfg,
        "panel_width": int(raw.get("panel_width", defaults["panel_width"]) or defaults["panel_width"]),
    }
    return normalized


def _export_to_state(export_data: dict) -> dict:
    downloader = dict((export_data or {}).get("downloader") or {})
    cache = dict(downloader.get("cache") or {})
    legacy_meta_cache = dict(downloader.get("meta_cache") or {})
    for ref, meta in legacy_meta_cache.items():
        ref_up = str(ref or "").strip().upper()
        if not ref_up or not isinstance(meta, dict) or not meta:
            continue
        merged = dict(cache.get(ref_up) or {})
        if not isinstance(merged.get("jav"), dict) or not merged.get("jav"):
            merged["jav"] = dict(meta)
        cache[ref_up] = merged
    return _normalize_state(
        {
            "created_at": export_data.get("created_at") or "",
            "queue": downloader.get("queue") or [],
            "cache": cache,
            "view_state": downloader.get("view_state") or {},
            "subtitle_cfg": downloader.get("subtitle_cfg") or {},
            "panel_width": downloader.get("panel_width", 295),
        }
    )


def _latest_export_path() -> Path | None:
    if not paths.MIGRATION_EXPORT_DIR.exists():
        return None
    exports = sorted(
        paths.MIGRATION_EXPORT_DIR.glob("session-state-export-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return exports[0] if exports else None


def _ensure_migrated_locked() -> None:
    if paths.DOWNLOADER_STATE_FILE.exists():
        return

    state: dict | None = None
    seed_path = paths.MIGRATION_SEED_DIR / "downloader_state.seed.json"
    seed_data = _read_json(seed_path) if seed_path.exists() else None
    if isinstance(seed_data, dict):
        state = _normalize_state(seed_data)

    if state is None:
        export_path = _latest_export_path()
        export_data = _read_json(export_path) if export_path else None
        if isinstance(export_data, dict):
            state = _export_to_state(export_data)

    if state is None:
        state = _default_state()

    if not state.get("created_at"):
        state["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_locked(state)


def _write_locked(state: dict) -> None:
    normalized = _normalize_state(state)
    if not normalized.get("created_at"):
        normalized["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paths.DOWNLOADER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = paths.DOWNLOADER_STATE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(paths.DOWNLOADER_STATE_FILE)


def load_downloader_state() -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        return deepcopy(_normalize_state(_read_json(paths.DOWNLOADER_STATE_FILE)))


def save_downloader_state(state: dict) -> dict:
    with _STATE_LOCK:
        _write_locked(state)
        return deepcopy(_normalize_state(state))


def update_downloader_state(mutator: Callable[[dict], dict | None]) -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        state = _normalize_state(_read_json(paths.DOWNLOADER_STATE_FILE))
        updated = mutator(deepcopy(state))
        next_state = _normalize_state(updated if updated is not None else state)
        if not next_state.get("created_at"):
            next_state["created_at"] = state.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_locked(next_state)
        return deepcopy(next_state)


def load_downloader_queue() -> list[dict]:
    return load_downloader_state()["queue"]


def load_downloader_cache() -> dict:
    return load_downloader_state()["cache"]


def load_downloader_view_state() -> dict:
    return load_downloader_state()["view_state"]


def load_downloader_subtitle_cfg() -> dict:
    return load_downloader_state()["subtitle_cfg"]


def get_downloader_panel_width() -> int:
    return int(load_downloader_state()["panel_width"])


def save_downloader_queue_cache(queue_items: list[dict], cache: dict) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["queue"] = _normalize_queue(queue_items)
        next_state["cache"] = dict(cache or {})
        return next_state

    update_downloader_state(_mutate)


def set_downloader_view_state(view_state: dict) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["view_state"] = dict(view_state or {})
        return next_state

    update_downloader_state(_mutate)


def set_downloader_subtitle_cfg(subtitle_cfg: dict) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["subtitle_cfg"] = deepcopy(subtitle_cfg or {})
        return next_state

    update_downloader_state(_mutate)


def set_downloader_panel_width(panel_width: int) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["panel_width"] = int(panel_width)
        return next_state

    update_downloader_state(_mutate)


def clear_downloader_runtime_state() -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["queue"] = []
        next_state["cache"] = {}
        return next_state

    update_downloader_state(_mutate)


def upsert_downloader_cache_entry(ref: str, entry: dict) -> None:
    ref = str(ref or "").strip().upper()
    if not ref:
        return

    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        cache = dict(next_state.get("cache") or {})
        merged = dict(cache.get(ref) or {})
        merged.update(dict(entry or {}))
        cache[ref] = merged
        next_state["cache"] = cache
        return next_state

    update_downloader_state(_mutate)


def append_downloader_queue_stub(
    ref: str,
    *,
    title: str = "",
    folder_path: str = "",
    downloaded: bool = False,
    ever_selected: bool = False,
) -> None:
    ref = str(ref or "").strip().upper()
    if not ref:
        return

    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        queue_items = list(next_state.get("queue") or [])
        if any(str(item.get("kw", "")).strip().upper() == ref for item in queue_items):
            return next_state
        queue_items.append(
            {
                "kw": ref,
                "title": title,
                "folder_path": folder_path,
                "downloaded": bool(downloaded),
                "ever_selected": bool(ever_selected),
            }
        )
        next_state["queue"] = queue_items
        return next_state

    update_downloader_state(_mutate)


def remove_downloader_refs(refs: list[str] | set[str] | tuple[str, ...]) -> None:
    ref_set = {str(ref).strip().upper() for ref in refs if str(ref).strip()}
    if not ref_set:
        return

    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["queue"] = [
            item
            for item in next_state.get("queue") or []
            if str(item.get("kw", "")).strip().upper() not in ref_set
        ]
        cache = dict(next_state.get("cache") or {})
        for ref in ref_set:
            cache.pop(ref, None)
        next_state["cache"] = cache
        return next_state

    update_downloader_state(_mutate)


def clear_downloader_cached_ref(ref: str, *, clear_meta: bool = False) -> None:
    ref = str(ref or "").strip().upper()
    if not ref:
        return

    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        cache = dict(next_state.get("cache") or {})
        if clear_meta and ref in cache:
            entry = dict(cache.get(ref) or {})
            entry.pop("jav", None)
            if entry:
                cache[ref] = entry
            else:
                cache.pop(ref, None)
        else:
            cache.pop(ref, None)
        next_state["cache"] = cache
        return next_state

    update_downloader_state(_mutate)