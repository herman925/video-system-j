"""
Unified settings dialog — shared across Downloader, Organiser, and Tracker.

Call build_settings_dialog() once at page init; the caller passes:
  - accent:               CSS colour string matching the module theme
    - on_save_downloader:   callable(poll_interval, cover_w, timer_ctx, all_handles) -> None
        - on_save_organiser:    callable(vtm_exe, vtm_preset, scan_folder, mover_base, renamer_panel_width, mover_panel_width, cleanup_delete_other_files, cleanup_delete_small_videos, cleanup_small_video_mb) -> None
    - on_save_tracker:      callable(cover_w, left_panel_w, auto_inactive_enabled, inactive_months) -> None
  - timer_ctx / all_handles: downloader-specific dicts for live timer updates
"""

import asyncio
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Dict, List, Optional

from nicegui import app, ui

from translator.llm import PROVIDERS, load_config, read_env_key, save_config
from utils.downloader_store import (
    get_downloader_panel_width,
    load_downloader_state,
    save_downloader_state,
    set_downloader_panel_width,
)
from utils.organiser import (
    DEFAULT_LOSSLESSCUT_EXE,
    DEFAULT_VTM_EXE,
    default_vtm_preset,
    list_vtm_presets,
)
from utils.organiser_store import load_organiser_state, save_organiser_preferences
from utils.paths import DATA_DIR, ENV_FILE, NICEGUI_STORAGE_DIR, set_data_dir
from utils.save_state import tracked_save_state
from utils.tracker_ui_store import get_tracker_left_panel_width, set_tracker_left_panel_width
from utils.ui_ratings import (
    DEFAULT_RATING_TOOLTIPS,
    DEFAULT_RATING_THRESHOLDS,
    get_rating_thresholds,
    get_rating_tooltips,
    TIER_ICONS,
    TIER_LABELS,
    TIER_ORDER,
)


# ── Local file-browser helpers ────────────────────────────────────────────────

def _browse_folder() -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select folder")
    root.destroy()
    return folder or ""


def _browse_file(title: str = "Select file", filetypes=None) -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title=title, filetypes=filetypes or [("All files", "*.*")]
    )
    root.destroy()
    return path or ""


def _tooltip_preview(text: str, limit: int = 150) -> str:
    collapsed = " ".join(part.strip() for part in str(text).splitlines() if part.strip())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "..."


# ── Unified settings dialog ───────────────────────────────────────────────────

def build_settings_dialog(
    accent: str = "#374151",
    on_save_downloader: Optional[Callable] = None,
    on_save_organiser:  Optional[Callable] = None,
    on_save_tracker:    Optional[Callable] = None,
    timer_ctx:   Optional[dict] = None,
    all_handles: Optional[dict] = None,
    save_state_key: Optional[str] = None,
) -> "ui.dialog":
    """Build and return the unified tabbed settings dialog."""
    cfg = load_config()
    organiser_state = load_organiser_state()
    downloader_panel_width = get_downloader_panel_width()
    aura_cfg = cfg.get("aura_config", {
        "enabled": True,
        "emission_scale": 2.0,
        "use_blur_filters": False,
        "particles": True,
        "vertical_beams": True,
        "god_light": True,
    })

    ui.add_head_html(f"""<style>
    .cfg-card  {{ background:#0f0f13 !important; border:1px solid #1a1a24; padding:0 !important; box-shadow:0 28px 80px rgba(0,0,0,0.48); display:flex; flex-direction:column; max-height:min(92vh, 980px); overflow:hidden; }}
    .cfg-titlebar {{ background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)); }}
    .cfg-title {{ font-size:1.08rem; font-weight:800; color:#f3f4f6; letter-spacing:0.01em; }}
    .cfg-jumpbar {{ border-bottom:1px solid #1a1a24; background:#101017; padding:10px 20px 12px; }}
    .cfg-jump-label {{ font-size:0.66rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#7b8394; margin-bottom:6px; }}
    .cfg-jump .q-field__control {{ background:#121521 !important; border-radius:12px !important; min-height:46px !important; }}
    .cfg-jump .q-field--outlined .q-field__control:before {{ border-color:#24293a !important; }}
    .cfg-jump .q-field--outlined.q-field--focused .q-field__control:before {{ border-color:{accent} !important; }}
    .cfg-jump .q-field__native, .cfg-jump .q-field__prefix, .cfg-jump .q-field__suffix, .cfg-jump .q-icon {{ color:#e5e7eb !important; }}
    .cfg-jump .q-field__label {{ color:#7b8394 !important; }}
    .cfg-panels {{ display:flex; flex-direction:column; flex:1 1 auto; min-height:0; overflow:hidden; }}
    .cfg-panels > .q-panel {{ flex:1 1 auto; min-height:0; }}
    .cfg-panels .q-panel.scroll {{ height:100% !important; min-height:0; overflow-y:auto; }}
    .cfg-panel {{ padding:18px 22px 28px; min-height:100%; overflow:visible;
                  background:#0f0f13; }}
    .cfg-section {{ font-size:0.66rem; font-weight:700; letter-spacing:0.09em;
                    text-transform:uppercase; color:{accent};
                    margin-top:18px; margin-bottom:7px; padding-bottom:4px;
                    border-bottom:1px solid #1a1a24; }}
    .cfg-hint  {{ font-size:0.79rem; color:#7b8394; line-height:1.62;
                  white-space:pre-line; margin-bottom:8px; width:100%; max-width:none; }}
    .cfg-summary-card {{ background:#11131a !important; border:1px solid #1f2432; border-radius:16px; box-shadow:none !important; padding:0 !important; }}
    .cfg-summary-head {{ font-size:0.74rem; letter-spacing:0.08em; text-transform:uppercase; color:#9ca3af; }}
    .cfg-summary-title {{ font-size:0.96rem; font-weight:700; color:#f3f4f6; }}
    .cfg-summary-copy {{ font-size:0.8rem; color:#8b95a7; line-height:1.62; width:100%; max-width:none; }}
    .cfg-status-row {{ display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:10px 0; border-top:1px solid #1a1d29; }}
    .cfg-status-row:first-child {{ border-top:0; padding-top:0; }}
    .cfg-status-name {{ font-size:0.8rem; font-weight:600; color:#e5e7eb; }}
    .cfg-status-detail {{ font-size:0.76rem; color:#8b95a7; line-height:1.55; max-width:420px; text-align:right; }}
    .cfg-pill {{ display:inline-flex; align-items:center; justify-content:center; padding:3px 8px; border-radius:999px; font-size:0.64rem; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; min-width:58px; }}
    .cfg-expansion .q-expansion-item__container {{ background:#10131b; border:1px solid #1c2030; border-radius:14px; overflow:hidden; }}
    .cfg-expansion .q-item {{ min-height:54px; }}
    .cfg-expansion .q-item__label {{ color:#f3f4f6; font-weight:600; }}
    .cfg-expansion .q-item__label--caption {{ color:#8b95a7; font-size:0.77rem; margin-top:4px; line-height:1.5; }}
    .cfg-save-btn.q-btn {{ background:{accent} !important; color:#fff !important; }}
        .cfg-save-btn.q-btn {{ border-radius:10px; padding:6px 20px; min-height:40px; }}
        @media (max-width: 760px) {{
            .cfg-jumpbar {{ padding:10px 16px 12px; }}
        }}
    </style>""")

    status_rows: Dict[str, Dict[str, ui.label]] = {}
    qbt_test_state = {"ok": None}

    def _make_status_row(title: str) -> Dict[str, ui.label]:
        with ui.row().classes("w-full cfg-status-row no-wrap"):
            name = ui.label(title).classes("cfg-status-name")
            with ui.column().classes("items-end gap-1"):
                state = ui.label("CHECK").classes("cfg-pill")
                detail = ui.label("").classes("cfg-status-detail")
        return {"name": name, "state": state, "detail": detail}

    def _set_status(row: Dict[str, ui.label], ready: bool, detail: str) -> None:
        row["state"].set_text("READY" if ready else "CHECK")
        row["state"].style(
            (
                "color:#d1fae5;background:rgba(16,185,129,0.14);border:1px solid rgba(16,185,129,0.28);"
                if ready else
                "color:#fde68a;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.26);"
            )
        )
        row["detail"].set_text(detail)

    with ui.dialog().props("persistent") as dlg, \
         ui.card().classes("cfg-card").style("width:860px; max-width:96vw;"):

        # ── Title bar ─────────────────────────────────────────────────────────
        with ui.column().classes("cfg-titlebar w-full px-5 pt-4 pb-1 gap-0"):
            ui.label("Settings").classes("cfg-title")

        # ── Hidden tabs (state driver for panels) ────────────────────────────
        with ui.tabs().classes("hidden").props("dense") as tabs:
            tab_essentials = ui.tab("essentials", label="Essentials", icon="dashboard_customize")
            tab_general    = ui.tab("general",    label="Scraping",   icon="travel_explore")
            tab_downloader = ui.tab("downloader", label="Downloader", icon="download")
            tab_organiser  = ui.tab("organiser",  label="Organiser",  icon="folder_special")
            tab_tracker    = ui.tab("tracker",    label="Tracker",    icon="star")
            tab_lookfeel   = ui.tab("lookfeel",   label="Look & Feel",icon="palette")
            tab_advanced   = ui.tab("advanced",   label="Advanced",   icon="build")

        panel_map = {
            "essentials": tab_essentials,
            "scraping": tab_general,
            "downloader": tab_downloader,
            "organiser": tab_organiser,
            "tracker": tab_tracker,
            "lookfeel": tab_lookfeel,
            "advanced": tab_advanced,
        }

        with ui.column().classes("cfg-jumpbar w-full gap-0"):
            ui.label("Jump To Section").classes("cfg-jump-label")
            panel_sel = ui.select(
                options={
                    "essentials": "Essentials",
                    "scraping": "Scraping",
                    "downloader": "Downloader",
                    "organiser": "Organiser",
                    "tracker": "Tracker",
                    "lookfeel": "Look & Feel",
                    "advanced": "Advanced",
                },
                value="essentials",
                with_input=False,
            ).classes("cfg-jump w-full").props("outlined dense dark options-dark")
            panel_sel.on_value_change(lambda e: setattr(tabs, "value", panel_map[e.value]))

        # ── Tab panels ────────────────────────────────────────────────────────
        with ui.tab_panels(tabs, value=tab_essentials).classes("cfg-panels w-full flex-1 min-h-0").style(
            "background:#0f0f13"
        ):

            # ── ESSENTIALS ───────────────────────────────────────────────────
            with ui.tab_panel(tab_essentials).classes("cfg-panel"):

                with ui.card().classes("cfg-summary-card w-full"):
                    with ui.column().classes("w-full gap-2 p-4"):
                        ui.label("Setup Health").classes("cfg-summary-head")
                        ui.label("Critical checks").classes("cfg-summary-title")
                        status_rows["download_folder"] = _make_status_row("Download folder")
                        status_rows["metadata"] = _make_status_row("Metadata source")
                        status_rows["provider"] = _make_status_row("Translation provider")
                        status_rows["api_key"] = _make_status_row("API key")
                        status_rows["qbt"] = _make_status_row("qBittorrent")

                ui.label("Core Setup").classes("cfg-section")

                ui.label("Metadata Source").classes("cfg-section")
                ui.label(
                    "Pick the primary scraper used during normal fetches. Browser and proxy behavior can be tuned in the Scraping tab."
                ).classes("cfg-hint")
                metadata_src_sel = ui.select(
                    options=["javdb", "javlibrary"],
                    label="Primary metadata source",
                    value=cfg.get("metadata_source", "javdb"),
                ).classes("w-full")

                ui.label("Download Folder").classes("cfg-section")
                with ui.row().classes("w-full items-center gap-2"):
                    dl_folder_inp = ui.input(
                        label="Base download folder",
                        value=cfg.get("download_folder", ""),
                        placeholder=r"e.g. D:\Downloads\JAV",
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(dl_folder_inp, "value", _browse_folder()),
                    ).props("flat dense round").tooltip("Browse...")

                ui.label("Translation Provider").classes("cfg-section")
                initial_provider = cfg.get("provider") or list(PROVIDERS.keys())[0]
                initial_pinfo = PROVIDERS.get(initial_provider, {})
                provider_sel = ui.select(
                    options=list(PROVIDERS.keys()),
                    label="Provider",
                    value=initial_provider,
                ).classes("w-full")
                base_url_inp = ui.input(
                    label="API Base URL",
                    value=cfg.get("base_url") or initial_pinfo.get("base_url", ""),
                    placeholder="https://api.example.com/v1",
                ).classes("w-full")
                initial_models = initial_pinfo.get("models", [])
                initial_model = cfg.get("model") or (initial_models[0] if initial_models else "")
                model_sel = ui.select(
                    options=initial_models or [""],
                    label="Model",
                    value=initial_model,
                    new_value_mode="add-unique",
                ).classes("w-full")
                initial_env_key = initial_pinfo.get("env_key", "CUSTOM_API_KEY")
                api_key_inp = ui.input(
                    label="API Key",
                    value=read_env_key(initial_env_key),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                with ui.row().classes("items-center justify-between w-full -mt-1 mb-1"):
                    env_note = ui.label(
                        f"Stored in .env as:  {initial_env_key}"
                    ).classes("text-xs text-gray-500")
                    key_url = initial_pinfo.get("key_url", "")
                    get_key_lnk = ui.link(
                        "Get API key", target=key_url, new_tab=True
                    ).classes("text-xs text-blue-400")
                    get_key_lnk.set_visibility(bool(key_url))

                def _on_provider_change(e) -> None:
                    p = PROVIDERS.get(e.value, {})
                    models = p.get("models", [])
                    base_url_inp.value = p.get("base_url", "")
                    model_sel.options = models or [""]
                    model_sel.value = models[0] if models else ""
                    ek = p.get("env_key", "CUSTOM_API_KEY")
                    api_key_inp.value = read_env_key(ek)
                    env_note.text = f"Stored in .env as:  {ek}"
                    ku = p.get("key_url", "")
                    get_key_lnk.props(f'href="{ku}"')
                    get_key_lnk.set_visibility(bool(ku))
                    _refresh_core_status()

                provider_sel.on_value_change(_on_provider_change)

                ui.label("qBittorrent").classes("cfg-section")
                ui.label(
                    "Enable Web UI in qBittorrent first, then keep the URL and credentials here. Use the test action to verify live connectivity."
                ).classes("cfg-hint")
                qbt_url_inp = ui.input(
                    label="Web UI URL",
                    value=cfg.get("qbt_url", "http://localhost:8080"),
                ).classes("w-full")
                qbt_user_inp = ui.input(
                    label="Username", value=cfg.get("qbt_username", "admin")
                ).classes("w-full")
                qbt_pass_inp = ui.input(
                    label="Password",
                    value=read_env_key("QBT_PASSWORD"),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                qbt_test_lbl = ui.label("Live connectivity has not been tested in this session.").classes("text-xs text-gray-500 -mt-1 mb-1")

                async def _test_qbt() -> None:
                    from utils.qbittorrent import is_reachable
                    ok = await is_reachable(qbt_url_inp.value.strip())
                    qbt_test_state["ok"] = ok
                    qbt_test_lbl.set_text(
                        "Connection test passed. qBittorrent is reachable."
                        if ok else
                        "Connection test failed. Check the URL and whether qBittorrent Web UI is enabled."
                    )
                    qbt_test_lbl.style(
                        "font-size:0.75rem;color:#34d399;margin-top:-4px;margin-bottom:4px;"
                        if ok else
                        "font-size:0.75rem;color:#f59e0b;margin-top:-4px;margin-bottom:4px;"
                    )
                    _refresh_core_status()
                    ui.notify(
                        "qBittorrent reachable" if ok
                        else "Cannot reach qBittorrent — check URL and Web UI is enabled",
                        color="positive" if ok else "negative",
                        timeout=4000,
                    )

                with ui.row().classes("items-center gap-2 mt-1 mb-2"):
                    ui.button("Test connection", icon="wifi", on_click=_test_qbt).props(
                        "flat dense"
                    ).classes("text-xs")
                    ui.button(
                        "Open .env file", icon="edit_note",
                        on_click=lambda: webbrowser.open(str(ENV_FILE)),
                    ).props("flat dense").classes("text-xs text-gray-400")

                def _refresh_core_status() -> None:
                    folder_value = dl_folder_inp.value.strip()
                    provider_value = str(provider_sel.value or "").strip()
                    model_value = str(model_sel.value or "").strip()
                    key_present = bool(api_key_inp.value.strip())
                    qbt_ready = all([
                        qbt_url_inp.value.strip(),
                        qbt_user_inp.value.strip(),
                        qbt_pass_inp.value.strip(),
                    ])
                    qbt_detail = (
                        "Reachable in this session"
                        if qbt_test_state["ok"] is True else
                        "Configured, but live connectivity has not been confirmed yet"
                        if qbt_ready else
                        "Missing URL, username, or password"
                    )
                    if qbt_test_state["ok"] is False:
                        qbt_detail = "Connection test failed. Review Web UI settings and URL"
                    _set_status(
                        status_rows["download_folder"],
                        bool(folder_value),
                        folder_value if folder_value else "Choose where downloader-created folders should be stored",
                    )
                    _set_status(
                        status_rows["metadata"],
                        True,
                        "Using JAVDB for headless speed" if metadata_src_sel.value == "javdb" else "Using JAVLibrary with browser-assisted fallback",
                    )
                    _set_status(
                        status_rows["provider"],
                        bool(provider_value and model_value),
                        f"{provider_value} / {model_value}" if provider_value and model_value else "Pick a provider and model",
                    )
                    _set_status(
                        status_rows["api_key"],
                        key_present,
                        "Secret loaded from .env" if key_present else "No API key found for the selected provider",
                    )
                    _set_status(status_rows["qbt"], bool(qbt_ready and qbt_test_state["ok"] is True), qbt_detail)

                for _field in [
                    metadata_src_sel,
                    dl_folder_inp,
                    provider_sel,
                    model_sel,
                    api_key_inp,
                    qbt_url_inp,
                    qbt_user_inp,
                    qbt_pass_inp,
                ]:
                    _field.on_value_change(lambda _e: _refresh_core_status())

                _refresh_core_status()

            # ── GENERAL ───────────────────────────────────────────────────────
            with ui.tab_panel(tab_general).classes("cfg-panel"):

                with ui.column().classes("cfg-hero w-full gap-1"):
                    ui.label("Scraper behavior").classes("cfg-hero-title")
                    ui.label(
                        "These controls affect how aggressively the app fetches, when Chrome is surfaced, and how proxy fallback behaves. They matter when scraping gets blocked or you need more throughput."
                    ).classes("cfg-hero-copy")

                with ui.column().classes("w-full"):
                    ui.label("JAVLibrary Browser Window").classes("cfg-section")
                    ui.label(
                        "Shared setting for all built-in JAVLibrary scraper flows.\n"
                        "Applies when Downloader metadata fetches or Tracker actress/page-count fetches\n"
                        "need manual Cloudflare input before surfacing Chrome in front."
                    ).classes("cfg-hint")
                    javlib_front_delay_inp = ui.number(
                        label="Bring Chrome to front after (seconds)",
                        value=float(cfg.get("javlibrary_foreground_delay", 3.0)),
                        min=0,
                        max=30,
                        step=0.5,
                    ).classes("w-56").props("outlined dense dark input-style=color:#f3f4f6")

                with ui.expansion(
                    "Network fallbacks and parallel sessions",
                    caption="Proxy rotation, javdb slots, and JAVLibrary browser fan-out",
                    value=False,
                    icon="settings_ethernet",
                ).classes("cfg-expansion w-full mt-4"):
                    with ui.column().classes("w-full gap-1 p-4"):
                        ui.label("Proxy / IP Rotation").classes("cfg-section")
                        ui.label(
                            "Direct connection is always tried first.\n"
                            "Proxies are used as fallbacks on 403/429.\n"
                            "Format:  http://user:pass@host:port   or   socks5://host:port"
                        ).classes("cfg-hint")
                        proxy_inp = ui.textarea(
                            label="javdb proxies (one per line)",
                            value="\n".join(cfg.get("javdb_proxies", [])),
                        ).props("outlined dense rows=4").classes("w-full font-mono text-xs")

                        ui.label("Parallel Fetch Sessions").classes("cfg-section")
                        ui.label(
                            "How many simultaneous fetches to run in parallel.\n"
                            "javdb: needs 1 proxy per extra slot (slot-0 = direct).\n"
                            "javlibrary: each slot launches its own Chrome profile."
                        ).classes("cfg-hint")
                        with ui.row().classes("items-center gap-6 w-full"):
                            with ui.row().classes("items-center gap-3 flex-1"):
                                ui.label("javdb concurrency").classes("text-xs text-grey-5 flex-1")
                                javdb_conc_inp = ui.number(
                                    label="Slots",
                                    value=cfg.get("javdb_concurrency", 1),
                                    min=1, max=10, step=1, format="%d",
                                ).style("width:90px")
                            with ui.row().classes("items-center gap-3 flex-1"):
                                ui.label("javlibrary concurrency").classes("text-xs text-grey-5 flex-1")
                                javlib_conc_inp = ui.number(
                                    label="Slots",
                                    value=cfg.get("javlibrary_concurrency", 1),
                                    min=1, max=5, step=1, format="%d",
                                ).style("width:90px")
                        ui.label(
                            "Restart the app after changing concurrency so new Chrome profiles initialise."
                        ).classes("text-xs text-orange-400 -mt-1 mb-2")

            # ── DOWNLOADER ────────────────────────────────────────────────────
            with ui.tab_panel(tab_downloader).classes("cfg-panel"):

                with ui.column().classes("cfg-hero w-full gap-1"):
                    ui.label("Downloader-specific behavior").classes("cfg-hero-title")
                    ui.label(
                        "Provider credentials now live in Essentials. This tab keeps queue refresh, display density, and layout controls together."
                    ).classes("cfg-hero-copy")

                with ui.row().classes("items-center gap-3 w-full mt-1"):
                    ui.label("Batch translate concurrency").classes("text-xs text-grey-5 flex-1")
                    trans_conc_inp = ui.number(
                        label="Max parallel",
                        value=cfg.get("trans_concurrency", 3),
                        min=1, max=10, step=1, format="%d",
                    ).style("width:100px")
                ui.label(
                    "Max simultaneous LLM calls. Lower to avoid provider rate-limits."
                ).classes("text-xs text-grey-6 -mt-1 mb-2")

                ui.label("Download Status Display").classes("cfg-section")
                with ui.row().classes("items-center gap-4 w-full"):
                    dl_poll_slider = ui.slider(
                        min=5, max=120, step=5,
                        value=cfg.get("dl_poll_interval", 30),
                    ).classes("flex-1")
                    dl_poll_lbl = ui.label(f"{cfg.get('dl_poll_interval', 30)}s").style(
                        "font-size:0.85rem;color:#9ca3af;min-width:48px;text-align:right"
                    )
                    dl_poll_slider.on_value_change(
                        lambda e: setattr(dl_poll_lbl, "text", f"{int(e.value)}s")
                    )
                ui.label("Poll interval").classes("text-xs text-gray-500 -mt-2 mb-1")
                dl_fields_sel = ui.select(
                    options={
                        "progress_bar": "Progress Bar",
                        "percentage":   "Percentage",
                        "state":        "State",
                        "speed":        "Speed",
                        "eta":          "ETA",
                        "torrent_name": "Torrent Name",
                    },
                    label="Display fields below cover",
                    value=cfg.get("dl_cover_fields", ["progress_bar", "percentage", "state"]),
                    multiple=True,
                ).classes("w-full mb-2")

                ui.label("Panel Layout").classes("cfg-section")
                with ui.row().classes("items-center gap-4 w-full"):
                    panel_w_slider = ui.slider(
                        min=200, max=500, step=5,
                        value=downloader_panel_width,
                    ).classes("flex-1")
                    panel_w_lbl = ui.label(
                        f"{downloader_panel_width}px"
                    ).style("font-size:0.85rem;color:#9ca3af;min-width:48px;text-align:right")
                    panel_w_slider.on_value_change(
                        lambda e: setattr(panel_w_lbl, "text", f"{int(e.value)}px")
                    )
                ui.label("Sidebar width").classes("text-xs text-gray-500 -mt-2")

                ui.label("Inspector Cover").classes("cfg-section")
                cur_dl_cover_w = int(cfg.get("downloader_cover_w", 240))
                dl_cover_w_lbl = ui.label(f"{cur_dl_cover_w} px").style(
                    "font-size:0.85rem;color:#9ca3af;min-width:56px;text-align:right"
                )
                dl_cover_w_ref: List[int] = [cur_dl_cover_w]

                def _on_dl_cover_w(e) -> None:
                    w = int(e.value)
                    dl_cover_w_ref[0] = w
                    dl_cover_w_lbl.set_text(f"{w} px")

                with ui.row().classes("items-center gap-4 w-full"):
                    ui.slider(
                        min=160,
                        max=360,
                        step=8,
                        value=cur_dl_cover_w,
                        on_change=_on_dl_cover_w,
                    ).classes("flex-1")
                    dl_cover_w_lbl
                ui.label("Cover column width in the downloader inspector").classes(
                    "text-xs text-gray-500 -mt-2"
                )

            # ── ORGANISER ─────────────────────────────────────────────────────
            with ui.tab_panel(tab_organiser).classes("cfg-panel"):

                ui.label("Video Thumbnails Maker (VTM)").classes("cfg-section")
                with ui.row().classes("w-full items-center gap-2"):
                    vtm_exe_inp = ui.input(
                        label="VTM executable",
                        value=cfg.get("vtm_exe", DEFAULT_VTM_EXE),
                        placeholder=DEFAULT_VTM_EXE,
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(
                            vtm_exe_inp, "value",
                            _browse_file("Select VTM exe", [("Executables", "*.exe")]),
                        ),
                    ).props("flat dense round").tooltip("Browse...")
                _preset_opts = list_vtm_presets() or [cfg.get("vtm_preset", default_vtm_preset())]
                vtm_preset_sel = ui.select(
                    options=_preset_opts or [""],
                    label="VTM preset (.vtm)",
                    value=cfg.get("vtm_preset", _preset_opts[0] if _preset_opts else ""),
                    new_value_mode="add-unique",
                ).classes("w-full")

                ui.label("LosslessCut").classes("cfg-section")
                with ui.row().classes("w-full items-center gap-2"):
                    llc_exe_inp = ui.input(
                        label="LosslessCut executable",
                        value=cfg.get("losslesscut_exe", DEFAULT_LOSSLESSCUT_EXE),
                        placeholder=DEFAULT_LOSSLESSCUT_EXE,
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(
                            llc_exe_inp, "value",
                            _browse_file("Select LosslessCut exe", [("Executables", "*.exe")]),
                        ),
                    ).props("flat dense round").tooltip("Browse...")

                ui.label("Default Folders").classes("cfg-section")
                with ui.row().classes("w-full items-center gap-2"):
                    org_scan_inp = ui.input(
                        label="Default scan folder (Renamer source)",
                        value=organiser_state.get("scan_folder", cfg.get("organiser_scan_folder", "")),
                        placeholder=r"e.g. Z:\AV\Rename Here",
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(org_scan_inp, "value", _browse_folder()),
                    ).props("flat dense round").tooltip("Browse...")
                with ui.row().classes("w-full items-center gap-2"):
                    org_mover_inp = ui.input(
                        label='Default "Move to" folder (Folder Mover destination)',
                        value=organiser_state.get("mover_base", cfg.get("organiser_mover_base", "")),
                        placeholder="Auto (leave blank to detect from scanned folder)",
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(org_mover_inp, "value", _browse_folder()),
                    ).props("flat dense round").tooltip("Browse...")

                ui.label("Panel Layout").classes("cfg-section")
                with ui.row().classes("items-center gap-4 w-full"):
                    org_renamer_panel_w_slider = ui.slider(
                        min=420, max=1200, step=10,
                        value=int(organiser_state.get("renamer_panel_width", organiser_state.get("left_panel_width", 780))),
                    ).classes("flex-1")
                    org_renamer_panel_w_lbl = ui.label(
                        f"{int(organiser_state.get('renamer_panel_width', organiser_state.get('left_panel_width', 780)))}px"
                    ).style("font-size:0.85rem;color:#9ca3af;min-width:52px;text-align:right")
                    org_renamer_panel_w_slider.on_value_change(
                        lambda e: setattr(org_renamer_panel_w_lbl, "text", f"{int(e.value)}px")
                    )
                ui.label("Rename list width").classes("text-xs text-gray-500 -mt-2")
                with ui.row().classes("items-center gap-4 w-full"):
                    org_mover_panel_w_slider = ui.slider(
                        min=360, max=1100, step=10,
                        value=int(organiser_state.get("mover_panel_width", organiser_state.get("left_panel_width", 680))),
                    ).classes("flex-1")
                    org_mover_panel_w_lbl = ui.label(
                        f"{int(organiser_state.get('mover_panel_width', organiser_state.get('left_panel_width', 680)))}px"
                    ).style("font-size:0.85rem;color:#9ca3af;min-width:52px;text-align:right")
                    org_mover_panel_w_slider.on_value_change(
                        lambda e: setattr(org_mover_panel_w_lbl, "text", f"{int(e.value)}px")
                    )
                ui.label("Move list width").classes("text-xs text-gray-500 -mt-2")

                ui.label("Quick Cleanup").classes("cfg-section")
                ui.label(
                    "Quick Clean keeps videos, images, and subtitle files. "
                    "You can also opt into deleting tiny video files below a size threshold."
                ).classes("cfg-hint")
                cleanup_other_chk = ui.checkbox(
                    "Delete files that are not video, image, or subtitle",
                    value=bool(organiser_state.get("cleanup_delete_other_files", cfg.get("organiser_cleanup_delete_other_files", True))),
                ).classes("w-full")
                cleanup_small_chk = ui.checkbox(
                    "Delete small video files",
                    value=bool(organiser_state.get("cleanup_delete_small_videos", cfg.get("organiser_cleanup_delete_small_videos", False))),
                ).classes("w-full")
                cleanup_small_mb_inp = ui.number(
                    label="Small video threshold (MB)",
                    value=float(organiser_state.get("cleanup_small_video_mb", cfg.get("organiser_cleanup_small_video_mb", 30.0))),
                    min=1,
                    max=4096,
                    step=1,
                ).classes("w-48").props("outlined dense dark input-style=color:#f3f4f6")
                ui.label("Videos smaller than this threshold will be deleted when that option is enabled.").classes(
                    "text-xs text-gray-500 -mt-2"
                )

            # ── TRACKER ───────────────────────────────────────────────────────
            with ui.tab_panel(tab_tracker).classes("cfg-panel"):

                ui.label("Cover Cards").classes("cfg-section")
                cur_cover_w = int(cfg.get("tracker_cover_w", 80))
                trk_width_lbl = ui.label(f"{cur_cover_w} px").style(
                    "font-size:0.78rem;color:#9ca3af;margin-bottom:4px"
                )
                trk_width_ref: List[int] = [cur_cover_w]

                def _on_trk_width(e) -> None:
                    w = int(e.value)
                    trk_width_ref[0] = w
                    trk_width_lbl.set_text(f"{w} px")
                    ui.run_javascript(
                        f"document.documentElement.style.setProperty('--trk-cover-w', '{w}px');"
                        f"document.documentElement.style.setProperty('--trk-cover-h', '{int(w * 0.65)}px');"
                    )

                ui.slider(
                    min=40, max=240, step=4,
                    value=cur_cover_w, on_change=_on_trk_width,
                ).style("width:100%;margin-bottom:4px")
                ui.label("40 px — 240 px").classes("cfg-hint")

                ui.label("Left Panel Width").classes("cfg-section")
                cur_left_w = get_tracker_left_panel_width(300)
                trk_left_w_lbl = ui.label(f"{cur_left_w} px").style(
                    "font-size:0.78rem;color:#9ca3af;margin-bottom:4px"
                )
                trk_left_w_ref: List[int] = [cur_left_w]

                def _on_trk_left_w(e) -> None:
                    w = int(e.value)
                    trk_left_w_ref[0] = w
                    trk_left_w_lbl.set_text(f"{w} px")

                ui.slider(
                    min=200, max=600, step=10,
                    value=cur_left_w, on_change=_on_trk_left_w,
                ).style("width:100%;margin-bottom:4px")
                ui.label("200 px — 600 px").classes("cfg-hint")

                ui.label("Activity Status").classes("cfg-section")
                tracker_auto_inactive_chk = ui.checkbox(
                    "Auto-mark actresses as inactive",
                    value=bool(cfg.get("tracker_auto_inactive_enabled", True)),
                ).classes("w-full")
                tracker_inactive_months_inp = ui.number(
                    label="Solo release window (months)",
                    value=int(cfg.get("tracker_inactive_months", 6)),
                    min=1,
                    max=60,
                    step=1,
                    format="%d",
                ).classes("w-48").props("outlined dense dark input-style=color:#f3f4f6")
                ui.label(
                    "Default: inactive when no fetched solo release exists within the last 6 months."
                ).classes("cfg-hint")


            # ── LOOK & FEEL ───────────────────────────────────────────────────
            with ui.tab_panel(tab_lookfeel).classes("cfg-panel"):

                ui.label("Anime Ratings Badge").classes("cfg-section")
                ui.label("Control GPU usage and visual intensity for tracker rating badges.").classes("cfg-hint")
                
                aura_enabled_chk = ui.checkbox("Enable Anime Effects", value=aura_cfg.get("enabled", True))
                
                with ui.row().classes("w-full items-center justify-between mb-4 mt-2"):
                    ui.label("Emission Scale").classes("text-sm text-gray-400")
                    scale_lbl = ui.label(f"{aura_cfg.get('emission_scale', 2.0):.1f}x").classes("font-mono text-xs text-indigo-400")
                def _on_scale(e): scale_lbl.set_text(f"{e.value:.1f}x")
                aura_scale_slider = ui.slider(min=0.5, max=5.0, step=0.1, value=aura_cfg.get("emission_scale", 2.0), on_change=_on_scale).style("width:100%")
                
                aura_particles_chk = ui.checkbox("Floating Energy Dots (DBZ-style embers)", value=aura_cfg.get("particles", True))
                aura_beams_chk = ui.checkbox("Upward Surging Energy Columns", value=aura_cfg.get("vertical_beams", True))
                aura_godlight_chk = ui.checkbox("Outward Rotating Celestial Rays", value=aura_cfg.get("god_light", True))
                
                ui.label("Performance Warning").classes("cfg-section mt-4")
                aura_blur_chk = ui.checkbox("Use SVG Blur Filters (Heavy GPU/RAM Load)", value=aura_cfg.get("use_blur_filters", False))
                ui.label("Keep unchecked for crisp vector style and high performance. Blurs significantly impact SVG frame rates on animated text.").classes("cfg-hint ml-8")

                ui.label("Rating Tooltips & Thresholds").classes("cfg-section mt-6")
                ui.label(
                    "Edit the tooltip copy and the minimum score for each tier. "
                    "Ranges must stay in descending order."
                ).classes("cfg-hint")

                current_tips = get_rating_tooltips(cfg)
                current_thrs = get_rating_thresholds(cfg)
                tier_keys = TIER_ORDER[:-1]
                batch_order = ["onyx", "garnet", "jade", "aquamarine", "silver", "topaz", "gold", "emerald", "amethyst", "sapphire", "ruby", "diamond"]

                with ui.dialog().props("persistent") as tip_dlg, \
                     ui.card().classes("cfg-card").style("width:980px; max-width:96vw; height:min(88vh, 920px); display:flex; flex-direction:column; padding:18px;"):
                    ui.label("Edit Score Tiers").classes("text-xl font-bold tracking-tight text-white")
                    ui.label(
                        "Each tier has a minimum score and tooltip text. "
                        "The low rank bucket automatically covers everything below Onyx."
                    ).classes("text-sm text-gray-400 mb-3")

                    with ui.scroll_area().classes("w-full flex-grow"):
                        tip_inputs: Dict[str, ui.textarea] = {}
                        preview_labels: Dict[str, ui.label] = {}
                        range_labels: Dict[str, ui.label] = {}
                        batch_refs: Dict[str, object] = {}

                        def _get_threshold_value(tier_key: str) -> int:
                            return int(current_thrs[tier_key])

                        def _threshold_chain_string() -> str:
                            return "; ".join(str(_get_threshold_value(key)) for key in batch_order)

                        def _sync_batch_editor() -> None:
                            batch_input = batch_refs.get("input")
                            low_label = batch_refs.get("low_label")
                            anchor_input = batch_refs.get("anchor_input")
                            if batch_input is not None:
                                batch_input.value = _threshold_chain_string()
                            if anchor_input is not None:
                                anchor_input.value = _get_threshold_value("onyx")
                            if low_label is not None:
                                low_label.set_text(f"Low Rank automatically means any score below {_get_threshold_value('onyx')}")

                        def _apply_threshold_values(values_by_key: Dict[str, int], success_message: str | None = None) -> bool:
                            invalid = []
                            for idx in range(len(tier_keys) - 1):
                                current_key = tier_keys[idx]
                                next_key = tier_keys[idx + 1]
                                if values_by_key[current_key] <= values_by_key[next_key]:
                                    invalid.append(f"{TIER_LABELS[current_key]} must be greater than {TIER_LABELS[next_key]}")

                            if invalid:
                                ui.notify(invalid[0], color="negative")
                                return False

                            for key in tier_keys:
                                current_thrs[key] = max(0, min(100, int(values_by_key[key])))

                            _refresh_range_labels()
                            if success_message:
                                ui.notify(success_message, color="positive")
                            return True

                        def _current_range_text(tier_key: str) -> str:
                            if tier_key == "low":
                                return f"Range: below {_get_threshold_value('onyx')}"
                            return f"Range: min {_get_threshold_value(tier_key)}"

                        def _refresh_range_labels() -> None:
                            for tier_key, label in range_labels.items():
                                label.set_text(_current_range_text(tier_key))
                            _sync_batch_editor()

                        def _refresh_preview(tier_key: str) -> None:
                            preview_labels[tier_key].set_text(_tooltip_preview(tip_inputs[tier_key].value or ""))

                        with ui.card().classes("w-full mb-4").style(
                            "background:#10131c; border:1px solid #232533; box-shadow:none;"
                        ):
                            with ui.column().classes("w-full gap-3 p-4"):
                                ui.label("Batch Threshold Editor").classes("text-sm font-semibold text-white")
                                ui.label(
                                    "Start from the lowest rank and work upward. Onyx is the anchor. "
                                    "The spacing helpers rebuild every higher band from that lowest anchor."
                                ).classes("text-xs text-gray-400")
                                ui.label(
                                    "Use the chain when you already know every exact cutoff. Use the spacing action when you only want to set the anchor and step sizes, and let the app generate the full ladder."
                                ).classes("text-xs text-gray-400")
                                ui.label(
                                    "Onyx ; Garnet ; Jade ; Aquamarine ; Silver ; Topaz ; Gold ; Emerald ; Amethyst ; Sapphire ; Ruby ; Diamond"
                                ).classes("font-mono text-xs text-amber-400")

                                def _set_anchor_value() -> None:
                                    anchor_input = batch_refs.get("anchor_input")
                                    if anchor_input is None:
                                        return
                                    current_thrs["onyx"] = max(0, min(100, int(anchor_input.value or 0)))
                                    _refresh_range_labels()

                                batch_refs["anchor_input"] = ui.number(
                                    label="Onyx anchor",
                                    value=_get_threshold_value("onyx"),
                                    min=0,
                                    max=100,
                                    step=1,
                                    on_change=lambda _e: _set_anchor_value(),
                                ).classes("w-28").props("outlined dense dark input-style=color:#f3f4f6")

                                batch_refs["input"] = ui.input(
                                    label="Minimum score chain",
                                    value=_threshold_chain_string(),
                                    placeholder="40; 50; 56; 61; 66; 71; 76; 81; 86; 90; 94; 96",
                                ).classes("w-full").props(
                                    "outlined dense dark input-style=color:#f3f4f6"
                                )

                                def _apply_batch_thresholds(notify_on_success: bool = False) -> None:
                                    raw_chain = str(batch_refs["input"].value or "")
                                    parts = [part.strip() for part in raw_chain.split(";") if part.strip()]
                                    if len(parts) != len(tier_keys):
                                        ui.notify(f"Expected {len(tier_keys)} values in the chain.", color="negative")
                                        return

                                    parsed: Dict[str, int] = {}
                                    for key, part in zip(batch_order, parts):
                                        try:
                                            parsed[key] = int(part)
                                        except ValueError:
                                            ui.notify(f"{TIER_LABELS[key]} must be a whole number.", color="negative")
                                            return

                                    _apply_threshold_values(
                                        parsed,
                                        "Batch thresholds updated." if notify_on_success else None,
                                    )

                                batch_refs["input"].on("change", lambda _e: _apply_batch_thresholds())

                                batch_refs["low_label"] = ui.label(
                                    f"Low Rank automatically means any score below {_get_threshold_value('onyx')}"
                                ).classes("text-xs text-gray-400")

                                def _apply_all_spacing() -> None:
                                    anchor_input = batch_refs.get("anchor_input")
                                    lower_step = int(lower_step_inp.value or 10)
                                    material_step = int(material_step_inp.value or 5)
                                    gem_step = int(gem_step_inp.value or 5)

                                    proposed = {key: _get_threshold_value(key) for key in tier_keys}
                                    proposed["onyx"] = max(0, min(100, int(anchor_input.value or proposed["onyx"])))
                                    proposed["garnet"] = proposed["onyx"] + lower_step
                                    proposed["jade"] = proposed["garnet"] + material_step
                                    proposed["aquamarine"] = proposed["jade"] + material_step
                                    proposed["silver"] = proposed["aquamarine"] + material_step
                                    proposed["topaz"] = proposed["silver"] + material_step
                                    proposed["gold"] = proposed["topaz"] + material_step
                                    proposed["emerald"] = proposed["gold"] + gem_step
                                    proposed["amethyst"] = proposed["emerald"] + gem_step
                                    proposed["sapphire"] = proposed["amethyst"] + gem_step
                                    proposed["ruby"] = proposed["sapphire"] + gem_step
                                    proposed["diamond"] = proposed["ruby"] + gem_step

                                    _apply_threshold_values(proposed, "Spacing ladder rebuilt from the lowest anchor.")

                                with ui.row().classes("w-full items-end gap-2 wrap"):
                                    batch_refs["anchor_input"]
                                    lower_step_inp = ui.number(
                                        label="Lower step",
                                        value=10,
                                        min=1,
                                        max=25,
                                        step=1,
                                    ).classes("w-24").props("outlined dense dark input-style=color:#f3f4f6")
                                    material_step_inp = ui.number(
                                        label="Material step",
                                        value=5,
                                        min=1,
                                        max=25,
                                        step=1,
                                    ).classes("w-28").props("outlined dense dark input-style=color:#f3f4f6")
                                    gem_step_inp = ui.number(
                                        label="Gem step",
                                        value=5,
                                        min=1,
                                        max=25,
                                        step=1,
                                    ).classes("w-24").props("outlined dense dark input-style=color:#f3f4f6")
                                    ui.button(
                                        "Generate Ladder From Anchor + Steps",
                                        on_click=_apply_all_spacing,
                                    ).props("flat").style("color:#f59e0b")

                        for key in TIER_ORDER:
                            icon = TIER_ICONS.get(key, "")
                            title = f"{icon} {TIER_LABELS[key]}".strip()

                            with ui.expansion(title, icon="expand_more").classes("w-full mb-3").style(
                                "background:#12131a; border:1px solid #232533; border-radius:12px; overflow:hidden;"
                            ):
                                with ui.column().classes("w-full gap-3 p-4"):
                                    range_labels[key] = ui.label(_current_range_text(key)).classes(
                                        "text-xs uppercase tracking-wide text-amber-400"
                                    )
                                    preview_labels[key] = ui.label(_tooltip_preview(current_tips[key])).classes(
                                        "text-sm text-gray-300"
                                    ).style(
                                        "line-height:1.5; background:#171923; border:1px solid #2a2d3f; border-radius:10px; padding:10px 12px;"
                                    )

                                    with ui.row().classes("w-full items-start gap-4 no-wrap"):
                                        with ui.column().classes("gap-2").style("min-width:170px;"):
                                            ui.label("Tier Range").classes("text-xs uppercase tracking-wide text-gray-400")
                                            if key != "low":
                                                ui.label("Thresholds are edited in the batch section above.").classes("text-xs text-gray-400")
                                            else:
                                                ui.label("Automatically covers anything below the current Onyx minimum.").classes("text-xs text-gray-400")

                                        with ui.column().classes("flex-1 gap-2"):
                                            ui.label("Tooltip text").classes("text-xs uppercase tracking-wide text-gray-400")
                                            tip_inputs[key] = ui.textarea(
                                                value=current_tips[key],
                                                on_change=lambda _e, tier_key=key: _refresh_preview(tier_key),
                                            ).classes("w-full").props(
                                                "outlined autogrow dark input-style=color:#f3f4f6"
                                            ).style(
                                                "min-height: 220px; background:#0d0f16; border-radius:12px;"
                                            )

                    def _apply_tips() -> None:
                        invalid = []
                        for idx in range(len(tier_keys) - 1):
                            current_key = tier_keys[idx]
                            next_key = tier_keys[idx + 1]
                            if current_thrs[current_key] <= current_thrs[next_key]:
                                invalid.append(f"{TIER_LABELS[current_key]} must be greater than {TIER_LABELS[next_key]}")

                        if invalid:
                            ui.notify(invalid[0], color="negative")
                            return

                        current_tips.clear()
                        for key in TIER_ORDER:
                            current_tips[key] = (tip_inputs[key].value or "").strip()
                            preview_labels[key].set_text(_tooltip_preview(current_tips[key]))

                        tip_dlg.close()
                        ui.notify("Tier changes staged. Click Save to persist them.", color="positive")

                    def _reset_tooltips_to_defaults() -> None:
                        for key in TIER_ORDER:
                            default_text = DEFAULT_RATING_TOOLTIPS[key]
                            tip_inputs[key].value = default_text
                            preview_labels[key].set_text(_tooltip_preview(default_text))
                        ui.notify("Tooltip text reset to defaults. Click Apply, then Save.", color="warning")

                    def _reset_thresholds_to_defaults() -> None:
                        current_thrs.clear()
                        current_thrs.update(DEFAULT_RATING_THRESHOLDS)
                        _refresh_range_labels()
                        ui.notify("Score thresholds reset to defaults. Click Apply, then Save.", color="warning")

                    with ui.row().classes("w-full justify-between items-center mt-4"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label("Changes here are only written after the main Settings Save.").classes("text-xs text-gray-500")
                            ui.button("Reset Tooltips", on_click=_reset_tooltips_to_defaults).props("flat").style("color:#f59e0b")
                            ui.button("Reset Thresholds", on_click=_reset_thresholds_to_defaults).props("flat").style("color:#f59e0b")
                        with ui.row().classes("items-center gap-2"):
                            ui.button("Cancel", on_click=tip_dlg.close).props("flat").style("color:#9ca3af")
                            ui.button("Apply", on_click=_apply_tips).props("flat").style("color:" + accent)

                ui.button(
                    "Customize Tiers & Tooltips",
                    icon="tune",
                    on_click=tip_dlg.open,
                ).props("outline").classes("mt-2 text-indigo-400 border-indigo-500")





            # ── ADVANCED ──────────────────────────────────────────────────────
            with ui.tab_panel(tab_advanced).classes("cfg-panel"):

                ui.label("Data Folder").classes("cfg-section")
                ui.label(
                    "Where config, secrets, Chrome profile and session cache are stored.\n"
                    "Move Data copies everything to the new location."
                ).classes("cfg-hint")
                with ui.row().classes("w-full items-center gap-2"):
                    data_dir_inp = ui.input(
                        label="Data folder",
                        value=str(DATA_DIR),
                    ).classes("flex-1")
                    ui.button(
                        icon="folder_open",
                        on_click=lambda: setattr(data_dir_inp, "value", _browse_folder()),
                    ).props("flat dense round").tooltip("Browse...")

                async def _move_data() -> None:
                    new_path = data_dir_inp.value.strip()
                    if not new_path or new_path == str(DATA_DIR):
                        ui.notify("Same folder — nothing to do.", color="info")
                        return
                    try:
                        await asyncio.to_thread(set_data_dir, new_path, migrate=True)
                        ui.notify(
                            f"Data moved to {new_path} — please restart the app.",
                            color="positive", timeout=0,
                        )
                    except Exception as exc:
                        ui.notify(f"Move failed: {exc}", color="negative", timeout=0)

                ui.button(
                    "Move Data & Restart", icon="drive_file_move", on_click=_move_data,
                ).props("flat dense").classes("text-xs mb-4")

                ui.label("Secrets File").classes("cfg-section")
                ui.button(
                    "Open .env file", icon="edit_note",
                    on_click=lambda: webbrowser.open(str(ENV_FILE)),
                ).props("flat dense").classes("text-xs text-gray-400")

                ui.label("Downloader Session Queue").classes("cfg-section")
                ui.label(
                    "Each browser session stores its own queue. If your queue vanished after\n"
                    "a restart or cookie reset, use this to scan all saved sessions and merge\n"
                    "all unique refs into the current session. Reload the Downloader page after."
                ).classes("cfg-hint")
                purge_merged_sessions_chk = ui.checkbox(
                    "After merge, purge downloader data from older session files",
                    value=True,
                ).props("dense").classes("text-xs")
                ui.label(
                    "Clears downloader queue and cached metadata from older session files,\n"
                    "then removes files that become empty or are fully redundant with the\n"
                    "newest merged session."
                ).classes("cfg-hint")
                _merge_status_lbl = ui.label("").style(
                    "font-size:0.71rem;color:#6b7280;margin-top:2px"
                )

                async def _merge_sessions() -> None:
                    import json as _json
                    _QUEUE_KEY = "jav_dl_queue"
                    _CACHE_KEY_LOCAL = "jav_dl_cache"
                    _META_CACHE_KEY = "_jav_meta_cache"

                    def _merge_legacy_meta_into_cache(cache: Dict[str, dict], meta_cache: dict) -> Dict[str, dict]:
                        merged_cache = dict(cache)
                        if not isinstance(meta_cache, dict):
                            return merged_cache
                        for kw, entry in meta_cache.items():
                            kw = kw.strip().upper()
                            if not kw or not isinstance(entry, dict) or not entry:
                                continue
                            merged_entry = dict(merged_cache.get(kw) or {})
                            if not isinstance(merged_entry.get("jav"), dict) or not merged_entry.get("jav"):
                                merged_entry["jav"] = dict(entry)
                            merged_cache[kw] = merged_entry
                        return merged_cache

                    def _is_redundant_subset(candidate: dict, primary: dict) -> bool:
                        if not candidate:
                            return True
                        for key, value in candidate.items():
                            if key not in primary or primary[key] != value:
                                return False
                        return True

                    merged_queue: Dict[str, dict] = {}
                    existing_state = load_downloader_state()
                    for item in existing_state.get("queue") or []:
                        kw = str(item.get("kw", "")).strip().upper()
                        if not kw:
                            continue
                        merged_queue[kw] = {
                            "kw": kw,
                            "title": item.get("title", ""),
                            "folder_path": item.get("folder_path", ""),
                            "downloaded": bool(item.get("downloaded")),
                            "ever_selected": bool(item.get("ever_selected")),
                        }
                    merged_cache: Dict[str, dict] = dict(existing_state.get("cache") or {})
                    total_raw = 0
                    file_count = 0
                    purged_files = 0
                    deleted_files = 0
                    try:
                        files = sorted(
                            NICEGUI_STORAGE_DIR.glob("storage-user-*.json"),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        file_count = len(files)
                        for f in files:
                            try:
                                data = _json.loads(f.read_text(encoding="utf-8"))

                                # ── Merge queue records ────────────────────
                                items = data.get(_QUEUE_KEY, [])
                                if isinstance(items, list):
                                    total_raw += len(items)
                                    for item in items:
                                        kw = (item.get("kw") or "").strip().upper()
                                        if not kw:
                                            continue
                                        if kw not in merged_queue:
                                            merged_queue[kw] = {
                                                "kw": kw,
                                                "title": item.get("title", ""),
                                                "folder_path": item.get("folder_path", ""),
                                                "downloaded": bool(item.get("downloaded")),
                                                "ever_selected": bool(item.get("ever_selected")),
                                            }
                                        else:
                                            ex = merged_queue[kw]
                                            if item.get("downloaded"):
                                                ex["downloaded"] = True
                                            if item.get("ever_selected"):
                                                ex["ever_selected"] = True
                                            if not ex["title"] and item.get("title"):
                                                ex["title"] = item["title"]
                                            if not ex["folder_path"] and item.get("folder_path"):
                                                ex["folder_path"] = item["folder_path"]

                                # ── Merge metadata cache (newest wins per kw) ──
                                cache = data.get(_CACHE_KEY_LOCAL, {})
                                if isinstance(cache, dict):
                                    for kw, entry in cache.items():
                                        kw = kw.strip().upper()
                                        if not kw or not isinstance(entry, dict):
                                            continue
                                        # Only keep entries that have real metadata
                                        if not entry.get("jav"):
                                            continue
                                        # Newest file is first (sorted desc); first hit wins
                                        if kw not in merged_cache:
                                            merged_cache[kw] = entry

                                meta_cache = data.get(_META_CACHE_KEY, {})
                                merged_cache = _merge_legacy_meta_into_cache(merged_cache, meta_cache)

                            except Exception:
                                continue
                    except Exception as exc:
                        ui.notify(f"Merge failed: {exc}", color="negative")
                        return

                    result = list(merged_queue.values())
                    merged_state = load_downloader_state()
                    merged_state["queue"] = result
                    merged_state["cache"] = merged_cache
                    save_downloader_state(merged_state)

                    # Optional cleanup: strip downloader-specific data from older
                    # session files, then delete shells that are empty or fully
                    # redundant with the newest merged session.
                    if purge_merged_sessions_chk.value:
                        try:
                            files = sorted(
                                NICEGUI_STORAGE_DIR.glob("storage-user-*.json"),
                                key=lambda p: p.stat().st_mtime,
                                reverse=True,
                            )
                        except Exception:
                            files = []

                        primary_file = files[0] if files else None
                        primary_data: dict = {}
                        if primary_file is not None:
                            try:
                                primary_data = _json.loads(primary_file.read_text(encoding="utf-8"))
                            except Exception:
                                primary_data = {}

                        for stale_file in files:
                            if primary_file is not None and stale_file == primary_file:
                                continue
                            try:
                                stale_data = _json.loads(stale_file.read_text(encoding="utf-8"))
                            except Exception:
                                continue
                            changed = False
                            for key in (_QUEUE_KEY, _CACHE_KEY_LOCAL, _META_CACHE_KEY):
                                if key in stale_data:
                                    stale_data.pop(key, None)
                                    changed = True

                            should_delete = _is_redundant_subset(stale_data, primary_data)

                            if should_delete:
                                try:
                                    stale_file.unlink(missing_ok=True)
                                    deleted_files += 1
                                except Exception:
                                    pass
                                continue

                            if not changed:
                                continue
                            try:
                                stale_file.write_text(
                                    _json.dumps(stale_data, ensure_ascii=False, indent=2),
                                    encoding="utf-8",
                                )
                                purged_files += 1
                            except Exception:
                                continue

                    dupes = total_raw - len(result)
                    cached_count = len(merged_cache)
                    msg = (
                        f"{len(result)} unique refs from {file_count} sessions "
                        f"({dupes} duplicates removed, {cached_count} metadata entries restored)"
                    )
                    if purged_files:
                        msg += f", purged {purged_files} older session files"
                    if deleted_files:
                        msg += f", deleted {deleted_files} redundant session files"
                    _merge_status_lbl.set_text(f"Last merge: {msg}. Reload the Downloader page.")
                    ui.notify(
                        f"Merged {msg}. Reload the Downloader page to see them.",
                        color="positive", timeout=8000,
                    )

                ui.button(
                    "Merge All Sessions into Current", icon="merge",
                    on_click=_merge_sessions,
                ).props("flat dense").classes("text-xs text-indigo-400")

        # ── Footer ────────────────────────────────────────────────────────────
        ui.separator().style("border-color:#1a1a24")
        with ui.row().classes("w-full items-center justify-end gap-2 px-5 py-3"):
            ui.button("Cancel", on_click=dlg.close).props("flat").style("color:#6b7280")

            def _save() -> None:
                try:
                    with tracked_save_state(save_state_key) if save_state_key else _NullSaveState():
                        raw_model = model_sel.value
                        save_config(
                            provider=provider_sel.value,
                            base_url=base_url_inp.value.strip(),
                            model=raw_model.strip() if isinstance(raw_model, str) else (raw_model or ""),
                            api_key=api_key_inp.value.strip(),
                            download_folder=dl_folder_inp.value.strip(),
                            qbt_url=qbt_url_inp.value.strip(),
                            qbt_username=qbt_user_inp.value.strip(),
                            qbt_password=qbt_pass_inp.value.strip(),
                            metadata_source=metadata_src_sel.value,
                            dl_poll_interval=int(dl_poll_slider.value),
                            dl_cover_fields=(
                                list(dl_fields_sel.value)
                                if dl_fields_sel.value
                                else ["progress_bar", "percentage", "state"]
                            ),
                            vtm_exe=vtm_exe_inp.value.strip(),
                            vtm_preset=(
                                vtm_preset_sel.value.strip()
                                if isinstance(vtm_preset_sel.value, str) else ""
                            ),
                            losslesscut_exe=llc_exe_inp.value.strip(),
                            trans_concurrency=max(1, int(trans_conc_inp.value or 3)),
                            javdb_proxies=[
                                p.strip() for p in proxy_inp.value.splitlines() if p.strip()
                            ],
                            javdb_concurrency=max(1, int(javdb_conc_inp.value or 1)),
                            javlibrary_concurrency=max(1, int(javlib_conc_inp.value or 1)),
                            javlibrary_foreground_delay=max(0.0, float(javlib_front_delay_inp.value or 0)),
                            downloader_cover_w=dl_cover_w_ref[0],
                            tracker_cover_w=trk_width_ref[0],
                            tracker_auto_inactive_enabled=bool(tracker_auto_inactive_chk.value),
                            tracker_inactive_months=max(1, int(tracker_inactive_months_inp.value or 6)),
                            organiser_scan_folder=org_scan_inp.value.strip(),
                            organiser_mover_base=org_mover_inp.value.strip(),
                            organiser_cleanup_delete_other_files=bool(cleanup_other_chk.value),
                            organiser_cleanup_delete_small_videos=bool(cleanup_small_chk.value),
                            organiser_cleanup_small_video_mb=float(cleanup_small_mb_inp.value or 30),
                            rating_tooltips=current_tips,
                            rating_thresholds=current_thrs,
                            aura_config={
                                "enabled": aura_enabled_chk.value,
                                "emission_scale": float(aura_scale_slider.value),
                                "use_blur_filters": aura_blur_chk.value,
                                "particles": aura_particles_chk.value,
                                "vertical_beams": aura_beams_chk.value,
                                "god_light": aura_godlight_chk.value,
                            },
                        )

                        from scraper.javdb import reset_javdb_pool
                        from scraper.javlibrary import reset_browser_pool

                        reset_javdb_pool()
                        reset_browser_pool()

                        pw = int(panel_w_slider.value)
                        set_downloader_panel_width(pw)
                        ui.run_javascript(
                            "var s=document.querySelector('.sidebar');"
                            f"if(s){{s.style.width='{pw}px';s.style.minWidth='{pw}px';}}"
                        )
                        ui.run_javascript(
                            "document.documentElement.style.setProperty('--dl-cover-w', "
                            f"'{dl_cover_w_ref[0]}px');"
                        )
                        if on_save_downloader:
                            on_save_downloader(
                                poll_interval=int(dl_poll_slider.value),
                                cover_w=dl_cover_w_ref[0],
                                timer_ctx=timer_ctx,
                                all_handles=all_handles,
                            )

                        org_renamer_pw = int(org_renamer_panel_w_slider.value)
                        org_mover_pw = int(org_mover_panel_w_slider.value)
                        save_organiser_preferences(
                            scan_folder=org_scan_inp.value.strip(),
                            mover_base=org_mover_inp.value.strip(),
                            renamer_panel_width=org_renamer_pw,
                            mover_panel_width=org_mover_pw,
                            cleanup_delete_other_files=bool(cleanup_other_chk.value),
                            cleanup_delete_small_videos=bool(cleanup_small_chk.value),
                            cleanup_small_video_mb=float(cleanup_small_mb_inp.value or 30),
                        )
                        if on_save_organiser:
                            on_save_organiser(
                                vtm_exe=vtm_exe_inp.value.strip(),
                                vtm_preset=(
                                    vtm_preset_sel.value.strip()
                                    if isinstance(vtm_preset_sel.value, str) else ""
                                ),
                                scan_folder=org_scan_inp.value.strip(),
                                mover_base=org_mover_inp.value.strip(),
                                renamer_panel_width=org_renamer_pw,
                                mover_panel_width=org_mover_pw,
                                cleanup_delete_other_files=bool(cleanup_other_chk.value),
                                cleanup_delete_small_videos=bool(cleanup_small_chk.value),
                                cleanup_small_video_mb=float(cleanup_small_mb_inp.value or 30),
                            )

                        trk_lp = trk_left_w_ref[0]
                        set_tracker_left_panel_width(trk_lp)
                        ui.run_javascript(
                            "var t=document.querySelector('.trk-left-panel');"
                            f"if(t){{t.style.width='{trk_lp}px';t.style.minWidth='{trk_lp}px';}}"
                        )
                        if on_save_tracker:
                            on_save_tracker(
                                cover_w=trk_width_ref[0],
                                left_panel_w=trk_lp,
                                auto_inactive_enabled=bool(tracker_auto_inactive_chk.value),
                                inactive_months=max(1, int(tracker_inactive_months_inp.value or 6)),
                            )
                except Exception as exc:
                    ui.notify(f"Settings save failed: {exc}", color="negative")
                    return

                dlg.close()
                ui.notify("Settings saved", color="positive")

        with ui.row().classes("w-full justify-end gap-2 px-5 py-3 border-t border-[#1a1a24]"):
            ui.button("Save Settings", icon="save", on_click=_save).classes("cfg-save-btn").props("unelevated")

    return dlg


class _NullSaveState:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False