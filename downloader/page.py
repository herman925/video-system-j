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

from scraper.javlibrary import get_rate_limit_cooldown_seconds
from scraper.nyaa import search_nyaa
from translator.llm import (
    PROVIDERS,
    extract_code_blocks,
    load_config,
    read_env_key,
    save_config,
    translate_title,
)
from utils.downloader_store import (
    clear_downloader_cached_ref,
    clear_downloader_runtime_state,
    default_downloader_subtitle_cfg,
    get_downloader_panel_width,
    load_downloader_cache,
    load_downloader_queue,
    load_downloader_subtitle_cfg,
    load_downloader_view_state,
    set_downloader_subtitle_cfg,
    set_downloader_view_state,
    save_downloader_queue_cache,
    upsert_downloader_cache_entry,
)
from utils.paths import CONFIG_FILE, DATA_DIR, DOWNLOADER_STATE_FILE, ENV_FILE, set_data_dir
from utils.metadata import fetch_jav_metadata, resolve_metadata_source
from utils.qbittorrent import add_torrent, get_all_torrents, get_torrents, is_reachable
from downloader.state import _session_save
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
from utils.ref_cleanup import prune_orphaned_refs
from utils.save_state import build_save_state_badge
from utils.scraper_lock import SCRAPER_SEM as _SCRAPER_SEM
from utils.sort_key import romaji_key as _romaji_key


# ── qBittorrent download-category helpers ─────────────────────────────────────
_DL_DOWNLOADING_STATES = frozenset(
    {
        "downloading",
        "stalledDL",
        "forcedDL",
        "metaDL",
        "checkingDL",
    }
)
_DL_COMPLETE_STATES = frozenset(
    {
        "uploading",
        "stalledUP",
        "forcedUP",
        "pausedUP",
        "checkingUP",
        "checkingResumeData",
    }
)
_DL_PAUSED_STATES = frozenset({"pausedDL", "queuedDL", "queuedUP"})


def _parse_keywords(raw: str) -> List[str]:
    """Split a comma/newline/space-separated string into uppercase ref numbers."""
    parts = re.split(r"[\s,，\n]+", raw.strip())
    seen, out = set(), []
    for p in parts:
        k = p.strip().upper()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _build_tracker_cached_jav(keyword: str) -> Optional[dict]:
    """Build a downloader-compatible JAV payload from persisted tracker data."""
    ref = str(keyword or "").strip().upper()
    if not ref:
        return None

    try:
        from tracker.store import get_preferred_actress_name, load_tracker
        from utils.covers import cover_exists
    except Exception:
        return None

    data = load_tracker()
    shared_video = (data.get("videos") or {}).get(ref)
    if not isinstance(shared_video, dict) or not shared_video:
        return None

    meta = shared_video.get("_meta") or {}
    actress_names: list[str] = []
    seen_names: set[str] = set()

    def _add_name(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen_names:
            return
        seen_names.add(text)
        actress_names.append(text)

    for actress_name in meta.get("actresses") or []:
        _add_name(actress_name)

    if not actress_names:
        for actress_id, actress in (data.get("actresses") or {}).items():
            videos = actress.get("videos", []) or []
            if any(str(video.get("ref", "")).strip().upper() == ref for video in videos):
                _add_name(get_preferred_actress_name(actress_id, actress))

    cached_jav = {
        "title": str(meta.get("title") or shared_video.get("title") or "").strip(),
        "cover_url": (
            f"/api/cover?ref={ref}"
            if cover_exists(ref)
            else str(shared_video.get("cover_url") or "").strip()
        ),
        "id": ref,
        "date": str(shared_video.get("date") or meta.get("date") or "").strip(),
        "studio": str(meta.get("studio") or "").strip(),
        "actresses": actress_names,
        "genres": list(meta.get("genres") or []),
    }
    if not any(
        (
            cached_jav["title"],
            cached_jav["cover_url"],
            cached_jav["date"],
            cached_jav["studio"],
            cached_jav["actresses"],
            cached_jav["genres"],
        )
    ):
        return None
    return cached_jav


def _hydrate_session_metadata_from_tracker(keyword: str) -> Optional[dict]:
    """Mirror canonical tracker metadata into the downloader JAV cache."""
    ref = str(keyword or "").strip().upper()
    cached_jav = _build_tracker_cached_jav(ref)
    if not cached_jav:
        return None

    downloader_cache = load_downloader_cache()
    cache_entry = dict(downloader_cache.get(ref) or {})
    cache_entry["jav"] = cached_jav
    if not isinstance(cache_entry.get("nyaa"), list):
        cache_entry["nyaa"] = []
    upsert_downloader_cache_entry(ref, cache_entry)
    return cached_jav


def _hydrate_downloaded_state_from_tracker(handle: dict, keyword: str) -> None:
    """Promote tracker-persisted download state into the live downloader row."""
    ref = str(keyword or "").strip().upper()
    if not ref or handle["state"].get("downloaded"):
        return

    try:
        from tracker.store import is_ref_downloaded_globally
    except Exception:
        return

    if is_ref_downloaded_globally(ref):
        handle["state"]["downloaded"] = True


async def _fetch_one(keyword: str) -> tuple:
    """Return (jav_result, nyaa_result) for a single keyword.

    Checks the stable downloader JAV cache first, then rebuilds from tracker if
    shared metadata already exists there, to avoid redundant scraping.
    """
    _cached_entry = dict(load_downloader_cache().get(keyword.upper()) or {})
    _cached = _cached_entry.get("jav") if isinstance(_cached_entry.get("jav"), dict) else None
    if not isinstance(_cached, dict) or not _cached:
        _cached = _hydrate_session_metadata_from_tracker(keyword)
    if isinstance(_cached, dict) and _cached:
        nyaa_result = await asyncio.to_thread(search_nyaa, keyword)
        return _cached, nyaa_result

    _cfg = load_config()
    source = resolve_metadata_source(_cfg.get("metadata_source", "javdb"))

    async def _jav_primary():
        return await fetch_jav_metadata(keyword, source=source)

    jav_result, nyaa_result = await asyncio.gather(
        _jav_primary(),
        asyncio.to_thread(search_nyaa, keyword),
        return_exceptions=True,
    )

    return jav_result, nyaa_result

# Thread-safe queue: extension POST drops refs here; build_ui timer drains it
_ext_ref_queue: _queue_mod.Queue = _queue_mod.Queue()

@ui.page("/downloader")
async def build_ui(client: Client) -> None:
    _timer_ctx: dict = {}
    # Define all_handles before the dialog so the save callback can update timers
    all_handles: Dict[str, dict] = {}
    def _on_save_downloader(poll_interval, cover_w, timer_ctx, all_handles):
        if timer_ctx:
            gt = timer_ctx.get("global_timer")
            if gt:
                gt.interval = poll_interval
        if all_handles:
            for h in all_handles.values():
                t = h.get("dl_timer")
                if t:
                    t.interval = poll_interval

    _cfg = load_config()
    _dl_cover_w = int(_cfg.get("downloader_cover_w", 240))
    ui.add_head_html(
        f"<style>:root {{ --dl-cover-w: {_dl_cover_w}px; }}</style>"
    )

    settings_dialog = _build_settings_dialog(
        accent="#4f46e5",
        on_save_downloader=_on_save_downloader,
        timer_ctx=_timer_ctx,
        all_handles=all_handles,
        save_state_key="downloader",
    )

    def _downloader_save_paths() -> List[Path]:
        return [CONFIG_FILE, DOWNLOADER_STATE_FILE]

    active_kw: List[str] = [None]

    # ── Global CSS ────────────────────────────────────────────────────────────
    ui.add_head_html('<meta charset="utf-8">')
    ui.add_head_html(f"<style>{Path('assets/theme.css').read_text(encoding='utf-8')}</style>")
    ui.colors(primary='#4f46e5', secondary='#6366f1', accent='#4338ca')


    # ── App header ────────────────────────────────────────────────────────────
    with ui.header().classes("app-header text-white px-6 items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="home").props("flat round size=sm").style(
                "color:#818cf8"
            ).tooltip("Back to Launchpad").on("click", lambda: ui.navigate.to("/"))
            ui.html(
                '<span class="app-logo" style="cursor:pointer" '
                'onclick="window.location=\'/\'" title="Home">JAV Video System</span>'
            )
            build_save_state_badge("downloader", resolver=_downloader_save_paths)
        with ui.row().classes("items-center gap-4"):
            progress_lbl = ui.html("").style(
                "font-size:0.82rem;color:#9ca3af;min-width:260px;line-height:1.4"
            )
            mass_meta_btn = ui.button(icon="sync").props(
                "flat round size=md"
            ).style("color:#818cf8").tooltip("Re-fetch all metadata (JAVLib/JAVDB)")
            mass_nyaa_btn = ui.button(icon="cloud_sync").props(
                "flat round size=md"
            ).style("color:#818cf8").tooltip("Re-fetch all Nyaa torrents (max 3 at a time)")
            mass_trans_btn = ui.button(icon="translate").props(
                "flat round size=md"
            ).style("color:#818cf8").tooltip("Translate all untranslated (API or You.com)")
            ui.button(icon="settings", on_click=settings_dialog.open).props(
                "flat round size=md"
            ).style("color:#818cf8").tooltip("Settings")

    # ── Two-pane workspace ────────────────────────────────────────────────────
    with (
        ui.row().classes("w-full gap-0 items-start dl-shell").style("height:calc(100vh - 60px)")
    ):
        # ── LEFT: Sidebar ─────────────────────────────────────────────────────
        _sidebar_w = get_downloader_panel_width()
        with (
            ui.column()
            .classes("sidebar gap-0")
            .style(f"width:{_sidebar_w}px;min-width:{_sidebar_w}px") as sidebar_col
        ):
            # Search input
            with ui.element("div").classes("sidebar-search"):
                ref_input = (
                    ui.input(placeholder="ABF-319, WAAA-622…")
                    .classes("w-full")
                    .props("outlined clearable")
                )
                with ui.row().classes("gap-2 mt-3 w-full"):
                    search_btn = (
                        ui.button("Add to Queue", icon="add")
                        .props("size=md")
                        .style(
                            "background:#4f46e5;color:#fff;flex:1;border-radius:8px;"
                            "font-weight:600;font-size:0.9rem"
                        )
                    )
                    clear_btn = (
                        ui.button(icon="clear_all")
                        .props("flat dense round size=md")
                        .style("color:#818cf8")
                        .tooltip("Clear all")
                    )

            # ── Queue header row ──────────────────────────────────────────
            with ui.row().classes("items-center px-4 pt-3 pb-1 gap-2"):
                ui.label("QUEUE").style(
                    "font-size:0.68rem;font-weight:700;letter-spacing:0.12em;"
                    "color:#4b5563;text-transform:uppercase;flex:1"
                )
                queue_count_lbl = ui.label("0").classes("queue-count")

            # ── Filter / Sort / Group controls ────────────────────────────
            with ui.element("div").classes("sidebar-controls"):
                with ui.row().classes("items-center gap-1 w-full"):
                    filter_inp = (
                        ui.input(placeholder="Filter…")
                        .classes("sidebar-filter flex-1")
                        .props("dense outlined clearable")
                    )

                    with (
                        ui.button(icon="swap_vert")
                        .props("flat dense round size=sm")
                        .classes("sidebar-ctrl-btn") as sort_btn_el
                    ):
                        sort_btn_el.tooltip("Sort")
                        with ui.menu():
                            for _lbl, _val in [
                                ("Default order", "default"),
                                ("Ref  A → Z", "ref_az"),
                                ("Ref  Z → A", "ref_za"),
                                ("Date newest", "date_desc"),
                                ("Date oldest", "date_asc"),
                                ("Studio  A → Z", "studio_az"),
                                ("By status", "status"),
                                ("M/T first (mosaic)", "badge_m"),
                                ("中 first (translated)", "badge_zh"),
                                ("N first (new)", "badge_n"),
                                ("By download status", "dl_status"),
                            ]:
                                ui.menu_item(_lbl, on_click=lambda v=_val: _set_sort(v))

                    with (
                        ui.button(icon="workspaces")
                        .props("flat dense round size=sm")
                        .classes("sidebar-ctrl-btn") as group_btn_el
                    ):
                        group_btn_el.tooltip("Group by")
                        with ui.menu():
                            for _lbl, _val in [
                                ("No grouping", "none"),
                                ("By studio", "studio"),
                                ("By status", "status"),
                                ("By month", "month"),
                                ("By actor", "actor"),
                                ("By M/T (torrent)", "badge_mt"),
                                ("By 中 (translated)", "badge_zh"),
                                ("By download status", "dl_status"),
                            ]:
                                ui.menu_item(
                                    _lbl, on_click=lambda v=_val: _set_group(v)
                                )

                    ui.button(icon="tune").props("flat dense round size=sm").classes(
                        "sidebar-ctrl-btn"
                    ).tooltip("Subtitle config").on(
                        "click", lambda: subtitle_cfg_dialog.open()
                    )

                sort_indicator = ui.label("").classes("sort-indicator w-full")
                sort_indicator.set_visibility(False)

            sidebar_list = (
                ui.column()
                .classes("w-full gap-0 pb-4 sidebar-queue")
                .style("flex:1 1 0;overflow-y:auto;min-height:0")
            )

        # ── RIGHT: Inspector ──────────────────────────────────────────────────
        with ui.column().classes("inspector gap-0") as inspector_col:
            with ui.element("div").classes("insp-empty") as _init_empty:
                ui.icon("movie", size="6rem").style("color:#374151")
                ui.label("Search for a video to get started").style(
                    "font-size:1rem;color:#4b5563;margin-top:16px;font-weight:500"
                )
                ui.label("Enter a reference code in the sidebar").style(
                    "font-size:0.82rem;color:#374151;margin-top:6px"
                )

    _insp_placeholder: List = [_init_empty]  # tracks any visible empty-state div

    # ── Queue view state ──────────────────────────────────────────────────────

    _vs_saved = load_downloader_view_state()
    view_state: Dict[str, str] = {
        "sort": _vs_saved.get("sort", "default"),
        "group": _vs_saved.get("group", "none"),
        "filter": _vs_saved.get("filter", ""),
    }

    # subtitle_cfg: per sort/group key, list of fields shown alongside actresses
    # Field values: "actress" | "date" | "studio" | "status"
    # Empty list = show nothing extra
    _SC_DEFAULTS = default_downloader_subtitle_cfg()

    def _coerce_list(v):
        """Stored value may be old string 'none'/'date' or already a list."""
        if isinstance(v, list):
            return v
        if v in ("none", "", None):
            return []
        return [v]

    _sc_saved = load_downloader_subtitle_cfg()
    subtitle_cfg: Dict[str, Dict[str, list]] = {
        "sort": {
            k: _coerce_list(_sc_saved.get("sort", {}).get(k, v))
            for k, v in _SC_DEFAULTS["sort"].items()
        },
        "group": {
            k: _coerce_list(_sc_saved.get("group", {}).get(k, v))
            for k, v in _SC_DEFAULTS["group"].items()
        },
    }

    # ── Subtitle config dialog ────────────────────────────────────────────────
    _FIELD_OPTS = [
        ("Actress", "actress"),
        ("Date", "date"),
        ("Studio", "studio"),
        ("Status", "status"),
        ("DL Status", "dl_status"),
    ]
    _SORT_NAMES = [
        ("Default order", "default"),
        ("Ref A→Z", "ref_az"),
        ("Ref Z→A", "ref_za"),
        ("Date newest", "date_desc"),
        ("Date oldest", "date_asc"),
        ("Studio A→Z", "studio_az"),
        ("By status", "status"),
        ("M/T first", "badge_m"),
        ("中 first", "badge_zh"),
        ("N first", "badge_n"),
        ("By DL status", "dl_status"),
    ]
    _GROUP_NAMES = [
        ("No grouping", "none"),
        ("By studio", "studio"),
        ("By status", "status"),
        ("By month", "month"),
        ("By actor", "actor"),
        ("By M/T", "badge_mt"),
        ("By 中", "badge_zh"),
        ("By DL status", "dl_status"),
    ]

    with (
        ui.dialog() as subtitle_cfg_dialog,
        ui.card().style(
            "background:#0d0d11;border:1px solid #1a1a24;width:680px;max-width:95vw"
        ),
    ):
        ui.label("Subtitle context field").style(
            "font-weight:700;font-size:1rem;color:#c4b5fd;padding:4px 0 4px"
        )
        ui.label(
            "Choose what appears next to actor names for each sort / group mode."
        ).style("font-size:0.78rem;color:#6b7280;padding-bottom:12px")

        ui.label("Sort modes").style(
            "font-size:0.72rem;font-weight:700;color:#4b5563;letter-spacing:.08em;text-transform:uppercase;padding-bottom:6px"
        )
        with ui.element("div").style(
            "display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;width:100%"
        ):
            _sort_sels: Dict[str, any] = {}
            for _lbl, _key in _SORT_NAMES:
                with ui.row().classes("items-center gap-2").style("min-width:0"):
                    ui.label(_lbl).style(
                        "font-size:0.82rem;color:#9ca3af;flex:1;min-width:0;white-space:nowrap"
                    )
                    _sel = (
                        ui.select(
                            options={v: l for l, v in _FIELD_OPTS},
                            value=subtitle_cfg["sort"][_key],
                            multiple=True,
                        )
                        .props("dense outlined")
                        .style("width:160px")
                    )
                    _sort_sels[_key] = _sel

        ui.separator().style("margin:12px 0;border-color:#1a1a24")
        ui.label("Group modes").style(
            "font-size:0.72rem;font-weight:700;color:#4b5563;letter-spacing:.08em;text-transform:uppercase;padding-bottom:6px"
        )
        with ui.element("div").style(
            "display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;width:100%"
        ):
            _group_sels: Dict[str, any] = {}
            for _lbl, _key in _GROUP_NAMES:
                with ui.row().classes("items-center gap-2").style("min-width:0"):
                    ui.label(_lbl).style(
                        "font-size:0.82rem;color:#9ca3af;flex:1;min-width:0;white-space:nowrap"
                    )
                    _sel = (
                        ui.select(
                            options={v: l for l, v in _FIELD_OPTS},
                            value=subtitle_cfg["group"][_key],
                            multiple=True,
                        )
                        .props("dense outlined")
                        .style("width:160px")
                    )
                    _group_sels[_key] = _sel

        with ui.row().classes("justify-end gap-2 pt-4"):
            ui.button("Cancel", on_click=subtitle_cfg_dialog.close).props("flat").style(
                "color:#6b7280"
            )

            def _save_subtitle_cfg():
                for k, sel in _sort_sels.items():
                    subtitle_cfg["sort"][k] = list(sel.value) if sel.value else []
                for k, sel in _group_sels.items():
                    subtitle_cfg["group"][k] = list(sel.value) if sel.value else []
                persisted_cfg = {
                    "sort": {k: list(v) for k, v in subtitle_cfg["sort"].items()},
                    "group": {k: list(v) for k, v in subtitle_cfg["group"].items()},
                }
                set_downloader_subtitle_cfg(persisted_cfg)
                subtitle_cfg_dialog.close()
                apply_view()

            ui.button("Save", on_click=_save_subtitle_cfg).props("color=primary")

    group_label_els: Dict[str, any] = {}
    _collapsed_groups: set = set()

    _STATUS_RANK = {
        "downloaded": 0,
        "found": 1,
        "partial": 2,
        "done": 3,
        "error": 4,
        "pending": 5,
    }
    _STATUS_LABEL = {
        "downloaded": "Downloaded",
        "found": "Found",
        "partial": "Partial",
        "done": "Folder Created",
        "error": "Error",
        "pending": "Pending",
    }

    _DL_STATUS_SORT_RANK = {"downloading": 0, "paused": 1, "complete": 2, "none": 3}
    _DL_CAT_LABELS = {
        "downloading": "Downloading",
        "complete": "Complete / Seeding",
        "paused": "Paused / Queued",
        "none": "No Torrent",
    }

    def _get_item_status(h: dict) -> str:
        if h["state"].get("downloaded"):
            return "downloaded"
        if not h["state"].get("_populated"):
            return "pending"
        if h["state"].get("folder_path"):
            return "done"
        jav = h["state"].get("_jav_result")
        nyaa = h["state"].get("_nyaa_result")
        ok_meta = isinstance(jav, dict) and bool(jav)
        ok_nyaa = isinstance(nyaa, list)
        if ok_meta and ok_nyaa:
            return "found"
        if ok_meta or ok_nyaa:
            return "partial"
        return "error"

    def apply_view() -> None:
        """Re-apply filter, sort and group to the sidebar queue without rebuilding DOM."""
        from tracker.store import load_tracker, build_name_to_rating, resolve_ref_actress_lookup
        from utils.ui_ratings import get_actor_rank_html_span
        tracker_data = load_tracker()
        name_to_rating = build_name_to_rating(tracker_data)

        ftext = view_state["filter"].lower().strip()
        sort_key = view_state["sort"]
        group_key = view_state["group"]

        # ── Collect items with metadata needed for sort/group ──────────────
        items = []
        for kw, h in all_handles.items():
            jav = h["state"].get("_jav_result")
            jav = jav if isinstance(jav, dict) else {}
            status = _get_item_status(h)
            studio = jav.get("studio", "") or "Unknown"
            date = jav.get("date", "") or ""
            if ftext:
                haystack = " ".join(
                    [
                        kw,
                        jav.get("title", ""),
                        studio,
                        " ".join(jav.get("actresses", [])),
                    ]
                ).lower()
                match = ftext in haystack
            else:
                match = True
            has_mosaic = _has_mosaic_torrent(h)
            has_torrent = isinstance(h["state"].get("_nyaa_result"), list) and bool(
                h["state"].get("_nyaa_result")
            )
            has_trans = bool(h["state"].get("_translation"))
            is_new = not h["state"].get("_ever_selected", False)
            dl_category = h["state"].get("_dl_category", "none")
            items.append(
                {
                    "kw": kw,
                    "h": h,
                    "studio": studio,
                    "date": date,
                    "status": status,
                    "match": match,
                    "has_mosaic": has_mosaic,
                    "has_torrent": has_torrent,
                    "has_trans": has_trans,
                    "is_new": is_new,
                    "dl_category": dl_category,
                }
            )

        # ── Sort ──────────────────────────────────────────────────────────
        if sort_key == "ref_az":
            items.sort(key=lambda i: i["kw"])
        elif sort_key == "ref_za":
            items.sort(key=lambda i: i["kw"], reverse=True)
        elif sort_key == "date_desc":
            items.sort(key=lambda i: i["date"], reverse=True)
        elif sort_key == "date_asc":
            items.sort(key=lambda i: i["date"])
        elif sort_key == "studio_az":
            items.sort(key=lambda i: i["studio"].lower())
        elif sort_key == "status":
            items.sort(key=lambda i: _STATUS_RANK.get(i["status"], 99))
        elif sort_key == "badge_m":
            # M first, then T, then others
            def _badge_m_rank(i):
                if i["has_mosaic"]:
                    return 0
                if i["has_torrent"]:
                    return 1
                return 2

            items.sort(key=_badge_m_rank)
        elif sort_key == "badge_zh":
            items.sort(key=lambda i: (0 if i["has_trans"] else 1))
        elif sort_key == "badge_n":
            items.sort(key=lambda i: (0 if i["is_new"] else 1))
        elif sort_key == "dl_status":
            items.sort(key=lambda i: _DL_STATUS_SORT_RANK.get(i["dl_category"], 99))

        # ── Update count badge ────────────────────────────────────────────
        visible_n = sum(1 for i in items if i["match"])
        total_n = len(items)
        queue_count_lbl.text = f"{visible_n}/{total_n}" if ftext else str(total_n)

        # ── Assign CSS flex order (+ visibility) ──────────────────────────
        if group_key == "none":
            for grp in group_label_els.values():
                grp["row"].set_visibility(False)
            for idx, item in enumerate(items):
                item["h"]["row_el"].set_visibility(item["match"])
                item["h"]["row_el"].style(f"order:{idx}")
        else:
            if group_key == "studio":

                def group_fn(i):
                    return i["studio"]
            elif group_key == "month":

                def group_fn(i):
                    d = i["date"]
                    return d[:7] if d and len(d) >= 7 else "Unknown"
            elif group_key == "actor":

                def group_fn(i):
                    jav_d = i["h"]["state"].get("_jav_result")
                    if isinstance(jav_d, dict):
                        acts = jav_d.get("actresses", [])
                        if acts:
                            return acts[0]
                    return "Unknown"
            elif group_key == "badge_mt":

                def group_fn(i):
                    if i["has_mosaic"]:
                        return "M — Mosaic / Uncensor"
                    if i["has_torrent"]:
                        return "T — Has Torrents"
                    return "— No Torrents"
            elif group_key == "badge_zh":

                def group_fn(i):
                    return "中 — Translated" if i["has_trans"] else "— Not Translated"
            elif group_key == "dl_status":

                def group_fn(i):
                    return _DL_CAT_LABELS.get(i["dl_category"], "No Torrent")
            else:  # status

                def group_fn(i):
                    return _STATUS_LABEL.get(i["status"], i["status"].title())

            grouped: Dict[str, list] = {}
            for item in items:
                if item["match"]:
                    g = group_fn(item)
                    grouped.setdefault(g, []).append(item)
                else:
                    item["h"]["row_el"].set_visibility(False)

            sorted_groups = sorted(grouped.keys(), key=_romaji_key)
            active_groups = set(sorted_groups)
            order = 0
            for g in sorted_groups:
                is_collapsed = g in _collapsed_groups
                count = len(grouped[g])
                if g not in group_label_els:
                    with sidebar_list:
                        with ui.row().classes(
                            "queue-group-hdr-row w-full items-center gap-1"
                        ) as _grp_row:
                            _grp_chevron = ui.icon("expand_more", size="xs").style(
                                "color:#4b5563;flex-shrink:0"
                            )
                            _grp_lbl = ui.label("").classes("queue-group-hdr-lbl")

                        def _make_toggle(gname):
                            def _toggle():
                                if gname in _collapsed_groups:
                                    _collapsed_groups.discard(gname)
                                else:
                                    _collapsed_groups.add(gname)
                                apply_view()
                            return _toggle

                        _grp_row.on("click", _make_toggle(g))
                        group_label_els[g] = {
                            "row": _grp_row,
                            "chevron": _grp_chevron,
                            "label": _grp_lbl,
                        }
                grp = group_label_els[g]
                grp["row"].set_visibility(True)
                grp["label"].text = f"{g.upper()}  ({count})"
                grp["chevron"].props(
                    f'name={"chevron_right" if is_collapsed else "expand_more"}'
                )
                grp["row"].style(f"order:{order}")
                order += 1
                for item in grouped[g]:
                    item["h"]["row_el"].set_visibility(not is_collapsed)
                    item["h"]["row_el"].style(f"order:{order}")
                    order += 1
            for g, grp in group_label_els.items():
                if g not in active_groups:
                    grp["row"].set_visibility(False)

        # ── Update subtitle from list-based subtitle_cfg ──────────────────────
        # Merge sort fields + group fields, deduped, preserving order
        sort_fields = list(subtitle_cfg["sort"].get(sort_key, []))
        group_fields = list(subtitle_cfg["group"].get(group_key, []))
        seen = set()
        ctx_fields = []
        for f in sort_fields + group_fields:
            if f not in seen:
                seen.add(f)
                ctx_fields.append(f)

        def _resolve_field(
            field: str,
            jav: dict,
            actresses: list,
            status: str,
            dl_cat: str = "none",
            ref_id: str = "",
        ) -> str:
            if field == "actress":
                if not actresses:
                    return ""
                from utils.ui_ratings import get_actor_rank_html_span
                ref_lookup = resolve_ref_actress_lookup(tracker_data, ref_id, actresses)
                spans = []
                for actress_name in actresses[:2]:
                    rating, _actress_id = ref_lookup.get(
                        actress_name,
                        (name_to_rating.get(actress_name), None),
                    )
                    spans.append(
                        get_actor_rank_html_span(
                            actress_name,
                            {actress_name: rating} if rating is not None else {},
                        )
                    )
                return ", ".join(spans)
            if field == "date":
                return jav.get("date", "") or ""
            if field == "studio":
                return jav.get("studio", "") or ""
            if field == "status":
                return _STATUS_LABEL.get(status, "")
            if field == "dl_status":
                return _DL_CAT_LABELS.get(dl_cat, "")
            return ""

        for item in items:
            slbl = item["h"].get("subtitle_lbl")
            if slbl is None:
                continue
            jav = item["h"]["state"].get("_jav_result")
            jav = jav if isinstance(jav, dict) else {}
            actresses = jav.get("actresses", [])

            parts = [
                _resolve_field(
                    f,
                    jav,
                    actresses,
                    item["status"],
                    item.get("dl_category", "none"),
                    item["kw"],
                )
                for f in ctx_fields
            ]
            parts = [p for p in parts if p]
            sub = "  ·  ".join(parts)
            if hasattr(slbl, 'content'):
                slbl.content = sub
            else:
                slbl.text = sub
            slbl.set_visibility(bool(sub))

    _SORT_LABELS_DISPLAY = {
        "default": "",
        "ref_az": "Ref A→Z",
        "ref_za": "Ref Z→A",
        "date_desc": "Date newest",
        "date_asc": "Date oldest",
        "studio_az": "Studio A→Z",
        "status": "Status",
        "badge_m": "M/T first",
        "badge_zh": "中 first",
        "badge_n": "N first",
        "dl_status": "DL Status",
    }
    _GROUP_LABELS_DISPLAY = {
        "none": "",
        "studio": "Studio",
        "status": "Status",
        "month": "Month",
        "actor": "Actor",
        "badge_mt": "M/T",
        "badge_zh": "中",
        "dl_status": "DL Status",
    }

    def _update_sort_group_label() -> None:
        parts = []
        s = view_state["sort"]
        g = view_state["group"]
        if s != "default":
            parts.append(f"↕  {_SORT_LABELS_DISPLAY[s]}")
        if g != "none":
            parts.append(f"≡  {_GROUP_LABELS_DISPLAY[g]}")
        sort_indicator.text = "  ·  ".join(parts)
        sort_indicator.set_visibility(bool(parts))

    def _set_sort(val: str) -> None:
        view_state["sort"] = val
        set_downloader_view_state(dict(view_state))
        if val == "default":
            sort_btn_el.classes(remove="active-ctrl")
        else:
            sort_btn_el.classes(add="active-ctrl")
        _update_sort_group_label()
        apply_view()

    def _set_group(val: str) -> None:
        _collapsed_groups.clear()
        view_state["group"] = val
        set_downloader_view_state(dict(view_state))
        if val == "none":
            group_btn_el.classes(remove="active-ctrl")
        else:
            group_btn_el.classes(add="active-ctrl")
        _update_sort_group_label()
        apply_view()

    def _on_filter(e=None) -> None:
        view_state["filter"] = filter_inp.value or ""
        set_downloader_view_state(dict(view_state))
        apply_view()

    filter_inp.on_value_change(_on_filter)
    filter_inp.on("clear", _on_filter)

    # ── Restore translation panel from cached state ───────────────────────────

    def _populate_translation(h: dict) -> None:
        """Restore name choices + LLM button from cached translation."""
        response = h["state"].get("_translation")
        if not response or h.get("name_sel") is None:
            return
        blocks = extract_code_blocks(response)
        old_choices = h["state"].get("_name_choices", [])
        custom_choices = [
            c for c in old_choices if c.get("value", "").startswith("custom_")
        ]
        new_trans = [{"label": b, "value": f"trans_{i}"} for i, b in enumerate(blocks)]
        h["state"]["_name_choices"] = new_trans + custom_choices
        rebuild = h.get("_rebuild_name_options")
        if rebuild:
            rebuild()
        if new_trans and not h["name_sel"].value:
            h["name_sel"].value = new_trans[0]["label"]
        if h.get("view_trans_btn") is not None:
            h["view_trans_btn"].set_visibility(True)

    # ── Inspector switch ──────────────────────────────────────────────────────

    def _resume_inspector_dl_polling(h: dict, force_once: bool = False) -> None:
        ensure_polling = h.get("ensure_dl_polling")
        if ensure_polling:
            ensure_polling(force_once=force_once)

    def show_inspector(kw: str) -> None:
        """Switch the right panel to show a given keyword's data."""
        # Deactivate old sidebar item
        old = active_kw[0]
        if old and old in all_handles:
            all_handles[old]["row_el"].classes(remove="active")
            # Hide old inspector wrap (cancel per-item timers too)
            old_wrap = all_handles[old].get("inspector_wrap")
            if old_wrap is not None:
                old_wrap.set_visibility(False)
            # Suspend DL progress polling timer for the outgoing inspector
            old_timer = all_handles[old].get("dl_timer")
            if old_timer is not None:
                old_timer.cancel()
                all_handles[old]["dl_timer"] = None
            old_once = all_handles[old].get("dl_timer_once")
            if old_once is not None:
                old_once.cancel()
                all_handles[old]["dl_timer_once"] = None
        active_kw[0] = kw

        h = all_handles.get(kw)
        if not h:
            return

        h["row_el"].classes(add="active")
        # Mark as ever-selected and hide N badge immediately
        h["state"]["_ever_selected"] = True
        if h.get("badge_n") is not None:
            h["badge_n"].set_visibility(False)

        # Remove the empty-state placeholder if it's still in the panel
        if _insp_placeholder[0] is not None:
            _insp_placeholder[0].delete()
            _insp_placeholder[0] = None

        already_built = h.get("inspector_wrap") is not None
        if not already_built:
            # First visit — create a per-handle wrapper div, build into it
            with inspector_col:
                inspector_wrap = ui.element("div").style(
                    "width:100%"
                ).classes("insp-first-build")
            h["inspector_wrap"] = inspector_wrap
            _attach_inspector(h, inspector_wrap)
            if h["state"].get("_populated") and isinstance(h["state"].get("_jav_result"), dict):
                _populate_inspector(
                    h, h["state"]["_jav_result"], h["state"]["_nyaa_result"]
                )
            if h["state"].get("_translation"):
                _populate_translation(h)
            # Wire refresh buttons once on first build
            if h.get("refresh_meta_btn") is not None:
                _wire_refetch_buttons(h)
            # Badges are accurate from the build; drop the animation class after one frame
            _update_badges(h)
            _resume_inspector_dl_polling(h, force_once=True)
            with client:  # provide slot context — avoids crash when called from asyncio.gather
                ui.timer(0.2, lambda iw=inspector_wrap: iw.classes(remove="insp-first-build"), once=True)
        else:
            # Already built — just reveal the cached wrap instantly (no DOM work)
            h["inspector_wrap"].set_visibility(True)
            _resume_inspector_dl_polling(h, force_once=True)

    # ── Confirm-delete dialog (built once, reused) ───────────────────────────
    _confirm_ctx: List[dict] = [{}]

    with ui.dialog() as _confirm_dialog, ui.card().style(
        "background:#0d0d11;border:1px solid #1a1a24;min-width:320px"
    ):
        _confirm_title = ui.label("").style(
            "font-size:1rem;font-weight:700;color:#f3f4f6;padding:4px 0 8px"
        )
        _confirm_note = ui.label("Removes from queue only. Files on disk are kept.").style(
            "font-size:0.8rem;color:#9ca3af;padding-bottom:8px"
        )
        with ui.row().classes("justify-end gap-2 pt-2"):
            ui.button("Cancel", on_click=_confirm_dialog.close).props("flat")

            def _on_confirm_delete():
                ctx = _confirm_ctx[0]
                kw = ctx.get("kw")
                if kw:
                    h = all_handles.get(kw)
                    if h:
                        # Cancel per-item timers so they don't fire after deletion
                        for tkey in ("dl_timer", "dl_timer_once"):
                            t = h.get(tkey)
                            if t:
                                t.cancel()
                        # Remove the sidebar row from the DOM
                        row_el = h.get("row_el")
                        if row_el:
                            row_el.delete()
                        # Clear the inspector if this item was active
                        if active_kw[0] == kw:
                            active_kw[0] = None
                            # Delete only this handle's wrap — keep other handles' cached wraps intact
                            wrap = h.get("inspector_wrap")
                            if wrap:
                                wrap.delete()
                            else:
                                inspector_col.clear()
                            with inspector_col:
                                with ui.element("div").classes("insp-empty") as _del_empty:
                                    ui.icon("movie", size="4rem").style("color:#374151")
                                    ui.label("Add a video to the queue to get started").style(
                                        "font-size:0.85rem;color:#4b5563;margin-top:12px"
                                    )
                            _insp_placeholder[0] = _del_empty
                        else:
                            # Not the active item — delete its wrap silently
                            wrap = h.get("inspector_wrap")
                            if wrap:
                                wrap.delete()
                    all_handles.pop(kw, None)
                    _session_save(all_handles)  # builds cache clean \u2014 deleted item excluded automatically
                    prune_orphaned_refs(app.storage.user, [kw])
                    apply_view()
                _confirm_dialog.close()

            ui.button("Delete", on_click=_on_confirm_delete).props("color=negative")

    def _do_remove(kw: str, row_element, ah: dict) -> None:
        h = ah.get(kw, {})
        folder_path = h.get("state", {}).get("folder_path")
        _confirm_ctx[0] = {
            "kw": kw,
            "folder_path": str(folder_path) if folder_path else None,
        }
        _confirm_title.text = f"Delete {kw}?"
        _confirm_dialog.open()

    # ── Internal: enqueue + search one keyword ──────────────────────────────

    async def _enqueue_and_search(
        kw: str,
        auto_select: bool = False,
        ever_selected: bool = False,
        skip_live_fetch: bool = False,
        persist_session: bool = True,
        refresh_view: bool = True,
        cache_snapshot: Optional[dict] = None,
    ) -> None:
        """Add kw to queue (if not present) and fire its search.

        skip_live_fetch=True (used during session restore): if no cache hit is
        found the item is still enqueued but no live scraper is launched.  The
        queue row shows a red dot so the user can re-fetch manually.
        """
        if kw in all_handles:
            return  # already queued — skip

        h = _build_queue_entry(
            kw, sidebar_list, all_handles, show_inspector, apply_view, _do_remove
        )
        _hydrate_downloaded_state_from_tracker(h, kw)

        # Restore ever_selected BEFORE any _update_badges call
        if ever_selected:
            h["state"]["_ever_selected"] = True

        if auto_select or active_kw[0] is None:
            show_inspector(kw)

        # Show loading spinner while fetching
        h["status_dot"].set_visibility(False)
        h["status_spinner"].set_visibility(True)

        # Use cached results if available (avoids re-scraping on restore)
        cache_source = cache_snapshot if isinstance(cache_snapshot, dict) else load_downloader_cache()
        cached = dict(cache_source.get(kw) or {})
        if not cached.get("jav"):
            _hydrate_session_metadata_from_tracker(kw)
            cache_source = cache_snapshot if isinstance(cache_snapshot, dict) else load_downloader_cache()
            cached = dict(cache_source.get(kw) or {})
        if cached and cached.get("jav"):
            jav_result = cached["jav"]
            nyaa_result = cached.get("nyaa") or []
            if cached.get("translation"):
                h["state"]["_translation"] = cached["translation"]
            if cached.get("name_choices"):
                h["state"]["_name_choices"] = cached["name_choices"]
            if cached.get("selected_name"):
                h["state"]["_selected_name"] = cached["selected_name"]
        elif skip_live_fetch:
            # Restore path: item has no cached metadata — enqueue it without
            # launching the scraper.  The red status dot signals the user to
            # re-fetch manually (individual refresh button or mass re-fetch).
            jav_result = None
            nyaa_result = []
        else:
            try:
                jav_result, nyaa_result = await _fetch_one(kw)
            except Exception as exc:
                jav_result = exc
                nyaa_result = exc

        h["state"]["_jav_result"] = jav_result
        h["state"]["_nyaa_result"] = nyaa_result
        h["state"]["_populated"] = True

        # Hide spinner, show result dot
        h["status_spinner"].set_visibility(False)
        h["status_dot"].set_visibility(True)
        ok_meta = not isinstance(jav_result, Exception) and bool(jav_result)
        ok_nyaa = isinstance(nyaa_result, list)
        if not h["state"].get("downloaded"):
            if ok_meta and ok_nyaa:
                h["status_dot"].style("color:#22c55e").props("name=circle")
            elif ok_meta or ok_nyaa:
                h["status_dot"].style("color:#f59e0b").props("name=circle")
            else:
                h["status_dot"].style("color:#ef4444").props("name=cancel")

        if active_kw[0] == kw and h.get("title_lbl") is not None:
            _populate_inspector(h, jav_result, nyaa_result)
            if h["state"].get("_translation"):
                _populate_translation(h)

        _update_badges(h)
        if persist_session:
            _session_save(all_handles)
        if h.get("refresh_meta_btn") is not None:
            _wire_refetch_buttons(h)
        if refresh_view:
            apply_view()

    # ── Re-fetch handlers (wired per-item after inspector is built) ────────────

    async def _mass_refetch_meta() -> None:
        """Re-scrape metadata for every queued item (parallel, pool-gated)."""
        handles = [h for h in all_handles.values() if not h["state"].get("downloaded")]
        if not handles:
            ui.notify("Nothing to re-fetch.", color="info")
            return
        mass_meta_btn.props("disable=true")
        _cfg = load_config()
        source = resolve_metadata_source(_cfg.get("metadata_source", "javdb"))
        source_lbl = "JAVLib" if source == "javlibrary" else "JAVDB"
        total = len(handles)
        done = [0]
        ok_count = [0]
        fail_count = [0]
        cooldown_notice = [False]

        async def _refetch_one_meta(h: dict) -> None:
            kw = h["keyword"]
            if kw not in all_handles:
                done[0] += 1
                return
            h["status_dot"].set_visibility(False)
            h["status_spinner"].set_visibility(True)
            clear_downloader_cached_ref(kw, clear_meta=True)
            try:
                jav_result = await fetch_jav_metadata(kw, source=source)
            except Exception as exc:
                jav_result = exc
            cooldown_notice[0] = cooldown_notice[0] or (
                source == "javlibrary" and get_rate_limit_cooldown_seconds(jav_result) is not None
            )
            done[0] += 1
            # Item may have been deleted while we were scraping
            if kw not in all_handles:
                return
            ok_meta = not isinstance(jav_result, Exception) and bool(jav_result)
            if ok_meta:
                ok_count[0] += 1
            else:
                fail_count[0] += 1
            progress_lbl.content = (
                f"Re-fetching metadata via {source_lbl}  ·  "
                f"{done[0]} of {total}  —  {ok_count[0]} ✓  {fail_count[0]} ✗"
            )
            h["state"]["_jav_result"] = jav_result
            h["state"]["_populated"] = True
            h["status_spinner"].set_visibility(False)
            h["status_dot"].set_visibility(True)
            if not h["state"].get("downloaded"):
                ok_nyaa = isinstance(h["state"].get("_nyaa_result"), list)
                if ok_meta and ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#22c55e")
                elif ok_meta or ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#f59e0b")
                else:
                    h["status_dot"].props("name=cancel").style("color:#ef4444")
            if active_kw[0] == kw and h.get("title_lbl") is not None:
                nyaa = h["state"].get("_nyaa_result")
                _populate_inspector(h, jav_result, nyaa)
            _update_badges(h)

        await asyncio.gather(*[_refetch_one_meta(h) for h in handles])
        _session_save(all_handles)
        apply_view()
        try:
            mass_meta_btn.props("disable=false")
        except Exception:
            pass
        try:
            progress_lbl.content = ""
        except Exception:
            pass
        try:
            ui.notify(
                f"Metadata re-fetched  ·  {ok_count[0]} succeeded, {fail_count[0]} failed",
                color="positive" if fail_count[0] == 0 else "warning",
            )
        except Exception:
            pass
        if cooldown_notice[0]:
            try:
                cooldown_seconds = get_rate_limit_cooldown_seconds()
                if cooldown_seconds is not None:
                    ui.notify(
                        f"JAVLibrary cooling down for ~{cooldown_seconds}s. Metadata retries are queued in memory; current requests fall back to JAVDB.",
                        color="warning",
                        timeout=5000,
                    )
            except Exception:
                pass

    async def _mass_refetch_nyaa() -> None:
        """Re-fetch Nyaa torrents for every queued item. Max 3 concurrent to avoid rate-limiting."""
        handles = [h for h in all_handles.values()]
        if not handles:
            ui.notify("Nothing to re-fetch.", color="info")
            return
        mass_nyaa_btn.props("disable=true")
        total = len(handles)
        done = [0]
        ok_count = [0]
        fail_count = [0]
        nyaa_sem = asyncio.Semaphore(3)

        async def _fetch_one_nyaa(h: dict) -> None:
            kw = h["keyword"]
            # Item may have been deleted before we even acquired the semaphore
            if kw not in all_handles:
                done[0] += 1
                return
            async with nyaa_sem:
                # Check again after waiting for semaphore
                if kw not in all_handles:
                    done[0] += 1
                    return
                try:
                    result = await asyncio.to_thread(search_nyaa, kw)
                except Exception as exc:
                    result = exc
                # Small delay between acquisitions to be polite to Nyaa
                await asyncio.sleep(1.5)
            done[0] += 1
            # Item may have been deleted while we were waiting on Nyaa
            if kw not in all_handles:
                return
            ok_nyaa = isinstance(result, list)
            if ok_nyaa:
                ok_count[0] += 1
            else:
                fail_count[0] += 1
            progress_lbl.content = (
                f"Re-fetching Nyaa torrents  ·  {kw}  ·  "
                f"{done[0]} of {total}  —  {ok_count[0]} ✓  {fail_count[0]} ✗"
            )
            h["state"]["_nyaa_result"] = result
            if h.get("torrent_table") is not None and ok_nyaa:
                rows = [
                    {
                        "name": t["name"], "size": t["size"],
                        "seeders": t["seeders"], "leechers": t["leechers"],
                        "magnet": t.get("magnet", ""), "torrent": t.get("torrent", ""),
                    }
                    for t in result
                ]
                h["torrent_table"].rows = rows
                if h.get("torrent_hdr"):
                    h["torrent_hdr"].text = f"TORRENTS  ({len(rows)})"
            if not h["state"].get("downloaded"):
                ok_meta = not isinstance(h["state"].get("_jav_result"), Exception) and bool(h["state"].get("_jav_result"))
                if ok_meta and ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#22c55e")
                elif ok_meta or ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#f59e0b")
                else:
                    h["status_dot"].props("name=cancel").style("color:#ef4444")
            _update_badges(h)

        await asyncio.gather(*[_fetch_one_nyaa(h) for h in handles])
        _session_save(all_handles)
        apply_view()
        try:
            mass_nyaa_btn.props("disable=false")
        except Exception:
            pass
        try:
            progress_lbl.content = ""
        except Exception:
            pass
        try:
            ui.notify(
                f"Nyaa re-fetched  ·  {ok_count[0]} found, {fail_count[0]} empty/failed",
                color="positive" if fail_count[0] == 0 else "warning",
            )
        except Exception:
            pass

    mass_meta_btn.on_click(_mass_refetch_meta)
    mass_nyaa_btn.on_click(_mass_refetch_nyaa)

    # ── Mass translate ────────────────────────────────────────────────────────
    def _untranslated_handles() -> list:
        """Return handles that have JAV metadata but no translations yet."""
        return [
            h for h in all_handles.values()
            if not (bool(h["state"].get("_translation")) or bool(h["state"].get("_name_choices")))
            and bool(h["state"].get("_jav_result") or h["state"].get("jav"))
        ]

    def _open_mass_youcom_dialog() -> None:
        targets = _untranslated_handles()
        if not targets:
            ui.notify("All items are already translated.", color="info")
            return

        with ui.dialog() as yc_dlg, ui.card().style(
            "min-width:520px;max-width:700px;max-height:80vh;display:flex;flex-direction:column"
        ):
            with ui.row().classes("items-center justify-between w-full q-mb-sm"):
                ui.label(f"You.com — {len(targets)} untranslated").classes("text-h6")
                ui.button(icon="close", on_click=yc_dlg.close).props("flat round dense")

            ui.label(
                "Open each item in You.com for manual translation, "
                "then paste results back via the individual Translate panel."
            ).classes("text-caption text-grey-6 q-mb-md")

            def _open_all_yc():
                for _h in targets:
                    jav = _h["state"].get("_jav_result") or _h["state"].get("jav")
                    if not jav:
                        continue
                    webbrowser.open(
                        _build_youcom_url(
                            jav.get("title", ""),
                            jav.get("date", ""),
                            jav.get("actresses", []),
                            _h["keyword"],
                        )
                    )

            ui.button(
                "Open All in Browser", icon="open_in_browser", on_click=_open_all_yc
            ).props("unelevated color=primary size=sm").classes("q-mb-md self-start")

            with ui.scroll_area().style("flex:1;overflow-y:auto"):
                for _h in targets:
                    jav = _h["state"].get("_jav_result") or _h["state"].get("jav")
                    kw = _h["keyword"]
                    title_str = jav.get("title", "") if jav else ""
                    short_title = title_str[:48] + ("…" if len(title_str) > 48 else "")
                    yc_url = _build_youcom_url(
                        title_str,
                        jav.get("date", "") if jav else "",
                        jav.get("actresses", []) if jav else [],
                        kw,
                    )

                    with ui.row().classes("items-center gap-2 w-full").style(
                        "padding:4px 0;border-bottom:1px solid #2a2a2a"
                    ):
                        ui.label(kw).classes("text-weight-bold").style(
                            "min-width:90px;font-size:0.82rem;color:#818cf8"
                        )
                        ui.label(short_title).classes("text-caption text-grey-5").style(
                            "flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis"
                        )
                        ui.button(
                            icon="open_in_new",
                            on_click=lambda u=yc_url: webbrowser.open(u),
                        ).props("flat round dense").tooltip(f"Open {kw} in You.com")

            with ui.row().classes("justify-end q-mt-sm"):
                ui.button("Close", on_click=yc_dlg.close).props("flat size=sm")

        yc_dlg.open()

    async def _mass_translate_api() -> None:
        targets = _untranslated_handles()
        if not targets:
            ui.notify("All items are already translated.", color="info")
            return

        # Validate config up-front while still in the main NiceGUI context
        _cfg = load_config()
        if not _cfg.get("api_key"):
            ui.notify(
                "API key is empty — open ⚙ Settings, re-enter your key and Save.",
                color="negative",
                timeout=6000,
            )
            return
        concurrency = max(1, int(_cfg.get("trans_concurrency", 3)))
        trans_sem = asyncio.Semaphore(concurrency)

        mass_trans_btn.props("disable=true")
        total = len(targets)
        done = [0]
        ok_count = [0]
        fail_count = [0]
        active_kws: set = set()
        errors: list = []

        def _refresh_progress() -> None:
            kws_html = "".join(
                f"<span style='color:#818cf8;font-weight:600;margin-left:6px'>{kw}</span>"
                for kw in sorted(active_kws)
            )
            sep = "<span style='color:#374151;margin:0 4px'>·</span>"
            try:
                progress_lbl.content = (
                    f"<span style='color:#a78bfa;font-weight:700;letter-spacing:.02em'>"
                    f"⟳ Translating</span>"
                    f"{(' ' + sep + kws_html) if active_kws else ''}"
                    f"<span style='color:#475569'>{sep}{done[0]}/{total}</span>"
                    f"<span style='color:#22c55e;font-weight:600;margin-left:6px'>"
                    f"✓ {ok_count[0]}</span>"
                    f"<span style='color:#ef4444;font-weight:600;margin-left:4px'>"
                    f"✗ {fail_count[0]}</span>"
                )
            except Exception:
                pass

        async def _translate_one(h: dict) -> None:
            kw = h["keyword"]
            if kw not in all_handles:
                done[0] += 1
                return
            async with trans_sem:
                if kw not in all_handles:
                    done[0] += 1
                    return
                jav = h["state"].get("_jav_result") or h["state"].get("jav")
                if not jav:
                    done[0] += 1
                    return
                active_kws.add(kw)
                _refresh_progress()
                try:
                    response = await translate_title(
                        title=jav.get("title", ""),
                        date=jav.get("date", ""),
                        actresses=jav.get("actresses", []),
                        ref_id=kw,
                        config=_cfg,
                    )
                    blocks = extract_code_blocks(response)
                    old_choices = h["state"].get("_name_choices", [])
                    custom_choices = [
                        c for c in old_choices if c.get("value", "").startswith("custom_")
                    ]
                    new_trans = [
                        {"label": block, "value": f"trans_{i}"}
                        for i, block in enumerate(blocks)
                    ]
                    h["state"]["_name_choices"] = new_trans + custom_choices
                    h["state"]["_translation"] = response
                    ok_count[0] += 1  # count success before UI updates
                    # UI updates — best-effort; client may have navigated away
                    try:
                        if new_trans and h.get("name_sel") is not None:
                            h["name_sel"].value = new_trans[0]["label"]
                        if h.get("llm_resp_btn") is not None:
                            h["llm_resp_btn"].set_visibility(True)
                        if h.get("view_trans_btn") is not None:
                            h["view_trans_btn"].set_visibility(True)
                        _update_badges(h)
                    except Exception:
                        pass
                except Exception as exc:
                    # LLM/API errors only — UI errors are caught above
                    fail_count[0] += 1
                    errors.append(f"{kw}: {exc}")
                finally:
                    active_kws.discard(kw)
                    done[0] += 1
                    _refresh_progress()

        async def _run_batch() -> None:
            await asyncio.gather(*[_translate_one(h) for h in targets])
            _session_save(all_handles)
            try:
                apply_view()
            except Exception:
                pass
            try:
                mass_trans_btn.props("disable=false")
            except Exception:
                pass
            try:
                progress_lbl.content = ""
            except Exception:
                pass
            for err in errors:
                try:
                    ui.notify(err, color="negative", timeout=6000)
                except Exception:
                    pass
            try:
                ui.notify(
                    f"Translation done  ·  {ok_count[0]} succeeded, {fail_count[0]} failed",
                    color="positive" if fail_count[0] == 0 else "warning",
                )
            except Exception:
                pass

        # Detach from NiceGUI's per-client task tracker so navigating away
        # (e.g. to /organiser) won't cancel the in-flight batch.
        asyncio.ensure_future(_run_batch())

    with ui.dialog() as mass_trans_dialog, ui.card().style("min-width:360px"):
        ui.label("Translate All Untranslated").classes("text-h6 q-mb-xs")
        ui.label(
            "Items with 中 badge are skipped. Choose how to translate the rest."
        ).classes("text-caption text-grey-6 q-mb-md")
        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button("Cancel", on_click=mass_trans_dialog.close).props("flat size=sm")

            async def _choose_api():
                mass_trans_dialog.close()
                await _mass_translate_api()

            ui.button("You.com", icon="open_in_new").props(
                "flat size=sm"
            ).on_click(lambda: (mass_trans_dialog.close(), _open_mass_youcom_dialog()))

            ui.button("API", icon="translate").props(
                "unelevated color=primary size=sm"
            ).on_click(_choose_api)

    mass_trans_btn.on_click(mass_trans_dialog.open)

    def _wire_refetch_buttons(h: dict) -> None:
        kw = h["keyword"]
        # Store active_kw reference so do_translate (defined in _attach_inspector) can read it
        h["_active_kw"] = active_kw

        async def _refetch_meta() -> None:
            if not h.get("refresh_meta_btn"):
                return
            h["refresh_meta_btn"].props("disable=true")
            h["spinner_top"].set_visibility(True)
            # Bust cache for meta only
            clear_downloader_cached_ref(kw, clear_meta=True)
            try:
                _cfg = load_config()
                source = resolve_metadata_source(_cfg.get("metadata_source", "javdb"))
                jav_result = await fetch_jav_metadata(
                    kw,
                    source=source,
                )
            except Exception as exc:
                jav_result = exc
                source = resolve_metadata_source(load_config().get("metadata_source", "javdb"))
            h["state"]["_jav_result"] = jav_result
            h["spinner_top"].set_visibility(False)
            h["refresh_meta_btn"].props("disable=false")
            cooldown_seconds = (
                get_rate_limit_cooldown_seconds(jav_result)
                if source == "javlibrary"
                else None
            )
            if not isinstance(jav_result, Exception) and h.get("title_lbl") is not None:
                nyaa = h["state"].get("_nyaa_result")  # pass raw so _populate_inspector sees None/Exception correctly
                _populate_inspector(h, jav_result, nyaa)
                if cooldown_seconds is not None:
                    ui.notify(
                        f"JAVLibrary cooling down for ~{cooldown_seconds}s. Metadata retry queued in memory; this refresh used JAVDB fallback.",
                        color="warning",
                        timeout=5000,
                    )
            else:
                # Meta failed — update dot to reflect current combined state
                if not h["state"].get("downloaded"):
                    ok_nyaa = isinstance(h["state"].get("_nyaa_result"), list)
                    if ok_nyaa:
                        h["status_dot"].props("name=circle").style("color:#f59e0b")
                    else:
                        h["status_dot"].props("name=cancel").style("color:#ef4444")
                if cooldown_seconds is not None:
                    ui.notify(
                        f"JAVLibrary cooling down for ~{cooldown_seconds}s. Metadata retry queued in memory; current requests fall back to JAVDB.",
                        color="warning",
                        timeout=5000,
                    )
            _update_badges(h)
            _session_save(all_handles)

        async def _refetch_nyaa() -> None:
            if not h.get("refresh_nyaa_btn"):
                return
            h["refresh_nyaa_btn"].props("disable=true")
            h["torrent_spinner"].set_visibility(True)
            h["torrent_table"].props(add="loading")
            h["torrent_hdr"].text = "TORRENTS — fetching…"
            try:
                nyaa_result = await asyncio.to_thread(search_nyaa, kw)
            except Exception as exc:
                nyaa_result = exc
            h["state"]["_nyaa_result"] = nyaa_result
            h["torrent_spinner"].set_visibility(False)
            h["torrent_table"].props(remove="loading")
            h["refresh_nyaa_btn"].props("disable=false")
            if (
                not isinstance(nyaa_result, Exception)
                and h.get("torrent_table") is not None
            ):
                rows = [
                    {
                        "name": t["name"],
                        "size": t["size"],
                        "seeders": t["seeders"],
                        "leechers": t["leechers"],
                        "magnet": t.get("magnet", ""),
                        "torrent": t.get("torrent", ""),
                    }
                    for t in nyaa_result
                ]
                h["torrent_table"].rows = rows
                h["torrent_hdr"].text = f"TORRENTS  ({len(rows)})"
            else:
                h["torrent_hdr"].text = "TORRENTS — fetch error"
            # Update status dot to reflect new combined ok/fail state
            if not h["state"].get("downloaded"):
                ok_meta = not isinstance(h["state"].get("_jav_result"), Exception) and bool(h["state"].get("_jav_result"))
                ok_nyaa = isinstance(nyaa_result, list)
                if ok_meta and ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#22c55e")
                elif ok_meta or ok_nyaa:
                    h["status_dot"].props("name=circle").style("color:#f59e0b")
                else:
                    h["status_dot"].props("name=cancel").style("color:#ef4444")
            _update_badges(h)
            _session_save(all_handles)

        h["refresh_meta_btn"].on("click", _refetch_meta)
        h["refresh_nyaa_btn"].on("click", _refetch_nyaa)

    # ── Search handler (add-to-queue) ─────────────────────────────────────────

    async def do_search() -> None:
        raw = ref_input.value.strip()
        if not raw:
            ui.notify("Enter at least one reference number.", color="warning")
            return
        keywords = _parse_keywords(raw)
        if not keywords:
            ui.notify("No valid reference numbers found.", color="warning")
            return

        # Filter out already-queued IDs
        new_kws = [kw for kw in keywords if kw not in all_handles]
        dupes = [kw for kw in keywords if kw in all_handles]
        if dupes:
            ui.notify(
                f"Already in queue: {', '.join(dupes)}", color="info", timeout=3000
            )
        if not new_kws:
            ref_input.value = ""
            return

        ref_input.value = ""
        search_btn.props("disable=true")

        # Clear the "empty" placeholder if this is the first batch
        if not all_handles:
            inspector_col.clear()
            _insp_placeholder[0] = None

        progress_lbl.content = f"+{len(new_kws)} searching…"
        first_new = new_kws[0]

        async def _one(kw: str) -> None:
            await _enqueue_and_search(kw, auto_select=(kw == first_new))

        await asyncio.gather(*[_one(kw) for kw in new_kws])
        progress_lbl.content = ""
        search_btn.props("disable=false")

    # ── Clear handler ─────────────────────────────────────────────────────────

    def do_clear() -> None:
        removed_refs = list(all_handles.keys())
        # Cancel all timers before destroying DOM elements
        old_kw = active_kw[0]
        if old_kw and old_kw in all_handles:
            for _tk in ("dl_timer", "dl_timer_once"):
                _t = all_handles[old_kw].get(_tk)
                if _t is not None:
                    _t.cancel()
        sidebar_list.clear()
        inspector_col.clear()
        all_handles.clear()
        group_label_els.clear()
        active_kw[0] = None
        _insp_placeholder[0] = None
        ref_input.value = ""
        filter_inp.value = ""
        view_state["filter"] = ""
        _collapsed_groups.clear()
        queue_count_lbl.text = "0"
        progress_lbl.content = ""
        clear_downloader_runtime_state()
        prune_orphaned_refs(app.storage.user, removed_refs)
        with inspector_col:
            with ui.element("div").classes("insp-empty") as _clear_empty:
                ui.icon("movie", size="4rem").style("color:#374151")
                ui.label("Add a video to the queue to get started").style(
                    "font-size:0.85rem;color:#4b5563;margin-top:12px"
                )
        _insp_placeholder[0] = _clear_empty

    # ── Session restore on page load ──────────────────────────────────────────

    async def _restore_session() -> None:
        """Read persisted queue from the stable downloader store on connect."""
        items = load_downloader_queue()

        if not items:
            await _consume_downloader_jump()
            return

        kws = [item["kw"] for item in items if item.get("kw")]
        if not kws:
            await _consume_downloader_jump()
            return

        inspector_col.clear()
        _insp_placeholder[0] = None
        progress_lbl.content = f"Restoring {len(kws)}…"
        search_btn.props("disable=true")

        first = kws[0]

        # Snapshot the FULL cache before any restore task calls _session_save.
        # _session_save rebuilds _CACHE_KEY from scratch using only the handles
        # that exist at that moment — so item 2's cache entry gets wiped before
        # item 2 even runs its lookup.  We merge the snapshot back before every
        # _enqueue_and_search call so each item always finds its cached data.
        _restore_cache_snapshot = load_downloader_cache()

        # Concurrency gate for the restore loop.
        # Cached items (fast path) run up to this many in parallel; uncached
        # items still serialise through the global SCRAPER_SEM(1) on top of this.
        # We derive the limit from the active scraper concurrency setting, but
        # floor it at 3 so cached restores aren't unnecessarily serialised.
        _restore_cfg = load_config()
        _src = resolve_metadata_source(_restore_cfg.get("metadata_source", "javdb"))
        _conc_key = "javlibrary_concurrency" if _src == "javlibrary" else "javdb_concurrency"
        _restore_slots = max(3, int(_restore_cfg.get(_conc_key, 1)))
        _restore_sem = asyncio.Semaphore(_restore_slots)

        async def _restore_one(item: dict) -> None:
            async with _restore_sem:
                await _enqueue_and_search(
                    item["kw"],
                    auto_select=(item["kw"] == first),
                    ever_selected=bool(item.get("ever_selected")),
                    skip_live_fetch=True,
                    persist_session=False,
                    refresh_view=False,
                    cache_snapshot=_restore_cache_snapshot,
                )
                h = all_handles.get(item["kw"])
                if not h:
                    return
                if item.get("folder_path"):
                    h["state"]["folder_path"] = Path(item["folder_path"])
                if item.get("downloaded"):
                    h["state"]["downloaded"] = True

        await asyncio.gather(*[_restore_one(it) for it in items])
        _session_save(all_handles)
        apply_view()
        # Final sweep — apply UI state that needs client context
        for h in all_handles.values():
            _update_badges(h)
            if h["state"].get("downloaded"):
                h["status_dot"].props("name=task_alt").style("color:#4ade80")
                h["row_el"].classes(add="downloaded")
            fp = h["state"].get("folder_path")
            if fp and h.get("folder_lbl") is not None:
                h["folder_lbl"].text = f"✓ {Path(str(fp)).name}"
                h["folder_lbl"].style("color:#4ade80")
            if h["state"].get("downloaded") and fp and h.get("organise_btn") is not None:
                h["organise_btn"].set_visibility(True)
        progress_lbl.content = ""
        search_btn.props("disable=false")

        await _consume_downloader_jump()

    async def _consume_downloader_jump() -> None:
        jump_ref = str(app.storage.user.get("_downloader_jump_ref") or "").strip().upper()
        if not jump_ref:
            return
        try:
            del app.storage.user["_downloader_jump_ref"]
        except Exception:
            pass

        if jump_ref not in all_handles:
            await _enqueue_and_search(jump_ref, auto_select=True)
        else:
            show_inspector(jump_ref)

        filter_inp.value = jump_ref
        view_state["filter"] = jump_ref
        set_downloader_view_state(dict(view_state))
        apply_view()

    search_btn.on_click(do_search)
    ref_input.on("keydown.enter", do_search)
    with ui.dialog() as _clear_confirm_dialog, ui.card().style(
        "background:#0d0d11;border:1px solid #1a1a24;min-width:280px"
    ):
        ui.label("Clear entire queue?").style(
            "font-size:1rem;font-weight:700;color:#f3f4f6;padding:4px 0 8px"
        )
        ui.label("All items and cached metadata will be removed from this session. Local folders on disk are not deleted.").style(
            "font-size:0.8rem;color:#9ca3af;padding-bottom:8px"
        )
        with ui.row().classes("justify-end gap-2 pt-2"):
            ui.button("Cancel", on_click=_clear_confirm_dialog.close).props("flat")
            ui.button("Clear All", on_click=lambda: (_clear_confirm_dialog.close(), do_clear())).props("color=negative")

    clear_btn.on_click(_clear_confirm_dialog.open)

    # ── Global background poller: updates _dl_category for all handles ────────

    async def _poll_all_dl_states() -> None:
        cfg = load_config()
        qbt_url = cfg.get("qbt_url", "").strip()
        if not qbt_url:
            return
        try:
            all_torrents = await get_all_torrents(
                qbt_url=qbt_url,
                username=cfg.get("qbt_username", "admin"),
                password=cfg.get("qbt_password", ""),
            )
        except Exception:
            return
        if not all_torrents:
            return

        changed = False
        for kw, h in all_handles.items():
            fp = h["state"].get("folder_path")
            if fp:
                norm = str(fp).replace("\\", "/").rstrip("/").lower()
                matched = [
                    t
                    for t in all_torrents
                    if t.get("save_path", "").replace("\\", "/").rstrip("/").lower()
                    == norm
                ]
            else:
                kw_lower = kw.lower()
                matched = [
                    t for t in all_torrents if kw_lower in t.get("name", "").lower()
                ]

            if not matched:
                cat = "none"
            else:
                raw_states = {t.get("state", "") for t in matched}
                if raw_states & _DL_DOWNLOADING_STATES:
                    cat = "downloading"
                elif raw_states & _DL_PAUSED_STATES:
                    cat = "paused"
                elif raw_states & _DL_COMPLETE_STATES:
                    cat = "complete"
                else:
                    cat = "none"

            old_cat = h["state"].get("_dl_category", "none")
            if old_cat != cat:
                h["state"]["_dl_category"] = cat
                changed = True

        if changed and (
            view_state["sort"] == "dl_status" or view_state["group"] == "dl_status"
        ):
            apply_view()

    _poll_cfg = load_config()
    _timer_ctx["global_timer"] = ui.timer(
        _poll_cfg.get("dl_poll_interval", 30), _poll_all_dl_states
    )

    asyncio.ensure_future(_restore_session())

    # ── Restore view controls UI to match persisted view_state ────────────────
    if view_state["filter"]:
        filter_inp.value = view_state["filter"]
    if view_state["sort"] != "default":
        sort_btn_el.classes(add="active-ctrl")
    if view_state["group"] != "none":
        group_btn_el.classes(add="active-ctrl")
    _update_sort_group_label()

    # ── Extension queue drain ──────────────────────────────────────────────────
    async def _drain_ext_queue() -> None:
        """Poll the thread-safe queue for refs sent by the browser extension."""
        drained: list[str] = []
        while True:
            try:
                drained.append(_ext_ref_queue.get_nowait())
            except _queue_mod.Empty:
                break
        new_refs = [ref for ref in drained if ref not in all_handles]
        if new_refs:
            for ref in new_refs:
                ui.notify(f"Extension → queuing {ref}", color="info", timeout=3000)
            await asyncio.gather(*[_enqueue_and_search(ref) for ref in new_refs])

    _timer_ctx["drain_timer"] = ui.timer(1.5, _drain_ext_queue)

    # ── Disconnect cleanup: cancel all page-scoped timers ─────────────────────
    async def _cleanup_page_timers() -> None:
        for h in all_handles.values():
            for key in ("dl_timer", "dl_timer_once"):
                t = h.get(key)
                if t:
                    t.cancel()
        for t in _timer_ctx.values():
            if t:
                t.cancel()
        _timer_ctx.clear()

    client.on_disconnect(_cleanup_page_timers)
