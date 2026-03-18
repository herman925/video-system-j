from pathlib import Path

root = Path(r"c:\Users\KeySteps\Downloads\Video Downloader JAV")
src = (root / "main.py").read_text(encoding="utf-8")

header = '''\
"""JAV Downloader — /downloader page module.

This module registers the @ui.page("/downloader") route and contains all
supporting helpers used exclusively by the downloader UI.
"""

import asyncio
import queue as _queue_mod
import re
from pathlib import Path
from typing import Dict, List, Optional

from nicegui import Client, app, ui

from scraper.javdb import search_javdb
from scraper.javlibrary import search_javlibrary
from scraper.nyaa import search_nyaa
from translator.llm import (
    PROVIDERS,
    extract_code_blocks,
    load_config,
    read_env_key,
    save_config,
    translate_title,
)
from utils.paths import DATA_DIR, ENV_FILE, set_data_dir
from utils.qbittorrent import add_torrent, get_all_torrents, get_torrents, is_reachable
from downloader.state import _SESSION_KEY, _CACHE_KEY, _session_save
from downloader.components.queue import (
    _has_mosaic_torrent,
    _update_badges,
    _build_queue_entry,
)
from downloader.components.inspector import (
    _attach_inspector,
    _populate_inspector,
    _build_youcom_url,
)
from downloader.components.settings import build_settings_dialog as _build_settings_dialog
from utils.scraper_lock import SCRAPER_SEM as _SCRAPER_SEM


'''

# Extract: _DL_*_STATES + _parse_keywords + settings/scraper imports + _fetch_one
# Anchor: from "# ── qBittorrent download-category helpers" to blank lines before "# ── Launchpad"
b1_start = src.index("# ── qBittorrent download-category helpers")
b1_end   = src.index("\n\n# ── Launchpad")
dl_and_helpers = src[b1_start:b1_end].rstrip()

# Queue definition (will be placed BEFORE build_ui so build_ui can reference it)
queue_def = """

# Thread-safe queue: extension POST drops refs here; build_ui timer drains it
_ext_ref_queue: _queue_mod.Queue = _queue_mod.Queue()

"""

# Extract build_ui: from @ui.page("/downloader") through disconnect cleanup
b2_start = src.index('@ui.page("/downloader")')
b2_end   = src.index("\n\n\n# ── Browser-extension API endpoint")
build_ui_block = src[b2_start:b2_end].rstrip()

content = header + dl_and_helpers + queue_def + build_ui_block + "\n"

(root / "downloader" / "page.py").write_text(content, encoding="utf-8")
print(f"Written downloader/page.py — {len(content.splitlines())} lines")
