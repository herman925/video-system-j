"""
Inspector panel: attach widgets and populate them after a JAV/Nyaa search.
"""

import asyncio
import json
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

from nicegui import ui

from translator.llm import extract_code_blocks, load_config, translate_title
from utils.folder import create_video_folder, download_cover
from utils.qbittorrent import add_torrent, get_torrents
from utils.ui_cover_preview import open_image_preview
from downloader.state import _session_save
from downloader.components.queue import _update_badges


YOU_COM_URL = (
    "https://you.com/search?q={query}"
    "&fromSearchBar=true&tbm=youchat"
    "&chatMode=user_mode_178853e5-c51c-4cbf-9266-61b5983b4610"
)

JAVLIBRARY_PAGE_URL = "https://www.javlibrary.com/tw/vl_searchbyid.php?keyword={}"

_QBT_STATE_LABELS: Dict[str, str] = {
    "downloading": "Downloading",
    "stalledDL": "Stalled",
    "forcedDL": "Downloading",
    "metaDL": "Fetching metadata",
    "uploading": "Seeding",
    "stalledUP": "Seeding (stalled)",
    "forcedUP": "Seeding",
    "pausedDL": "Paused",
    "pausedUP": "Complete",
    "checkingDL": "Checking",
    "checkingUP": "Checking",
    "checkingResumeData": "Checking",
    "queuedDL": "Queued",
    "queuedUP": "Queued",
    "error": "Error",
    "missingFiles": "Missing files",
    "moving": "Moving files",
    "unknown": "Unknown",
}

_TORRENT_COLS = [
    {
        "name": "name",
        "label": "Name",
        "field": "name",
        "align": "left",
        "sortable": True,
        "style": "white-space:normal; word-break:break-word;",
    },
    {"name": "size", "label": "Size", "field": "size", "sortable": True},
    {"name": "seeders", "label": "Seeds", "field": "seeders", "sortable": True},
    {"name": "leechers", "label": "Leech", "field": "leechers", "sortable": True},
    {"name": "action", "label": "", "field": "action"},
]


def _fmt_speed(bps: int) -> str:
    if bps <= 0:
        return ""
    if bps < 1_024:
        return f"↓ {bps} B/s"
    if bps < 1_048_576:
        return f"↓ {bps / 1_024:.1f} KB/s"
    return f"↓ {bps / 1_048_576:.1f} MB/s"


def _fmt_eta(seconds: int) -> str:
    if seconds < 0 or seconds >= 8_640_000:
        return ""
    if seconds == 0:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"ETA {h}h {m}m"
    if m:
        return f"ETA {m}m {s}s"
    return f"ETA {s}s"


def _copy(text: str) -> None:
    ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(text)})")
    ui.notify("Copied!", color="positive", timeout=1500)


def _build_youcom_url(title: str, date: str, actresses: List[str], ref_id: str) -> str:
    actress_str = "、".join(actresses) if actresses else "不明"
    query = f"原文標題：{title}\n發行日期：{date}\n女優：{actress_str}\n番號：{ref_id}"
    return YOU_COM_URL.format(query=urllib.parse.quote(query))


# ── Tracker integration helpers ───────────────────────────────────────────────


def _actress_tracker_lookup(names: List[str], ref_id: str = "") -> dict:
    """Return {name: (rating, actress_id)} using ref-aware tracker identity matching."""
    try:
        from tracker.store import load_tracker, resolve_ref_actress_lookup

        data = load_tracker()
        return resolve_ref_actress_lookup(data, ref_id, names)
    except Exception:
        return {name: (None, None) for name in names}


def _nav_to_tracker(actress_id: str) -> None:
    """Navigate to the tracker page and pre-select the given actress."""
    from nicegui import app as _app, ui as _ui
    _app.storage.user["_tracker_jump_actress_id"] = actress_id
    _ui.navigate.to("/tracker")


def _nav_to_tracker_ref(ref_id: str) -> None:
    """Navigate to the tracker page and focus the given reference."""
    from nicegui import app as _app, ui as _ui

    _app.storage.user["_tracker_jump_ref"] = str(ref_id or "").strip().upper()
    _ui.navigate.to("/tracker")


def _build_cast_chips(h: dict, actress_names: List[str]) -> None:
    """Clear and rebuild the cast container with per-actress colored chips.

    Each chip is colored by the actress's tracker rating and clickable —
    clicking navigates to the Tracker page with that actress pre-selected.
    """
    container = h["cast_lbl"]  # ui.element("div")
    container.clear()
    if not actress_names:
        with container:
            ui.label("—").style("color:#6b7280;font-size:0.9rem")
        return
    lookup = _actress_tracker_lookup(actress_names, h["keyword"])
    from utils.ui_ratings import get_actor_rank_html_span
    with container:
        for i, name in enumerate(actress_names):
            rating, actress_id = lookup.get(name, (None, None))
            is_tracked = actress_id is not None
            tooltip_text = (
                f"Tracked: {rating}" if rating is not None
                else ("Tracked — unrated" if is_tracked else name)
            )
            
            # Using the exact identical aura format as the tracker/queue
            span_html = get_actor_rank_html_span(name, {name: rating} if rating is not None else {})
            
            lbl_style = (
                f"font-size:0.9rem;line-height:1.6;"
                f"cursor:{'pointer' if is_tracked else 'default'};"
                "white-space:nowrap;padding-block:4px;margin-block:-4px;padding-inline:4px;"
            )
            lbl = ui.html(span_html).style(lbl_style).tooltip(tooltip_text)
            if is_tracked:
                lbl.on(
                    "click",
                    lambda aid=actress_id: _nav_to_tracker(aid),
                )
            if i < len(actress_names) - 1:
                ui.label("·").style("color:#374151;font-size:0.85rem;line-height:1.6")


async def _send_to_qbt_or_browser(
    link: str, torrent_name: str = "", folder_path: Optional[Path] = None
) -> None:
    cfg = load_config()
    qbt_url = cfg.get("qbt_url", "").strip()
    if qbt_url:
        if folder_path:
            save_path = str(folder_path)
        else:
            base = cfg.get("download_folder", "").strip()
            if not base:
                ui.notify(
                    "No folder created and no base download folder set. "
                    "Create a folder first or set one in ⚙ Settings.",
                    color="warning",
                    timeout=6000,
                )
                return
            save_path = base
            ui.notify(
                "No video folder created yet — downloading to base folder. "
                "Click 'Create Folder' first to organise by video.",
                color="info",
                timeout=5000,
            )
        success = await add_torrent(
            url=link,
            save_path=save_path,
            qbt_url=qbt_url,
            username=cfg.get("qbt_username", "admin"),
            password=cfg.get("qbt_password", ""),
            rename=torrent_name or None,
        )
        if success:
            dest = Path(save_path).name or save_path
            ui.notify(f"Added to qBittorrent → {dest}", color="positive")
            return
        ui.notify(
            "qBittorrent API failed — opening in browser instead",
            color="warning",
            timeout=4000,
        )
    webbrowser.open(link)


def _attach_inspector(h: dict, inspector_col) -> None:
    """
    Build the inspector widgets inside inspector_col and store handles in h.
    Called once per keyword when that keyword is first selected.
    """
    state = h["state"]

    with inspector_col:
        # ── Top strip: ref ID + action buttons ───────────────────────────────
        with ui.row().classes("insp-topbar w-full items-center gap-4 px-6 py-4"):
            ui.html(
                f'<span style="font-family:monospace;font-weight:800;font-size:1.25rem;'
                f'color:#c4b5fd;letter-spacing:0.1em">{h["keyword"]}</span>'
            )
            (
                ui.button(icon="content_copy", on_click=lambda ref=h["keyword"]: _copy(ref))
                .props("flat dense round size=sm")
                .style("color:#d97706")
                .tooltip(f"Copy {h['keyword']}")
            )
            (
                ui.button(icon="manage_search", on_click=lambda ref=h["keyword"]: _nav_to_tracker_ref(ref))
                .props("flat dense round size=sm")
                .style("color:#f59e0b")
                .tooltip(f"Open {h['keyword']} in Tracker")
            )
            spinner_top = ui.spinner(size="md").props("color=purple")
            trans_spinner2 = ui.spinner(size="sm").props("color=purple")
            _is_translating = bool(state.get("_translating"))
            trans_spinner2.set_visibility(_is_translating)
            trans_status = ui.label("Calling LLM…" if _is_translating else "").style(
                "font-size:0.75rem;color:#6b7280"
            )
            trans_status.set_visibility(_is_translating)
            ui.element("div").classes("flex-1")
            refresh_meta_btn = (
                ui.button(icon="refresh")
                .props("flat dense round size=md")
                .style("color:#818cf8")
                .tooltip("Re-fetch metadata")
            )
            javlib_btn = (
                ui.button(icon="open_in_new")
                .props("flat dense round size=sm")
                .style("color:#34d399")
                .tooltip("Open in JAVLibrary")
            )
            youcom_btn = (
                ui.button(icon="travel_explore")
                .props("flat dense round size=sm")
                .style("color:#60a5fa")
                .tooltip("Research on You.com")
            )
            if not isinstance(state.get("_jav_result"), dict):
                youcom_btn.props("disable=true")
            trans_btn = (
                ui.button("Translate", icon="translate")
                .props("flat size=sm")
                .style("color:#c084fc;font-size:0.88rem")
                .tooltip("Translate via LLM")
            )

        # ── Info row: cover + metadata side by side ──────────────────────────
        with ui.element("div").classes("insp-info-row w-full"):
            # ── Cover ─────────────────────────────────────────────────────────
            with ui.element("div").classes("insp-cover"):
                cover_img = ui.image("").classes("cover-img w-full")
                cover_img.set_visibility(False)
                with ui.element("div").classes(
                    "cover-placeholder-wrap"
                ) as cover_placeholder_wrap:
                    cover_placeholder = ui.icon("movie").style(
                        "font-size:4rem;color:#3f3f46"
                    )
                # ── Download status (below cover) ──────────────────────────
                with ui.element("div").classes(
                    "cover-dl-status w-full"
                ) as dl_cover_wrap:
                    with ui.row().classes("items-center pb-1 gap-1"):
                        ui.label("DOWNLOAD").style(
                            "font-size:0.62rem;font-weight:700;"
                            "letter-spacing:0.1em;color:#6b7280;flex:1"
                        )
                        dl_refresh_btn = (
                            ui.button(icon="refresh")
                            .props("flat dense round size=xs")
                            .style("color:#818cf8")
                            .tooltip("Refresh download status")
                        )
                    dl_content_col = ui.column().classes("w-full gap-1")
                # Wrap starts hidden; becomes visible as soon as qBittorrent
                # is configured (even before a torrent is found) so the
                # refresh button is always reachable for manually-added torrents.
                dl_cover_wrap.set_visibility(False)

            # ── Metadata ──────────────────────────────────────────────────────
            with ui.element("div").classes("insp-meta"):
                title_lbl = ui.label("").style(
                    "font-size:1.1rem;font-weight:600;line-height:1.5;color:#f3f4f6;margin-bottom:10px"
                )
                with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-2"):
                    ui.label("Date").classes("meta-field-key")
                    date_lbl = ui.label("").classes("meta-field-val")
                    ui.label("Studio").classes("meta-field-key")
                    studio_lbl = ui.label("").classes("meta-field-val")
                    ui.label("Cast").classes("meta-field-key")
                    cast_lbl = ui.element("div").style(
                        "display:flex;flex-wrap:wrap;gap:2px 6px;align-items:center;"
                        "min-height:1.6em;padding:1px 0"
                    )
                    ui.label("Genres").classes("meta-field-key")
                    genres_lbl = ui.label("").style(
                        "font-size:0.88rem;color:#6b7280;line-height:1.6;"
                        "max-height:5.2rem;overflow-y:auto;display:block"
                    )

                ui.element("div").style("height:1px;background:#1e1e2a;margin:14px 0")

                ui.label("FOLDER NAME").style(
                    "font-size:0.72rem;font-weight:700;letter-spacing:0.1em;color:#6b7280"
                )
                with (
                    ui.row()
                    .classes("w-full items-center gap-2 mt-2")
                    .style("min-width:0;overflow:hidden")
                ):
                    _ADD_SENTINEL = "✏  Add Custom Name…"
                    _initial_choices = state.get("_name_choices", [])
                    _initial_opts = [c["label"] for c in _initial_choices] + [
                        _ADD_SENTINEL
                    ]
                    name_sel = (
                        ui.select(
                            options=_initial_opts,
                            label="Choose or add a name…",
                            value=None,
                        )
                        .classes("name-sel flex-1")
                        .props("outlined dense clearable")
                    )
                    # Restore previously selected name, else default to first choice
                    _saved_sel = state.get("_selected_name", "")
                    if _saved_sel and any(
                        c["label"] == _saved_sel for c in _initial_choices
                    ):
                        name_sel.value = _saved_sel
                    elif _initial_choices:
                        name_sel.value = _initial_choices[0]["label"]
                    view_trans_btn = (
                        ui.button(icon="translate")
                        .props("flat dense round size=sm")
                        .style("color:#c084fc")
                        .tooltip("View full translation response")
                    )
                    view_trans_btn.set_visibility(bool(state.get("_translation")))
                    llm_resp_btn = view_trans_btn
                    llm_resp_btn.set_visibility(bool(state.get("_translation")))

                    def _copy_name():
                        v = name_sel.value
                        if v and v != _ADD_SENTINEL:
                            _copy(v)

                    ui.button(icon="content_copy", on_click=_copy_name).props(
                        "flat dense round size=sm"
                    ).style("color:#818cf8").tooltip("Copy name")

                def _rebuild_name_options():
                    choices = state.get("_name_choices", [])
                    opts = [c["label"] for c in choices] + [_ADD_SENTINEL]
                    cur = name_sel.value
                    name_sel.options = opts
                    # Keep current selection if still valid
                    if (
                        cur
                        and cur != _ADD_SENTINEL
                        and cur not in [c["label"] for c in choices]
                    ):
                        name_sel.value = None

                h["_rebuild_name_options"] = _rebuild_name_options
                h["_ADD_SENTINEL"] = _ADD_SENTINEL

                create_btn = (
                    ui.button("Create Folder", icon="create_new_folder")
                    .props("size=md")
                    .classes("create-folder-btn mt-3")
                )
                folder_lbl = ui.label("").style(
                    "font-size:0.8rem;color:#6b7280;margin-top:4px;"
                    "word-break:break-all;white-space:normal;overflow-wrap:anywhere;width:100%"
                )
                _fp = state.get("folder_path")
                _organise_btn = (
                    ui.button("Organise", icon="folder_special")
                    .props("flat dense size=sm")
                    .style("color:#818cf8;margin-top:6px;font-size:0.8rem")
                    .tooltip("Open this folder in the Organiser")
                )
                _organise_btn.set_visibility(
                    bool(state.get("downloaded") and _fp)
                )

        # ── Cover zoom ─────────────────────────────────────────────────────────
        def _on_cover_click():
            if not cover_img.source:
                return
            open_image_preview(cover_img.source)

        cover_img.on("click", _on_cover_click)

        # ── Dialogs (folder name helpers) ────────────────────────────────────
        with ui.dialog() as custom_name_dialog, ui.card().classes("w-96 gap-3 p-4"):
            ui.label("Add Custom Folder Name").classes("text-base font-bold").style(
                "margin-bottom:4px"
            )
            custom_inp = (
                ui.input(label="Folder name", placeholder="Enter your folder name…")
                .classes("w-full")
                .props("outlined")
            )

            def _do_add_custom():
                val = custom_inp.value.strip()
                if not val:
                    return
                choices = state.get("_name_choices", [])
                uid = f"custom_{len(choices)}"
                choices.append({"label": val, "value": uid})
                state["_name_choices"] = choices
                _rebuild_name_options()
                name_sel.value = val  # plain string label
                _update_badges(h)
                if h.get("_view_fn"):
                    h["_view_fn"]()
                custom_inp.value = ""
                custom_name_dialog.close()

            with ui.row().classes("justify-end gap-2 pt-2"):
                ui.button("Cancel", on_click=custom_name_dialog.close).props("flat")
                ui.button("Add", on_click=_do_add_custom).props("color=primary")

        with ui.dialog() as llm_resp_dialog, ui.card().classes("w-[700px] gap-0"):
            with ui.element("div").style("padding:16px 20px 8px"):
                ui.label("Full Translation Response").classes("text-base font-bold")
            with ui.element("div").style(
                "overflow-y:auto;max-height:65vh;padding:0 20px 16px"
            ):
                llm_resp_md = ui.markdown("").style("font-size:0.82rem")
            with ui.row().classes("justify-end px-4 py-3"):
                ui.button("Close", on_click=llm_resp_dialog.close).props("flat")

        def _on_name_sel_change(e):
            if e.value == _ADD_SENTINEL:
                name_sel.value = None
                custom_name_dialog.open()
            elif e.value:
                state["_selected_name"] = e.value
                _session_save(h.get("_all_handles", {}))

        name_sel.on_value_change(_on_name_sel_change)

        def _open_llm_resp():
            llm_resp_md.content = state.get("_translation", "") or ""
            llm_resp_dialog.open()

        view_trans_btn.on_click(_open_llm_resp)

        # ── Torrents: FULL WIDTH below info row ───────────────────────────────
        with ui.column().classes("insp-torrents w-full"):
            with ui.row().classes("items-center px-6 pt-4 pb-3 gap-2"):
                torrent_hdr = ui.label("TORRENTS").style(
                    "font-size:0.75rem;font-weight:700;letter-spacing:0.1em;color:#6b7280;flex:1"
                )
                refresh_nyaa_btn = (
                    ui.button(icon="refresh")
                    .props("flat dense round size=sm")
                    .style("color:#818cf8")
                    .tooltip("Re-fetch torrents")
                )
                torrent_spinner = ui.spinner(size="sm").props("color=purple")

            torrent_table = (
                ui.table(columns=_TORRENT_COLS, rows=[], row_key="name")
                .classes("torrent-table w-full")
                .props("dense flat loading")
            )

            torrent_table.add_slot(
                "no-data",
                r"""<div style="text-align:center;padding:24px 0;font-size:0.82rem;color:#4b5563;">
                  No results found on Sukebei Nyaa
                </div>""",
            )

            torrent_table.add_slot(
                "body-cell-seeders",
                r"""
                <q-td :props="props" class="text-center">
                  <span :style="{ color: props.row.seeders > 0 ? '#4ade80' : '#374151',
                                  fontWeight: props.row.seeders > 0 ? '700' : 'normal' }">
                    {{ props.row.seeders }}
                  </span>
                </q-td>""",
            )
            torrent_table.add_slot(
                "body-cell-leechers",
                r"""
                <q-td :props="props" class="text-center">
                  <span :style="{ color: props.row.leechers > 0 ? '#fb923c' : '#374151' }">
                    {{ props.row.leechers }}
                  </span>
                </q-td>""",
            )
            torrent_table.add_slot(
                "body-cell-action",
                r"""
                <q-td :props="props" auto-width>
                  <q-btn v-if="props.row.magnet"
                    dense flat round icon="open_in_new" size="xs"
                    style="color:#818cf8"
                    title="Send magnet to qBittorrent"
                    @click.stop="$parent.$emit('do_magnet', props.row)" />
                  <q-btn v-if="props.row.torrent"
                    dense flat round icon="download" size="xs"
                    style="color:#34d399"
                    title="Download .torrent"
                    @click.stop="$parent.$emit('do_torrent', props.row)" />
                </q-td>""",
            )

            async def _on_magnet(e, _h=h) -> None:
                row = e.args or {}
                if row.get("magnet"):
                    await _send_to_qbt_or_browser(
                        row["magnet"],
                        row.get("name", ""),
                        _h["state"].get("folder_path"),
                    )
                    # Give qBittorrent ~2 s to register the torrent, then show status
                    async def _delayed():
                        await asyncio.sleep(2)
                        ensure_polling = _h.get("ensure_dl_polling")
                        if ensure_polling:
                            ensure_polling(force_once=True)
                        await _refresh_dl_progress()
                    asyncio.ensure_future(_delayed())

            async def _on_torrent(e, _h=h) -> None:
                row = e.args or {}
                if row.get("torrent"):
                    await _send_to_qbt_or_browser(
                        row["torrent"],
                        row.get("name", ""),
                        _h["state"].get("folder_path"),
                    )
                    async def _delayed():
                        await asyncio.sleep(2)
                        ensure_polling = _h.get("ensure_dl_polling")
                        if ensure_polling:
                            ensure_polling(force_once=True)
                        await _refresh_dl_progress()
                    asyncio.ensure_future(_delayed())

            torrent_table.on("do_magnet", _on_magnet)
            torrent_table.on("do_torrent", _on_torrent)

        # ── Compact download status (renders below cover image) ───────────────
        _dl_refreshing = [False]

        async def _refresh_dl_progress(
            _h=h,
            _state=state,
            _wrap=dl_cover_wrap,
            _content=dl_content_col,
        ) -> None:
            if _dl_refreshing[0]:
                return
            _dl_refreshing[0] = True
            try:
                _content.clear()
                cfg = load_config()
                qbt_url = cfg.get("qbt_url", "").strip()
                if not qbt_url:
                    _wrap.set_visibility(False)
                    return
                fields = cfg.get(
                    "dl_cover_fields", ["progress_bar", "percentage", "state"]
                )
                if not fields:
                    _wrap.set_visibility(False)
                    return

                # qBittorrent is configured — always show the header + refresh btn
                _wrap.set_visibility(True)

                fp = _state.get("folder_path")
                kw = _h["keyword"]
                if fp:
                    torrents = await get_torrents(
                        qbt_url=qbt_url,
                        username=cfg.get("qbt_username", "admin"),
                        password=cfg.get("qbt_password", ""),
                        save_path=str(fp),
                    )
                else:
                    torrents = await get_torrents(
                        qbt_url=qbt_url,
                        username=cfg.get("qbt_username", "admin"),
                        password=cfg.get("qbt_password", ""),
                        keyword=kw,
                    )

                if not torrents:
                    _content.set_visibility(False)
                    return

                _content.set_visibility(True)
                with _content:
                    for t in torrents:
                        progress = t.get("progress", 0.0)
                        state_raw = t.get("state", "unknown")
                        label = _QBT_STATE_LABELS.get(state_raw, state_raw)
                        dlspeed = t.get("dlspeed", 0)
                        eta = t.get("eta", -1)
                        name = t.get("name", "")

                        if state_raw in ("error", "missingFiles"):
                            state_color = "#ef4444"
                        elif state_raw in (
                            "uploading",
                            "stalledUP",
                            "forcedUP",
                            "pausedUP",
                        ):
                            state_color = "#4ade80"
                        elif state_raw == "stalledDL":
                            state_color = "#f59e0b"
                        elif state_raw == "pausedDL":
                            state_color = "#6b7280"
                        else:
                            state_color = "#60a5fa"

                        with ui.element("div").classes("cover-dl-entry w-full"):
                            if "state" in fields:
                                ui.label(label).style(
                                    f"font-size:0.72rem;font-weight:600;color:{state_color}"
                                )
                            if "progress_bar" in fields and progress < 1.0:
                                ui.linear_progress(
                                    value=progress,
                                    size="4px",
                                    color="indigo",
                                    show_value=False,
                                ).classes("w-full mt-1 mb-1")
                            row_parts: list = []
                            if "percentage" in fields:
                                row_parts.append((f"{int(progress * 100)}%", "#c4b5fd"))
                            if "speed" in fields:
                                sp = _fmt_speed(dlspeed)
                                if sp:
                                    row_parts.append((sp, "#6b7280"))
                            if row_parts:
                                with ui.row().classes("items-center gap-2 flex-wrap"):
                                    for txt, clr in row_parts:
                                        ui.label(txt).style(
                                            f"font-size:0.78rem;color:{clr}"
                                        )
                            if "eta" in fields:
                                eta_str = _fmt_eta(eta)
                                if eta_str:
                                    ui.label(eta_str).style(
                                        "font-size:0.72rem;color:#6b7280"
                                    )
                            if "torrent_name" in fields and name:
                                ui.label(name).style(
                                    "font-size:0.65rem;color:#4b5563;"
                                    "word-break:break-all;line-height:1.3;margin-top:2px"
                                )

            except Exception:
                pass
            finally:
                _dl_refreshing[0] = False

        def _ensure_dl_polling(force_once: bool = False) -> None:
            wrap = h.get("inspector_wrap")
            if wrap is None:
                return
            poll_interval = int(load_config().get("dl_poll_interval", 30))
            timer = h.get("dl_timer")
            if timer is None:
                with wrap:
                    h["dl_timer"] = ui.timer(poll_interval, _refresh_dl_progress)
            else:
                timer.interval = poll_interval
            if force_once:
                once_timer = h.get("dl_timer_once")
                if once_timer is not None:
                    once_timer.cancel()
                    h["dl_timer_once"] = None
            if force_once or h.get("dl_timer_once") is None:
                with wrap:
                    h["dl_timer_once"] = ui.timer(0.4, _refresh_dl_progress, once=True)

        async def _manual_refresh_dl_progress() -> None:
            _ensure_dl_polling()
            await _refresh_dl_progress()

        dl_refresh_btn.on_click(_manual_refresh_dl_progress)
        _ensure_dl_polling(force_once=True)

        trans_col = None  # no longer used as a separate section

    # Store all widget handles
    h.update(
        {
            "spinner_top": spinner_top,
            "refresh_meta_btn": refresh_meta_btn,
            "refresh_nyaa_btn": refresh_nyaa_btn,
            "cover_img": cover_img,
            "cover_placeholder": cover_placeholder,
            "cover_placeholder_wrap": cover_placeholder_wrap,
            "title_lbl": title_lbl,
            "date_lbl": date_lbl,
            "studio_lbl": studio_lbl,
            "cast_lbl": cast_lbl,
            "genres_lbl": genres_lbl,
            "torrent_hdr": torrent_hdr,
            "torrent_spinner": torrent_spinner,
            "torrent_table": torrent_table,
            "name_sel": name_sel,
            "llm_resp_btn": view_trans_btn,
            "llm_resp_md": llm_resp_md,
            "view_trans_btn": view_trans_btn,
            "create_btn": create_btn,
            "folder_lbl": folder_lbl,
            "organise_btn": _organise_btn,
            "trans_col": trans_col,
            "trans_spinner2": trans_spinner2,
            "trans_status": trans_status,
            "trans_btn": trans_btn,
            "youcom_btn": youcom_btn,
            "javlib_btn": javlib_btn,
            "ensure_dl_polling": _ensure_dl_polling,
            "refresh_dl_progress_fn": _refresh_dl_progress,
        }
    )

    # ── Organise handler ──────────────────────────────────────────────────────
    def _open_organiser() -> None:
        fp = h["state"].get("folder_path")
        if fp:
            encoded = urllib.parse.quote(str(fp))
            ui.navigate.to(f"/organiser?folder={encoded}")

    _organise_btn.on_click(_open_organiser)

    # ── Translate handler ─────────────────────────────────────────────────────
    async def do_translate() -> None:
        jav = h["state"].get("_jav_result") or h["state"].get("jav")
        if not jav:
            ui.notify("Search not complete yet.", color="warning")
            return
        h["trans_btn"].props("disable=true")
        h["state"]["_translating"] = True
        h["status_dot"].set_visibility(False)
        h["status_spinner"].set_visibility(True)
        if h.get("trans_spinner2"):
            h["trans_spinner2"].set_visibility(True)
        if h.get("trans_status"):
            h["trans_status"].text = "Calling LLM…"
            h["trans_status"].set_visibility(True)
        try:
            response = await translate_title(
                title=jav.get("title", ""),
                date=jav.get("date", ""),
                actresses=jav.get("actresses", []),
                ref_id=h["keyword"],
                config=load_config(),
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
            rebuild = h.get("_rebuild_name_options")
            if rebuild:
                rebuild()
            if new_trans and h.get("name_sel") is not None:
                h["name_sel"].value = new_trans[0]["label"]
            if h.get("llm_resp_btn") is not None:
                h["llm_resp_btn"].set_visibility(True)
            n = len(new_trans)
            if h.get("trans_status"):
                h["trans_status"].text = (
                    f"{n} name(s) added" if n else "No names extracted"
                )
            if h.get("view_trans_btn") is not None:
                h["view_trans_btn"].set_visibility(True)
            _update_badges(h)
            if h.get("_view_fn"):
                h["_view_fn"]()
            # Notify if the user has switched away from this video
            if h.get("_active_kw") is not None and h["_active_kw"][0] != h["keyword"]:
                msg = (
                    f"✓ {h['keyword']}: {n} translation(s) ready"
                    if n
                    else f"{h['keyword']}: no names extracted"
                )
                ui.notify(msg, color="positive" if n else "warning", timeout=5000)
        except Exception as exc:
            ui.notify(str(exc), color="negative", timeout=8000)
            if h.get("trans_status"):
                h["trans_status"].text = "Error"
        finally:
            h["state"]["_translating"] = False
            h["status_spinner"].set_visibility(False)
            h["status_dot"].set_visibility(True)
            if h.get("trans_spinner2"):
                h["trans_spinner2"].set_visibility(False)
            h["trans_btn"].props("disable=false")

    trans_btn.on_click(do_translate)

    # ── You.com handler ───────────────────────────────────────────────────────
    def open_youcom() -> None:
        jav = h["state"].get("jav")
        if not jav:
            return
        webbrowser.open(
            _build_youcom_url(
                jav.get("title", ""),
                jav.get("date", ""),
                jav.get("actresses", []),
                h["keyword"],
            )
        )

    youcom_btn.on_click(open_youcom)

    # ── JAVLibrary handler ────────────────────────────────────────────────────
    def open_javlibrary() -> None:
        webbrowser.open(JAVLIBRARY_PAGE_URL.format(urllib.parse.quote(h["keyword"])))

    javlib_btn.on_click(open_javlibrary)

    # ── Create folder handler ─────────────────────────────────────────────────
    async def do_create_folder() -> None:
        # name_sel stores plain label strings — use directly
        selected_val = h["name_sel"].value if h.get("name_sel") else None
        sentinel = h.get("_ADD_SENTINEL", "✏  Add Custom Name…")
        name = (selected_val or "").strip() if selected_val != sentinel else ""
        jav = h["state"].get("_jav_result") or h["state"].get("jav")
        if not name:
            ui.notify("Select or add a folder name first.", color="warning")
            return
        if not isinstance(jav, dict):
            ui.notify("No metadata — search first.", color="warning")
            return
        cfg = load_config()
        base_folder = cfg.get("download_folder", "").strip()
        if not base_folder:
            ui.notify(
                "No download folder set — open ⚙ Settings.",
                color="warning",
                timeout=5000,
            )
            return
        h["create_btn"].disable()
        h["folder_lbl"].text = "Creating…"
        h["folder_lbl"].style("color:#6b7280")
        try:
            folder_path = await asyncio.to_thread(
                create_video_folder, base_folder, name
            )
            h["state"]["folder_path"] = folder_path
            _session_save(h.get("_all_handles", {}))
            h["folder_lbl"].text = "Copying cover…"
            cover_url = jav.get("cover_url", "")
            try:
                cover_file = await asyncio.to_thread(
                    download_cover, folder_path, h["keyword"], cover_url
                )
                h["folder_lbl"].text = f"✓ {folder_path.name}  ({cover_file.name})"
            except Exception:
                h["folder_lbl"].text = f"✓ {folder_path.name}"
            h["folder_lbl"].style("color:#4ade80")
            ui.notify(f"Folder ready: {folder_path.name}", color="positive")
        except Exception as exc:
            h["folder_lbl"].text = f"Error: {exc}"
            h["folder_lbl"].style("color:#ef4444")
            ui.notify(str(exc), color="negative", timeout=6000)
        finally:
            h["create_btn"].enable()

    create_btn.on_click(do_create_folder)


def _populate_inspector(h: dict, jav_result, nyaa_result) -> None:
    keyword = h["keyword"]
    h["spinner_top"].set_visibility(False)

    if isinstance(jav_result, Exception):
        h["status_dot"].style("color:#ef4444")
        ui.notify(f"{keyword}: {jav_result}", color="negative", timeout=6000)
    else:
        h["state"]["jav"] = jav_result
        # Scraper has already saved the cover to COVERS_DIR; serve from there.
        try:
            from utils.covers import cover_path as _cover_path
            p = _cover_path(keyword)
        except Exception:
            p = None
        cover_src = (
            f"/api/cover?ref={keyword}" if p is not None
            else jav_result.get("cover_url", "")
        )
        if cover_src:
            h["cover_img"].source = cover_src
            h["cover_img"].set_visibility(True)
            h["cover_placeholder_wrap"].set_visibility(False)
        h["title_lbl"].text = jav_result.get("title", keyword)
        h["date_lbl"].text = jav_result.get("date", "")
        h["studio_lbl"].text = jav_result.get("studio", "")
        _build_cast_chips(h, jav_result.get("actresses", []))
        h["genres_lbl"].text = "  ·  ".join(jav_result.get("genres", []))
        if h.get("youcom_btn"):
            h["youcom_btn"].props("disable=false")
        # Subtitle is updated by apply_view() based on current sort mode

    if not isinstance(nyaa_result, list):
        h["torrent_hdr"].text = "TORRENTS — fetch error"
        if isinstance(nyaa_result, Exception):
            ui.notify(f"{keyword} nyaa: {nyaa_result}", color="negative", timeout=6000)
    else:
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

    h["torrent_spinner"].set_visibility(False)
    h["torrent_table"].props(remove="loading")

    ok_meta = not isinstance(jav_result, Exception) and bool(jav_result)
    ok_nyaa = isinstance(nyaa_result, list)  # None and Exception both mean not yet fetched / failed
    if not h["state"].get("downloaded"):
        if ok_meta and ok_nyaa:
            h["status_dot"].style("color:#22c55e")
            h["status_dot"].props("name=circle")
        elif ok_meta or ok_nyaa:
            h["status_dot"].style("color:#f59e0b")
            h["status_dot"].props("name=circle")
        else:
            h["status_dot"].style("color:#ef4444")
            h["status_dot"].props("name=cancel")
