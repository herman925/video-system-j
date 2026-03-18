"""
JAV Downloader — NiceGUI local web app.
Usage:  python main.py   →   http://localhost:8765

Supports single or multi-video input (comma / newline separated).
Each video gets its own collapsible card with parallel search.
"""

import os
import sys
from pathlib import Path

# On Windows, uvicorn forces SelectorEventLoop when reload=True (subprocess worker mode),
# which breaks nodriver's Chrome subprocess spawning.  Override to always use ProactorEventLoop.
if sys.platform == "win32":
    import asyncio
    import uvicorn.loops.asyncio as _uvicorn_loop
    _uvicorn_loop.asyncio_loop_factory = lambda use_subprocess=False: asyncio.ProactorEventLoop

from nicegui import Client, app, ui
from nicegui.storage import Storage as _NiceGUIStorage

from utils.paths import NICEGUI_STORAGE_DIR

# MUST be set on the Storage CLASS (not the instance) before any @ui.page
# decorator — NiceGUI's _create_persistent_dict reads Storage.path directly.
# Setting app.storage.path only creates a shadowed instance attribute that
# _create_persistent_dict never sees.
NICEGUI_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
_NiceGUIStorage.path = NICEGUI_STORAGE_DIR

import datetime as _dt
import traceback as _tb


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


_WS_LOG_ENABLED = _env_flag('JAV_WS_LOG', default=False)
_WS_DISCONNECT_STACK_ENABLED = _env_flag('JAV_WS_DISCONNECT_STACK', default=False)


def _launchpad_debug_script() -> str:
    return r'''
        <script>
        (() => {
            const prefix = '[JAV-DL launchpad]';

            function logIconDiagnostics(stage) {
                const iconNodes = Array.from(document.querySelectorAll('.material-icons'));
                const fontEntries = performance.getEntriesByType('resource')
                    .map(entry => entry.name)
                    .filter(name => /fonts\.css|\/fonts\//.test(name));

                const ligatureProbe = document.createElement('span');
                ligatureProbe.className = 'material-icons';
                ligatureProbe.textContent = 'movie';
                ligatureProbe.style.cssText = 'position:absolute;left:-9999px;top:-9999px;font-size:24px;visibility:hidden;';

                const plainProbe = document.createElement('span');
                plainProbe.textContent = 'movie';
                plainProbe.style.cssText = 'position:absolute;left:-9999px;top:-9999px;font-size:24px;font-family:Arial,sans-serif;visibility:hidden;';

                document.body.appendChild(ligatureProbe);
                document.body.appendChild(plainProbe);

                const ligatureWidth = ligatureProbe.getBoundingClientRect().width;
                const plainWidth = plainProbe.getBoundingClientRect().width;
                const ligatureLikelyApplied = ligatureWidth < plainWidth * 0.75;

                ligatureProbe.remove();
                plainProbe.remove();

                const iconSamples = iconNodes.slice(0, 6).map((node, index) => {
                    const style = getComputedStyle(node);
                    return {
                        index,
                        text: node.textContent,
                        className: node.className,
                        fontFamily: style.fontFamily,
                        fontFeatureSettings: style.fontFeatureSettings,
                        webkitFontFeatureSettings: style.getPropertyValue('-webkit-font-feature-settings'),
                        fontVariantLigatures: style.fontVariantLigatures,
                        display: style.display,
                        width: Math.round(node.getBoundingClientRect().width * 100) / 100,
                        height: Math.round(node.getBoundingClientRect().height * 100) / 100,
                    };
                });

                const fontStatus = document.fonts
                    ? Array.from(document.fonts)
                            .filter(font => /Material Icons|Roboto/.test(font.family))
                            .map(font => ({ family: font.family, status: font.status }))
                    : 'document.fonts unavailable';

                console.group(`${prefix} diagnostics (${stage})`);
                console.log('userAgent:', navigator.userAgent);
                console.log('material icon count:', iconNodes.length);
                console.log('font resources:', fontEntries);
                console.log('font status:', fontStatus);
                console.log('ligature probe:', {
                    ligatureWidth,
                    plainWidth,
                    ligatureLikelyApplied,
                });
                console.table(iconSamples);
                if (!ligatureLikelyApplied) {
                    console.warn(`${prefix} Material icon ligatures do not appear to be applying on this page.`);
                }
                console.groupEnd();
            }

            const run = (stage) => {
                try {
                    logIconDiagnostics(stage);
                } catch (error) {
                    console.error(`${prefix} diagnostic failure`, error);
                }
            };

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => run('domcontentloaded'), { once: true });
            } else {
                run('immediate');
            }

            if (document.fonts?.ready) {
                document.fonts.ready.then(() => run('fonts-ready'));
            }
        })();
        </script>
        '''

@app.on_connect
def _log_connect(client) -> None:
    if not _WS_LOG_ENABLED:
        return
    print(f"[WS] +connect  client={getattr(client,'id','?')} at {_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}", flush=True)

@app.on_disconnect
def _log_disconnect(client) -> None:
    if not (_WS_LOG_ENABLED or _WS_DISCONNECT_STACK_ENABLED):
        return
    if _WS_LOG_ENABLED:
        print(f"[WS] -DISCONNECT client={getattr(client,'id','?')} at {_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}", flush=True)
    if _WS_DISCONNECT_STACK_ENABLED:
        _tb.print_stack(limit=12)

import organiser.page   # noqa: F401 — registers /organiser route
import tracker.page     # noqa: F401 — registers /tracker route
import tracker.effects_lab  # noqa: F401 — registers /tracker-effects-lab route
import downloader.page  # noqa: F401 — registers /downloader route
import api.routes       # noqa: F401 — registers /api/* endpoints


# ── Launchpad ─────────────────────────────────────────────────────────────────


@ui.page("/")
async def launchpad(client: Client) -> None:
    """Home screen — shows all available modules."""
    ui.add_head_html('<meta charset="utf-8">')
    ui.add_head_html(f"<style>{Path('assets/theme.css').read_text(encoding='utf-8')}</style>")
    # Remove Quasar/NiceGUI default content padding so lp-root fills the viewport
    ui.add_head_html('<style>.nicegui-content { padding: 0 !important; }</style>')
    ui.add_head_html(_launchpad_debug_script())


    with ui.element("div").classes("lp-root"):
        ui.html('<div class="lp-wordmark">JAV Video System</div>')
        ui.html('<div class="lp-tagline">SELECT A MODULE TO GET STARTED</div>')

        with ui.element("div").classes("lp-grid"):
            # ── JAV Downloader ──────────────────────────────────────────────
            with ui.element("div").classes("lp-card lp-card-dl").on(
                "click", lambda: ui.navigate.to("/downloader")
            ):
                ui.html(
                    '<div class="lp-icon lp-icon-dl">'
                    '<span class="material-icons" style="font-size:1.5rem">movie</span>'
                    '</div>'
                )
                ui.html('<div class="lp-card-title">JAV Video System</div>')
                ui.html(
                    '<div class="lp-card-desc">'
                    "Search metadata from JAVDB or JAVLibrary, fetch torrents from "
                    "Sukebei Nyaa, translate titles, and send directly to qBittorrent."
                    "</div>"
                )
                ui.html(
                    '<div class="lp-card-arrow">'
                    'OPEN&nbsp;<span class="material-icons" style="font-size:0.9rem">arrow_forward</span>'
                    '</div>'
                )

            # ── Video Organiser ─────────────────────────────────────────────
            with ui.element("div").classes("lp-card lp-card-org").on(
                "click", lambda: ui.navigate.to("/organiser")
            ):
                ui.html(
                    '<div class="lp-icon lp-icon-org">'
                    '<span class="material-icons" style="font-size:1.5rem">folder_special</span>'
                    '</div>'
                )
                ui.html('<div class="lp-card-title">Video Organiser</div>')
                ui.html(
                    '<div class="lp-card-desc">'
                    "Rename video files and folders, move content between directories, "
                    "generate thumbnails with VTM, and edit clips with LosslessCut."
                    "</div>"
                )
                ui.html(
                    '<div class="lp-card-arrow">'
                    'OPEN&nbsp;<span class="material-icons" style="font-size:0.9rem">arrow_forward</span>'
                    '</div>'
                )

            # ── Actress Tracker ─────────────────────────────────────────────
            with ui.element("div").classes("lp-card lp-card-trk").on(
                "click", lambda: ui.navigate.to("/tracker")
            ):
                ui.html(
                    '<div class="lp-icon lp-icon-trk">'
                    '<span class="material-icons" style="font-size:1.5rem">star</span>'
                    '</div>'
                )
                ui.html('<div class="lp-card-title">Actress Tracker</div>')
                ui.html(
                    '<div class="lp-card-desc">'
                    "Track favourite actresses, monitor for new releases, scrape "
                    "filmographies from JAVLibrary, and queue new titles automatically."
                    "</div>"
                )
                ui.html(
                    '<div class="lp-card-arrow">'
                    'OPEN&nbsp;<span class="material-icons" style="font-size:0.9rem">arrow_forward</span>'
                    '</div>'
                )

        ui.html('<div class="lp-footer">localhost:8765</div>')

app.add_static_files('/assets', 'assets')

ui.run(
    title="JAV Video System",
    port=8765,
    favicon="🎬",
    dark=True,
    reload=_env_flag('JAV_DEV_RELOAD', default=False),
    storage_secret="jav-dl-secret-key-2025",
)
