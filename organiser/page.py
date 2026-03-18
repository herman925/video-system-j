"""
Organiser page: /organiser
A NiceGUI page that provides Renamer and Folder Mover functionality.
Imported by main.py to register the route in the same NiceGUI server.
"""

import asyncio
from datetime import datetime
import html as _html
import os
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import filedialog
from typing import List, Optional

from fastapi.responses import FileResponse, JSONResponse
from nicegui import Client, app, ui

from downloader.components.settings import build_settings_dialog as _build_settings_dialog
from translator.llm import load_config
from utils.organiser_store import load_organiser_state
from utils.paths import CONFIG_FILE, ORGANISER_STATE_FILE
from utils.save_state import build_save_state_badge
from utils.sort_key import romaji_key as _romaji_key
from utils.ui_cover_preview import open_image_preview
from utils.organiser import (
    DEFAULT_LOSSLESSCUT_EXE,
    DEFAULT_VTM_EXE,
    FolderInfo,
    MoverInfo,
    cleanup_folder_files,
    check_move_conflicts,
    default_vtm_preset,
    delete_file,
    delete_image_file,
    generate_thumbnails,
    has_cover_only,
    has_thumbnails,
    list_all_folder_files,
    build_file_rename_preview,
    list_folder_images,
    list_vtm_presets,
    load_mover_folders,
    load_renamer_folders,
    merge_folder,
    move_folder,
    open_folder_in_explorer,
    open_in_losslesscut,
    open_path,
    recalc_target,
    rename_file,
    rename_folders_batch,
    rename_images_in_folder,
    rename_videos_for_actor,
)

# ── Image serving endpoint ─────────────────────────────────────────────────────

@app.get('/api/organiser-img')
async def _serve_organiser_img(path: str = ''):
    if path and os.path.isfile(path):
        return FileResponse(path)
    return JSONResponse({'error': 'not found'}, status_code=404)


@app.get('/api/organiser-open-folder')
async def _open_organiser_folder(path: str = ''):
    if path and os.path.isdir(path):
        open_folder_in_explorer(path)
        return JSONResponse({'ok': True})
    return JSONResponse({'error': 'not found'}, status_code=404)

# ── Table column definitions ───────────────────────────────────────────────────

_RENAMER_COLS = [
    {'name': 'date',             'label': 'Date',       'field': 'date',             'sortable': True, 'align': 'left'},
    {'name': 'actor_name',       'label': 'Actor',      'field': 'actor_name',       'sortable': True, 'align': 'left'},
    {'name': 'reference_number', 'label': 'Ref',        'field': 'reference_number', 'sortable': True, 'align': 'left'},
    {'name': 'video_name',       'label': 'Video Name', 'field': 'video_name',       'sortable': True, 'align': 'left', 'classes': 'max-w-xs truncate'},
    {'name': 'number_of_videos', 'label': '#',          'field': 'number_of_videos', 'sortable': True, 'align': 'center', 'style': 'width:48px'},
]

_MOVER_COLS = [
    {'name': 'folder_name',     'label': 'Folder',  'field': 'folder_name',     'sortable': True, 'align': 'left', 'classes': 'max-w-xs truncate'},
    {'name': 'detected_actor',  'label': 'Actor',   'field': 'detected_actor',  'sortable': True, 'align': 'left'},
    {'name': 'target_dir',      'label': 'Target',  'field': 'target_dir',      'sortable': True, 'align': 'left', 'classes': 'max-w-xs truncate'},
    {'name': 'number_of_videos','label': '#',       'field': 'number_of_videos','sortable': True, 'align': 'center', 'style': 'width:48px'},
]

# ── Grouping helper ────────────────────────────────────────────────────────────

_GROUP_BY_OPTIONS = {
    'No grouping':    '',
    'By Actor':       'actor_name',
    'By Date':        'date',
    'By Reference':   'reference_number',
}


def _format_display_date(raw_date: str) -> str:
    raw_date = (raw_date or '').strip()
    if len(raw_date) == 8 and raw_date.isdigit():
        try:
            return datetime.strptime(raw_date, '%Y%m%d').strftime('%d %b, %Y')
        except ValueError:
            return raw_date
    return raw_date

def _build_renamer_rows(data: List[FolderInfo], group_by: str) -> List[dict]:
    """Return flat row dicts, with group-header pseudo-rows injected when group_by is set."""
    if not group_by:
        return [f.to_row() for f in data]

    def _key(fi: FolderInfo) -> str:
        if group_by == 'actor_name':
            return fi.actor_name or '—'
        if group_by == 'date':
            return fi.date or '—'
        if group_by == 'reference_number':
            # Group by prefix (e.g. "ABC" from "ABC-123")
            return fi.reference_number.split('-')[0] if '-' in fi.reference_number else (fi.reference_number or '—')
        return ''

    # Build ordered groups (sorted by key, then each group sorted by date desc)
    # _romaji_key handles Latin/Japanese/Chinese uniformly for A-Z ordering.
    groups: dict = {}
    for fi in sorted(data, key=lambda f: _romaji_key(_key(f))):
        groups.setdefault(_key(fi), []).append(fi)

    rows: List[dict] = []
    for g_key, items in groups.items():
        label = g_key
        if group_by == 'date' and len(g_key) == 8 and g_key.isdigit():
            label = f'{g_key[:4]}-{g_key[4:6]}-{g_key[6:]}'
        rows.append({
            '_is_header': True,
            '_header_label': label,
            '_header_count': len(items),
            'full_path': f'__header__{g_key}',
            'date': '', 'actor_name': '', 'reference_number': '',
            'video_name': '', 'number_of_videos': 0, 'videos': [],
        })
        for fi in sorted(items, key=lambda f: f.date, reverse=True):
            rows.append(fi.to_row())
    return rows


# ── Directory picker ───────────────────────────────────────────────────────────

def _browse_folder_sync(title: str = 'Select folder') -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    d = filedialog.askdirectory(title=title)
    root.destroy()
    return d or ''

# ── Page ───────────────────────────────────────────────────────────────────────

@ui.page('/organiser')
async def organiser_page(client: Client, folder: str = '') -> None:
    cfg = load_config()
    organiser_state = load_organiser_state()
    ui_loop = asyncio.get_running_loop()

    # ── Mutable state ──────────────────────────────────────────────────────────
    panel_w_ref = {
        'renamer': int(organiser_state.get('renamer_panel_width', organiser_state.get('left_panel_width', 780))),
        'mover': int(organiser_state.get('mover_panel_width', organiser_state.get('left_panel_width', 680))),
    }
    settings_dialog_ref: list = []
    vtm_exe_ref: List[str]    = [cfg.get('vtm_exe', DEFAULT_VTM_EXE)]
    vtm_preset_ref: List[str] = [cfg.get('vtm_preset', default_vtm_preset())]
    cleanup_delete_other_files_ref: List[bool] = [bool(organiser_state.get('cleanup_delete_other_files', cfg.get('organiser_cleanup_delete_other_files', True)))]
    cleanup_delete_small_videos_ref: List[bool] = [bool(organiser_state.get('cleanup_delete_small_videos', cfg.get('organiser_cleanup_delete_small_videos', False)))]
    cleanup_small_video_mb_ref: List[float] = [float(organiser_state.get('cleanup_small_video_mb', cfg.get('organiser_cleanup_small_video_mb', 30.0)) or 30.0)]
    _default_scan   = str(organiser_state.get('scan_folder', '') or cfg.get('download_folder', ''))
    _default_mover  = str(organiser_state.get('mover_base', '') or '')
    current_dir:       List[str]             = [folder or _default_scan]
    mover_target_base: List[str]             = [_default_mover]
    
    from tracker.store import (
        build_name_to_rating,
        load_tracker,
        resolve_ref_actress_details,
        split_actress_names,
    )
    from utils.ui_ratings import get_actor_rank_html_span
    tracker_data = load_tracker()
    name_to_rating_dict = build_name_to_rating(tracker_data)

    def _refresh_tracker_context() -> None:
        nonlocal tracker_data, name_to_rating_dict
        tracker_data = load_tracker()
        name_to_rating_dict = build_name_to_rating(tracker_data)

    def _canonicalize_actor_name(raw_name: str, ref: str = '') -> dict:
        raw_text = str(raw_name or '').strip()
        names = split_actress_names(raw_text)
        if not names and raw_text:
            names = [raw_text]
        if not names:
            return {
                'display_name': '',
                'raw_name': raw_text,
                'matched': False,
                'full_match': False,
                'match_sources': [],
            }

        details = resolve_ref_actress_details(tracker_data, ref, names)
        resolved_names: list[str] = []
        match_sources: list[str] = []
        matched_count = 0

        for name in names:
            detail = details.get(name, {})
            canonical = str(detail.get('canonical_name') or '').strip()
            resolved_names.append(canonical or name)
            source = str(detail.get('matched_by') or '').strip()
            if source:
                matched_count += 1
                match_sources.append(source)

        deduped_names: list[str] = []
        seen_names: set[str] = set()
        for name in resolved_names:
            if name not in seen_names:
                seen_names.add(name)
                deduped_names.append(name)

        display_name = '、'.join(deduped_names)
        return {
            'display_name': display_name,
            'raw_name': raw_text,
            'matched': matched_count > 0,
            'full_match': matched_count == len(names),
            'match_sources': match_sources,
        }

    def _apply_tracker_actor_names_to_renamer() -> None:
        for info in renamer_data:
            raw_name = getattr(info, 'raw_actor_name', '') or info.actor_name
            resolved = _canonicalize_actor_name(raw_name, info.reference_number)
            info.raw_actor_name = raw_name
            info.actor_name = resolved['display_name'] or raw_name

    def _get_actor_rank_html(actor_text: str, ref: str = '') -> str:
        text = str(actor_text or '').strip()
        if not text:
            return ''

        names = split_actress_names(text)
        if not names:
            names = [text]

        details = resolve_ref_actress_details(tracker_data, ref, names)
        spans: list[str] = []
        for name in names:
            detail = details.get(name, {})
            display_name = str(detail.get('canonical_name') or '').strip() or name
            rating = detail.get('rating')
            if rating is None:
                rating = name_to_rating_dict.get(display_name)
            spans.append(
                get_actor_rank_html_span(
                    display_name,
                    {display_name: rating} if rating is not None else {},
                )
            )
        return ' <span style="color:#4b5563">·</span> '.join(spans)

    def _summary_piece(label: str, value: str, tone: str = 'muted') -> str:
        return (
            f'<span class="org-summary-piece org-summary-piece-{tone}">'
            f'<span class="org-summary-piece-label">{_html.escape(label)}</span> '
            f'<span class="org-summary-piece-value">{_html.escape(value)}</span>'
            f'</span>'
        )

    def _status_mark(value: str, tone: str, title: str) -> str:
        return (
            f'<span class="org-mover-grid-mark org-mover-grid-mark-{tone}" '
            f'title="{_html.escape(title)}">{_html.escape(value)}</span>'
        )

    def _status_spinner(title: str) -> str:
        return (
            f'<span class="org-mover-grid-mark org-mover-grid-mark-progress" '
            f'title="{_html.escape(title)}">'
            '<span class="org-mover-dot-spinner"><span></span><span></span><span></span></span>'
            '</span>'
        )

    def _build_mover_status_html(row: dict) -> str:
        folder_path = str(row.get('full_path', '') or '')
        actor = str(row.get('detected_actor', '') or '').strip()
        target_exists = bool(row.get('target_exists'))
        target = str(row.get('target_dir', '') or '').strip()
        video_count = int(row.get('number_of_videos', 0) or 0)
        has_cover = bool(row.get('has_cover'))
        has_thumb = bool(row.get('has_thumbnails'))
        has_subtitles = bool(row.get('has_subtitles'))

        if not actor:
            dest_mark = _status_mark('—', 'danger', 'No actor detected, so no destination can be resolved')
        elif target_exists:
            dest_mark = _status_mark('✓', 'ok', 'Destination folder already exists')
        elif target:
            dest_mark = _status_mark('+', 'info', 'Destination is resolved and will be created if needed')
        else:
            dest_mark = _status_mark('—', 'danger', 'No destination resolved')

        video_mark = _status_mark(str(video_count), 'ok' if video_count else 'danger', f'{video_count} video file(s) found')
        cover_mark = _status_mark('✓' if has_cover else '—', 'ok' if has_cover else 'warn', 'Cover image found' if has_cover else 'No cover image found')
        if folder_path and folder_path in thumbnail_generating_set:
            thumb_mark = _status_spinner('Generating thumbnails...')
        else:
            thumb_mark = _status_mark('✓' if has_thumb else '—', 'ok' if has_thumb else 'warn', 'Thumbnail image found' if has_thumb else 'No thumbnail image found')
        srt_mark = _status_mark('✓' if has_subtitles else '—', 'ok' if has_subtitles else 'warn', 'Subtitle file found' if has_subtitles else 'No subtitle file found')

        return (
            '<div class="org-mover-grid">'
            f'<span class="org-mover-grid-cell">{dest_mark}</span>'
            f'<span class="org-mover-grid-cell">{video_mark}</span>'
            f'<span class="org-mover-grid-cell">{cover_mark}</span>'
            f'<span class="org-mover-grid-cell">{thumb_mark}</span>'
            f'<span class="org-mover-grid-cell">{srt_mark}</span>'
            '</div>'
        )

    renamer_data:    List[FolderInfo] = []
    mover_data:      List[MoverInfo]  = []
    active_row_ref:  List[Optional[dict]] = [None]
    active_tab_ref:  List[str]        = ['renamer']
    total_renamer:   List[int]        = [0]
    total_mover:     List[int]        = [0]
    group_by_ref:    List[str]        = ['']
    # Per-tab active row for inspector restoration on tab switch
    tab_rows:        dict             = {'renamer': None, 'mover': None}
    # Mutable refs for loading spinners (populated during UI build)
    renamer_loading_ref: List         = []
    mover_loading_ref:   List         = []
    scan_progress_state = {
        'renamer': {'active': False, 'phase': 'idle', 'scanned': 0, 'total': 0, 'discovered': 0},
        'mover': {'active': False, 'phase': 'idle', 'scanned': 0, 'total': 0, 'discovered': 0},
    }
    # Native row element refs  full_path → div element
    renamer_row_els: dict             = {}
    mover_row_els:   dict             = {}
    renamer_row_checks: dict          = {}
    mover_row_checks: dict            = {}
    mover_row_actor_lbls: dict        = {}   # full_path → actor label element
    mover_row_status_lbls: dict       = {}   # full_path → status html element
    mover_row_info: dict              = {}   # full_path → row dict (tracks actor edits)
    renamer_count_lbls: dict          = {}   # full_path → # count label element
    mover_count_lbls: dict            = {}   # full_path → # count label element
    thumbnail_generating_set: set     = set()
    # Row selection state (Explorer selection / focus range)
    renamer_selected_set: set         = set()
    mover_selected_set:   set         = set()
    # Checked rows (batch action set)
    renamer_checked_set: set          = set()
    mover_checked_set:   set          = set()
    renamer_anchor_ref:   List[Optional[str]] = [None]
    mover_anchor_ref:     List[Optional[str]] = [None]

    # ── CSS ────────────────────────────────────────────────────────────────────
    ui.add_head_html('<meta charset="utf-8">')
    ui.add_head_html(f"<style>{Path('assets/theme.css').read_text(encoding='utf-8')}</style>")
    ui.colors(primary='#059669', secondary='#10b981', accent='#047857')

    # ── Header ─────────────────────────────────────────────────────────────────
    with ui.header().classes('org-header text-white px-6 items-center justify-between'):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="home").props("flat round size=sm").style(
                "color:#34d399"
            ).tooltip("Back to Launchpad").on("click", lambda: ui.navigate.to("/"))
            ui.html(
                '<span class="org-logo" style="cursor:pointer" '
                'onclick="window.location=\'/\'" title="Home">JAV Video System</span>'
            )
            build_save_state_badge("organiser", resolver=lambda: [CONFIG_FILE, ORGANISER_STATE_FILE])
        with ui.row().classes("items-center gap-4"):
            last_op_lbl = ui.label('').classes('org-last-op')
            dir_lbl = ui.label(current_dir[0] or 'No folder selected').classes('org-dir-lbl')
            count_chip = ui.html('').classes('org-count-chip').style('display:none')
            # Folder picker: filled icon to distinguish from refresh
            ui.button(icon='folder', on_click=lambda: asyncio.ensure_future(_pick_and_load())).props(
                'unelevated round size=sm'
            ).style('background:#022c22; color:#34d399').tooltip('Change folder')
            ui.button(icon='refresh', on_click=lambda: asyncio.ensure_future(_reload())).props(
                'flat round size=md'
            ).style('color:#34d399').tooltip('Reload')
            ui.button(icon='settings', on_click=lambda: settings_dialog_ref[0].open()).props(
                'flat round size=md'
            ).style('color:#34d399').tooltip('Settings')

    # ── Body ───────────────────────────────────────────────────────────────────
    with ui.row().classes('w-full gap-0 items-start org-shell').style('height:calc(100dvh - 60px)'):

        # ── Left panel ─────────────────────────────────────────────────────────
        with ui.column().classes('org-left gap-0').style(
            f"width:{panel_w_ref['renamer']}px;min-width:{panel_w_ref['renamer']}px"
        ) as left_col:

            with ui.tabs().classes('org-tabs px-1 pt-0') as tab_bar:
                tab_renamer = ui.tab('renamer', label='Renamer', icon='drive_file_rename_outline')
                tab_mover   = ui.tab('mover',   label='Mover', icon='drive_file_move')

            with ui.tab_panels(tab_bar, value=tab_renamer).classes('flex-1 overflow-hidden').style(
                'display:flex; flex-direction:column; width:100%'
            ):
                # ── Renamer panel ───────────────────────────────────────────
                with ui.tab_panel(tab_renamer).classes('q-pa-none').style(
                    'display:flex; flex-direction:column; height:100%; overflow:hidden; width:100%'
                ):
                    with ui.column().classes('org-renamer-top'):
                        with ui.row().classes('org-toolbar org-toolbar-hero'):
                            with ui.column().classes('gap-0'):
                                ui.label('Renamer').classes('org-renamer-title')
                                renamer_sub_lbl = ui.label(
                                    'Normalize matched JAV folders, then use quick checks to catch missing thumbnails or cover-only sets before renaming.'
                                ).classes('org-renamer-subtitle')
                            ui.element('div').classes('flex-1')
                            _r_spin = ui.spinner('dots', size='sm').style('color:#38bdf8')
                            _r_spin.set_visibility(False)
                            renamer_loading_ref.append(_r_spin)

                        renamer_summary_html = ui.html('').classes('org-renamer-summary')

                        with ui.row().classes('org-toolbar org-renamer-toolbar'):
                            ui.label('Group by:').classes('org-toolbar-lbl')
                            group_sel = ui.select(
                                options=list(_GROUP_BY_OPTIONS.keys()),
                                value='No grouping',
                            ).props('dense outlined borderless').style(
                                'font-size:0.75rem; min-width:110px; color:#94a3b8'
                            ).tooltip('Group rows by field')
                            ui.element('div').classes('flex-1')

                    # Column headers
                    with ui.element('div').classes('org-list-col-hdr'):
                        ui.element('div').style('width:36px;flex-shrink:0')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:90px;flex-shrink:0'):
                            ui.label('Date')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('flex:1;min-width:0'):
                            ui.label('Actor')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:100px;flex-shrink:0'):
                            ui.label('Ref')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:34px;flex-shrink:0;text-align:center'):
                            ui.label('#')

                    with ui.element('div').classes('org-table-wrap') as renamer_list_wrap:
                        pass  # populated by _build_renamer_list()

                    with ui.row().classes('org-action-bar items-center gap-2 w-full flex-wrap'):
                        renamer_sel_lbl = ui.label('0 selected · 0 checked').style(
                            'font-size:0.78rem; color:#6b7280'
                        ).classes('org-selection-status')
                        ui.label('Quick Check').classes('org-toolbar-lbl')
                        check_all_renamer_btn = ui.button('Check All', icon='select_all',
                                  on_click=lambda: _check_all_renamer()).props('flat dense size=sm').classes('org-sel-all').tooltip('Check all visible rows')
                        uncheck_all_renamer_btn = ui.button('Uncheck All', icon='deselect',
                                  on_click=lambda: _uncheck_all_renamer()).props('flat dense size=sm').style('color:#34d399').tooltip('Uncheck all visible rows')
                        no_thumb_btn = ui.button('No Thumbs', icon='photo_library',
                                  on_click=lambda: asyncio.ensure_future(_select_no_thumbnails())).props('flat dense size=sm').style('color:#f59e0b').tooltip('Check folders with no thumbnail image named like Thumbnails')
                        cover_only_btn = ui.button('Cover Only', icon='image',
                                  on_click=lambda: asyncio.ensure_future(_select_cover_only())).props('flat dense size=sm').style('color:#fb923c').tooltip('Check folders that only have a cover image (no thumbnails)')
                        ui.separator().props('vertical').style('height:20px; border-color:#1a1a24')
                        ui.label('Checking').classes('org-toolbar-lbl')
                        check_selected_renamer_btn = ui.button('Check Selected', icon='check_box',
                                  on_click=lambda: _check_selected_renamer()).props('flat dense size=sm').style('color:#86efac').tooltip('Check the currently selected rows')
                        uncheck_selected_renamer_btn = ui.button('Uncheck Selected', icon='deselect',
                                  on_click=lambda: _uncheck_selected_renamer()).props('flat dense size=sm').style('color:#34d399').tooltip('Uncheck the currently selected rows')
                        ui.separator().props('vertical').style('height:20px; border-color:#1a1a24')
                        rename_btn = ui.button('Rename', icon='drive_file_rename_outline',
                                               on_click=lambda: asyncio.ensure_future(_do_rename())).props(
                            'size=sm'
                        ).style('background:#059669; color:#fff').tooltip('Rename selected folders')

                # ── Folder Mover panel ──────────────────────────────────────
                with ui.tab_panel(tab_mover).classes('q-pa-none').style(
                    'display:flex; flex-direction:column; height:100%; overflow:hidden; width:100%'
                ):
                    with ui.column().classes('org-mover-top'):
                        with ui.row().classes('org-toolbar org-toolbar-hero'):
                            with ui.column().classes('gap-0'):
                                ui.label('Mover').classes('org-mover-title')
                                mover_sub_lbl = ui.label(
                                    'Base root comes from Settings. Review destinations and catch folders missing thumbnails before moving.'
                                ).classes('org-mover-subtitle')
                            ui.element('div').classes('flex-1')
                            _m_spin = ui.spinner('dots', size='sm').style('color:#10b981')
                            _m_spin.set_visibility(False)
                            mover_loading_ref.append(_m_spin)

                        mover_summary_html = ui.html('').classes('org-mover-summary')

                    # Column headers
                    with ui.element('div').classes('org-list-col-hdr'):
                        ui.element('div').style('width:36px;flex-shrink:0')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:72px;flex-shrink:0'):
                            ui.label('Date')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:138px;flex-shrink:0'):
                            ui.label('Actor')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('flex:1;min-width:0'):
                            ui.label('Video')
                        with ui.element('div').classes('org-list-col-hdr-cell').style('width:178px;flex-shrink:0'):
                            ui.html('<div class="org-mover-grid-hdr"><span>Dest</span><span>Vid</span><span>Cover</span><span>Thumb</span><span>SRT</span></div>')

                    with ui.element('div').classes('org-table-wrap') as mover_list_wrap:
                        pass  # populated by _build_mover_list()

                    with ui.row().classes('org-action-bar items-center gap-2 w-full flex-wrap'):
                        mover_sel_lbl = ui.label('0 selected · 0 checked').style(
                            'font-size:0.78rem; color:#6b7280'
                        ).classes('org-selection-status')
                        rename_vids_toggle = ui.switch('Rename videos inside').props('dense').style(
                            'font-size:0.75rem; color:#9ca3af'
                        ).tooltip(
                            'When the actor name has been edited, also rename video files inside to match'
                        )
                        rename_vids_toggle.value = True
                        ui.label('Quick Check').classes('org-toolbar-lbl')
                        no_thumb_mover_btn = ui.button('No Thumbs', icon='photo_library',
                                  on_click=lambda: _select_mover_no_thumbnails()).props('flat dense size=sm').style('color:#f59e0b').tooltip('Check mover folders without thumbnail images, skipping rows with no videos or no detected actor')
                        target_found_btn = ui.button('Target Found', icon='check_circle',
                                  on_click=lambda: _select_target_found()).props('flat dense size=sm').style('color:#4ade80').tooltip('Check folders whose actor destination already exists')
                        check_all_mover_btn = ui.button('Check All', icon='select_all',
                                  on_click=lambda: _check_all_mover()).props('flat dense size=sm').classes('org-sel-all').tooltip('Check all visible rows')
                        uncheck_all_mover_btn = ui.button('Uncheck All', icon='deselect',
                                on_click=lambda: _uncheck_all_mover()).props('flat dense size=sm').style('color:#34d399').tooltip('Uncheck all visible rows')
                        ui.separator().props('vertical').style('height:20px; border-color:#1a1a24')
                        ui.label('Checking').classes('org-toolbar-lbl')
                        check_selected_mover_btn = ui.button('Check Selected', icon='check_box',
                                  on_click=lambda: _check_selected_mover()).props('flat dense size=sm').style('color:#86efac').tooltip('Check the currently selected rows')
                        uncheck_selected_mover_btn = ui.button('Uncheck Selected', icon='deselect',
                                  on_click=lambda: _uncheck_selected_mover()).props('flat dense size=sm').style('color:#34d399').tooltip('Uncheck the currently selected rows')
                        ui.separator().props('vertical').style('height:20px; border-color:#1a1a24')
                        vtm_batch_btn = ui.button('Thumbnails', icon='photo_library',
                                  on_click=lambda: asyncio.ensure_future(_do_vtm_batch())).props('dense size=sm').style('background:#065f46; color:#6ee7b7').tooltip('Generate thumbnails for selected mover folders (VTM)')
                        move_btn = ui.button('Move Selected', icon='drive_file_move',
                                             on_click=lambda: asyncio.ensure_future(_do_move())).props(
                            'size=sm'
                        ).style('background:#0891b2; color:#fff')

        # ── Right panel ────────────────────────────────────────────────────────
        with ui.column().classes('org-right gap-0') as right_col:
            _build_empty_right(right_col)

    # Disable action buttons initially (nothing selected yet)
    rename_btn.set_enabled(False)
    check_selected_renamer_btn.set_enabled(False)
    uncheck_selected_renamer_btn.set_enabled(False)
    check_all_renamer_btn.set_enabled(False)
    uncheck_all_renamer_btn.set_enabled(False)
    move_btn.set_enabled(False)
    check_selected_mover_btn.set_enabled(False)
    uncheck_selected_mover_btn.set_enabled(False)
    check_all_mover_btn.set_enabled(False)
    uncheck_all_mover_btn.set_enabled(False)
    vtm_batch_btn.set_enabled(False)

    def _left_panel_style(tab_name: Optional[str] = None) -> str:
        active_tab = tab_name or active_tab_ref[0]
        width = int(panel_w_ref.get(active_tab, panel_w_ref['renamer']))
        return f'width:{width}px;min-width:{width}px'

    def _apply_left_panel_width(tab_name: Optional[str] = None) -> None:
        left_col.style(_left_panel_style(tab_name))

    def _render_scan_progress_summary(kind: str) -> str:
        state = scan_progress_state[kind]
        noun = 'Matched' if kind == 'renamer' else 'Found'
        phase_value = {
            'queued': 'Queued',
            'start': 'Starting',
            'progress': 'Scanning',
            'complete': 'Finishing',
        }.get(state['phase'], 'Loading')
        pieces = [
            _summary_piece('Stage', phase_value, 'warn'),
            _summary_piece('Scan', f"{state['scanned']}/{state['total'] or '—'}", 'info'),
            _summary_piece(noun, str(state['discovered']), 'ok'),
        ]
        return f'<div class="org-mover-summary-line">{"".join(pieces)}</div>'

    def _render_scan_progress_subtitle(kind: str) -> str:
        state = scan_progress_state[kind]
        if state['phase'] == 'queued':
            return 'Waiting to start scan after the current organiser scan finishes.'
        if state['total']:
            return (
                f"Scanning {state['scanned']}/{state['total']} folder(s). "
                f"Discovered {state['discovered']} {'match' if kind == 'renamer' else 'mover row'}"
                f"{'es' if state['discovered'] != 1 else ''} so far."
            )
        return 'Preparing organiser scan…'

    def _set_scan_progress(kind: str, **updates) -> None:
        scan_progress_state[kind].update(updates)
        if kind == 'renamer':
            _update_renamer_summary()
        else:
            _update_mover_summary()

    def _queue_scan_progress(kind: str, payload: dict) -> None:
        snapshot = dict(payload)

        def _apply() -> None:
            _set_scan_progress(
                kind,
                active=True,
                phase=snapshot.get('phase', 'progress'),
                scanned=int(snapshot.get('scanned', 0) or 0),
                total=int(snapshot.get('total', 0) or 0),
                discovered=int(snapshot.get('discovered', 0) or 0),
            )

        ui_loop.call_soon_threadsafe(_apply)

    def _make_scan_progress_callback(kind: str):
        def _callback(payload: dict) -> None:
            _queue_scan_progress(kind, payload)

        return _callback

    def _begin_scan_progress(kind: str, phase: str = 'start') -> None:
        _set_scan_progress(kind, active=True, phase=phase, scanned=0, total=0, discovered=0)

    def _end_scan_progress(kind: str) -> None:
        scan_progress_state[kind].update(active=False, phase='idle')

    def _update_mover_summary() -> None:
        if scan_progress_state['mover']['active']:
            mover_summary_html.content = _render_scan_progress_summary('mover')
            mover_sub_lbl.text = _render_scan_progress_subtitle('mover')
            return

        rows = list(mover_row_info.values()) if mover_row_info else [m.to_row() for m in mover_data]
        total = len(rows)
        ready = sum(1 for row in rows if row.get('detected_actor') and row.get('target_exists'))
        new_targets = sum(1 for row in rows if row.get('detected_actor') and row.get('target_dir') and not row.get('target_exists'))
        missing_actor = sum(1 for row in rows if not str(row.get('detected_actor', '') or '').strip())
        missing_cover = sum(1 for row in rows if not row.get('has_cover'))
        no_thumbs = sum(1 for row in rows if not row.get('has_thumbnails'))
        missing_srt = sum(1 for row in rows if not row.get('has_subtitles'))

        mover_summary_html.content = (
            f'<div class="org-mover-summary-line">'
            f'{_summary_piece("Ready", str(ready), "ok")}'
            f'{_summary_piece("New", str(new_targets), "info")}'
            f'{_summary_piece("Actor?", str(missing_actor), "danger")}'
            f'{_summary_piece("Cover?", str(missing_cover), "warn")}'
            f'{_summary_piece("Thumb?", str(no_thumbs), "warn")}'
            f'{_summary_piece("SRT?", str(missing_srt), "warn")}'
            f'</div>'
        )
        generating = len(thumbnail_generating_set)
        mover_sub_lbl.text = (
            f'{total} folders in mover queue. '
            + (f'{generating} thumbnail job(s) running. ' if generating else '')
            + 'Raw actor text stays untouched; colors still split across multi-actor names.'
        )

    def _update_renamer_summary() -> None:
        if scan_progress_state['renamer']['active']:
            renamer_summary_html.content = _render_scan_progress_summary('renamer')
            renamer_sub_lbl.text = _render_scan_progress_subtitle('renamer')
            return

        total = len(renamer_data)
        total_videos = sum(info.number_of_videos for info in renamer_data)
        multi_video = sum(1 for info in renamer_data if info.number_of_videos > 1)
        selected = len(renamer_selected_set)
        checked = len(renamer_checked_set)

        renamer_summary_html.content = (
            f'<div class="org-mover-summary-line">'
            f'{_summary_piece("Folders", str(total), "info")}'
            f'{_summary_piece("Videos", str(total_videos), "ok")}'
            f'{_summary_piece("Multi", str(multi_video), "warn")}'
            f'{_summary_piece("Selected", str(selected), "info")}'
            f'{_summary_piece("Checked", str(checked), "ok")}'
            f'</div>'
        )
        renamer_sub_lbl.text = (
            f'{total} matched folder(s) ready for normalization. '
            f'{multi_video} folder(s) contain multiple video files. '
            'Quick checks help isolate missing thumbnails and cover-only folders.'
        )

    # ── Row building helpers ───────────────────────────────────────────────────

    def _add_renamer_group_header(row: dict) -> None:
        label = row.get('_header_label', '—')
        count = row.get('_header_count', 0)
        with ui.element('div').classes('org-list-group-hdr'):
            ui.html(
                f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;'
                f'color:#34d399;text-transform:uppercase">{_html.escape(str(label))}</span>'
                f'<span style="font-size:0.68rem;color:#4b5563;margin-left:4px">— {count}</span>'
            )

    def _add_renamer_row(row: dict) -> None:
        fp = row['full_path']
        is_sel = fp in renamer_selected_set
        is_checked = fp in renamer_checked_set
        active_fp = active_row_ref[0].get('full_path', '') if active_row_ref[0] else ''
        css = 'org-list-row' + (' selected' if is_sel else '') + (' active-row' if fp == active_fp else '')
        with ui.element('div').classes(css) as row_el:
            renamer_row_els[fp] = row_el
            # Checkbox wrapper — @click.stop prevents bubbling to row_el
            with ui.element('div').style(
                'width:36px;flex-shrink:0;display:flex;align-items:center;justify-content:center'
            ).props('@click.stop="() => {}"'):
                renamer_check = ui.checkbox(
                    value=is_checked,
                    on_change=lambda e, p=fp, el=row_el: _toggle_renamer_sel(p, e.value, el)
                ).props('dense color=indigo')
                renamer_row_checks[fp] = renamer_check
            # Date
            d = row.get('date', '')
            date_str = f'{d[:4]}-{d[4:6]}-{d[6:]}' if len(d) == 8 else d
            with ui.element('div').style('width:90px;flex-shrink:0'):
                ui.label(date_str).style('font-family:monospace;font-size:0.8rem;color:#cbd5e1;white-space:nowrap')
            # Actor — takes remaining width
            with ui.element('div').style('flex:1;min-width:0;overflow:hidden;line-height:2;padding-block:4px;margin-block:-4px;'):
                _act = row.get('actor_name', '')
                _raw_act = row.get('raw_actor_name', '') or _act
                _tip = _act
                if _raw_act and _raw_act != _act:
                    _tip = f'{_act}\nOriginal folder actor: {_raw_act}'
                ui.html(_get_actor_rank_html(_act, row.get('reference_number', '')) if _act else '').classes('org-list-sm').tooltip(_tip)
            # Ref badge
            with ui.element('div').style('width:100px;flex-shrink:0'):
                ui.html(f'<span class="ref-badge">{_html.escape(row.get("reference_number", ""))}</span>')
            # Count — store ref for live updates
            with ui.element('div').style('width:34px;flex-shrink:0;text-align:center'):
                _cnt = ui.label(str(row.get('number_of_videos', 0))).style('font-size:0.82rem;color:#6b7280')
                renamer_count_lbls[fp] = _cnt
            # Context menu (NiceGUI native — pure Python handlers)
            with ui.context_menu():
                with ui.list().props('dense').style(
                    'background:#111118;border:1px solid #1a1a24;min-width:190px'
                ):
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp: open_folder_in_explorer(p)
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('folder_open', color='blue-4', size='xs')
                        with ui.item_section():
                            ui.label('Open Folder').style('font-size:0.82rem;color:#e2e8f0')
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp: ui.run_javascript(
                            f'navigator.clipboard.writeText({repr(p)})'
                        )
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('content_copy', color='grey-5', size='xs')
                        with ui.item_section():
                            ui.label('Copy Full Path').style('font-size:0.82rem;color:#e2e8f0')
                    ui.separator()
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp, el=row_el: _toggle_renamer_sel(
                            p, p not in renamer_checked_set, el
                        )
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('check_box_outline_blank', color='indigo-4', size='xs')
                        with ui.item_section():
                            ui.label('Check / Uncheck').style('font-size:0.82rem;color:#e2e8f0')
        row_el.on(
            'click',
            lambda e, r=row: _on_renamer_row_click_native(r, e),
            ['ctrlKey', 'shiftKey', 'metaKey'],
        )

    def _build_renamer_list() -> None:
        renamer_list_wrap.clear()
        renamer_row_els.clear()
        renamer_row_checks.clear()
        renamer_count_lbls.clear()
        rows = _build_renamer_rows(renamer_data, group_by_ref[0])
        if not rows:
            with renamer_list_wrap:
                with ui.element('div').classes('org-empty'):
                    ui.icon('folder').style('font-size:2rem;opacity:.3')
                    ui.html(
                        '<div>No matching folders found.<br>Select a folder containing JAV folders named'
                        '<br><code style="color:#34d399">YYYYMMDD - Title Actor REF-123</code></div>'
                    )
            return
        with renamer_list_wrap:
            for row in rows:
                if row.get('_is_header'):
                    _add_renamer_group_header(row)
                else:
                    _add_renamer_row(row)

    def _add_mover_row(row: dict) -> None:
        fp = row['full_path']
        is_sel = fp in mover_selected_set
        is_checked = fp in mover_checked_set
        active_fp = active_row_ref[0].get('full_path', '') if active_row_ref[0] else ''
        css = 'org-list-row org-mover-list-row' + (' selected' if is_sel else '') + (' active-row' if fp == active_fp else '')
        mover_row_info[fp] = row
        with ui.element('div').classes(css) as row_el:
            mover_row_els[fp] = row_el
            # Checkbox wrapper
            with ui.element('div').style(
                'width:36px;flex-shrink:0;display:flex;align-items:center;justify-content:center'
            ).props('@click.stop="() => {}"'):
                mover_check = ui.checkbox(
                    value=is_checked,
                    on_change=lambda e, p=fp, el=row_el: _toggle_mover_sel(p, e.value, el)
                ).props('dense color=indigo')
                mover_row_checks[fp] = mover_check
            # Date (from folder_name prefix YYYYMMDD)
            fn = row.get('folder_name', '')
            d_raw = fn[:8] if len(fn) >= 8 and fn[:8].isdigit() else ''
            date_str = f'{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:]}' if d_raw else '—'
            with ui.element('div').style('width:72px;flex-shrink:0'):
                ui.label(date_str).style('font-family:monospace;font-size:0.74rem;color:#cbd5e1;white-space:nowrap')
            # Actor column
            with ui.element('div').classes('org-mover-actor-col'):
                _act2 = row.get('detected_actor', '')
                actor_lbl = ui.html(_get_actor_rank_html(_act2) if _act2 else '—').classes('org-list-sm')
                mover_row_actor_lbls[fp] = actor_lbl
            # Video column with reserved two-line clamp
            with ui.element('div').classes('org-mover-video-col'):
                video_hint = row.get('detected_video_name', '') or 'No video name detected'
                ui.label(video_hint).classes('org-mover-subline org-mover-video-title').tooltip(video_hint)
            with ui.element('div').style('width:178px;flex-shrink:0;overflow:hidden'):
                status_html = ui.html(_build_mover_status_html(row)).tooltip(
                    _fmt_target(row.get('target_dir', ''), row.get('target_exists', False))
                )
                mover_row_status_lbls[fp] = status_html
            # Context menu
            with ui.context_menu():
                with ui.list().props('dense').style(
                    'background:#111118;border:1px solid #1a1a24;min-width:190px'
                ):
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp: open_folder_in_explorer(p)
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('folder_open', color='blue-4', size='xs')
                        with ui.item_section():
                            ui.label('Open Folder').style('font-size:0.82rem;color:#e2e8f0')
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp: ui.run_javascript(
                            f'navigator.clipboard.writeText({repr(p)})'
                        )
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('content_copy', color='grey-5', size='xs')
                        with ui.item_section():
                            ui.label('Copy Full Path').style('font-size:0.82rem;color:#e2e8f0')
                    ui.separator()
                    with ui.item().props('clickable v-close-popup dense').on(
                        'click', lambda p=fp, el=row_el: _toggle_mover_sel(
                            p, p not in mover_checked_set, el
                        )
                    ):
                        with ui.item_section().props('side'):
                            ui.icon('check_box_outline_blank', color='indigo-4', size='xs')
                        with ui.item_section():
                            ui.label('Check / Uncheck').style('font-size:0.82rem;color:#e2e8f0')
        row_el.on(
            'click',
            lambda e, r=row: _on_mover_row_click_native(r, e),
            ['ctrlKey', 'shiftKey', 'metaKey'],
        )

    def _build_mover_list() -> None:
        mover_list_wrap.clear()
        mover_row_els.clear()
        mover_row_checks.clear()
        mover_row_actor_lbls.clear()
        mover_row_status_lbls.clear()
        mover_row_info.clear()
        mover_count_lbls.clear()
        rows = [m.to_row() for m in mover_data]
        if not rows:
            _update_mover_summary()
            with mover_list_wrap:
                with ui.element('div').classes('org-empty'):
                    ui.icon('folder').style('font-size:2rem;opacity:.3')
                    ui.html(
                        '<div>No date-prefixed folders found.<br>Select a folder containing subfolders named'
                        '<br><code style="color:#34d399">YYYYMMDD - ...</code></div>'
                    )
            return
        with mover_list_wrap:
            for row in rows:
                _add_mover_row(row)
        _update_mover_summary()

    # ── Selection helpers ──────────────────────────────────────────────────────

    def _sync_row_checkbox(checkbox_refs: dict, fp: str, is_checked: bool) -> None:
        checkbox = checkbox_refs.get(fp)
        if not checkbox:
            return
        checkbox.value = is_checked
        try:
            checkbox.update()
        except Exception:
            pass

    def _set_row_checked(checkbox_refs: dict, checked_set: set, fp: str, is_checked: bool) -> None:
        if is_checked:
            checked_set.add(fp)
        else:
            checked_set.discard(fp)
        _sync_row_checkbox(checkbox_refs, fp, is_checked)

    def _toggle_renamer_sel(fp: str, new_val: bool, row_el) -> None:
        _set_row_checked(renamer_row_checks, renamer_checked_set, fp, new_val)
        _update_sel_labels()

    def _toggle_mover_sel(fp: str, new_val: bool, row_el) -> None:
        _set_row_checked(mover_row_checks, mover_checked_set, fp, new_val)
        _update_sel_labels()

    def _set_row_selected(row_els: dict, checkbox_refs: dict, selected_set: set, fp: str, is_selected: bool) -> None:
        if is_selected:
            selected_set.add(fp)
            if fp in row_els:
                row_els[fp].classes(add='selected')
        else:
            selected_set.discard(fp)
            if fp in row_els:
                row_els[fp].classes(remove='selected')

    def _apply_selection_range(
        ordered_paths: List[str],
        row_els: dict,
        checkbox_refs: dict,
        selected_set: set,
        anchor_path: Optional[str],
        current_path: str,
        *,
        keep_existing: bool,
    ) -> None:
        if not anchor_path or anchor_path not in ordered_paths or current_path not in ordered_paths:
            if not keep_existing:
                for path in list(selected_set):
                    _set_row_selected(row_els, checkbox_refs, selected_set, path, False)
            _set_row_selected(row_els, checkbox_refs, selected_set, current_path, True)
            return

        start = ordered_paths.index(anchor_path)
        end = ordered_paths.index(current_path)
        lower, upper = (start, end) if start <= end else (end, start)
        range_paths = set(ordered_paths[lower:upper + 1])

        if not keep_existing:
            for path in list(selected_set):
                if path not in range_paths:
                    _set_row_selected(row_els, checkbox_refs, selected_set, path, False)

        for path in range_paths:
            _set_row_selected(row_els, checkbox_refs, selected_set, path, True)

    def _set_active_row(row: dict, *, tab_name: str, row_els: dict) -> None:
        active_row_ref[0] = row
        active_tab_ref[0] = tab_name
        tab_rows[tab_name] = row
        for fp, el in row_els.items():
            if fp == row['full_path']:
                el.classes(add='active-row')
            else:
                el.classes(remove='active-row')
        _refresh_right_panel(row)

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _update_sel_labels() -> None:
        renamer_selected = len(renamer_selected_set)
        renamer_checked = len(renamer_checked_set)
        renamer_sel_lbl.text = f'{renamer_selected} selected · {renamer_checked} checked'
        _update_renamer_summary()
        rename_btn.set_enabled(renamer_checked > 0)
        check_selected_renamer_btn.set_enabled(renamer_selected > 0)
        uncheck_selected_renamer_btn.set_enabled(renamer_selected > 0)
        check_all_renamer_btn.set_enabled(total_renamer[0] > 0)
        uncheck_all_renamer_btn.set_enabled(renamer_checked > 0)

        mover_selected = len(mover_selected_set)
        mover_checked = len(mover_checked_set)
        mover_sel_lbl.text = f'{mover_selected} selected · {mover_checked} checked'
        busy = bool(thumbnail_generating_set)
        move_btn.set_enabled(mover_checked > 0 and not busy)
        check_selected_mover_btn.set_enabled(mover_selected > 0)
        uncheck_selected_mover_btn.set_enabled(mover_selected > 0)
        check_all_mover_btn.set_enabled(total_mover[0] > 0)
        uncheck_all_mover_btn.set_enabled(mover_checked > 0)
        vtm_batch_btn.set_enabled(mover_checked > 0 and not busy)

    def _clear_renamer_selection() -> None:
        for fp in list(renamer_selected_set):
            if fp in renamer_row_els:
                renamer_row_els[fp].classes(remove='selected')
        renamer_selected_set.clear()
        renamer_anchor_ref[0] = None
        _update_sel_labels()

    def _clear_mover_selection() -> None:
        for fp in list(mover_selected_set):
            if fp in mover_row_els:
                mover_row_els[fp].classes(remove='selected')
        mover_selected_set.clear()
        mover_anchor_ref[0] = None
        _update_sel_labels()

    def _check_selected_renamer() -> None:
        for fp in list(renamer_selected_set):
            _set_row_checked(renamer_row_checks, renamer_checked_set, fp, True)
        _update_sel_labels()

    def _uncheck_selected_renamer() -> None:
        for fp in list(renamer_selected_set):
            _set_row_checked(renamer_row_checks, renamer_checked_set, fp, False)
        _update_sel_labels()

    def _check_selected_mover() -> None:
        for fp in list(mover_selected_set):
            _set_row_checked(mover_row_checks, mover_checked_set, fp, True)
        _update_sel_labels()

    def _uncheck_selected_mover() -> None:
        for fp in list(mover_selected_set):
            _set_row_checked(mover_row_checks, mover_checked_set, fp, False)
        _update_sel_labels()

    def _check_all_renamer() -> None:
        for fp in renamer_row_els.keys():
            _set_row_checked(renamer_row_checks, renamer_checked_set, fp, True)
        _update_sel_labels()

    def _uncheck_all_renamer() -> None:
        for fp in list(renamer_checked_set):
            _set_row_checked(renamer_row_checks, renamer_checked_set, fp, False)
        _update_sel_labels()

    def _check_all_mover() -> None:
        for fp in mover_row_els.keys():
            _set_row_checked(mover_row_checks, mover_checked_set, fp, True)
        _update_sel_labels()

    def _uncheck_all_mover() -> None:
        for fp in list(mover_checked_set):
            _set_row_checked(mover_row_checks, mover_checked_set, fp, False)
        _update_sel_labels()

    def _select_all_renamer() -> None:
        for fp in renamer_row_els.keys():
            _set_row_selected(renamer_row_els, renamer_row_checks, renamer_selected_set, fp, True)
        renamer_anchor_ref[0] = next(reversed(renamer_row_els), None) if renamer_row_els else None
        _update_sel_labels()

    def _select_all_mover() -> None:
        for fp in mover_row_els.keys():
            _set_row_selected(mover_row_els, mover_row_checks, mover_selected_set, fp, True)
        mover_anchor_ref[0] = next(reversed(mover_row_els), None) if mover_row_els else None
        _update_sel_labels()

    # Row click → inspector
    def _on_renamer_row_click_native(row: dict, e) -> None:
        args = e.args or {}
        use_ctrl = bool(args.get('ctrlKey') or args.get('metaKey'))
        use_shift = bool(args.get('shiftKey'))
        fp = row['full_path']
        ordered_paths = list(renamer_row_els.keys())

        if use_shift:
            _apply_selection_range(
                ordered_paths,
                renamer_row_els,
                renamer_row_checks,
                renamer_selected_set,
                renamer_anchor_ref[0],
                fp,
                keep_existing=use_ctrl,
            )
        elif use_ctrl:
            _set_row_selected(renamer_row_els, renamer_row_checks, renamer_selected_set, fp, fp not in renamer_selected_set)
        else:
            for path in list(renamer_selected_set):
                if path != fp:
                    _set_row_selected(renamer_row_els, renamer_row_checks, renamer_selected_set, path, False)
            _set_row_selected(renamer_row_els, renamer_row_checks, renamer_selected_set, fp, True)

        renamer_anchor_ref[0] = fp
        _update_sel_labels()
        _set_active_row(row, tab_name='renamer', row_els=renamer_row_els)

    def _on_mover_row_click_native(row: dict, e) -> None:
        args = e.args or {}
        use_ctrl = bool(args.get('ctrlKey') or args.get('metaKey'))
        use_shift = bool(args.get('shiftKey'))
        fp = row['full_path']
        ordered_paths = list(mover_row_els.keys())

        if use_shift:
            _apply_selection_range(
                ordered_paths,
                mover_row_els,
                mover_row_checks,
                mover_selected_set,
                mover_anchor_ref[0],
                fp,
                keep_existing=use_ctrl,
            )
        elif use_ctrl:
            _set_row_selected(mover_row_els, mover_row_checks, mover_selected_set, fp, fp not in mover_selected_set)
        else:
            for path in list(mover_selected_set):
                if path != fp:
                    _set_row_selected(mover_row_els, mover_row_checks, mover_selected_set, path, False)
            _set_row_selected(mover_row_els, mover_row_checks, mover_selected_set, fp, True)

        mover_anchor_ref[0] = fp
        _update_sel_labels()
        _set_active_row(row, tab_name='mover', row_els=mover_row_els)

    # Tab switch → restore per-tab inspector
    def _on_tab_change(e) -> None:
        new_tab = e.value  # 'renamer' or 'mover'
        active_tab_ref[0] = new_tab
        _apply_left_panel_width(new_tab)
        saved_row = tab_rows.get(new_tab)
        if saved_row and saved_row.get('full_path') and os.path.isdir(saved_row['full_path']):
            active_row_ref[0] = saved_row
            _refresh_right_panel(saved_row)
        else:
            right_col.clear()
            _build_empty_right(right_col)

    tab_bar.on_value_change(_on_tab_change)

    # Group by change → rebuild renamer list
    def _on_group_change(e) -> None:
        group_by_ref[0] = _GROUP_BY_OPTIONS.get(e.value, '')
        renamer_selected_set.clear()
        renamer_checked_set.clear()
        renamer_anchor_ref[0] = None
        _build_renamer_list()
        _update_sel_labels()
        right_col.clear()
        _build_empty_right(right_col)

    group_sel.on_value_change(_on_group_change)

    # ── Right panel builder ────────────────────────────────────────────────────

    def _refresh_right_panel(row: dict) -> None:
        right_col.clear()
        folder_path = row.get('full_path', '')
        if not folder_path or not os.path.isdir(folder_path):
            _build_empty_right(right_col)
            return

        cfg_now = load_config()
        llc_exe = cfg_now.get('losslesscut_exe', DEFAULT_LOSSLESSCUT_EXE)
        vtm_ok = os.path.isfile(vtm_exe_ref[0]) and os.path.isfile(vtm_preset_ref[0])

        with right_col:
            all_files = list_all_folder_files(folder_path)
            covers = [f for f in all_files if f['is_image'] and f['is_cover']]
            cover_img_path = (covers[0]['path'] if covers else
                              next((f['path'] for f in all_files if f['is_image']), None))
            videos: List[dict] = row.get('videos', [])
            is_mover_tab = active_tab_ref[0] == 'mover'
            cover_width = 184 if is_mover_tab else 220
            is_thumb_generating = folder_path in thumbnail_generating_set
            target_dir_now = row.get('target_dir', '')
            target_exists_now = bool(row.get('target_exists'))

            def _cleanup_tooltip() -> str:
                parts = []
                if cleanup_delete_other_files_ref[0]:
                    parts.append('delete non-media files')
                if cleanup_delete_small_videos_ref[0]:
                    parts.append(f'delete videos under {cleanup_small_video_mb_ref[0]:g} MB')
                if not parts:
                    parts.append('no cleanup rules enabled in Settings')
                return 'Quick Clean: ' + '; '.join(parts)

            hero_gap = 12 if is_mover_tab else 14
            with ui.column().classes('org-right-scroll gap-0').style(
                f'--org-cover-col-w:{cover_width}px;--org-hero-gap:{hero_gap}px'
            ):
                # ══ TOP: Cover (left) + Info (right) ═══════════════════════════
                hero_classes = 'w-full items-start org-inspector-hero' if is_mover_tab else 'w-full items-start org-renamer-hero'

                def _target_leaf(target_dir: str) -> str:
                    if not target_dir:
                        return 'No target selected'
                    leaf = os.path.basename(target_dir) or target_dir
                    parent = os.path.basename(os.path.dirname(target_dir))
                    return f'{parent}\\{leaf}' if parent else leaf

                with ui.row().classes(hero_classes).style('margin-bottom:16px'):

                    name = row.get('video_name') or row.get('folder_name') or os.path.basename(folder_path)
                    ref  = row.get('reference_number', '')
                    actor = row.get('actor_name', '') or row.get('detected_actor', '')
                    date_str = row.get('date', '')
                    date_display = _format_display_date(date_str)

                    # ── Cover column ──────────────────────────────────────────
                    cover_col_class = 'org-inspector-cover-col' if is_mover_tab else 'org-renamer-cover-col'
                    with ui.element('div').classes(cover_col_class).style(f'width:{cover_width}px;flex-shrink:0'):
                        if cover_img_path:
                            encoded = urllib.parse.quote(cover_img_path)
                            img_src = f'/api/organiser-img?path={encoded}'
                            cover_el = ui.image(img_src).style(
                                f'width:{cover_width}px;border-radius:10px;cursor:zoom-in;display:block;object-fit:cover'
                            )
                            cover_el.on('click', lambda src=img_src: _lightbox(src))
                        else:
                            with ui.element('div').style(
                                f'width:{cover_width}px;height:300px;background:#0f0f14;border-radius:10px;'
                                'display:flex;align-items:center;justify-content:center;color:#374151'
                            ):
                                ui.icon('image_not_supported').style('font-size:3rem')

                    # ── Info column ───────────────────────────────────────────
                    if is_mover_tab:
                        with ui.column().classes('gap-0 org-inspector-meta-col').style('flex:1;min-width:0'):
                            ui.label(name).classes('org-folder-title org-folder-title-cover').style('margin-bottom:6px')
                            meta_plain = ' · '.join([p for p in [ref, date_display] if p])
                            if meta_plain or actor:
                                with ui.row().classes('items-center gap-1 flex-wrap').style(
                                    'margin-bottom:10px;min-width:0'
                                ):
                                    if meta_plain:
                                        ui.label(meta_plain).style(
                                            'font-size:0.75rem;color:#6b7280;max-width:100%;'
                                            'overflow:hidden;text-overflow:ellipsis;white-space:nowrap'
                                        )
                                    if meta_plain and actor:
                                        ui.label('·').style('font-size:0.75rem;color:#4b5563')
                                    if actor:
                                        ui.html(_get_actor_rank_html(actor, row.get('reference_number', ''))).style(
                                            'font-size:0.75rem;line-height:1.6;min-width:0;max-width:100%'
                                        )

                            def _mover_target_label(target_dir: str, exists: bool) -> str:
                                if not target_dir:
                                    return 'No target'
                                return 'Target exists' if exists else 'New target'

                            def _render_mover_meta_pills(ref_value: str, date_value: str, target_dir: str, exists: bool) -> str:
                                target_tone = 'ok' if exists else ('info' if target_dir else 'warn')
                                pills: list[str] = []
                                if ref_value:
                                    pills.append(f'<span class="org-meta-pill">{_html.escape(ref_value)}</span>')
                                if date_value:
                                    pills.append(f'<span class="org-meta-pill org-meta-pill-muted">{_html.escape(date_value)}</span>')
                                pills.append(
                                    f'<span class="org-meta-pill org-meta-pill-{target_tone}">{_html.escape(_mover_target_label(target_dir, exists))}</span>'
                                )
                                return '<div class="org-meta-pill-row">' + ''.join(pills) + '</div>'

                            mover_meta_pills_html = ui.html(
                                _render_mover_meta_pills(ref, date_display, target_dir_now, target_exists_now)
                            ).style('margin-bottom:10px')

                    else:
                        with ui.column().classes('gap-0 org-renamer-meta-col').style('flex:1;min-width:0'):
                            ui.label(name).classes('org-folder-title org-folder-title-cover org-renamer-folder-title').style('margin-bottom:6px')
                            renamer_facts: list[tuple[str, str]] = []
                            if ref:
                                renamer_facts.append(('Reference', _html.escape(ref)))
                            if date_display:
                                renamer_facts.append(('Released', _html.escape(date_display)))
                            renamer_facts.append(('Files', f'{len(videos)} video(s)'))

                            with ui.element('div').classes('org-renamer-facts-card'):
                                if actor:
                                    with ui.element('div').classes('org-renamer-fact-row org-renamer-fact-row-featured'):
                                        ui.label('Performer').classes('org-renamer-fact-label')
                                        ui.html(_get_actor_rank_html(actor, row.get('reference_number', ''))).classes('org-renamer-fact-value org-renamer-fact-actor')
                                for fact_label, fact_value in renamer_facts:
                                    with ui.element('div').classes('org-renamer-fact-row'):
                                        ui.label(fact_label).classes('org-renamer-fact-label')
                                        ui.html(f'<span class="org-renamer-fact-value">{fact_value}</span>')

                if not is_mover_tab:
                    old_name = os.path.basename(folder_path)
                    new_name = f"{row.get('date', '')} - {row.get('video_name', '')}"
                    _preview_videos: List[dict] = row.get('videos', [])

                    with ui.element('div').classes('org-renamer-detail-row'):
                        with ui.element('div').classes('org-action-group-card org-renamer-action-panel'):
                            with ui.element('div').classes('org-renamer-action-section'):
                                ui.label('Folder').classes('org-section-hdr org-renamer-action-heading')
                                with ui.column().classes('org-renamer-action-buttons'):
                                    ui.button('Open Folder', icon='folder_open',
                                              on_click=lambda p=folder_path: open_folder_in_explorer(p)
                                              ).props('flat dense size=sm').classes('org-renamer-action-btn').style('color:#60a5fa')
                                    ui.button(
                                        'Quick Clean', icon='cleaning_services',
                                        on_click=lambda r=row, fp=folder_path: asyncio.ensure_future(_do_cleanup(r, fp))
                                    ).props('flat dense size=sm').classes('org-renamer-action-btn').style('color:#f59e0b').tooltip(_cleanup_tooltip())
                                    ui.button(
                                        'Copy Folder Path', icon='content_copy',
                                        on_click=lambda p=folder_path: ui.run_javascript(
                                            f'navigator.clipboard.writeText({repr(p)})'
                                        ),
                                    ).props('flat dense size=sm').classes('org-renamer-action-btn').style('color:#67e8f9')

                            if row.get('reference_number'):
                                with ui.element('div').classes('org-renamer-action-section'):
                                    ui.label('Assets').classes('org-section-hdr org-renamer-action-heading')
                                    with ui.column().classes('org-renamer-action-buttons'):
                                        ui.button('Rename Images', icon='image',
                                                  on_click=lambda r=row, fp=folder_path: asyncio.ensure_future(
                                                      _do_rename_images(r, fp)
                                                  )).props('flat dense size=sm').classes('org-renamer-action-btn').style('color:#67e8f9').tooltip(
                                            'Rename image files to REF Cover/Thumbnails convention')

                        with ui.element('div').classes('org-renamer-preview-card'):
                            ui.label('RENAME PREVIEW').classes('org-section-hdr').style('margin-bottom:6px')
                            if old_name != new_name:
                                with ui.element('div').style('width:100%;margin-bottom:4px'):
                                    with ui.element('div').classes('rename-diff-row'):
                                        ui.html(
                                            f'<div class="rename-diff-item"><span class="rename-diff-label">Current</span>'
                                            f'<span class="rename-diff-old" title="{_html.escape(old_name)}">{_html.escape(old_name)}</span></div>'
                                        )
                                        ui.html(
                                            f'<div class="rename-diff-item"><span class="rename-diff-label">Result</span>'
                                            f'<span class="rename-diff-new" title="{_html.escape(new_name)}">{_html.escape(new_name)}</span></div>'
                                        )
                            else:
                                ui.label('Folder name already matches the normalised title.').classes('org-renamer-preview-note')
                            if _preview_videos:
                                ui.label(f'{len(_preview_videos)} video(s) and matching assets will be renamed inside the folder.').classes('org-renamer-preview-note').style('margin-top:6px')

                if is_mover_tab:
                    with ui.element('div').classes('org-mover-detail-row'):
                        with ui.element('div').classes('org-action-group-card org-side-action-panel'):
                            with ui.element('div').classes('org-side-action-section'):
                                ui.label('Folder').classes('org-section-hdr org-side-action-heading')
                                with ui.column().classes('org-side-action-buttons'):
                                    ui.button('Open Folder', icon='folder_open',
                                              on_click=lambda p=folder_path: open_folder_in_explorer(p)
                                              ).props('flat dense size=sm').classes('org-side-action-btn').style('color:#60a5fa')
                                    ui.button(
                                        'Quick Clean', icon='cleaning_services',
                                        on_click=lambda r=row, fp=folder_path: asyncio.ensure_future(_do_cleanup(r, fp))
                                    ).props('flat dense size=sm').classes('org-side-action-btn').style('color:#f59e0b').tooltip(_cleanup_tooltip())

                            with ui.element('div').classes('org-side-action-section'):
                                ui.label('Preparation').classes('org-section-hdr org-side-action-heading')
                                if is_thumb_generating:
                                    with ui.row().classes('items-center gap-2 org-side-action-status'):
                                        ui.spinner('dots', size='xs').style('color:#f59e0b;flex-shrink:0')
                                        ui.label('Generating thumbnails...').classes('org-thumb-inline-status')
                                with ui.column().classes('org-side-action-buttons'):
                                    if vtm_ok:
                                        _thumb_btn = ui.button('Thumbnails', icon='photo_library',
                                                  on_click=lambda p=folder_path: asyncio.ensure_future(
                                                      _do_vtm(p, vtm_exe_ref[0], vtm_preset_ref[0])
                                                  )).props('flat dense size=sm').classes('org-side-action-btn').style('color:#a78bfa').tooltip(
                                            'Generate Thumbnails (VTM)')
                                        if is_thumb_generating:
                                            _thumb_btn.set_enabled(False)
                                    ui.button(
                                        'Copy Folder Path', icon='content_copy',
                                        on_click=lambda p=folder_path: ui.run_javascript(
                                            f'navigator.clipboard.writeText({repr(p)})'
                                        ),
                                    ).props('flat dense size=sm').classes('org-side-action-btn').style('color:#67e8f9')

                            if target_dir_now:
                                with ui.element('div').classes('org-side-action-section'):
                                    ui.label('Destination').classes('org-section-hdr org-side-action-heading')
                                    with ui.column().classes('org-side-action-buttons'):
                                        ui.button(
                                            'Copy Target', icon='content_copy',
                                            on_click=lambda p=target_dir_now: ui.run_javascript(
                                                f'navigator.clipboard.writeText({repr(p)})'
                                            ),
                                        ).props('flat dense size=sm').classes('org-side-action-btn').style('color:#67e8f9')
                                        if target_exists_now:
                                            ui.button(
                                                'Open Target', icon='folder_open',
                                                on_click=lambda p=target_dir_now: open_folder_in_explorer(p),
                                            ).props('flat dense size=sm').classes('org-side-action-btn').style('color:#4ade80')

                        with ui.element('div').classes('org-mover-preview-card org-mover-preview-card-wide'):
                            ui.label('MOVE PREVIEW').classes('org-section-hdr').style('margin-bottom:6px')
                            mover_status_html = ui.html(_build_mover_status_html(row)).classes('org-mover-inspector-status')
                            actor_inp = ui.input(
                                value=row.get('detected_actor', ''),
                                placeholder='Actor name…'
                            ).classes('w-full').props('dense outlined').style('margin-bottom:8px')
                            ui.label(
                                'Editing the actor name updates the destination immediately and keeps your raw text untouched.'
                            ).classes('org-actor-hint').style('margin-bottom:8px')
                            if mover_target_base[0]:
                                ui.label(f'Base root: {mover_target_base[0]}').classes('org-mover-base-hint')
                            source_name = os.path.basename(folder_path)
                            target_display = _target_leaf(target_dir_now)
                            with ui.element('div').style('width:100%;margin-bottom:4px'):
                                with ui.element('div').classes('rename-diff-row'):
                                    ui.html(
                                        f'<div class="rename-diff-item"><span class="rename-diff-label">Current</span>'
                                        f'<span class="rename-diff-old" title="{_html.escape(source_name)}">{_html.escape(source_name)}</span></div>'
                                    )
                                    target_result_html = ui.html(
                                        f'<div class="rename-diff-item"><span class="rename-diff-label">Result</span>'
                                        f'<span class="rename-diff-new" title="{_html.escape(target_display)}">{_html.escape(target_display)}</span></div>'
                                    )
                            ui.label(
                                'The folder itself stays intact; only its destination parent changes.'
                            ).classes('org-actor-hint').style('margin-top:6px')

                    def _on_actor_change(e, _row=row) -> None:
                        new_actor = e.value.strip()
                        new_target, new_exists = recalc_target(
                            os.path.dirname(_row['full_path']), new_actor, mover_target_base[0]
                        ) if new_actor else ('', False)
                        _row['detected_actor'] = new_actor
                        _row['target_dir'] = new_target
                        _row['target_exists'] = new_exists
                        target_result = _target_leaf(new_target)
                        target_result_html.content = (
                            f'<div class="rename-diff-item"><span class="rename-diff-label">Result</span>'
                            f'<span class="rename-diff-new" title="{_html.escape(target_result)}">{_html.escape(target_result)}</span></div>'
                        )
                        actor_lbl = mover_row_actor_lbls.get(_row['full_path'])
                        if actor_lbl:
                            actor_lbl.content = _get_actor_rank_html(new_actor) if new_actor else '—'
                        row_status_lbl = mover_row_status_lbls.get(_row['full_path'])
                        if row_status_lbl:
                            row_status_lbl.content = _build_mover_status_html(_row)
                        mover_status_html.content = _build_mover_status_html(_row)
                        mover_meta_pills_html.content = _render_mover_meta_pills(ref, date_display, new_target, new_exists)
                        _update_mover_summary()

                    actor_inp.on_value_change(_on_actor_change)

            # ══ BOTTOM: Docked files drawer ══════════════════════════════════
            if all_files:
                files_dock_open = [True]
                with ui.element('div').classes('org-files-dock') as files_dock_el:
                    with ui.row().classes('org-files-dock-header'):
                        ui.label(f'FILES ({len(all_files)})').classes('org-section-hdr').style('margin-bottom:0')
                        ui.element('div').classes('flex-1')
                        files_toggle_lbl = ui.label('Hide').classes('org-files-toggle-text')
                        files_toggle_btn = ui.button(icon='keyboard_arrow_down').props('flat round dense size=sm').classes('org-files-toggle-btn').style('color:#94a3b8')

                    with ui.element('div').classes('org-files-dock-body') as files_dock_body:
                        for f in all_files:
                            f_state = {'path': f['path']}

                            with ui.row().classes('items-center gap-2').style(
                                'padding:5px 0;border-bottom:1px solid #111118;flex-wrap:nowrap'
                            ) as file_row_el:

                                # Thumbnail / icon (56 × 38)
                                if f['is_image']:
                                    enc = urllib.parse.quote(f['path'])
                                    _ts = f'/api/organiser-img?path={enc}'
                                    ui.image(_ts).style(
                                        'width:56px;height:38px;object-fit:cover;'
                                        'border-radius:3px;flex-shrink:0;cursor:zoom-in'
                                    ).on('click', lambda s=_ts: _lightbox(s))
                                elif f['is_video']:
                                    with ui.element('div').style(
                                        'width:56px;height:38px;flex-shrink:0;display:flex;'
                                        'align-items:center;justify-content:center;'
                                        'background:#0f0f14;border-radius:3px'
                                    ):
                                        ui.icon('videocam').style('font-size:1.4rem;color:#34d399')
                                elif f.get('is_subtitle'):
                                    with ui.element('div').style(
                                        'width:56px;height:38px;flex-shrink:0;display:flex;'
                                        'align-items:center;justify-content:center;'
                                        'background:#0f0f14;border-radius:3px'
                                    ):
                                        ui.icon('subtitles').style('font-size:1.2rem;color:#38bdf8')
                                else:
                                    with ui.element('div').style(
                                        'width:56px;height:38px;flex-shrink:0;display:flex;'
                                        'align-items:center;justify-content:center;'
                                        'background:#0f0f14;border-radius:3px'
                                    ):
                                        ui.icon('description').style('font-size:1.2rem;color:#6b7280')

                                # Editable filename
                                f_inp = ui.input(value=f['name']).props('dense borderless').style(
                                    'flex:1;min-width:0;font-size:0.78rem;font-family:monospace;color:#e2e8f0'
                                )

                                # Size
                                size_kb = f['size'] / 1024
                                size_str = (f'{size_kb/1024:.1f} MB' if size_kb >= 1024
                                            else f'{size_kb:.0f} KB')
                                ui.label(size_str).style(
                                    'font-size:0.68rem;color:#4b5563;flex-shrink:0;white-space:nowrap'
                                )

                                # Video quick-actions
                                if f['is_video']:
                                    ui.button(
                                        icon='play_circle_outline',
                                        on_click=lambda p=f['path']: open_path(p)
                                    ).props('flat dense size=xs').style('color:#4ade80;flex-shrink:0'
                                    ).tooltip('Play')
                                    if llc_exe and os.path.isfile(llc_exe):
                                        ui.button(
                                            icon='content_cut',
                                            on_click=lambda p=f['path']: _do_losslesscut(p, llc_exe)
                                    ).props('flat dense size=xs').style('color:#fb923c;flex-shrink:0'
                                    ).tooltip('LosslessCut')

                                ui.button(
                                    icon='delete_outline',
                                    on_click=lambda fst=f_state, rel=file_row_el: asyncio.ensure_future(
                                        _del_file(fst, rel)
                                    )
                                ).props('flat dense size=xs').style('color:#f87171;flex-shrink:0'
                                ).tooltip('Delete')

                            # Delete
                            async def _del_file(fst=f_state, row_el=file_row_el,
                                                _row=row, _fp=folder_path) -> None:
                                res = await asyncio.to_thread(delete_file, fst['path'])
                                if res['success']:
                                    with client:
                                        try:
                                            row_el.delete()
                                        except Exception:
                                            pass
                                        try:
                                            ui.notify(res['message'], color='positive', timeout=1500)
                                        except Exception:
                                            pass
                                    await _refresh_single_row(_row, _fp)
                                else:
                                    with client:
                                        try:
                                            ui.notify(res['message'], color='negative')
                                        except Exception:
                                            pass

                            # Rename on Enter or blur
                            async def _commit_rename(new_val: str, fst=f_state, inp=f_inp,
                                                     _row=row, _fp=folder_path) -> None:
                                old_name = os.path.basename(fst['path'])
                                if new_val.strip() == old_name or not new_val.strip():
                                    with client:
                                        inp.value = old_name
                                    return
                                res = await asyncio.to_thread(rename_file, fst['path'], new_val.strip())
                                if res['success']:
                                    fst['path'] = res['new_path']
                                    with client:
                                        ui.notify(res['message'], color='positive', timeout=1500)
                                    await _refresh_single_row(_row, _fp)
                                else:
                                    with client:
                                        ui.notify(res['message'], color='negative')
                                        inp.value = old_name

                            f_inp.on('keydown.enter',
                                     lambda e, fst=f_state, inp=f_inp: asyncio.ensure_future(
                                         _commit_rename(inp.value, fst, inp)))
                            f_inp.on('blur',
                                     lambda e, fst=f_state, inp=f_inp: asyncio.ensure_future(
                                         _commit_rename(inp.value, fst, inp)))

                    def _toggle_files_dock() -> None:
                        files_dock_open[0] = not files_dock_open[0]
                        if files_dock_open[0]:
                            files_dock_el.classes(remove='org-files-dock-collapsed')
                            files_toggle_lbl.text = 'Hide'
                            files_toggle_btn.props('icon=keyboard_arrow_down')
                        else:
                            files_dock_el.classes(add='org-files-dock-collapsed')
                            files_toggle_lbl.text = 'Show'
                            files_toggle_btn.props('icon=keyboard_arrow_up')

                    files_toggle_btn.on('click', lambda _: _toggle_files_dock())

                if active_tab_ref[0] == 'renamer' and row.get('reference_number'):
                    preview_info = FolderInfo(
                        full_path=row['full_path'],
                        date=row.get('date', ''),
                        video_name=row.get('video_name', ''),
                        actor_name=row.get('actor_name', ''),
                        reference_number=row.get('reference_number', ''),
                        raw_actor_name=row.get('raw_actor_name', ''),
                        videos=row.get('videos', []),
                    )
                    file_preview = build_file_rename_preview(preview_info, include_videos=True)
                    if file_preview:
                        with ui.element('div').classes('org-renamer-file-preview-card'):
                            ui.label(f'FILE RENAME PREVIEW ({len(file_preview)})').classes('org-section-hdr')
                            with ui.element('div').style('width:100%'):
                                for item in file_preview:
                                    esc_old = _html.escape(item['old_name'])
                                    esc_new = _html.escape(item['new_name'])
                                    with ui.element('div').classes('rename-diff-row'):
                                        ui.html(
                                            f'<div class="rename-diff-item"><span class="rename-diff-label">Current</span>'
                                            f'<span class="rename-diff-old" title="{esc_old}">{esc_old}</span></div>'
                                        )
                                        ui.html(
                                            f'<div class="rename-diff-item"><span class="rename-diff-label">Result</span>'
                                            f'<span class="rename-diff-new" title="{esc_new}">{esc_new}</span></div>'
                                        )

    # ── Action implementations ─────────────────────────────────────────────────

    async def _refresh_single_row(row: dict, folder_path: str) -> None:
        """Re-scan one folder's files and update its left-panel count + right-panel inspector."""
        # Re-scan files in the folder
        new_files = await asyncio.to_thread(list_all_folder_files, folder_path)
        new_videos = [f for f in new_files if f['is_video']]
        row['has_thumbnails'] = await asyncio.to_thread(has_thumbnails, folder_path)
        row['has_cover'] = any(f['is_image'] and f.get('is_cover') for f in new_files)
        row['has_subtitles'] = any(f.get('is_subtitle') for f in new_files)
        # Update in-memory row dict
        row['videos'] = [{'name': f['name'], 'path': f['path']} for f in new_videos]
        row['number_of_videos'] = len(new_videos)
        with client:
            # Update left-panel # count label
            fp = folder_path
            count_lbl = renamer_count_lbls.get(fp) or mover_count_lbls.get(fp)
            if count_lbl:
                count_lbl.text = str(len(new_videos))
            row_status_lbl = mover_row_status_lbls.get(fp)
            if row_status_lbl:
                row_status_lbl.content = _build_mover_status_html(row)
            _update_mover_summary()
            # Rebuild right-panel inspector in place (FILES section now reflects new state)
            if active_row_ref[0] and active_row_ref[0].get('full_path') == folder_path:
                active_row_ref[0] = row
                tab_rows[active_tab_ref[0]] = row
                _refresh_right_panel(row)

    def _set_thumbnail_generation_state(folder_path: str, is_generating: bool) -> None:
        if is_generating:
            thumbnail_generating_set.add(folder_path)
        else:
            thumbnail_generating_set.discard(folder_path)

        with client:
            row = mover_row_info.get(folder_path)
            row_status_lbl = mover_row_status_lbls.get(folder_path)
            if row and row_status_lbl:
                row_status_lbl.content = _build_mover_status_html(row)

            _update_mover_summary()
            _update_sel_labels()

            if active_row_ref[0] and active_row_ref[0].get('full_path') == folder_path:
                _refresh_right_panel(row or active_row_ref[0])

    async def _run_vtm_for_folder(
        folder_path: str,
        vtm_exe: str,
        vtm_preset: str,
        *,
        batch_index: Optional[int] = None,
        batch_total: Optional[int] = None,
    ) -> dict:
        if folder_path in thumbnail_generating_set:
            return {'success': False, 'message': 'Thumbnail generation is already running for this folder.'}

        row = mover_row_info.get(folder_path)
        label = os.path.basename(folder_path)
        with client:
            if batch_index is not None and batch_total is not None:
                last_op_lbl.text = f'⏳ Thumbnails {batch_index}/{batch_total}: {label}…'
            else:
                last_op_lbl.text = f'⏳ Thumbnails: {label}…'

        _set_thumbnail_generation_state(folder_path, True)
        try:
            result = await asyncio.to_thread(generate_thumbnails, folder_path, vtm_exe, vtm_preset)
        except Exception as exc:
            result = {'success': False, 'message': str(exc)}
        finally:
            _set_thumbnail_generation_state(folder_path, False)

        if row:
            await _refresh_single_row(row, folder_path)

        return result

    async def _pick_and_load() -> None:
        d = await asyncio.to_thread(_browse_folder_sync, 'Select folder to organise')
        if d:
            current_dir[0] = d
            dir_lbl.text = d
            await _reload()

    async def _reload_mover() -> None:
        """Reload only the Folder Mover list (e.g. after target base changes)."""
        d = current_dir[0]
        if not d or not os.path.isdir(d):
            return
        if mover_loading_ref:
            mover_loading_ref[0].set_visibility(True)
        _begin_scan_progress('mover')
        nonlocal mover_data
        try:
            _refresh_tracker_context()
            mover_data = await asyncio.to_thread(
                load_mover_folders,
                d,
                mover_target_base[0],
                _make_scan_progress_callback('mover'),
            )
            mover_selected_set.clear()
            mover_checked_set.clear()
            total_mover[0] = len(mover_data)
            _build_mover_list()
            _update_sel_labels()
            right_col.clear()
            _build_empty_right(right_col)
        except Exception as exc:
            with client:
                ui.notify(f'Mover reload failed: {exc}', color='negative')
        finally:
            _end_scan_progress('mover')
            _update_mover_summary()
            if mover_loading_ref:
                mover_loading_ref[0].set_visibility(False)

    async def _reload() -> None:
        d = current_dir[0]
        if not d or not os.path.isdir(d):
            with client:
                ui.notify('No valid folder selected', color='warning')
            return
        if renamer_loading_ref:
            renamer_loading_ref[0].set_visibility(True)
        if mover_loading_ref:
            mover_loading_ref[0].set_visibility(True)
        _begin_scan_progress('renamer')
        _begin_scan_progress('mover', phase='queued')
        nonlocal renamer_data, mover_data
        try:
            _refresh_tracker_context()
            renamer_data = await asyncio.to_thread(
                load_renamer_folders,
                d,
                _make_scan_progress_callback('renamer'),
            )
            _apply_tracker_actor_names_to_renamer()
            _begin_scan_progress('mover')
            mover_data = await asyncio.to_thread(
                load_mover_folders,
                d,
                mover_target_base[0],
                _make_scan_progress_callback('mover'),
            )
            renamer_selected_set.clear()
            mover_selected_set.clear()
            renamer_checked_set.clear()
            mover_checked_set.clear()
            total_renamer[0] = len(renamer_data)
            total_mover[0] = len(mover_data)
            _build_renamer_list()
            _build_mover_list()
            _update_sel_labels()
            right_col.clear()
            _build_empty_right(right_col)
            # Reset per-tab row cache since data has changed
            tab_rows['renamer'] = None
            tab_rows['mover'] = None
            # Update count chip
            r_count = total_renamer[0]
            m_count = total_mover[0]
            if r_count or m_count:
                count_chip.content = f'{r_count} rename · {m_count} move'
                count_chip.style('display:inline')
            else:
                count_chip.content = ''
                count_chip.style('display:none')
            # If we have a pre-selected folder from the query param, highlight it
            if folder:
                for fi in renamer_data:
                    if fi.full_path == folder:
                        row = fi.to_row()
                        active_row_ref[0] = row
                        active_tab_ref[0] = 'renamer'
                        tab_rows['renamer'] = row
                        if fi.full_path in renamer_row_els:
                            renamer_row_els[fi.full_path].classes(add='active-row')
                        _refresh_right_panel(row)
                        break
        except Exception as exc:
            with client:
                ui.notify(f'Organiser reload failed: {exc}', color='negative')
        finally:
            _end_scan_progress('renamer')
            _end_scan_progress('mover')
            _update_renamer_summary()
            _update_mover_summary()
            if renamer_loading_ref:
                renamer_loading_ref[0].set_visibility(False)
            if mover_loading_ref:
                mover_loading_ref[0].set_visibility(False)

    async def _do_rename() -> None:
        sel = [fi.to_row() for fi in renamer_data if fi.full_path in renamer_checked_set]
        if not sel:
            with client:
                ui.notify('Check folders to rename first', color='warning')
            return

        confirmed = await _confirm_rename_dialog(client, len(sel))
        if not confirmed:
            return

        # Build FolderInfo objects from row dicts
        infos = [
            FolderInfo(
                full_path=r['full_path'],
                date=r['date'],
                video_name=r['video_name'],
                actor_name=r['actor_name'],
                reference_number=r['reference_number'],
                raw_actor_name=r.get('raw_actor_name', ''),
                videos=r.get('videos', []),
            )
            for r in sel
        ]
        result = await asyncio.to_thread(rename_folders_batch, infos)
        with client:
            if result['success']:
                ui.notify(result['message'], color='positive')
                last_op_lbl.text = f'✓ {result["message"]}'
            else:
                ui.notify(result['message'], color='negative', timeout=8000)
                last_op_lbl.text = f'✗ Rename failed'
        await _reload()

    async def _do_cleanup(row: dict, folder_path: str) -> None:
        result = await asyncio.to_thread(
            cleanup_folder_files,
            folder_path,
            delete_other_files=cleanup_delete_other_files_ref[0],
            delete_small_videos=cleanup_delete_small_videos_ref[0],
            min_video_mb=cleanup_small_video_mb_ref[0],
        )
        with client:
            if result['success']:
                ui.notify(result['message'], color='positive' if result.get('deleted_count', 0) else 'warning')
                last_op_lbl.text = f"✓ {result['message']}"
            else:
                ui.notify(result['message'], color='negative', timeout=6000)
                last_op_lbl.text = '✗ Cleanup failed'
        await _refresh_single_row(row, folder_path)

    async def _do_move() -> None:
        sel = [mover_row_info[fp] for fp in mover_checked_set if fp in mover_row_info]
        if not sel:
            with client:
                ui.notify('Check folders to move first', color='warning')
            return

        do_rename_vids = rename_vids_toggle.value

        # Check for folder-name conflicts at each destination
        moves_input = [
            {'source_path': row['full_path'], 'target_dir': row.get('target_dir', '')}
            for row in sel
        ]
        conflict_results = await asyncio.to_thread(check_move_conflicts, moves_input)
        # Map source_path → conflict result for quick lookup
        conflict_map = {r['source_path']: r for r in conflict_results}

        # Build confirmation preview (includes conflict info)
        previews = []
        for row in sel:
            actor = row.get('detected_actor', '').strip()
            target = row.get('target_dir', '')
            exists = row.get('target_exists', False)
            cr = conflict_map.get(row['full_path'], {})
            conflict_info = cr.get('conflicts', []) if cr.get('status') == 'conflict' else None
            previews.append((row['folder_name'], actor, target, exists, conflict_info))

        confirmed = await _confirm_move_dialog(client, previews)
        if not confirmed:
            return

        errors: List[str] = []
        ok = 0
        for row in sel:
            actor = row.get('detected_actor', '').strip()
            if not actor:
                errors.append(f"{row['folder_name']}: no actor detected")
                continue
            target = row.get('target_dir', '')
            if not target:
                errors.append(f"{row['folder_name']}: no target directory")
                continue

            # Optionally rename videos inside to match the (possibly edited) actor name
            vid_name = row.get('detected_video_name', '').strip()
            if do_rename_vids and actor and vid_name:
                rv = await asyncio.to_thread(
                    rename_videos_for_actor, row['full_path'], actor, vid_name
                )
                if not rv['success']:
                    errors.append(f"{row['folder_name']} (video rename): {rv['message']}")
                    # Non-fatal — continue with the move

            # Check if this move has a conflict → merge instead of plain move
            cr = conflict_map.get(row['full_path'], {})
            if cr.get('status') == 'conflict':
                final_path = cr.get('final_path', os.path.join(target, os.path.basename(row['full_path'])))
                result = await asyncio.to_thread(merge_folder, row['full_path'], final_path)
            else:
                result = await asyncio.to_thread(move_folder, row['full_path'], target)

            if result['success']:
                ok += 1
            else:
                errors.append(f"{row['folder_name']}: {result['message']}")

        with client:
            if ok:
                ui.notify(f'Moved {ok} folder(s)', color='positive')
                last_op_lbl.text = f'✓ Moved {ok} folder(s)'
            if errors:
                ui.notify('\n'.join(errors), color='negative', timeout=8000, multi_line=True)
                last_op_lbl.text = f'✗ Move: {len(errors)} error(s)'
        await _reload()

    async def _select_no_thumbnails() -> None:
        """Check all renamer rows whose folder has no thumbnail image."""
        if not renamer_data:
            return
        for row in renamer_data:
            fp = row.full_path
            thumb = await asyncio.to_thread(has_thumbnails, fp)
            if not thumb:
                _set_row_checked(renamer_row_checks, renamer_checked_set, fp, True)
        _update_sel_labels()

    async def _select_cover_only() -> None:
        """Check renamer rows whose folder has a cover image but no thumbnail images."""
        if not renamer_data:
            return
        for row in renamer_data:
            fp = row.full_path
            if await asyncio.to_thread(has_cover_only, fp):
                _set_row_checked(renamer_row_checks, renamer_checked_set, fp, True)
        _update_sel_labels()

    def _select_target_found() -> None:
        """Check all mover rows whose actor destination folder already exists."""
        for fp, row in mover_row_info.items():
            if row.get('target_exists'):
                _set_row_checked(mover_row_checks, mover_checked_set, fp, True)
        _update_sel_labels()

    def _select_mover_no_thumbnails() -> None:
        """Check actionable mover rows that do not yet have a thumbnail image."""
        for fp, row in mover_row_info.items():
            actor = str(row.get('detected_actor', '') or '').strip()
            video_count = int(row.get('number_of_videos', 0) or 0)
            if not row.get('has_thumbnails') and actor and video_count > 0:
                _set_row_checked(mover_row_checks, mover_checked_set, fp, True)
        _update_sel_labels()

    async def _do_vtm_batch() -> None:
        """Run VTM on checked mover folders without blocking the UI."""
        vtm_exe    = vtm_exe_ref[0]
        vtm_preset = vtm_preset_ref[0]
        if not vtm_exe or not os.path.isfile(vtm_exe):
            with client:
                ui.notify('VTM executable not found — configure it in Settings ⚙', color='warning', timeout=5000)
            return
        if not vtm_preset or not os.path.isfile(vtm_preset):
            with client:
                ui.notify('VTM preset not found — configure it in Settings ⚙', color='warning', timeout=5000)
            return
        folders = list(mover_checked_set)
        if not folders:
            with client:
                ui.notify('No checked mover folders', color='info', timeout=2000)
            return

        total = len(folders)
        successes = 0
        failures: list[str] = []

        for idx, fp in enumerate(folders, start=1):
            result = await _run_vtm_for_folder(
                fp,
                vtm_exe,
                vtm_preset,
                batch_index=idx,
                batch_total=total,
            )
            if result.get('success'):
                successes += 1
            else:
                failures.append(f"{os.path.basename(fp)}: {result.get('message', 'Unknown error')}")

        msg = f'Done: {successes} succeeded'
        if failures:
            msg += f', {len(failures)} failed'
        with client:
            ui.notify(msg, color='positive' if not failures else 'warning', timeout=4000)
            if failures:
                ui.notify('\n'.join(failures), color='negative', timeout=8000, multi_line=True)
            last_op_lbl.text = f'✓ {msg}' if not failures else f'⚠ {msg}'

    async def _do_vtm(folder_path: str, vtm_exe: str, vtm_preset: str) -> None:
        result = await _run_vtm_for_folder(folder_path, vtm_exe, vtm_preset)
        if result['success']:
            last_op_lbl.text = f'✓ {result["message"]}'
            ui.notify(result['message'], color='positive', timeout=2500)
        else:
            last_op_lbl.text = f'✗ VTM failed'
            ui.notify(result['message'], color='negative', timeout=6000)

    def _do_losslesscut(video_path: str, llc_exe: str) -> None:
        result = open_in_losslesscut(video_path, llc_exe)
        if not result['success']:
            ui.notify(result['message'], color='negative', timeout=5000)

    async def _do_delete_image(img_path: str, folder_path: str) -> None:
        result = await asyncio.to_thread(delete_image_file, img_path)
        with client:
            if result['success']:
                ui.notify(result['message'], color='positive', timeout=2000)
            else:
                ui.notify(result['message'], color='negative', timeout=5000)
        # Refresh right panel so deleted image disappears
        if active_row_ref[0] and active_row_ref[0].get('full_path') == folder_path:
            _refresh_right_panel(active_row_ref[0])

    async def _do_rename_images(row: dict, folder_path: str) -> None:
        info = FolderInfo(
            full_path=row['full_path'],
            date=row['date'],
            video_name=row['video_name'],
            actor_name=row['actor_name'],
            reference_number=row['reference_number'],
            videos=row.get('videos', []),
        )
        result = await asyncio.to_thread(rename_images_in_folder, info)
        with client:
            if result['success']:
                ui.notify(result['message'], color='positive')
            else:
                ui.notify(result['message'], color='negative', timeout=5000)
        # Refresh right panel so renamed image filenames update
        if active_row_ref[0] and active_row_ref[0].get('full_path') == folder_path:
            _refresh_right_panel(active_row_ref[0])

    initial_reload_started_ref: List[bool] = [False]

    def _schedule_initial_reload() -> None:
        if initial_reload_started_ref[0]:
            return
        initial_reload_started_ref[0] = True
        asyncio.create_task(_reload())

    def _lightbox(src: str) -> None:
                open_image_preview(src)

    # ── Unified settings dialog ──────────────────────────────────────────────────

    def _on_save_organiser(
        vtm_exe,
        vtm_preset,
        scan_folder,
        mover_base,
        renamer_panel_width,
        mover_panel_width,
        cleanup_delete_other_files,
        cleanup_delete_small_videos,
        cleanup_small_video_mb,
    ) -> None:
        vtm_exe_ref[0]    = vtm_exe or DEFAULT_VTM_EXE
        vtm_preset_ref[0] = vtm_preset or default_vtm_preset()
        panel_w_ref['renamer'] = int(renamer_panel_width)
        panel_w_ref['mover'] = int(mover_panel_width)
        cleanup_delete_other_files_ref[0] = bool(cleanup_delete_other_files)
        cleanup_delete_small_videos_ref[0] = bool(cleanup_delete_small_videos)
        cleanup_small_video_mb_ref[0] = float(cleanup_small_video_mb or 30.0)
        prev_mover_base = mover_target_base[0]
        if scan_folder and not current_dir[0]:
            current_dir[0] = scan_folder
            dir_lbl.text = scan_folder
        mover_target_base[0] = mover_base
        _apply_left_panel_width()
        _update_mover_summary()
        if current_dir[0] and os.path.isdir(current_dir[0]) and prev_mover_base != mover_target_base[0]:
            asyncio.create_task(_reload_mover())

    _settings_dlg = _build_settings_dialog(
        accent='#059669',
        on_save_organiser=_on_save_organiser,
        save_state_key="organiser",
    )
    settings_dialog_ref.append(_settings_dlg)


    # ── Initial load ───────────────────────────────────────────────────────────
    if current_dir[0] and os.path.isdir(current_dir[0]):
        if renamer_loading_ref:
            renamer_loading_ref[0].set_visibility(True)
        if mover_loading_ref:
            mover_loading_ref[0].set_visibility(True)
        ui.timer(0.05, _schedule_initial_reload, once=True)

    # ── Keyboard shortcuts ─────────────────────────────────────────────────────
    # Ctrl+A = Select All in active tab | Escape = Clear selection | Space = Toggle checked state
    ui.keyboard(on_key=lambda e: _handle_key(e), ignore=['input', 'select', 'textarea'])

    def _handle_key(e) -> None:
        if e.key == 'Escape':
            if active_tab_ref[0] == 'renamer':
                _clear_renamer_selection()
            else:
                _clear_mover_selection()
        elif e.key == ' ':
            active_row = active_row_ref[0] or {}
            fp = active_row.get('full_path')
            if active_tab_ref[0] == 'renamer':
                target_paths = [path for path in renamer_selected_set if path in renamer_row_checks]
                if not target_paths and fp in renamer_row_checks:
                    target_paths = [fp]
                if not target_paths:
                    return
                should_check = any(path not in renamer_checked_set for path in target_paths)
                for path in target_paths:
                    _set_row_checked(renamer_row_checks, renamer_checked_set, path, should_check)
                _update_sel_labels()
            elif active_tab_ref[0] == 'mover':
                target_paths = [path for path in mover_selected_set if path in mover_row_checks]
                if not target_paths and fp in mover_row_checks:
                    target_paths = [fp]
                if not target_paths:
                    return
                should_check = any(path not in mover_checked_set for path in target_paths)
                for path in target_paths:
                    _set_row_checked(mover_row_checks, mover_checked_set, path, should_check)
                _update_sel_labels()
        elif e.key == 'a' and e.modifiers.ctrl:
            if active_tab_ref[0] == 'renamer':
                _select_all_renamer()
            else:
                _select_all_mover()


# ── Confirmation dialogs ────────────────────────────────────────────────────────

async def _confirm_rename_dialog(client, previews: List[tuple]) -> bool:
    """Ask for batch rename confirmation. Returns True if confirmed."""
    fut: asyncio.Future = asyncio.get_running_loop().create_future()

    def _set(val: bool, dlg) -> None:
        dlg.close()
        if not fut.done():
            fut.set_result(val)

    with client:
        with ui.dialog().props('persistent') as dlg:
            with ui.card().classes('org-dialog-card').style(
                'background:#111118; border:1px solid #1a1a24; min-width:420px; max-width:520px'
            ):
                ui.label('Confirm Rename').classes('org-dialog-title')
                ui.label(
                    f'You are about to rename {previews} folder(s). '
                    'Files inside each folder will also be renamed. This cannot be undone from the UI.'
                ).classes('org-dialog-warn')

                with ui.row().classes('w-full justify-end gap-2').style('margin-top:16px'):
                    ui.button('Cancel', on_click=lambda: _set(False, dlg)).props('flat').style('color:#9ca3af')
                    ui.button('Rename', icon='drive_file_rename_outline',
                              on_click=lambda: _set(True, dlg)).style(
                        'background:#059669; color:#fff'
                    )
        dlg.open()

    return await fut


async def _confirm_move_dialog(client, previews: List[tuple]) -> bool:
    """Show folder→target preview (including merge warnings) and ask for confirmation.

    previews: list of (folder_name, actor, target, target_exists, conflict_info)
      conflict_info is None if no conflict, or a list of file-level conflict dicts.
    Returns True if confirmed.
    """
    fut: asyncio.Future = asyncio.get_running_loop().create_future()

    def _set(val: bool, dlg) -> None:
        dlg.close()
        if not fut.done():
            fut.set_result(val)

    has_conflicts = any(c is not None for _, _, _, _, c in previews)
    n = len(previews)

    with client:
        with ui.dialog().props('persistent') as dlg:
            with ui.card().style(
                'background:#111118; border:1px solid #1a1a24; min-width:520px; max-width:740px'
            ):
                ui.label('Confirm Move').style('font-size:1rem; font-weight:700; color:#f1f5f9')
                subtitle = (f'The following {n} folder(s) will be moved. '
                            'This cannot be undone from the UI.')
                if has_conflicts:
                    subtitle += ' Folders marked ⚠ will be MERGED — existing files at the destination will be overwritten.'
                ui.label(subtitle).classes('org-dialog-warn')

                with ui.element('div').style('max-height:360px; overflow-y:auto; width:100%'):
                    for folder_name, actor, target, exists, conflict_info in previews:
                        esc_fn = _html.escape(folder_name)
                        if not actor or not target:
                            with ui.element('div').classes('rename-diff-row'):
                                ui.html(f'<span style="font-family:monospace;font-size:0.78rem;'
                                        f'color:#9ca3af">{esc_fn}</span>')
                                ui.html('<span class="rename-diff-arrow">→</span>')
                                ui.html('<span style="font-family:monospace;font-size:0.78rem;'
                                        'color:#f87171">⚠ No actor / no target — will be skipped</span>')
                        elif conflict_info is not None:
                            # Folder name collision at destination → will merge
                            leaf = os.path.basename(target) or target
                            parent = os.path.basename(os.path.dirname(target))
                            display = f'{parent}\\{leaf}' if parent else leaf
                            esc_display = _html.escape(display)
                            esc_target  = _html.escape(target)
                            n_conflicts = len(conflict_info)
                            vid_conflicts = sum(1 for c in conflict_info if c.get('is_video'))
                            with ui.element('div').style(
                                'padding:6px 0; border-bottom:1px solid #111118'
                            ):
                                ui.html(
                                    f'<div style="display:grid;grid-template-columns:1fr 24px 1fr;'
                                    f'align-items:center;gap:8px;font-size:0.78rem">'
                                    f'<span class="rename-diff-old" title="{esc_fn}">{esc_fn}</span>'
                                    f'<span class="rename-diff-arrow">→</span>'
                                    f'<span style="font-family:monospace;color:#f59e0b" title="{esc_target}">'
                                    f'{esc_display}</span>'
                                    f'</div>'
                                    f'<div style="font-size:0.7rem;color:#f59e0b;margin-top:2px;padding-left:4px">'
                                    f'⚠ Destination folder exists — will MERGE '
                                    f'({n_conflicts} file conflict(s)'
                                    f'{f", {vid_conflicts} video(s)" if vid_conflicts else ""})'
                                    f'</div>'
                                )
                        else:
                            leaf = os.path.basename(target) or target
                            parent = os.path.basename(os.path.dirname(target))
                            display = f'{parent}\\{leaf}' if parent else leaf
                            esc_display = _html.escape(display)
                            esc_target  = _html.escape(target)
                            status_color = '#4ade80' if exists else '#f59e0b'
                            status_txt = '✓ exists' if exists else '✗ will be created'
                            with ui.element('div').classes('rename-diff-row'):
                                ui.html(f'<span class="rename-diff-old" title="{esc_fn}">{esc_fn}</span>')
                                ui.html('<span class="rename-diff-arrow">→</span>')
                                ui.html(
                                    f'<span style="font-family:monospace;font-size:0.78rem;'
                                    f'color:{status_color}" title="{esc_target}">'
                                    f'{esc_display} <span style="font-size:0.68rem;opacity:0.8">'
                                    f'({status_txt})</span></span>'
                                )

                with ui.row().classes('w-full justify-end gap-2').style('margin-top:16px'):
                    ui.button('Cancel', on_click=lambda: _set(False, dlg)).props('flat').style('color:#9ca3af')
                    move_label = 'Move & Merge' if has_conflicts else 'Move'
                    ui.button(move_label, icon='drive_file_move',
                              on_click=lambda: _set(True, dlg)).style('background:#0891b2; color:#fff')
        dlg.open()

    return await fut


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_empty_right(container) -> None:
    with container:
        with ui.element('div').classes('org-empty').style('height:calc(100vh - 80px)'):
            ui.icon('folder_open').style('font-size:3rem; color:#1f2937')
            ui.label('Select a folder row to preview its contents').style('color:#4b5563')


def _fmt_target(target_dir: str, exists: bool, include_status: bool = True) -> str:
    if not target_dir:
        return 'No target — enter actor name'
    leaf = os.path.basename(target_dir) or target_dir
    parent = os.path.basename(os.path.dirname(target_dir))
    display = f'{parent}\\{leaf}' if parent else leaf
    if not include_status:
        return display
    status = '✓ exists' if exists else '✗ will be created'
    return f'{display}  ({status})'
