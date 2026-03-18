from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable

from translator.llm import load_config
from utils import paths


_STATE_LOCK = threading.RLock()


def _default_state() -> dict:
    cfg = load_config()
    return {
        "created_at": "",
        "left_panel_width": 780,
        "renamer_panel_width": 780,
        "mover_panel_width": 680,
        "scan_folder": str(cfg.get("organiser_scan_folder", "") or cfg.get("download_folder", "") or ""),
        "mover_base": str(cfg.get("organiser_mover_base", "") or ""),
        "cleanup_delete_other_files": bool(cfg.get("organiser_cleanup_delete_other_files", True)),
        "cleanup_delete_small_videos": bool(cfg.get("organiser_cleanup_delete_small_videos", False)),
        "cleanup_small_video_mb": float(cfg.get("organiser_cleanup_small_video_mb", 30.0) or 30.0),
    }


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_state(raw: dict | None) -> dict:
    defaults = _default_state()
    raw = raw or {}
    renamer_panel_width = int(raw.get("renamer_panel_width", raw.get("left_panel_width", defaults["renamer_panel_width"])) or defaults["renamer_panel_width"])
    mover_panel_width = int(raw.get("mover_panel_width", raw.get("left_panel_width", defaults["mover_panel_width"])) or defaults["mover_panel_width"])
    return {
        "created_at": str(raw.get("created_at") or ""),
        "left_panel_width": renamer_panel_width,
        "renamer_panel_width": renamer_panel_width,
        "mover_panel_width": mover_panel_width,
        "scan_folder": str(raw.get("scan_folder", defaults["scan_folder"]) or ""),
        "mover_base": str(raw.get("mover_base", defaults["mover_base"]) or ""),
        "cleanup_delete_other_files": bool(raw.get("cleanup_delete_other_files", defaults["cleanup_delete_other_files"])),
        "cleanup_delete_small_videos": bool(raw.get("cleanup_delete_small_videos", defaults["cleanup_delete_small_videos"])),
        "cleanup_small_video_mb": float(raw.get("cleanup_small_video_mb", defaults["cleanup_small_video_mb"]) or defaults["cleanup_small_video_mb"]),
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
    organiser = dict((export_data or {}).get("organiser") or {})
    return _normalize_state(
        {
            "created_at": export_data.get("created_at") or "",
            "left_panel_width": organiser.get("left_panel_width", 780),
            "renamer_panel_width": organiser.get("renamer_panel_width"),
            "mover_panel_width": organiser.get("mover_panel_width"),
            "scan_folder": organiser.get("scan_folder", ""),
            "mover_base": organiser.get("mover_base", ""),
            "cleanup_delete_other_files": organiser.get("cleanup_delete_other_files", True),
            "cleanup_delete_small_videos": organiser.get("cleanup_delete_small_videos", False),
            "cleanup_small_video_mb": organiser.get("cleanup_small_video_mb", 30.0),
        }
    )


def _write_locked(state: dict) -> None:
    normalized = _normalize_state(state)
    if not normalized.get("created_at"):
        normalized["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paths.ORGANISER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = paths.ORGANISER_STATE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(paths.ORGANISER_STATE_FILE)


def _ensure_migrated_locked() -> None:
    if paths.ORGANISER_STATE_FILE.exists():
        return

    state: dict | None = None
    seed_path = paths.MIGRATION_SEED_DIR / "organiser_state.seed.json"
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


def load_organiser_state() -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        return deepcopy(_normalize_state(_read_json(paths.ORGANISER_STATE_FILE)))


def update_organiser_state(mutator: Callable[[dict], dict | None]) -> dict:
    with _STATE_LOCK:
        _ensure_migrated_locked()
        state = _normalize_state(_read_json(paths.ORGANISER_STATE_FILE))
        updated = mutator(deepcopy(state))
        next_state = _normalize_state(updated if updated is not None else state)
        if not next_state.get("created_at"):
            next_state["created_at"] = state.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_locked(next_state)
        return deepcopy(next_state)


def save_organiser_state(state: dict) -> dict:
    with _STATE_LOCK:
        _write_locked(state)
        return deepcopy(_normalize_state(state))


def save_organiser_preferences(
    *,
    scan_folder: str,
    mover_base: str,
    renamer_panel_width: int,
    mover_panel_width: int,
    cleanup_delete_other_files: bool,
    cleanup_delete_small_videos: bool,
    cleanup_small_video_mb: float,
) -> None:
    def _mutate(state: dict) -> dict:
        next_state = dict(state)
        next_state.update(
            {
                "left_panel_width": int(renamer_panel_width),
                "renamer_panel_width": int(renamer_panel_width),
                "mover_panel_width": int(mover_panel_width),
                "scan_folder": str(scan_folder or ""),
                "mover_base": str(mover_base or ""),
                "cleanup_delete_other_files": bool(cleanup_delete_other_files),
                "cleanup_delete_small_videos": bool(cleanup_delete_small_videos),
                "cleanup_small_video_mb": float(cleanup_small_video_mb or 30.0),
            }
        )
        return next_state

    update_organiser_state(_mutate)