from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.paths import CONFIG_FILE, DATA_DIR


SEED_DIR = DATA_DIR / "migration_seed"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _update_config(export_data: dict[str, Any]) -> dict[str, Any]:
    config = _load_json(CONFIG_FILE) if CONFIG_FILE.exists() else {}
    downloader = export_data.get("downloader", {})
    organiser = export_data.get("organiser", {})
    tracker = export_data.get("tracker", {})

    config.update(
        {
            "downloader_cover_w": config.get("downloader_cover_w", 240),
            "organiser_scan_folder": organiser.get("scan_folder", config.get("organiser_scan_folder", "")),
            "organiser_mover_base": organiser.get("mover_base", config.get("organiser_mover_base", "")),
            "organiser_cleanup_delete_other_files": organiser.get(
                "cleanup_delete_other_files",
                config.get("organiser_cleanup_delete_other_files", True),
            ),
            "organiser_cleanup_delete_small_videos": organiser.get(
                "cleanup_delete_small_videos",
                config.get("organiser_cleanup_delete_small_videos", False),
            ),
            "organiser_cleanup_small_video_mb": organiser.get(
                "cleanup_small_video_mb",
                config.get("organiser_cleanup_small_video_mb", 30.0),
            ),
            "tracker_video_page_size": tracker.get(
                "video_page_size",
                config.get("tracker_video_page_size", 20),
            ),
            "jav_dl_panel_width": downloader.get(
                "panel_width",
                config.get("jav_dl_panel_width", 295),
            ),
            "organiser_left_panel_width": organiser.get(
                "left_panel_width",
                config.get("organiser_left_panel_width", 780),
            ),
            "organiser_renamer_left_panel_width": organiser.get(
                "renamer_panel_width",
                config.get("organiser_renamer_left_panel_width", config.get("organiser_left_panel_width", 780)),
            ),
            "organiser_mover_left_panel_width": organiser.get(
                "mover_panel_width",
                config.get("organiser_mover_left_panel_width", config.get("organiser_left_panel_width", 680)),
            ),
            "tracker_left_panel_width": tracker.get(
                "left_panel_width",
                config.get("tracker_left_panel_width", 300),
            ),
        }
    )
    return config


def write_seed_files(export_path: Path) -> list[Path]:
    export_data = _load_json(export_path)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    config_seed = _update_config(export_data)
    downloader = export_data.get("downloader", {})
    organiser = export_data.get("organiser", {})
    tracker = export_data.get("tracker", {})

    paths: list[Path] = []

    config_seed_path = SEED_DIR / "config.seed.json"
    config_seed_path.write_text(json.dumps(config_seed, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.append(config_seed_path)

    downloader_seed_path = SEED_DIR / "downloader_state.seed.json"
    downloader_seed_path.write_text(
        json.dumps(
            {
                "created_at": created_at,
                "queue": downloader.get("queue", []),
                "cache": downloader.get("cache", {}),
                "meta_cache": downloader.get("meta_cache", {}),
                "view_state": downloader.get("view_state", {}),
                "subtitle_cfg": downloader.get("subtitle_cfg", {}),
                "panel_width": downloader.get("panel_width", 295),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(downloader_seed_path)

    organiser_seed_path = SEED_DIR / "organiser_state.seed.json"
    organiser_seed_path.write_text(
        json.dumps(
            {
                "created_at": created_at,
                **organiser,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(organiser_seed_path)

    tracker_seed_path = SEED_DIR / "tracker_ui_state.seed.json"
    tracker_seed_path.write_text(
        json.dumps(
            {
                "created_at": created_at,
                **tracker,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(tracker_seed_path)

    manifest_path = SEED_DIR / "seed_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": created_at,
                "source_export": str(export_path),
                "files": [str(path) for path in paths],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(manifest_path)

    return paths


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python migration_tools/write_seed_files.py <export-json-path>")
    export_file = Path(sys.argv[1]).resolve()
    if not export_file.exists():
        raise SystemExit(f"Export file not found: {export_file}")
    written = write_seed_files(export_file)
    print("Wrote seed files:")
    for path in written:
        print(f"- {path}")