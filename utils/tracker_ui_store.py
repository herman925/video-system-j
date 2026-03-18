from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable

from utils import paths


_STATE_LOCK = threading.RLock()


def _default_state() -> dict:
    return {
        "created_at": "",
        "left_panel_width": 300,
        "video_page_size": 20,
        "sort_cache": {},
    }


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_state(raw: dict | None) -> dict:
    defaults = _default_state()
    raw = raw or {}
    page_size = int(raw.get("video_page_size", defaults["video_page_size"]) or defaults["video_page_size"])
    sort_cache = raw.get("sort_cache") or {}
    if not isinstance(sort_cache, dict):
        sort_cache = {}
    normalized_sort_cache = {}
    fingerprint = sort_cache.get("fingerprint")
    az_order = sort_cache.get("az_order")
    if isinstance(fingerprint, str) and isinstance(az_order, list):
        normalized_sort_cache = {
            "fingerprint": fingerprint,
            "az_order": [str(item) for item in az_order if str(item)],
        }
    return {
        "created_at": str(raw.get("created_at") or ""),
        "left_panel_width": int(raw.get("left_panel_width", defaults["left_panel_width"]) or defaults["left_panel_width"]),
        "video_page_size": page_size,
        "sort_cache": normalized_sort_cache,
    }


def _latest_export_path() -> Path | None:
    if not paths.MIGRATION_EXPORT_DIR.exists():
        return None
    exports = sorted(
        paths.MIGRATION_EXPORT_DIR.glob("session-state-export-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return exports[0] if exports else None


def _export_to_state(export_data: dict) -> dict:
    tracker_ui = dict((export_data or {}).get("tracker_ui") or {})
    return _normalize_state(
        {
            "created_at": export_data.get("created_at") or "",
            "left_panel_width": tracker_ui.get("left_panel_width", 300),
            "video_page_size": tracker_ui.get("video_page_size", 20),
            "sort_cache": tracker_ui.get("sort_cache") or {},
        }
    )


def _write_locked(state: dict) -> None:
    normalized = _normalize_state(state)
    if not normalized.get("created_at"):
        normalized["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paths.TRACKER_UI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = paths.TRACKER_UI_STATE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(paths.TRACKER_UI_STATE_FILE)


def _ensure_migrated_locked() -> None:
    if paths.TRACKER_UI_STATE_FILE.exists():
        return

    state: dict | None = None
    seed_path = paths.MIGRATION_SEED_DIR / "tracker_ui_state.seed.json"
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


def load_tracker_ui_state() -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        return deepcopy(_normalize_state(_read_json(paths.TRACKER_UI_STATE_FILE)))


def update_tracker_ui_state(mutator: Callable[[dict], dict | None]) -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        state = _normalize_state(_read_json(paths.TRACKER_UI_STATE_FILE))
        updated = mutator(deepcopy(state))
        next_state = _normalize_state(updated if updated is not None else state)
        if not next_state.get("created_at"):
            next_state["created_at"] = state.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_locked(next_state)
        return deepcopy(next_state)


def get_tracker_left_panel_width(default: int = 300) -> int:
    return int(load_tracker_ui_state().get("left_panel_width", default))


def get_tracker_video_page_size(default: int = 20) -> int:
    return int(load_tracker_ui_state().get("video_page_size", default))


def get_tracker_sort_cache() -> dict:
    return dict(load_tracker_ui_state().get("sort_cache") or {})


def set_tracker_left_panel_width(value: int) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["left_panel_width"] = int(value)
        return next_state

    update_tracker_ui_state(_mutate)


def set_tracker_video_page_size(value: int) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["video_page_size"] = int(value)
        return next_state

    update_tracker_ui_state(_mutate)


def set_tracker_sort_cache(fingerprint: str, az_order: list[str]) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state["sort_cache"] = {
            "fingerprint": str(fingerprint or ""),
            "az_order": [str(item) for item in az_order if str(item)],
        }
        return next_state

    update_tracker_ui_state(_mutate)