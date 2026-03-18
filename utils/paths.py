"""
Central path resolver for all mutable app data.

Resolution order for DATA_DIR:
  1. data_dir.txt next to the .exe (or main.py in dev)
  2. %APPDATA%\\JAV Downloader   (Windows default)
  3. ~/.jav-downloader           (fallback on non-Windows)

All config, secrets, Chrome profile, and NiceGUI session storage live here.
The location can be changed from within the app's Settings dialog.
"""
import os
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """Directory that contains the running .exe (frozen) or main.py (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _read_data_dir_override() -> Path | None:
    marker = _exe_dir() / "data_dir.txt"
    if marker.exists():
        raw = marker.read_text(encoding="utf-8").strip()
        if raw:
            p = Path(raw)
            if p.is_absolute():
                return p
    return None


def _default_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "JAV Downloader"
    return Path.home() / ".jav-downloader"


def resolve_data_dir() -> Path:
    override = _read_data_dir_override()
    return override if override is not None else _default_data_dir()


# ── Public paths ──────────────────────────────────────────────────────────────
# Re-evaluated at import time; call reload_paths() after changing DATA_DIR.

DATA_DIR: Path = resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE        : Path = DATA_DIR / "config.json"
ENV_FILE           : Path = DATA_DIR / ".env"
CHROME_PROFILE_DIR : Path = DATA_DIR / "chrome_profile"
NICEGUI_STORAGE_DIR: Path = DATA_DIR / "storage"
TRACKER_FILE       : Path = DATA_DIR / "tracker.json"
TRACKER_UI_STATE_FILE: Path = DATA_DIR / "tracker_ui_state.json"
COVERS_DIR         : Path = DATA_DIR / "covers"
DOWNLOADER_STATE_FILE: Path = DATA_DIR / "downloader_state.json"
ORGANISER_STATE_FILE : Path = DATA_DIR / "organiser_state.json"
MIGRATION_EXPORT_DIR : Path = DATA_DIR / "migration_exports"
MIGRATION_SEED_DIR   : Path = DATA_DIR / "migration_seed"


def reload_paths() -> None:
    """Re-resolve all module-level paths after DATA_DIR changes at runtime."""
    global DATA_DIR, CONFIG_FILE, ENV_FILE, CHROME_PROFILE_DIR, NICEGUI_STORAGE_DIR, TRACKER_FILE, TRACKER_UI_STATE_FILE, COVERS_DIR
    global DOWNLOADER_STATE_FILE, ORGANISER_STATE_FILE, MIGRATION_EXPORT_DIR, MIGRATION_SEED_DIR
    DATA_DIR = resolve_data_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE         = DATA_DIR / "config.json"
    ENV_FILE            = DATA_DIR / ".env"
    CHROME_PROFILE_DIR  = DATA_DIR / "chrome_profile"
    NICEGUI_STORAGE_DIR = DATA_DIR / "storage"
    TRACKER_FILE        = DATA_DIR / "tracker.json"
    TRACKER_UI_STATE_FILE = DATA_DIR / "tracker_ui_state.json"
    COVERS_DIR          = DATA_DIR / "covers"
    DOWNLOADER_STATE_FILE = DATA_DIR / "downloader_state.json"
    ORGANISER_STATE_FILE  = DATA_DIR / "organiser_state.json"
    MIGRATION_EXPORT_DIR  = DATA_DIR / "migration_exports"
    MIGRATION_SEED_DIR    = DATA_DIR / "migration_seed"


def set_data_dir(new_path: Path, migrate: bool = True) -> None:
    """
    Change the data directory:
      1. Optionally migrate existing files to new_path.
      2. Write data_dir.txt next to the exe so the change persists across restarts.
      3. Call reload_paths() to update all in-process path constants.
    """
    import shutil

    new_path = Path(new_path)
    new_path.mkdir(parents=True, exist_ok=True)

    if migrate:
        current = DATA_DIR
        for item in current.iterdir():
            dest = new_path / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    marker = _exe_dir() / "data_dir.txt"
    marker.write_text(str(new_path), encoding="utf-8")

    reload_paths()
