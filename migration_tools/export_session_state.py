from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.paths import DATA_DIR, NICEGUI_STORAGE_DIR


EXPORT_DIR = DATA_DIR / "migration_exports"
QUEUE_KEY = "jav_dl_queue"
CACHE_KEY = "jav_dl_cache"
META_CACHE_KEY = "_jav_meta_cache"


@dataclass(frozen=True)
class SessionSnapshot:
    path: Path
    data: dict[str, Any]
    mtime: float


def _load_snapshots() -> list[SessionSnapshot]:
    snapshots: list[SessionSnapshot] = []
    for path in sorted(
        NICEGUI_STORAGE_DIR.glob("storage-user-*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        snapshots.append(SessionSnapshot(path=path, data=data, mtime=path.stat().st_mtime))
    return snapshots


def _pick_first_non_empty(snapshots: list[SessionSnapshot], key: str, default: Any) -> Any:
    for snapshot in snapshots:
        value = snapshot.data.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _merge_downloader_queue(snapshots: list[SessionSnapshot]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        items = snapshot.data.get(QUEUE_KEY, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            kw = str(item.get("kw") or "").strip().upper()
            if not kw:
                continue
            existing = merged.get(kw)
            if existing is None:
                merged[kw] = {
                    "kw": kw,
                    "title": item.get("title", ""),
                    "folder_path": item.get("folder_path", ""),
                    "downloaded": bool(item.get("downloaded")),
                    "ever_selected": bool(item.get("ever_selected")),
                }
                continue
            if item.get("downloaded"):
                existing["downloaded"] = True
            if item.get("ever_selected"):
                existing["ever_selected"] = True
            if not existing.get("title") and item.get("title"):
                existing["title"] = item["title"]
            if not existing.get("folder_path") and item.get("folder_path"):
                existing["folder_path"] = item["folder_path"]
    return list(merged.values())


def _merge_mapping(snapshots: list[SessionSnapshot], key: str, *, require_jav: bool = False) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for snapshot in snapshots:
        payload = snapshot.data.get(key, {})
        if not isinstance(payload, dict):
            continue
        for raw_ref, entry in payload.items():
            ref = str(raw_ref or "").strip().upper()
            if not ref or ref in merged:
                continue
            if require_jav and (not isinstance(entry, dict) or not entry.get("jav")):
                continue
            merged[ref] = entry
    return merged


def build_export() -> dict[str, Any]:
    snapshots = _load_snapshots()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_files = [
        {
            "name": snapshot.path.name,
            "size": snapshot.path.stat().st_size,
            "modified_at": datetime.fromtimestamp(snapshot.mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for snapshot in snapshots
    ]

    export = {
        "generated_at": generated_at,
        "data_dir": str(DATA_DIR),
        "source_files": source_files,
        "downloader": {
            "queue": _merge_downloader_queue(snapshots),
            "cache": _merge_mapping(snapshots, CACHE_KEY, require_jav=True),
            "meta_cache": _merge_mapping(snapshots, META_CACHE_KEY),
            "view_state": _pick_first_non_empty(snapshots, "jav_dl_view_state", {}),
            "subtitle_cfg": _pick_first_non_empty(snapshots, "jav_dl_subtitle_cfg", {}),
            "panel_width": _pick_first_non_empty(snapshots, "jav_dl_panel_width", 295),
        },
        "organiser": {
            "left_panel_width": _pick_first_non_empty(snapshots, "organiser_left_panel_width", 780),
            "renamer_panel_width": _pick_first_non_empty(snapshots, "organiser_renamer_left_panel_width", None),
            "mover_panel_width": _pick_first_non_empty(snapshots, "organiser_mover_left_panel_width", None),
            "scan_folder": _pick_first_non_empty(snapshots, "organiser_scan_folder", ""),
            "mover_base": _pick_first_non_empty(snapshots, "organiser_mover_base", ""),
            "cleanup_delete_other_files": _pick_first_non_empty(
                snapshots,
                "organiser_cleanup_delete_other_files",
                True,
            ),
            "cleanup_delete_small_videos": _pick_first_non_empty(
                snapshots,
                "organiser_cleanup_delete_small_videos",
                False,
            ),
            "cleanup_small_video_mb": _pick_first_non_empty(
                snapshots,
                "organiser_cleanup_small_video_mb",
                30.0,
            ),
        },
        "tracker": {
            "left_panel_width": _pick_first_non_empty(snapshots, "tracker_left_panel_width", 300),
            "video_page_size": _pick_first_non_empty(snapshots, "tracker_video_page_size", 20),
            "sort_cache": _pick_first_non_empty(snapshots, "_tracker_sort_cache", {}),
        },
    }
    return export


def write_export() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_path = EXPORT_DIR / f"session-state-export-{stamp}.json"
    export_path.write_text(json.dumps(build_export(), ensure_ascii=False, indent=2), encoding="utf-8")
    return export_path


if __name__ == "__main__":
    path = write_export()
    print(f"Wrote consolidated export to: {path}")