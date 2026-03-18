"""
Sidebar queue entry builder and badge helpers.
"""

from typing import Dict

from nicegui import ui

from downloader.state import _session_save


def _sync_downloaded_to_tracker(keyword: str, downloaded: bool) -> None:
    """Update tracker.json when the user toggles the downloaded state in the downloader."""
    try:
        from tracker.store import mark_ref_downloaded_globally
        mark_ref_downloaded_globally(keyword, downloaded=downloaded)
    except Exception:
        pass  # tracker is optional; never break the downloader


_MOSAIC_KEYWORDS = {"mosaic", "uncensor", "無碼", "无码"}


def _has_mosaic_torrent(h: dict) -> bool:
    """Return True if any torrent name contains a mosaic/uncensor keyword."""
    nyaa = h["state"].get("_nyaa_result")
    if not isinstance(nyaa, list):
        return False
    for t in nyaa:
        name_lower = t.get("name", "").lower()
        for kw in _MOSAIC_KEYWORDS:
            if kw.lower() in name_lower:
                return True
    return False


def _update_badges(h: dict) -> None:
    """Refresh all sidebar badges (N, T/M, 中) for a queue entry.

    Safe to call from background tasks — all badge elements live in the
    always-visible sidebar list, not in the inspector panel.
    """
    state = h["state"]

    # N badge — new/unselected: hide once item has ever been opened
    if h.get("badge_n") is not None:
        h["badge_n"].set_visibility(not state.get("_ever_selected", False))

    # T and M badges — torrent/mosaic
    has_torrents = isinstance(state.get("_nyaa_result"), list) and bool(
        state.get("_nyaa_result")
    )
    has_mosaic = _has_mosaic_torrent(h)
    if h.get("badge_m") is not None:
        h["badge_m"].set_visibility(has_mosaic)
    if h.get("badge_t") is not None:
        # T only shows if has torrents but NOT mosaic (M supersedes T)
        h["badge_t"].set_visibility(has_torrents and not has_mosaic)

    # 中 badge — has any folder name choices (translated or custom)
    if h.get("badge_zh") is not None:
        has_names = bool(state.get("_translation")) or bool(state.get("_name_choices"))
        h["badge_zh"].set_visibility(has_names)


def _build_queue_entry(
    keyword: str,
    sidebar_list,
    all_handles: dict,
    inspector_fn,
    view_fn=None,
    remove_fn=None,
) -> dict:
    """Add a row to the sidebar queue and return its handle dict."""
    state: Dict = {"jav": None, "folder_path": None, "downloaded": False}

    with sidebar_list:
        with ui.element("div").classes(
            "queue-item w-full px-3 py-2 cursor-pointer"
        ) as row_el:
            with ui.column().classes("w-full gap-0"):
                # ── Top line: status dot · ref code · badges · actions ────
                with ui.row().classes("items-center gap-2 w-full"):
                    status_dot = ui.icon("radio_button_unchecked", size="sm").style(
                        "color:#4b5563;flex-shrink:0;cursor:pointer"
                    )
                    status_spinner = (
                        ui.spinner(size="xs")
                        .props("color=purple")
                        .style("flex-shrink:0")
                    )
                    status_spinner.set_visibility(False)
                    ui.html(
                        f'<span class="queue-item-ref" style="font-family:monospace;'
                        f"font-weight:700;font-size:0.95rem;color:#c4b5fd;"
                        f'letter-spacing:0.07em">{keyword}</span>'
                    )
                    # Spacer — pushes badges + buttons to the right
                    ui.element("div").style("flex:1")
                    # ── Status badges ─────────────────────────────────────
                    badge_n = ui.html(
                        '<span class="qi-badge badge-n" title="New — never opened">N</span>'
                    )
                    badge_t = ui.html(
                        '<span class="qi-badge badge-t" title="Has torrents">T</span>'
                    )
                    badge_t.set_visibility(False)
                    badge_m = ui.html(
                        '<span class="qi-badge badge-m" title="Mosaic/Uncensor torrent found">M</span>'
                    )
                    badge_m.set_visibility(False)
                    badge_zh = ui.html(
                        '<span class="qi-badge badge-zh" title="Translated">\u4e2d</span>'
                    )
                    badge_zh.set_visibility(False)
                    def _copy_ref() -> None:
                        ui.run_javascript(f"navigator.clipboard.writeText({keyword!r})")
                        ui.notify("Copied!", color="positive", timeout=1500)

                    copy_dot = (
                        ui.button(icon="content_copy")
                        .props("flat dense round size=xs")
                        .style("color:#d97706;flex-shrink:0")
                        .tooltip(f"Copy {keyword}")
                    )
                    remove_dot = (
                        ui.button(icon="close")
                        .props("flat dense round size=xs")
                        .classes("remove-btn")
                        .style("flex-shrink:0")
                    )
                # ── Subtitle: date · studio (populated after search) ──────
                subtitle_lbl = ui.html("").classes("queue-item-sub").style("line-height:2; padding:4px; margin:-4px;")
                subtitle_lbl.set_visibility(False)

    handles: Dict = {
        "state": state,
        "keyword": keyword,
        "_all_handles": all_handles,
        "_view_fn": view_fn,
        "row_el": row_el,
        "status_dot": status_dot,
        "status_spinner": status_spinner,
        "remove_dot": remove_dot,
        "subtitle_lbl": subtitle_lbl,
        "badge_n": badge_n,
        "badge_t": badge_t,
        "badge_m": badge_m,
        "badge_zh": badge_zh,
        # inspector widgets filled by _attach_inspector
        "cover_img": None,
        "cover_placeholder": None,
        "title_lbl": None,
        "date_lbl": None,
        "studio_lbl": None,
        "cast_lbl": None,
        "genres_lbl": None,
        "torrent_hdr": None,
        "torrent_spinner": None,
        "torrent_table": None,
        "name_sel": None,
        "llm_resp_btn": None,
        "llm_resp_md": None,
        "create_btn": None,
        "folder_lbl": None,
        "organise_btn": None,
        "trans_spinner2": None,
        "trans_status": None,
        "trans_btn": None,
        "youcom_btn": None,
        "javlib_btn": None,
        "dl_timer": None,       # download progress polling timer (recurring)
        "dl_timer_once": None,  # one-shot 0.4s initial refresh timer
    }

    all_handles[keyword] = handles

    row_el.on("click", lambda kw=keyword: inspector_fn(kw))

    def _remove():
        if remove_fn:
            remove_fn(keyword, row_el, all_handles)
        else:
            row_el.set_visibility(False)
            all_handles.pop(keyword, None)
            _session_save(all_handles)
            if view_fn:
                view_fn()

    def _toggle_downloaded():
        dl = not state.get("downloaded", False)
        state["downloaded"] = dl
        _sync_downloaded_to_tracker(keyword, dl)
        if dl:
            status_dot.props("name=task_alt").style("color:#4ade80")
            row_el.classes(add="downloaded")
        else:
            # Restore icon to fetch-result state
            populated = state.get("_populated", False)
            ok_meta = populated and not isinstance(state.get("_jav_result"), Exception)
            ok_nyaa = populated and not isinstance(state.get("_nyaa_result"), Exception)
            if not populated:
                status_dot.props("name=radio_button_unchecked").style("color:#4b5563")
            elif ok_meta and ok_nyaa:
                status_dot.props("name=circle").style("color:#22c55e")
            elif ok_meta or ok_nyaa:
                status_dot.props("name=circle").style("color:#f59e0b")
            else:
                status_dot.props("name=cancel").style("color:#ef4444")
            row_el.classes(remove="downloaded")
        _session_save(all_handles)
        if view_fn:
            view_fn()

    status_dot.on("click.stop", lambda: _toggle_downloaded())
    status_dot.props('title="Click to toggle downloaded ✓"')
    copy_dot.on("click.stop", _copy_ref)
    remove_dot.on("click.stop", _remove)

    return handles
