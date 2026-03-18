"""
Actress Tracker page — /tracker

Imported by main.py to register the route.
Two-panel layout: left = actress list, right = video inspector.
"""

import asyncio
import traceback as _tb
from datetime import date as _date_cls, datetime, timezone
from typing import List, Optional

import httpx
from nicegui import Client, app, ui
from pathlib import Path

from downloader.components.settings import (
    build_settings_dialog as _build_settings_dialog,
)
from utils.downloader_store import (
    append_downloader_queue_stub,
    load_downloader_queue,
    upsert_downloader_cache_entry,
)
from utils.tracker_ui_store import (
    get_tracker_left_panel_width,
    get_tracker_sort_cache,
    get_tracker_video_page_size,
    set_tracker_left_panel_width,
    set_tracker_sort_cache,
    set_tracker_video_page_size,
)
from translator.llm import load_config
from utils.ui_ratings import (
    get_rating_tier as _get_rating_tier,
    get_rating_tooltips as _get_rating_tooltips,
    get_score_info as _score_info,
)
from utils.covers import cover_exists, delete_cover, keep_latest_cover, get_cover_source
from utils.metadata import fetch_jav_metadata, resolve_metadata_source
from utils.ui_cover_preview import open_image_preview
import tracker.fetch_queue as _cover_queue
from translator.llm import load_config, save_config
from utils.sort_key import romaji_key as _romaji_key, log_sorted_order as _log_sorted_order
from scraper.javlibrary import (
    fetch_actress_total_pages,
    get_rate_limit_cooldown_seconds,
    scrape_actress_page,
    scrape_actress_page_range,
)
from tracker.state import clear_pagination, get_pagination, set_pagination
from utils.paths import CONFIG_FILE, TRACKER_FILE, TRACKER_UI_STATE_FILE
from utils.save_state import build_save_state_badge
from tracker.store import (
    actress_id_from_url,
    add_actress,
    delete_actress,
    delete_video_from_actress,
    get_all_deleted_refs,
    get_deleted_refs_for_actress,
    is_ref_downloaded_globally,
    load_tracker,
    mark_all_seen,
    mark_ref_downloaded_globally,
    mark_seen,
    migrate_ratings_to_score,
    record_deleted_ref,
    remove_from_deleted_refs,
    rename_actress,
    recalculate_all_inactive_statuses,
    save_pagination_state,
    save_tracker,
    save_video_meta,
    sort_fingerprint,
    update_actress_rating,
    update_actress_videos,
)
from utils.ref_cleanup import prune_orphaned_refs, get_downloader_refs

_DEFAULT_LEFT_W = 300
_TRACKER_PAGE_SIZE_OPTIONS = (10, 20, 30, 40, 50, 100)

# ref → unix timestamp of last cover force-refresh (deep-fetch).
# Used to append ?_t= to img src so the browser doesn't serve the old
# cached image after a cover overwrite.  All other refs use the plain URL.
_cover_busted: dict[str, int] = {}

# page navigation (shared across all NiceGUI client connections).
_SCRAPING_IDS: set[str] = set()


# ── Relative time helper ───────────────────────────────────────────────────────


def _fmt_relative(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((now - dt).total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ""


# ── Page ──────────────────────────────────────────────────────────────────────


@ui.page("/tracker")
async def tracker_page(client: Client) -> None:  # noqa: C901 (complex but self-contained)
    # ── Mutable state refs ────────────────────────────────────────────────────
    panel_w_ref: List[int] = [get_tracker_left_panel_width(_DEFAULT_LEFT_W)]
    _stored_page_size = get_tracker_video_page_size(20)
    if _stored_page_size not in _TRACKER_PAGE_SIZE_OPTIONS:
        _stored_page_size = 20
    page_size_ref: List[int] = [_stored_page_size]
    current_page_ref: List[int] = [1]

    # Load settings once per page load to avoid spamming disk reads
    _user_cfg_cache: dict = load_config().get("aura_config", {})
    selected_id_ref: List[Optional[str]] = [None]
    selected_video_ref: List[Optional[str]] = [None]  # currently highlighted video ref
    pending_video_page_ref: List[Optional[str]] = [None]
    filter_ref: List[str] = ["all"]
    search_ref: List[str] = [""]  # left panel search text
    sort_ref: List[str] = ["az"]  # az | za | unseen | rating | scraped
    search_mode_ref: List[str] = ["actress"]  # "actress" | "ref"
    search_inp_ref: list = []  # [0] = search input element
    sort_row_ref: list = []  # [0] = sort chips row element
    actress_row_els: dict = {}  # actress_id -> row element
    video_row_els: dict[str, dict[str, object]] = {}  # ref -> row handle bundle

    # ── CSS ───────────────────────────────────────────────────────────────────
    _cfg = load_config()
    _cover_w = int(_cfg.get("tracker_cover_w", 80))
    _cover_h = int(_cover_w * 0.65)

    # Inject CSS variables driven by config (separate from the static block below)
    ui.add_head_html(
        f"<style>:root {{ --trk-cover-w: {_cover_w}px; --trk-cover-h: {_cover_h}px; }}</style>"
    )

    ui.add_head_html('<meta charset="utf-8">')
    ui.add_head_html(
        f"<style>{Path('assets/theme.css').read_text(encoding='utf-8')}</style>"
    )

    # Override Quasar brand colors for the tracker theme
    ui.colors(primary="#d97706", secondary="#f59e0b", accent="#b45309")

    # ── Helpers ───────────────────────────────────────────────────────────────

    # ── Score colour + effects system ─────────────────────────────────────────
    # Smooth RGB colour stops for the unranked 0-39 range only.
    _SCORE_STOPS = [
        (0, (80, 80, 92)),  # muted slate-grey
        (12, (160, 20, 20)),  # dark red
        (25, (210, 45, 10)),  # red-orange
        (39, (195, 100, 6)),  # burnt amber
    ]

    def _lerp_rgb(s: int):
        stops = _SCORE_STOPS
        for i in range(len(stops) - 1):
            s0, c0 = stops[i]
            s1, c1 = stops[i + 1]
            if s0 <= s <= s1:
                t = (s - s0) / (s1 - s0)
                return tuple(int(c0[k] + t * (c1[k] - c0[k])) for k in range(3))
        return stops[-1][1]

    _B = (  # shared base badge — stretches full row height, icon + number side by side
        "display:flex;flex-direction:row;align-items:center;justify-content:center;"
        "font-size:10px;font-weight:700;border-radius:5px;width:100%;"
        "letter-spacing:0.03em;box-sizing:border-box;padding:0 3px;gap:3px;"
    )
    _SCORE_TOOLTIP = (
        "Rate her by how consistently and reliably she gets you off — across five dimensions.\n\n"
        "FACE — Is her face your type? Does she look good in close-up shots? Do her expressions during sex — mouth open, eyes glazed, biting her lip — add to the experience or kill it? Does her face during a blowjob or while taking it from behind actually make you harder?\n\n"
        "BODY — Tits, ass, legs, waist, skin tone, curves or lack of. Does her body make you want to pause and look? Do her tits move right, does her ass look good getting slapped, does her figure in a specific outfit or position make you throb? Physical type match.\n\n"
        "THE ACT — How does she actually perform during sex? Is she active — grinding, bouncing, pushing back — or does she just lie there? Does she moan authentically or robotically? Does she make the noises that push you over the edge? Cowgirl energy, the way she deepthroats, how she reacts to getting pounded — all counts.\n\n"
        "THEMES — Does she work in the genres and fetishes you're into? Nakadashi, gangbang, cosplay, NTR, POV, lesbian, BDSM, or whatever gets you going. A girl can have a perfect body but if she only does vanilla missionary it may not do it for you. Theme alignment matters.\n\n"
        "NUT CONSISTENCY — When you sit down to jerk to her, how often do you actually finish? Every single time without fail? More than half the time? Only if the scene is set up exactly right? She's carried by a co-star or scenario? Almost never?\n\n"
        "💎 Diamond (96-100) = guaranteed orgasm every time, seek out her releases immediately.\n"
        "♦ Ruby (90-95) = 90%+ nut rate, instant queue, you edge on purpose.\n"
        "✦ Sapphire (86-89) = 80%+ rate, reliable shortlist, one of your regulars.\n"
        "✦ Amethyst (81-85) = 70%+ when theme aligns, fetish-specific goldmine.\n"
        "◆ Emerald (76-80) = 60-70% rate, good when scene setup cooperates.\n"
        "🥇 Gold (71-75) = 50-60% rate, conditional fap, need the right tags.\n"
        "◈ Topaz (66-70) = 40-50% rate, only works in very specific scenarios.\n"
        "🥈 Silver (61-65) = 30-40% rate, mostly carried by co-star or setup.\n"
        "◇ Aquamarine (56-60) = 20-30% rate, rare hit, mostly a pass.\n"
        "◈ Jade (50-55) = 10-20% rate, neutral to mild turn-off.\n"
        "🥉 Garnet (40-49) = under 10%, actively unappealing.\n"
        "◼ Onyx (30-39) = hard pass, kills the mood.\n"
        "Unrated = haven't watched enough of her to form an opinion."
    )

    def _score_html(rating: "Optional[int]") -> str:
        """Return just the badge HTML for a score (convenience wrapper)."""
        if rating is None:
            return ""
        return _score_info(int(rating))[2]

    # === ANIME CONFIGURATION ===
    # Tweak these variables to control GPU usage and visual intensity
    AURA_CONFIG = {
        "enabled": True,  # Master switch for anime effects
        "emission_scale": 2.0,  # Size multiplier for outward blasts
        "use_blur_filters": False,  # GPU heavy. Keep False for crisp vector style, True for soft glow
        "particles": True,  # Floating upward energy dots (DBZ style)
        "vertical_beams": True,  # Upward rising surging energy columns
        "god_light": True,  # Outward rotating celestial rays
    }

    def _svg_score_badge(score: "Optional[int]", size=48) -> str:
        """Returns complex SVG string for right panel profile picture style."""
        s = score
        if s is None:
            return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:pointer;opacity:0.9;transition:all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0" onmouseover="this.style.transform='scale(1.1) rotate(2deg)'" onmouseout="this.style.transform='scale(1) rotate(0)'"><title>Unrated — Haven\'t watched enough of her content to form a real opinion. Get some scenes in before rating.</title><circle cx="24" cy="24" r="22" fill="#1f2937" stroke="#374151" stroke-width="1"/><text x="24" y="24" fill="#9ca3af" font-size="10" font-family="sans-serif" font-weight="600" text-anchor="middle" dominant-baseline="central">N/A</text></svg>'''

        s = max(0, min(100, int(s)))
        _rating_cfg = load_config()
        _tier = _get_rating_tier(s, _rating_cfg)
        _tooltips = _get_rating_tooltips(_rating_cfg)

        cfg = AURA_CONFIG.copy()
        if isinstance(_user_cfg_cache, dict):
            cfg.update(_user_cfg_cache)

        scale = cfg["emission_scale"]

        glow_opacity = "0.7"
        aura_xml = ""
        tt = "Unrated"

        def _beams(col):
            if not cfg["vertical_beams"]:
                return ""
            return f'''
            <g opacity="0.6">
                <!-- CSS classes bypass Vue removing inline <animate> tags -->
                <rect x="8" width="4" height="40" fill="{col}" class="anime-beam-1" />
                <rect x="18" width="8" height="60" fill="{col}" class="anime-beam-2" />
                <rect x="30" width="3" height="30" fill="{col}" class="anime-beam-3" />
                <rect x="38" width="6" height="50" fill="{col}" class="anime-beam-4" />
            </g>
            '''

        def _particles(col):
            if not cfg["particles"]:
                return ""
            return f'''
            <g fill="{col}">
                <circle cx="12" r="1.5" class="anime-particle-1" />
                <circle cx="24" r="2" class="anime-particle-2" />
                <circle cx="36" r="1" class="anime-particle-3" />
            </g>
            '''

        def _god_rays(col):
            if not cfg["god_light"]:
                return ""
            return f'''
            <g opacity="0.4" fill="{col}" class="anime-spin-fw">
                <polygon points="24,24 -20,-10 0,-30" />
                <polygon points="24,24 68,-10 48,-30" />
                <polygon points="24,24 68,58 48,78" />
                <polygon points="24,24 -20,58 0,78" />
            </g>
            '''

        def make_spiky_burst(color, outer, inner, points=12):
            import math

            pts = []
            for i in range(points * 2):
                angle = i * math.pi / points
                r = (outer * scale) if i % 2 == 0 else (inner * scale)
                pts.append(f"{24 + math.cos(angle) * r},{24 + math.sin(angle) * r}")
            return " ".join(pts)

        if _tier == "diamond":
            c1, c2, border, text_col = "#1e1b4b", "#06b6d4", "#a5f3fc", "#ffffff"
            shape = "diamond"
            glow = "#3b82f6"
            tt = _tooltips["diamond"]
            aura_class = (
                ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ""
            )

            aura_xml = (
                f'''
                {_god_rays("#a5f3fc")}
                {_beams("#3b82f6")}
                {_particles("#67e8f9")}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst("#60a5fa", 28, 14, 20)}" fill="#60a5fa" class="anime-burst-1" />
                    <polygon points="{make_spiky_burst("#a5f3fc", 22, 12, 12)}" fill="#a5f3fc" class="anime-burst-2" />
                </g>
                <circle cx="24" cy="24" r="24" fill="none" stroke="#fff" stroke-width="2.5" class="anime-ripple" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "ruby":
            c1, c2, border, text_col = "#4c0519", "#e11d48", "#fb7185", "#fff0f3"
            shape = "gem"
            glow = "#be123c"
            tt = _tooltips["ruby"]
            aura_class = (
                ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ""
            )

            aura_xml = (
                f'''
                {_beams("#e11d48")}
                {_particles("#fda4af")}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst("#e11d48", 26, 12, 16)}" fill="#e11d48" class="anime-burst-3" />
                </g>
                <circle cx="24" cy="24" r="24" fill="none" stroke="{border}" stroke-width="1.5" class="anime-ripple-slow" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "sapphire":
            c1, c2, border, text_col = "#172554", "#3b82f6", "#60a5fa", "#eff6ff"
            shape = "gem"
            glow = "#2563eb"
            tt = _tooltips["sapphire"]
            aura_class = (
                ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ""
            )
            aura_xml = (
                f'''
                {_particles("#93c5fd")}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst("#2563eb", 24, 14, 14)}" fill="#2563eb" class="anime-burst-4" />
                </g>
                <circle cx="24" cy="24" r="28" fill="none" stroke="{border}" stroke-width="2" stroke-dasharray="12,6" class="anime-spin-fw-med" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "amethyst":
            c1, c2, border, text_col = "#2e1065", "#7e22ce", "#c084fc", "#faf5ff"
            shape = "hex"
            glow = "#9333ea"
            tt = _tooltips["amethyst"]
            aura_xml = (
                f'''
                {_god_rays("#a855f7")}
                <polygon points="{make_spiky_burst("#9333ea", 25, 14, 12)}" fill="#9333ea" class="anime-burst-5" />
                <polygon points="24,-12 60,8 60,40 24,60 -12,40 -12,8" fill="none" stroke="{border}" stroke-width="1.5" opacity="0.5" class="anime-spin-bw-med" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "emerald":
            c1, c2, border, text_col = "#022c22", "#10b981", "#34d399", "#ecfdf5"
            shape = "hex"
            glow = "#059669"
            tt = _tooltips["emerald"]
            aura_xml = (
                f'''
                 {_particles("#6ee7b7")}
                 <circle cx="24" cy="24" r="28" fill="none" stroke="{border}" stroke-width="2" stroke-dasharray="10,12" class="anime-spin-bw-med" />
                 <circle cx="24" cy="24" r="24" fill="none" stroke="{glow}" stroke-width="1.5" class="anime-ripple-med" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "gold":
            c1, c2, border, text_col = "#78350f", "#f59e0b", "#fde68a", "#ffffff"
            shape = "medal"
            glow = "#d97706"
            tt = _tooltips["gold"]
            aura_xml = (
                f'''
                {_beams("#fef3c7")}
                <polygon points="{make_spiky_burst("#f59e0b", 21, 14, 10)}" fill="#fde68a" class="anime-burst-6" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "topaz":
            c1, c2, border, text_col = "#451a03", "#d97706", "#fef3c7", "#ffffff"
            shape = "medal"
            glow = "#b45309"
            tt = _tooltips["topaz"]
            aura_xml = (
                f'''
                <rect x="0" y="0" width="48" height="48" fill="none" stroke="{glow}" stroke-width="1.5" opacity="0.5" class="anime-spin-fw-slow" />
                <rect x="4" y="4" width="40" height="40" fill="none" stroke="{border}" stroke-width="1" opacity="0.4" class="anime-spin-bw-slow" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "silver":
            c1, c2, border, text_col = "#334155", "#94a3b8", "#f1f5f9", "#ffffff"
            shape = "medal"
            glow = "#64748b"
            tt = _tooltips["silver"]
            aura_xml = (
                f'''
                <polygon points="{make_spiky_burst("#cbd5e1", 24, 14, 4)}" fill="#e2e8f0" opacity="0.3" class="anime-spin-fw-slow" />
                <polygon points="{make_spiky_burst("#94a3b8", 24, 14, 4)}" fill="none" stroke="#f1f5f9" stroke-width="1.5" opacity="0.5" transform="rotate(45 24 24)" class="anime-spin-bw-slow" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "aquamarine":
            c1, c2, border, text_col = "#083344", "#06b6d4", "#cffafe", "#ffffff"
            shape = "shield"
            glow = "#0e7490"
            tt = _tooltips["aquamarine"]
            aura_xml = (
                f'''
                <circle cx="24" cy="24" r="22" fill="none" stroke="{border}" stroke-width="1" class="anime-ripple-aqua" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "jade":
            c1, c2, border, text_col = "#1a2416", "#4a7c40", "#dcfce7", "#ffffff"
            shape = "shield"
            glow = "#166534"
            tt = _tooltips["jade"]
            aura_xml = (
                f'''
                <circle cx="24" cy="24" r="26" fill="none" stroke="{glow}" stroke-width="1.5" stroke-dasharray="8,16" class="anime-spin-fw-med" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "garnet":
            c1, c2, border, text_col = "#3b0000", "#b91c1c", "#fee2e2", "#ffffff"
            shape = "shield"
            glow = "#991b1b"
            tt = _tooltips["garnet"]
            p_c = "#f87171"
            aura_xml = (
                f'''
                {_particles(p_c)}
                <polygon points="{make_spiky_burst("#b91c1c", 16, 12, 6)}" fill="#f87171" class="anime-burst-7" />
            '''
                if cfg["enabled"]
                else ""
            )

        elif _tier == "onyx":
            t = (s - 40) / 9.0
            r2, g2, b2 = (180 + int(t * 30), 100 + int(t * 20), 10 + int(t * 20))
            hex_c = f"#{r2:02x}{g2:02x}{b2:02x}"
            c1, c2, border, text_col = "#09090b", "#27272a", hex_c, "#ffffff"
            shape = "shield"
            glow = "#27272a"
            tt = _tooltips["onyx"]
        else:
            rt, gt, bt = _lerp_rgb(s)
            c1, c2, border, text_col, shape, glow, glow_opacity = (
                f"rgba({rt // 6},{gt // 6},{bt // 6},1)",
                f"rgba({rt // 2},{gt // 2},{bt // 2},1)",
                f"rgba({rt},{gt},{bt},0.8)",
                f"rgba({rt},{gt},{bt},1)",
                "pill",
                f"rgba({rt},{gt},{bt},1)",
                "0.3",
            )
            tt = _tooltips["low"]

        rId = f"grad_sq_{s}"
        layers = ""
        txt_y = "25"
        font_size = "15"

        # Dropshadow config
        shadow_xml = (
            f'<feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="{glow}" flood-opacity="{glow_opacity}"/><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#000000" flood-opacity="0.8"/>'
            if cfg["use_blur_filters"]
            else f'<feDropShadow dx="0" dy="4" stdDeviation="2" flood-color="#000000" flood-opacity="0.8"/>'
        )

        if shape == "diamond":
            d_path = "M 24,0 L 48,22 L 24,52 L 0,22 Z"
            txt_y = "24"
            font_size = "16"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 24,4 L 43,22 L 24,48 L 5,22 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.6" /><path d="M 24,2 L 34,22 L 24,50 L 14,22 Z" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.5" /><polygon points="24,2 14,22 24,4" fill="#ffffff" opacity="0.5" /><polygon points="24,2 2,22 14,22" fill="#ffffff" opacity="0.2" /><polygon points="24,22 34,22 24,50" fill="#000000" opacity="0.3" />'
        elif shape == "gem":
            d_path = "M 12,2 L 36,2 L 50,16 L 50,32 L 36,48 L 12,48 L -2,32 L -2,16 Z"
            txt_y = "25"
            font_size = "15"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 14,4 L 34,4 L 47,17 L 47,31 L 34,46 L 14,46 L 1,31 L 1,17 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.5" /><polygon points="12,2 36,2 24,18" fill="#ffffff" opacity="0.4" /><polygon points="-2,16 12,2 24,18 10,24" fill="#ffffff" opacity="0.2" /><polygon points="24,18 50,32 36,48" fill="#000000" opacity="0.25" /><path d="M 24,18 L 50,16 M 24,18 L 50,32 M 24,18 L 36,48 M 24,18 L 12,48 M 24,18 L -2,32 M 24,18 L -2,16 M 24,18 L 12,2 M 24,18 L 36,2" stroke="#ffffff" stroke-width="1" opacity="0.4"/>'
        elif shape == "hex":
            d_path = "M 24,2 L 46,14 L 46,36 L 24,48 L 2,36 L 2,14 Z"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 24,6 L 42,16 L 42,34 L 24,44 L 6,34 L 6,16 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" /><polygon points="24,2 46,14 24,24" fill="#ffffff" opacity="0.2" /><polygon points="2,14 24,2 24,24" fill="#ffffff" opacity="0.3" />'
        elif shape == "medal":
            layers = f'<circle cx="24" cy="24" r="22" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><circle cx="24" cy="24" r="18" fill="none" stroke="{border}" stroke-width="2" opacity="0.8" stroke-dasharray="2,2" /><circle cx="24" cy="24" r="14" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" /><circle cx="24" cy="24" r="22" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.4" /><path d="M 6,10 Q 24,-2 42,10" fill="none" stroke="#ffffff" stroke-width="5" opacity="0.2" filter="blur(1px)"/><path d="M 12,38 Q 24,46 36,38" fill="none" stroke="#000000" stroke-width="4" opacity="0.3" filter="blur(1px)"/>'
        elif shape == "shield":
            d_path = "M 4,4 L 44,4 L 44,22 C 44,36 24,46 24,46 C 24,46 4,36 4,22 Z"
            txt_y = "24"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 8,7 L 40,7 L 40,21 C 40,32 24,41 24,41 C 24,41 8,32 8,21 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" /><path d="M 4,4 L 24,18 L 44,4" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4"/><rect x="10" y="6" width="28" height="6" fill="#ffffff" opacity="0.2" rx="2"/><path d="M 16,0 L 20,24 L 42,14 L 24,46" fill="#ffffff" opacity="0.1" />'
        else:
            layers = f'<path d="M 8,4 L 40,4 A 6,6 0 0 1 46,10 L 46,38 A 6,6 0 0 1 40,44 L 8,44 A 6,6 0 0 1 2,38 L 2,10 A 6,6 0 0 1 8,4 Z" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 10,6.5 L 38,6.5 A 3.5,3.5 0 0 1 43.5,10 L 43.5,38 A 3.5,3.5 0 0 1 38,41.5 L 10,41.5 A 3.5,3.5 0 0 1 4.5,38 L 4.5,10 A 3.5,3.5 0 0 1 10,6.5 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.3" /><rect x="4" y="4" width="40" height="20" fill="#ffffff" opacity="0.1" rx="4"/><path d="M 6,12 L 42,12" stroke="#ffffff" stroke-width="1" opacity="0.3"/>'

        return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:help;transform-origin:center;transition:transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0;overflow:visible;z-index:99;" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform='scale(1)'">
    <title>{tt}</title>
    <defs>
        <linearGradient id="{rId}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="{c1}" /><stop offset="40%" stop-color="{c1}" /><stop offset="100%" stop-color="{c2}" /></linearGradient>
        <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">{shadow_xml}</filter>
        <filter id="glow-filter" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="blur" /><feComposite in="SourceGraphic" in2="blur" operator="over" /></filter>
        <filter id="text-glow"><feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000000" flood-opacity="0.8"/></filter>
    </defs>
    {aura_xml}
    {layers}
    <!-- Top-left rim highlight for gloss -->
    <path d="M 12,6 A 16,16 0 0 1 20,4" fill="none" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" opacity="0.8" style="mix-blend-mode: overlay;"/>
    <text x="24" y="{txt_y}" fill="{text_col}" font-size="{font_size}" font-family="system-ui, -apple-system, sans-serif" font-weight="900" text-anchor="middle" dominant-baseline="central" alignment-baseline="middle" filter="url(#text-glow)" letter-spacing="0.5">{s}</text>
</svg>'''

    def _rebuild_left_list() -> None:
        trk_list_wrap.clear()
        data = load_tracker()
        actresses = data.get("actresses", {})
        if not actresses:
            with trk_list_wrap:
                with ui.element("div").classes("trk-empty").style("padding:40px 16px"):
                    ui.icon("person_search").style("font-size:2rem;opacity:.25")
                    ui.label("No actresses tracked yet").style(
                        "font-size:0.8rem;color:#374151;text-align:center"
                    )
            return

        q = search_ref[0].strip().lower()
        mode = search_mode_ref[0]

        # ── Video ref search mode ─────────────────────────────────────────────
        if mode == "ref" and q:
            results = []
            for aid, actress in actresses.items():
                matched = [
                    v["ref"] for v in actress.get("videos", []) if q in v["ref"].lower()
                ]
                if matched:
                    results.append((aid, actress, matched))
            if not results:
                with trk_list_wrap:
                    with (
                        ui.element("div")
                        .classes("trk-empty")
                        .style("padding:40px 16px")
                    ):
                        ui.icon("search_off").style("font-size:2rem;opacity:.25")
                        ui.label("No matching refs found").style(
                            "font-size:0.8rem;color:#374151;text-align:center"
                        )
                return
            for aid, actress, matched_refs in results:
                _build_actress_ref_match_row(aid, actress, matched_refs)
            return

        # ── Actress name search mode ──────────────────────────────────────────
        items = [
            (aid, a)
            for aid, a in actresses.items()
            if not q or q in (a.get("name") or aid).lower()
        ]

        # Apply sort
        sort_key = sort_ref[0]
        if sort_key in ("az", "za"):
            # Persist A-Z order in tracker UI state.
            # Cache is keyed by a fingerprint of all (id, name) pairs —
            # invalidated automatically when any actress is added/removed/renamed.
            fp = sort_fingerprint(actresses)
            cached = get_tracker_sort_cache()
            if not q and cached.get("fingerprint") == fp:
                # Cache hit — reorder by saved A-Z position, no pykakasi needed.
                order_map = {aid: i for i, aid in enumerate(cached["az_order"])}
                items.sort(key=lambda x: order_map.get(x[0], len(order_map)))
            else:
                # Cache miss — sort normally, then persist the order.
                items.sort(key=lambda x: _romaji_key(x[1].get("name") or x[0]))
                if not q:
                    set_tracker_sort_cache(fp, [x[0] for x in items])
            if sort_key == "za":
                items.reverse()
            _log_sorted_order("A→Z" if sort_key == "az" else "Z→A", items, lambda x: x[1].get("name") or x[0])
        elif sort_key == "unseen":
            items.sort(
                key=lambda x: sum(
                    1 for v in x[1].get("videos", []) if not v.get("seen")
                ),
                reverse=True,
            )
        elif sort_key == "rating":
            items.sort(key=lambda x: x[1].get("rating") or 0.0, reverse=True)
        elif sort_key == "scraped":
            items.sort(key=lambda x: x[1].get("last_scraped") or "", reverse=True)

        if not items:
            with trk_list_wrap:
                with ui.element("div").classes("trk-empty").style("padding:40px 16px"):
                    ui.icon("search_off").style("font-size:2rem;opacity:.25")
                    ui.label("No results").style(
                        "font-size:0.8rem;color:#374151;text-align:center"
                    )
            return

        for actress_id, actress in items:
            _build_actress_row(actress_id, actress)

    def _populate_actress_row_content(row_el, actress_id: str, actress: dict) -> None:
        """Fill the inner content of an actress list row.
        Clears existing children and rebuilds them in-place.
        Also syncs the active-row CSS class on the outer element.
        """
        _dl_items = load_downloader_queue()
        _queued_refs = {item["kw"].upper() for item in _dl_items}
        _session_dl_refs = {
            item["kw"].upper() for item in _dl_items if item.get("downloaded")
        }

        all_videos = actress.get("videos", [])
        unseen = sum(
            1
            for v in all_videos
            if not v.get("seen") and v["ref"].upper() not in _queued_refs
        )
        in_queue_count = sum(
            1
            for v in all_videos
            if v["ref"].upper() in _queued_refs
            and not (v.get("downloaded") or v["ref"].upper() in _session_dl_refs)
        )
        is_active = actress_id == selected_id_ref[0]
        is_scraping = actress_id in _SCRAPING_IDS
        name = actress.get("name") or actress_id
        last_scraped = actress.get("last_scraped")
        inactive = bool(actress.get("inactive", False))
        inactive_reason = str(actress.get("inactive_reason", "")).strip()
        latest_solo = str(actress.get("inactive_last_solo", "")).strip()
        inactive_tooltip = inactive_reason or (
            f"Latest solo release: {latest_solo}" if latest_solo else "No fetched solo release found."
        )

        # Sync active-row class without touching the click handler.
        if is_active:
            row_el.classes(add="active-row")
        else:
            row_el.classes(remove="active-row")

        row_el.clear()
        with row_el:
            rating = actress.get("rating")
            _nc, _ns, _bh, _aura = _score_info(rating)

            # Fixed-width score column — stretches full row height so names align
            ui.html(
                f'<div style="width:52px;flex-shrink:0;align-self:stretch;'
                f'display:flex;align-items:stretch;padding:2px 0;">'
                + (_bh if _bh else "")
                + "</div>"
            )

            with (
                ui.column()
                .classes("gap-0")
                .style("flex:1;min-width:0;overflow:visible")
            ):
                _name_style = f"color:{_nc}" + (
                    f";text-shadow:{_ns}" if _ns else ""
                )
                ui.html(
                    f'<span class="trk-actress-name {_aura}" style="{_name_style}">{name}</span>'
                )
                if last_scraped or inactive:
                    with ui.row().classes("items-center gap-2").style("min-width:0;flex-wrap:wrap"):
                        if last_scraped:
                            ui.html(
                                f'<span class="trk-actress-sub">{_fmt_relative(last_scraped)}</span>'
                            )
                        if inactive:
                            ui.html(
                                f'<span class="trk-badge-inactive" title="{inactive_tooltip}">INACTIVE</span>'
                            )

            if unseen:
                _u_word = "video" if unseen == 1 else "videos"
                ui.html(
                    f'<span class="trk-badge-unseen" title="{unseen} unseen {_u_word}">{unseen}</span>'
                )
            if in_queue_count:
                _q_word = "video" if in_queue_count == 1 else "videos"
                ui.html(
                    f'<span class="trk-badge-in-queue" title="{in_queue_count} {_q_word} in downloader queue">⬇{in_queue_count}</span>'
                )

            # Refresh icon — spins when scraping
            if is_scraping:
                ui.spinner("dots", size="xs").style("color:#f59e0b;flex-shrink:0")
            else:
                ui.button(icon="refresh").props("flat round size=xs").style(
                    "color:#fbbf24;flex-shrink:0"
                ).tooltip("Refresh").on(
                    "click.stop",
                    lambda aid=actress_id: _open_page_fetch_dialog(aid),
                )

            # Delete icon
            ui.button(icon="close").props("flat round size=xs").style(
                "color:#6b7280;flex-shrink:0"
            ).tooltip("Remove").on(
                "click.stop",
                lambda aid=actress_id: _confirm_delete(aid),
            )

    def _build_actress_row(actress_id: str, actress: dict) -> None:
        with trk_list_wrap:
            with (
                ui.element("div")
                .classes("trk-row")
                .on("click", lambda aid=actress_id: _select_actress(aid)) as row_el
            ):
                actress_row_els[actress_id] = row_el
                _populate_actress_row_content(row_el, actress_id, actress)

    def _refresh_actress_row(actress_id: str) -> None:
        """Update a single actress row in-place without rebuilding the whole list."""
        row_el = actress_row_els.get(actress_id)
        if row_el is None:
            _rebuild_left_list()
            return
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if actress is None:
            _rebuild_left_list()
            return
        _populate_actress_row_content(row_el, actress_id, actress)

    def _build_actress_ref_match_row(
        actress_id: str, actress: dict, matched_refs: list
    ) -> None:
        """Compact row used in ref-search mode: actress name + matched ref chips."""
        name = actress.get("name") or actress_id
        is_active = actress_id == selected_id_ref[0]
        videos_by_ref = {v["ref"]: v for v in actress.get("videos", [])}

        with trk_list_wrap:
            with ui.element("div").classes(
                f"trk-ref-match-row{'  active-row' if is_active else ''}"
            ) as row_el:
                actress_row_els[actress_id] = row_el
                ui.html(f'<span class="trk-ref-match-actress">{name}</span>').on(
                    "click", lambda aid=actress_id: _select_actress(aid)
                )
                with ui.element("div").style(
                    "display:flex;flex-wrap:wrap;gap:3px;margin-top:4px"
                ):
                    for ref in matched_refs:
                        seen = videos_by_ref.get(ref, {}).get("seen", False)
                        cc = "trk-ref-chip" + (" seen" if seen else "")
                        ui.html(f'<span class="{cc}">{ref}</span>').on(
                            "click",
                            lambda r=ref, aid=actress_id: _select_actress_video(aid, r),
                        )

    def _select_actress(actress_id: str) -> None:
        if selected_id_ref[0] != actress_id:
            current_page_ref[0] = 1
        selected_id_ref[0] = actress_id
        for aid, el in actress_row_els.items():
            if aid == actress_id:
                el.classes(add="active-row")
            else:
                el.classes(remove="active-row")
        _refresh_right_panel()

    def _select_actress_video(actress_id: str, ref: str) -> None:
        """Select an actress and pre-highlight a specific video (from ref search)."""
        selected_video_ref[0] = ref
        pending_video_page_ref[0] = ref
        filter_ref[0] = "all"
        _select_actress(actress_id)

    def _nav_to_downloader_ref(ref: str) -> None:
        app.storage.user["_downloader_jump_ref"] = str(ref or "").strip().upper()
        ui.navigate.to("/downloader")

    def _refresh_right_panel() -> None:
        import datetime as _dt
        _caller = _tb.extract_stack()[-2]
        print(
            f"[TRK] _refresh_right_panel at {_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
            f" — {_caller.filename.split('/')[-1].split(chr(92))[-1]}:{_caller.lineno} {_caller.name}",
            flush=True,
        )
        video_row_els.clear()
        right_col.clear()
        actress_id = selected_id_ref[0]
        if not actress_id:
            _build_empty_right()
            return
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            _build_empty_right()
            return
        _build_actress_inspector(actress_id, actress, data)

    def _get_live_downloader_sets() -> tuple[set[str], set[str]]:
        """Read live downloader state shared in this NiceGUI session."""
        _dl_items = load_downloader_queue()
        queued_refs = {item["kw"].upper() for item in _dl_items}
        session_dl_refs = {
            item["kw"].upper() for item in _dl_items if item.get("downloaded")
        }
        return queued_refs, session_dl_refs

    def _vmerge(v: dict, vd: dict) -> dict:
        """Merge per-actress entry {ref, seen, downloaded} with shared video data."""
        ref = str(v.get("ref", "")).upper()
        shared = vd.get(ref, {})
        return {**shared, **v}

    def _video_matches_filter(video: dict, flt: str, today: str) -> bool:
        if flt == "released":
            return bool(video.get("date")) and video["date"] <= today
        if flt == "upcoming":
            return (not video.get("date")) or video["date"] > today
        if flt == "unseen":
            return not video.get("seen")
        if flt == "solo":
            return len(video.get("_meta", {}).get("actresses") or []) == 1
        return True

    def _normalize_fetched_pages(value) -> list[int]:
        return sorted(
            {
                max(1, int(page))
                for page in (value or [])
                if str(page).strip()
            }
        )

    def _get_detected_page_limit(pag: dict) -> int:
        total_pages = pag.get("total_pages")
        if total_pages:
            return max(1, int(total_pages))
        next_page = pag.get("next_page")
        fetched_pages = _normalize_fetched_pages(pag.get("fetched_pages"))
        if next_page:
            return max(int(next_page), max(fetched_pages, default=0), 1)
        return max(int(pag.get("pages_loaded", 0) or 0), max(fetched_pages, default=0), 1)

    def _get_page_summary(pag: dict) -> tuple[str, str]:
        fetched_pages = _normalize_fetched_pages(pag.get("fetched_pages"))
        total_pages = pag.get("total_pages")

        if total_pages:
            headline = f"Detected {int(total_pages)} page(s)"
        else:
            headline = "JAVLibrary page count unavailable"

        if fetched_pages:
            fetched_text = ", ".join(str(page) for page in fetched_pages[:12])
            if len(fetched_pages) > 12:
                fetched_text += f" +{len(fetched_pages) - 12} more"
            detail = f"Fetched: {fetched_text}"
        else:
            detail = "Fetched: none yet"

        return headline, detail

    def _merge_page_tracking(
        actress_id: str,
        page_numbers: list[int],
        *,
        result: dict | None = None,
        replace_fetched_pages: bool = False,
    ) -> dict:
        current = get_pagination(actress_id)
        fetched_pages = (
            _normalize_fetched_pages(page_numbers)
            if replace_fetched_pages
            else _normalize_fetched_pages(list(current.get("fetched_pages", [])) + list(page_numbers))
        )

        current_total = current.get("total_pages")
        result_total = (result or {}).get("total_pages")
        total_pages = max(
            [
                int(value)
                for value in (current_total, result_total, max(fetched_pages, default=0))
                if value
            ],
            default=None,
        )

        if total_pages is not None:
            remaining = [page for page in range(1, total_pages + 1) if page not in fetched_pages]
            next_page = remaining[0] if remaining else None
            has_more = bool(remaining)
        else:
            next_page = (result or {}).get("next_page") or current.get("next_page")
            has_more = bool((result or {}).get("has_more") or current.get("has_more") or next_page)

        pages_loaded = max(
            int(current.get("pages_loaded", 0) or 0),
            max(fetched_pages, default=0),
        )
        pages_scraped = int((result or {}).get("pages_scraped", len(page_numbers)) or len(page_numbers))

        new_pag = {
            "has_more": has_more,
            "next_page": next_page,
            "pages_scraped": pages_scraped,
            "pages_loaded": pages_loaded,
            "total_pages": total_pages,
            "fetched_pages": fetched_pages,
        }
        set_pagination(actress_id, **new_pag)
        save_pagination_state(
            actress_id,
            pages_loaded=new_pag["pages_loaded"],
            next_page=new_pag["next_page"],
            has_more=new_pag["has_more"],
            total_pages=new_pag["total_pages"],
            fetched_pages=new_pag["fetched_pages"],
        )
        return new_pag

    def _merge_scraped_videos(actress_id: str, actress: dict, scraped_videos: list[dict], *, scraped_name: str = "") -> int:
        existing = {v["ref"]: v for v in actress.get("videos", [])}
        added = 0
        for video in scraped_videos:
            if video["ref"] not in existing:
                existing[video["ref"]] = video
                added += 1

        tracker_data = load_tracker()
        shared_videos = tracker_data.get("videos", {})
        merged = sorted(
            existing.values(),
            key=lambda item: (
                item.get("date")
                or shared_videos.get(item["ref"].upper(), {}).get("date")
                or "0000-00-00"
            ),
            reverse=True,
        )
        # Prefer whatever name is already stored (user-set or previously scraped);
        # only fall back to the scraped name if no name has been set yet.
        stored_name = actress.get("name", "")
        update_actress_videos(actress_id, stored_name or scraped_name, list(merged))
        return added

    def _set_video_row_selected(ref: str, selected: bool) -> None:
        handles = video_row_els.get(str(ref).strip().upper())
        if not handles:
            return
        row_el = handles.get("row")
        if row_el is None:
            return
        row_el.classes(remove="active-video")
        if selected:
            row_el.classes(add="active-video")

    def _render_video_row_content(
        handles: dict[str, object],
        actress_id: str,
        v: dict,
        today: str,
        queued_refs: set = frozenset(),
        session_dl_refs: set = frozenset(),
        name_to_rating: dict = None,
        *,
        refresh_cover: bool = False,
    ) -> None:
        if name_to_rating is None:
            name_to_rating = {}
        row_el = handles["row"]
        cover_el = handles["cover"]
        info_el = handles["info"]
        actions_el = handles["actions"]
        ref = v["ref"]
        ref_up = ref.upper()
        is_seen = v.get("seen", False)
        is_downloaded = v.get("downloaded", False) or ref_up in session_dl_refs
        is_in_queue = ref_up in queued_refs and not is_downloaded
        is_upcoming = bool(v.get("date")) and v["date"] > today
        is_selected = ref == selected_video_ref[0]

        row_el.classes(
            remove="active-video trk-video-downloaded trk-video-queued"
        )
        if is_selected:
            row_el.classes(add="active-video")
        if is_downloaded:
            row_el.classes(add="trk-video-downloaded")
        if is_in_queue:
            row_el.classes(add="trk-video-queued")

        if refresh_cover:
            cover_el.clear()
            with cover_el:
                # Cover image — served from shared cache if available
                if cover_exists(ref):

                    def _open_cover_zoom(r=ref):
                        open_image_preview(f"/api/cover?ref={r}")

                    ui.image(
                        f"/api/cover?ref={ref}"
                        + (
                            f"&_t={_cover_busted[ref.upper()]}"
                            if ref.upper() in _cover_busted
                            else ""
                        )
                    ).classes("trk-cover-img").props("loading=lazy").style(
                        "cursor:zoom-in"
                    ).on("click.stop", _open_cover_zoom)
                else:
                    ui.html('<div class="trk-cover-placeholder">🎬</div>')

        info_el.clear()
        with info_el:
            with ui.row().classes("items-center gap-1").style("flex-wrap:wrap"):
                ui.html(f'<span class="trk-ref-badge">{ref}</span>')
                ui.button(icon="content_copy").props("flat round size=xs").style(
                    "color:#d97706;margin-left:-2px"
                ).tooltip(f"Copy {ref}").on(
                    "click.stop",
                    lambda r=ref: ui.run_javascript(
                        f"navigator.clipboard.writeText({repr(r)})"
                    ),
                )
                if is_downloaded:
                    ui.html(
                        '<span class="trk-badge-downloaded" title="Downloaded and saved to disk">✓ ON DISK</span>'
                    )
                elif is_in_queue:
                    ui.html(
                        '<span class="trk-badge-queued" title="Currently queued in the downloader">⬇ IN QUEUE</span>'
                    )
                elif not is_seen:
                    ui.html(
                        '<span class="trk-badge-new" title="New — you haven\'t seen this one yet">●NEW</span>'
                    )
                if is_upcoming:
                    ui.html(
                        '<span class="trk-badge-upcoming" title="Not yet released — mark your calendar">UPCOMING</span>'
                    )
            ui.label(v.get("title", "")).style(
                "font-size:0.82rem;color:#e2e8f0;"
                "overflow:hidden;display:-webkit-box;"
                "-webkit-line-clamp:3;-webkit-box-orient:vertical;"
                "min-height:calc(0.82rem * 1.4 * 3);max-width:100%"
            )
            with ui.column().classes("gap-0").style("min-width:0;overflow:visible;"):
                _meta = v.get("_meta", {})
                _acts = _meta.get("actresses", [])
                if _acts:
                    _solo = len(_acts) == 1
                    _acts_tip = "Solo" if _solo else f"{len(_acts)} actresses"

                    _parts = []
                    for _a in _acts:
                        _r = name_to_rating.get(_a)
                        _c, _s, _, _aura = _score_info(_r)
                        _style = f"color:{_c};" + (f"text-shadow:{_s};" if _s else "")
                        _parts.append(
                            f'<span class="{_aura}" style="{_style}">{_a}</span>'
                        )

                    _acts_html = ", ".join(_parts)
                    ui.html(_acts_html).classes("trk-video-actresses").tooltip(
                        _acts_tip
                    )
                if v.get("date"):
                    ui.label(v["date"]).classes("trk-video-date")

        actions_el.clear()
        with actions_el:
            _has_meta = bool(v.get("_meta"))
            _fetch_tip = (
                "Re-fetch metadata + overwrite cover"
                if _has_meta
                else "Fetch metadata + cover"
            )
            _fetch_color = "#f59e0b" if _has_meta else "#4b5563"
            _fetch_btn = (
                ui.button(icon="manage_search")
                .props("flat round size=sm")
                .style(f"color:{_fetch_color}")
                .tooltip(_fetch_tip)
            )
            _fetch_btn.on(
                "click.stop",
                lambda r=ref, aid=actress_id, b=_fetch_btn: _deep_fetch_video(r, aid, b),
            )

            _dl_icon = "task_alt" if is_downloaded else "radio_button_unchecked"
            _dl_color = "#4ade80 !important" if is_downloaded else "#d97706"
            _dl_tip = (
                "Unmark as downloaded" if is_downloaded else "Mark as downloaded on disk"
            )
            ui.button(icon=_dl_icon).props("flat round size=sm").style(
                f"color:{_dl_color}"
            ).tooltip(_dl_tip).on(
                "click.stop",
                lambda r=ref, aid=actress_id, cur=is_downloaded: _toggle_video_downloaded(
                    r, aid, cur
                ),
            )

            if is_in_queue:
                ui.button(icon="open_in_new").props("flat round size=sm").style(
                    "color:#60a5fa"
                ).tooltip(f"Open {ref} in downloader").on(
                    "click.stop",
                    lambda r=ref: _nav_to_downloader_ref(r),
                )

            if is_in_queue or is_downloaded:
                ui.button(icon="playlist_add_check").props("flat round size=sm").style(
                    "color:#4b5563"
                ).tooltip(
                    "Already in downloader queue" if is_in_queue else "Already downloaded"
                )
            else:
                ui.button(icon="add_circle_outline").props("flat round size=sm").style(
                    "color:#fbbf24"
                ).tooltip(f"Add {ref} to downloader queue").on(
                    "click.stop",
                    lambda r=ref, aid=actress_id: _queue_ref(r, aid),
                )

            ui.button(icon="delete_outline").props("flat round size=sm").style(
                "color:#6b7280"
            ).tooltip(f"Remove {ref} from tracker").on(
                "click.stop",
                lambda r=ref, aid=actress_id: _confirm_remove_video(aid, r),
            )

    def _refresh_video_rows(
        actress_id: str,
        refs: list[str],
        *,
        allow_membership_change: bool = False,
        refresh_cover: bool = False,
    ) -> None:
        if selected_id_ref[0] != actress_id:
            return

        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            _refresh_right_panel()
            return

        today = _date_cls.today().isoformat()
        flt = filter_ref[0]
        queued_refs, session_dl_refs = _get_live_downloader_sets()

        vd = data.get("videos", {})
        name_to_rating = {}
        for a_id, a_data in data["actresses"].items():
            r = a_data.get("rating")
            if r is not None:
                if "name" in a_data and a_data["name"]:
                    name_to_rating[a_data["name"]] = r
                name_to_rating[a_id] = r
                c = {}
                for vv in a_data.get("videos", []):
                    ref_k = str(vv.get("ref", "")).upper()
                    for act in (vd.get(ref_k, {}).get("_meta", {}) or {}).get("actresses", []):
                        c[act] = c.get(act, 0) + 1
                if c:
                    top_name = max(c, key=c.get)
                    name_to_rating[top_name] = r

        videos_by_ref = {
            str(video.get("ref", "")).upper(): _vmerge(video, vd)
            for video in actress.get("videos", [])
            if str(video.get("ref", "")).strip()
        }

        normalized_refs = []
        for ref in refs:
            ref_up = str(ref).strip().upper()
            if ref_up and ref_up not in normalized_refs:
                normalized_refs.append(ref_up)

        if allow_membership_change:
            for ref_up in normalized_refs:
                video = videos_by_ref.get(ref_up)
                handles = video_row_els.get(ref_up)
                matches = bool(video) and _video_matches_filter(video, flt, today)
                if matches != bool(handles):
                    _refresh_right_panel()
                    return

        for ref_up in normalized_refs:
            video = videos_by_ref.get(ref_up)
            handles = video_row_els.get(ref_up)
            if not video or handles is None:
                _refresh_right_panel()
                return
            _render_video_row_content(
                handles,
                actress_id,
                video,
                today,
                queued_refs,
                session_dl_refs,
                name_to_rating,
                refresh_cover=refresh_cover,
            )

    def _build_empty_right() -> None:
        with right_col:
            with ui.element("div").classes("trk-empty"):
                ui.icon("star_border").style("font-size:2.5rem;opacity:.15")
                ui.label("Select an actress from the list").style(
                    "font-size:0.85rem;color:#374151"
                )

    def _build_actress_inspector(
        actress_id: str, actress: dict, data: dict = None
    ) -> None:  # noqa: C901
        if data is None:
            data = {"actresses": {}, "videos": {}}

        vd = data.get("videos", {})
        name_to_rating = {}
        for a_id, a_data in data["actresses"].items():
            r = a_data.get("rating")
            if r is not None:
                # Map the user's custom name if set
                if "name" in a_data and a_data["name"]:
                    name_to_rating[a_data["name"]] = r

                # Also fall back to the actress ID (in case they literally named it using the code)
                name_to_rating[a_id] = r

                # Finally, infer the original scraped name by finding the most common name in her videos
                # This ensures renaming an actress doesn't break colorization of the actual Japanese name
                # found inside the video metadata block.
                c = {}
                for v in a_data.get("videos", []):
                    ref_k = str(v.get("ref", "")).upper()
                    for act in (vd.get(ref_k, {}).get("_meta", {}) or {}).get("actresses", []):
                        c[act] = c.get(act, 0) + 1
                if c:
                    top_name = max(c, key=c.get)
                    name_to_rating[top_name] = r

        def _is_fetched_solo_video(video: dict) -> bool:
            """Only treat deep-fetched entries with exactly one actress as solo."""
            actresses = video.get("_meta", {}).get("actresses") or []
            return len(actresses) == 1

        today = _date_cls.today().isoformat()
        flt = filter_ref[0]
        all_videos = [_vmerge(v, vd) for v in actress.get("videos", [])]

        # Apply filter
        if flt == "released":
            videos = [v for v in all_videos if v.get("date") and v["date"] <= today]
        elif flt == "upcoming":
            videos = [v for v in all_videos if not v.get("date") or v["date"] > today]
        elif flt == "unseen":
            videos = [v for v in all_videos if not v.get("seen")]
        elif flt == "solo":
            videos = [v for v in all_videos if _is_fetched_solo_video(v)]
        else:
            videos = list(all_videos)

        # Sort: newest first; undated at bottom
        videos = sorted(
            videos,
            key=lambda v: v.get("date") or "0000-00-00",
            reverse=True,
        )

        page_size = page_size_ref[0]
        selected_ref_up = str(pending_video_page_ref[0] or "").strip().upper()
        if selected_ref_up:
            for idx, video in enumerate(videos):
                if str(video.get("ref", "")).strip().upper() == selected_ref_up:
                    current_page_ref[0] = (idx // page_size) + 1
                    break
            pending_video_page_ref[0] = None

        total_filtered = len(videos)
        total_pages = max(1, (total_filtered + page_size - 1) // page_size)
        current_page_ref[0] = max(1, min(current_page_ref[0], total_pages))
        page_start = (current_page_ref[0] - 1) * page_size
        page_end = page_start + page_size
        paged_videos = videos[page_start:page_end]

        pag = get_pagination(actress_id)

        with right_col:
            # ── Inspector header ──────────────────────────────────────────────
            with ui.column().classes("w-full gap-2").style("margin-bottom:6px"):
                with ui.row().classes("w-full items-center gap-2"):
                    _insp_rating = actress.get("rating")
                    _insp_inactive = bool(actress.get("inactive", False))
                    _insp_inactive_reason = str(actress.get("inactive_reason", "")).strip()
                    _insp_latest_solo = str(actress.get("inactive_last_solo", "")).strip()
                    _insp_inactive_tip = _insp_inactive_reason or (
                        f"Latest solo release: {_insp_latest_solo}" if _insp_latest_solo else "No fetched solo release found."
                    )
                    _inc, _ins, _, _aura = _score_info(_insp_rating)
                    _insp_name_style = (
                        f"font-size:1.05rem;font-weight:700;flex:1;padding-block:4px;margin-block:-4px;"
                        f"color:{_inc};" + (f"text-shadow:{_ins};" if _ins else "")
                    )

                    # Score badge (clickable to edit)
                    def _open_score_dialog(
                        aid=actress_id, cur_score=actress.get("rating")
                    ):
                        with (
                            ui.dialog() as _sdlg,
                            ui.card().style(
                                "min-width:320px;background:#0f0f13;border:1px solid #1a1a24"
                            ),
                        ):
                            ui.label("Set Score (0-100)").style(
                                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:8px"
                            )
                            ui.label(
                                "0-100 score rating. Hover over list badges for tooltip tiers."
                            ).style(
                                "font-size:0.75rem;color:#9ca3af;margin-bottom:12px"
                            )
                            _score_inp = (
                                ui.input(
                                    value=str(int(cur_score))
                                    if cur_score is not None
                                    else "",
                                    placeholder="Enter 0-100",
                                )
                                .classes("w-full")
                                .props("outlined dense")
                            )
                            with (
                                ui.row()
                                .classes("gap-2 justify-end w-full items-center")
                                .style("margin-top:10px")
                            ):
                                ui.button(
                                    "Clear", on_click=lambda: _commit_score("")
                                ).props("flat size=sm").style("color:#ef4444")
                                ui.space()
                                ui.button("Cancel", on_click=_sdlg.close).props(
                                    "flat size=sm"
                                ).style("color:#6b7280")

                                def _commit_score(val):
                                    v = val
                                    if v == "":
                                        _set_star_rating(aid, None)
                                        _sdlg.close()
                                        return
                                    try:
                                        v_int = int(v)
                                    except ValueError:
                                        return
                                    v_int = max(0, min(100, v_int))
                                    _set_star_rating(aid, v_int)
                                    _sdlg.close()

                                def _do_save():
                                    _commit_score(_score_inp.value.strip())

                                ui.button("Save", icon="save", on_click=_do_save).props(
                                    "unelevated size=sm"
                                ).style("background:#d97706;color:#fff")
                                _score_inp.on("keydown.enter", _do_save)
                        _sdlg.open()

                    ui.html(_svg_score_badge(_insp_rating)).on(
                        "click", _open_score_dialog
                    )

                    with ui.column().classes("gap-0").style("flex:1;min-width:0"):
                        ui.label(actress.get("name") or actress_id).style(
                            _insp_name_style
                        ).classes(_aura)
                        ls = actress.get("last_scraped")
                        if ls or _insp_inactive:
                            with ui.row().classes("items-center gap-2").style("min-width:0;flex-wrap:wrap"):
                                if ls:
                                    ui.label(f"scraped {_fmt_relative(ls)}").style(
                                        "font-size:0.7rem;color:#4b5563"
                                    )
                                if _insp_inactive:
                                    ui.html(
                                        f'<span class="trk-badge-inactive" title="{_insp_inactive_tip}">INACTIVE</span>'
                                    )
                    # Open JAVLibrary actress page
                    _jl_url = actress.get("url", "")
                    if _jl_url:
                        ui.button(
                            icon="open_in_new",
                            on_click=lambda u=_jl_url: ui.run_javascript(
                                f"window.open({repr(u)}, '_blank')"
                            ),
                        ).props("flat round size=sm").style("color:#d97706").tooltip(
                            "Open JAVLibrary actress page"
                        )

                    # Rename actress
                    def _open_rename_dialog(
                        aid=actress_id, cur_name=actress.get("name") or actress_id
                    ):
                        with (
                            ui.dialog() as _rdlg,
                            ui.card().style(
                                "min-width:360px;background:#0f0f13;border:1px solid #1a1a24"
                            ),
                        ):
                            ui.label("Rename Actress").style(
                                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:8px"
                            )
                            _name_inp = (
                                ui.input(value=cur_name, placeholder="Actress name")
                                .classes("w-full")
                                .props("outlined dense")
                            )
                            with (
                                ui.row()
                                .classes("gap-2 justify-end w-full")
                                .style("margin-top:10px")
                            ):
                                ui.button("Cancel", on_click=_rdlg.close).props(
                                    "flat size=sm"
                                ).style("color:#6b7280")

                                def _do_rename(rdlg=_rdlg, ninp=_name_inp, a=aid):
                                    rename_actress(a, ninp.value)
                                    rdlg.close()
                                    _refresh_actress_row(a)
                                    _refresh_right_panel()

                                ui.button(
                                    "Save", icon="save", on_click=_do_rename
                                ).props("unelevated size=sm").style(
                                    "background:#d97706;color:#fff"
                                )
                        _rdlg.open()

                    ui.button(
                        icon="edit",
                        on_click=_open_rename_dialog,
                    ).props("flat round size=sm").style("color:#d97706").tooltip(
                        "Rename actress"
                    )

                    ui.button(
                        icon="refresh",
                        on_click=lambda: _open_page_fetch_dialog(actress_id),
                    ).props("flat round size=sm").style("color:#fbbf24").tooltip(
                        "Fetch or refetch a specific page"
                    )
                    _page_headline, _page_detail = _get_page_summary(pag)
                    with ui.column().classes("gap-0").style("min-width:220px;margin-left:auto"):
                        ui.label(_page_headline).classes("trk-page-summary-title")
                        ui.label(_page_detail).classes("trk-page-summary-detail")
                    ui.button(
                        "Mark All Seen",
                        icon="done_all",
                        on_click=lambda: _do_mark_all_seen(actress_id),
                    ).props("flat size=sm").style(
                        "color:#4ade80;font-size:0.72rem"
                    ).tooltip("Mark all as seen")
                    _cover_src = get_cover_source()
                    ui.button(
                        icon="cloud_download",
                        on_click=lambda: _queue_cover_fetch(actress_id),
                    ).props("flat round size=sm").style("color:#d97706").tooltip(
                        f"Fetch missing metadata & covers via {_cover_src} "
                        f"(change source in Settings → Metadata Source)"
                    )

            # ── Filter chips ──────────────────────────────────────────────────
            with ui.row().classes("w-full items-center gap-2").style("margin-bottom:6px;flex-wrap:nowrap"):
                with ui.row().classes("gap-2 items-center").style("flex-wrap:wrap;min-width:0"):
                    for label, value in [
                        ("All", "all"),
                        ("Released", "released"),
                        ("Upcoming", "upcoming"),
                        ("Unseen", "unseen"),
                        ("Solo", "solo"),
                    ]:
                        is_active = filter_ref[0] == value
                        ui.html(
                            f'<span class="trk-filter-chip{"  active" if is_active else ""}">'
                            f"{label}</span>"
                        ).on("click", lambda v=value: _set_filter(actress_id, v))

                ui.element("div").classes("flex-1")

                with ui.row().classes("items-center gap-2").style("margin-left:auto;flex-wrap:nowrap"):
                    if total_pages > 1:
                        ui.label("Page").classes("trk-pagination-meta")
                        ui.select(
                            options=list(range(1, total_pages + 1)),
                            value=current_page_ref[0],
                            on_change=lambda e: _set_video_page(int(e.value)),
                        ).props("dense outlined options-dense").classes("trk-page-select")
                        ui.label(f"/ {total_pages}").classes("trk-pagination-meta")

                    ui.label("Show").classes("trk-pagination-meta")
                    ui.select(
                        options=list(_TRACKER_PAGE_SIZE_OPTIONS),
                        value=page_size_ref[0],
                        on_change=lambda e: _set_page_size(int(e.value)),
                    ).props("dense outlined options-dense").classes("trk-page-size-select")

            # Video count
            total = len(all_videos)
            shown = len(videos)
            if shown != total:
                range_start = page_start + 1 if paged_videos else 0
                range_end = page_start + len(paged_videos)
                count_txt = (
                    f"{range_start}-{range_end} of {shown} filtered · {total} total"
                    if paged_videos
                    else f"0 of {shown} filtered · {total} total"
                )
            elif total_pages > 1:
                range_start = page_start + 1 if paged_videos else 0
                range_end = page_start + len(paged_videos)
                count_txt = f"{range_start}-{range_end} of {total} videos"
            else:
                count_txt = f"{total} video{'s' if total != 1 else ''}"
            ui.label(count_txt).style(
                "font-size:0.72rem;color:#6b7280;margin-bottom:2px"
            )

            # ── Read live downloader session for cross-module indicators ─────
            # app.storage.user is shared across all pages in the same session,
            # so we can see the downloader queue without any explicit syncing.
            _dl_items = load_downloader_queue()
            _queued_refs: set = {item["kw"].upper() for item in _dl_items}
            _session_dl_refs: set = {
                item["kw"].upper() for item in _dl_items if item.get("downloaded")
            }

            # ── Video list ────────────────────────────────────────────────────
            if not paged_videos:
                with ui.element("div").classes("trk-empty").style("padding:40px"):
                    ui.icon("movie_filter").style("font-size:2rem;opacity:.2")
                    ui.label("No videos match the current filter").style(
                        "font-size:0.82rem;color:#374151"
                    )
            else:
                for v in paged_videos:
                    _build_video_row(
                        actress_id,
                        v,
                        today,
                        _queued_refs,
                        _session_dl_refs,
                        name_to_rating,
                    )

    def _build_video_row(
        actress_id: str,
        v: dict,
        today: str,
        queued_refs: set = frozenset(),
        session_dl_refs: set = frozenset(),
        name_to_rating: dict = None,
    ) -> None:
        ref = v["ref"]
        ref_up = ref.upper()
        with (
            ui.element("div")
            .classes("trk-video-row")
            .on("click", lambda r=ref, aid=actress_id: _on_video_click(r, aid))
        ) as row_el:
            with ui.element("div") as cover_el:
                pass
            with ui.column().classes("gap-1").style("min-width:0;flex:1") as info_el:
                pass
            with ui.column().classes("gap-0 items-center").style("flex-shrink:0") as actions_el:
                pass
            handles = {
                "row": row_el,
                "cover": cover_el,
                "info": info_el,
                "actions": actions_el,
            }
            video_row_els[ref_up] = handles
            _render_video_row_content(
                handles,
                actress_id,
                v,
                today,
                queued_refs,
                session_dl_refs,
                name_to_rating,
                refresh_cover=True,
            )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_video_downloaded(
        ref: str, actress_id: str, currently_downloaded: bool
    ) -> None:
        new_state = not currently_downloaded
        mark_ref_downloaded_globally(ref, downloaded=new_state)
        _refresh_actress_row(actress_id)
        _refresh_video_rows(
            actress_id,
            [ref],
            allow_membership_change=new_state and filter_ref[0] == "unseen",
        )

    def _set_filter(actress_id: str, value: str) -> None:
        filter_ref[0] = value
        current_page_ref[0] = 1
        _refresh_right_panel()

    def _set_page_size(value: int) -> None:
        if value not in _TRACKER_PAGE_SIZE_OPTIONS:
            return
        page_size_ref[0] = value
        set_tracker_video_page_size(value)
        current_page_ref[0] = 1
        _refresh_right_panel()

    def _set_video_page(value: int) -> None:
        current_page_ref[0] = max(1, int(value))
        _refresh_right_panel()

    def _set_star_rating(actress_id: str, value: "Optional[int]") -> None:
        update_actress_rating(actress_id, value)
        _refresh_actress_row(actress_id)
        _refresh_right_panel()

    def _set_sort(key: str) -> None:
        sort_ref[0] = key
        _rebuild_left_list()
        if selected_id_ref[0] and selected_id_ref[0] in actress_row_els:
            actress_row_els[selected_id_ref[0]].classes(add="active-row")

    def _set_search_mode(mode: str) -> None:
        """Toggle between actress-name search and video-ref search."""
        mode = str(mode)  # guard against unexpected event arg types
        search_mode_ref[0] = mode
        search_ref[0] = ""
        if search_inp_ref:
            search_inp_ref[0].value = ""
            placeholder = (
                "Search ref code… (e.g. SONE)"
                if mode == "ref"
                else "Search actress name…"
            )
            search_inp_ref[0].props(f'placeholder="{placeholder}"')
        if sort_row_ref:
            sort_row_ref[0].style("display:none" if mode == "ref" else "display:flex")
        _rebuild_left_list()
        if selected_id_ref[0] and selected_id_ref[0] in actress_row_els:
            actress_row_els[selected_id_ref[0]].classes(add="active-row")

    def _on_video_click(ref: str, actress_id: str) -> None:
        prev_ref = selected_video_ref[0]
        data = load_tracker()
        actress = data["actresses"].get(actress_id, {})
        clicked_video = next(
            (
                video
                for video in actress.get("videos", [])
                if str(video.get("ref", "")).upper() == ref.upper()
            ),
            None,
        )
        was_seen = bool(clicked_video.get("seen")) if clicked_video else False
        selected_video_ref[0] = ref  # highlight this row
        mark_seen(actress_id, [ref])
        _refresh_actress_row(actress_id)
        if filter_ref[0] == "unseen":
            _refresh_right_panel()
            return
        if prev_ref and prev_ref.upper() != ref.upper():
            _set_video_row_selected(prev_ref, False)
        _set_video_row_selected(ref, True)
        if not was_seen:
            _refresh_video_rows(actress_id, [ref])

    def _do_mark_all_seen(actress_id: str) -> None:
        mark_all_seen(actress_id)
        _refresh_actress_row(actress_id)
        _refresh_right_panel()

    def _queue_cover_fetch(
        actress_id: str,
        refs: list[str] | None = None,
        *,
        silent: bool = False,
    ) -> None:
        """
        Enqueue cover fetching for *actress_id* via the module-level
        fetch_queue so the job continues even if the user navigates away.

        silent=True  – suppresses all toasts; used after a scrape/refresh.
        silent=False – shows start/done toasts via the current client.
        """
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            return

        requested_refs: list[str] = []
        if refs is not None:
            requested_refs = [
                str(ref).strip().upper()
                for ref in refs
                if str(ref).strip()
            ]

        vd = data.get("videos", {})
        missing: list[str] = []
        seen_missing: set[str] = set()
        for video in actress.get("videos", []):
            ref = str(video.get("ref", "")).strip().upper()
            if not ref:
                continue
            if requested_refs and ref not in requested_refs:
                continue
            if ref in seen_missing:
                continue
            ref_has_meta = bool(((vd.get(ref) or {}).get("_meta") or {}).get("title"))
            if cover_exists(ref) and ref_has_meta:
                continue
            seen_missing.add(ref)
            missing.append(ref)

        if not missing:
            if not silent:
                try:
                    with ui.context.client:
                        ui.notify(
                            "No missing covers or metadata found for the selected videos"
                            if refs is not None
                            else "All covers and metadata already cached",
                            color="info",
                            timeout=2500,
                        )
                except Exception:
                    pass
            return

        source = get_cover_source()

        # Capture the client NOW (sync context) so callbacks can send
        # notifications after the originating slot is long gone.
        try:
            _client = ui.context.client if not silent else None
        except RuntimeError:
            _client = None

        def _notify(msg: str, color: str = "info") -> None:
            try:
                if _client is not None:
                    with _client:
                        ui.notify(msg, color=color)
            except Exception:
                pass

        def _on_cover_ok(ref: str) -> None:
            return

        def _on_meta(ref: str, meta: dict) -> None:
            """Persist metadata fetched as a side-effect of cover fetching."""
            try:
                save_video_meta(actress_id, ref, meta)
            except Exception:
                pass

        def _on_done(fetched: int, total: int) -> None:
            try:
                if _client is None:
                    return
                with _client:
                    if fetched and selected_id_ref[0] == actress_id:
                        # Update rows in-place — avoids full panel teardown/rebuild
                        # which looks like a page refresh and loses scroll position.
                        d = load_tracker()
                        actress_d = d["actresses"].get(actress_id)
                        if actress_d:
                            all_refs = [v["ref"] for v in actress_d.get("videos", [])]
                            _refresh_video_rows(
                                actress_id, all_refs,
                                allow_membership_change=True,
                                refresh_cover=True,
                            )
                        else:
                            _refresh_right_panel()
                    if fetched:
                        _refresh_actress_row(actress_id)
            except Exception:
                pass

        started = _cover_queue.enqueue(
            actress_id,
            missing,
            source,
            on_cover_ok=_on_cover_ok,
            on_meta=_on_meta,
            on_notify=_notify if not silent else None,
            on_done=_on_done,
        )
        if not started and not silent:
            _notify("Cover fetch already in progress for this actress", color="info")

    async def _probe_new_release_page(actress_id: str, *, skip_deleted: bool) -> dict:
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            raise ValueError(f"Missing tracked actress: {actress_id}")

        existing_refs = {
            str(video.get("ref", "")).strip().upper()
            for video in actress.get("videos", [])
            if str(video.get("ref", "")).strip()
        }
        result = await scrape_actress_page_range(actress["url"], 1, 1)
        raw_videos = list(result.get("videos", []))

        deleted_for_actress = get_deleted_refs_for_actress(actress_id)
        reacquired_refs: list[str] = []
        if deleted_for_actress:
            if skip_deleted:
                raw_videos = [
                    video
                    for video in raw_videos
                    if str(video.get("ref", "")).strip().upper() not in deleted_for_actress
                ]
            else:
                for video in raw_videos:
                    ref_up = str(video.get("ref", "")).strip().upper()
                    if ref_up and ref_up not in existing_refs and ref_up in deleted_for_actress:
                        reacquired_refs.append(ref_up)

        discovered_refs = [
            str(video.get("ref", "")).strip().upper()
            for video in raw_videos
            if str(video.get("ref", "")).strip().upper() not in existing_refs
        ]
        return {
            "actress_id": actress_id,
            "scraped_name": result.get("name") or actress.get("name", ""),
            "raw_videos": raw_videos,
            "reacquired_refs": reacquired_refs,
            "discovered_refs": discovered_refs,
            "result": result,
        }

    def _apply_new_release_probe(snapshot: dict) -> int:
        actress_id = snapshot["actress_id"]
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            return 0

        total_added = _merge_scraped_videos(
            actress_id,
            actress,
            snapshot["raw_videos"],
            scraped_name=snapshot.get("scraped_name", ""),
        )

        for ref in snapshot.get("reacquired_refs", []):
            remove_from_deleted_refs(ref)

        result = snapshot.get("result") or {}
        _merge_page_tracking(
            actress_id,
            [1],
            result={
                "pages_scraped": 1,
                "has_more": bool(result.get("has_more")),
                "next_page": result.get("next_page"),
                "total_pages": result.get("total_pages"),
            },
        )

        discovered_refs = snapshot.get("discovered_refs", [])
        if discovered_refs:
            _queue_cover_fetch(actress_id, discovered_refs, silent=True)

        if selected_id_ref[0] == actress_id:
            _refresh_right_panel()
        _refresh_actress_row(actress_id)
        return total_added

    async def _fetch_pages_for_actress(
        actress_id: str,
        page_numbers: list[int],
        *,
        silent: bool = False,
        replace_fetched_pages: bool = False,
        skip_deleted: bool = True,
    ) -> None:
        if actress_id in _SCRAPING_IDS:
            return

        pages = _normalize_fetched_pages(page_numbers)
        if not pages:
            return

        _SCRAPING_IDS.add(actress_id)
        _refresh_actress_row(actress_id)

        # Capture client before any await so notifies work after long scrapes.
        try:
            _client = ui.context.client
        except RuntimeError:
            _client = None

        def _notify(msg: str, color: str = "info", **kw) -> None:
            try:
                if _client is not None:
                    with _client:
                        ui.notify(msg, color=color, **kw)
            except Exception:
                pass

        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            _SCRAPING_IDS.discard(actress_id)
            return

        try:
            total_added = 0
            discovered_refs: list[str] = []
            reacquired_refs: list[str] = []
            aggregate_total_pages: int | None = None
            aggregate_has_more = False
            aggregate_next_page: int | None = None
            latest_name = actress.get("name", "")

            for page in pages:
                data = load_tracker()
                actress = data["actresses"].get(actress_id)
                if not actress:
                    break

                existing_refs = {
                    str(video.get("ref", "")).strip().upper()
                    for video in actress.get("videos", [])
                    if str(video.get("ref", "")).strip()
                }
                result = await scrape_actress_page_range(actress["url"], page, page)
                latest_name = result.get("name") or latest_name
                aggregate_has_more = aggregate_has_more or bool(result.get("has_more"))
                if result.get("next_page"):
                    aggregate_next_page = max(aggregate_next_page or 0, int(result["next_page"]))
                if result.get("total_pages"):
                    aggregate_total_pages = max(
                        aggregate_total_pages or 0,
                        int(result["total_pages"]),
                    )

                raw_videos = result.get("videos", [])

                # Apply deleted-refs filter (skip or reacquire)
                deleted_for_actress = get_deleted_refs_for_actress(actress_id)
                if deleted_for_actress:
                    if skip_deleted:
                        raw_videos = [
                            v for v in raw_videos
                            if v.get("ref", "").upper() not in deleted_for_actress
                        ]
                    else:
                        # Reacquire mode: collect refs being added back from deleted list
                        for v in raw_videos:
                            ref_up = v.get("ref", "").upper()
                            if ref_up and ref_up not in existing_refs and ref_up in deleted_for_actress:
                                reacquired_refs.append(ref_up)

                new_refs = [
                    video["ref"]
                    for video in raw_videos
                    if str(video.get("ref", "")).strip().upper() not in existing_refs
                ]
                discovered_refs.extend(new_refs)
                total_added += _merge_scraped_videos(
                    actress_id,
                    actress,
                    raw_videos,
                    scraped_name=latest_name,
                )

            # Remove reacquired refs from deleted lists so they're treated normally going forward
            for ref in reacquired_refs:
                remove_from_deleted_refs(ref)

            page_state = _merge_page_tracking(
                actress_id,
                pages,
                result={
                    "pages_scraped": len(pages),
                    "has_more": aggregate_has_more,
                    "next_page": aggregate_next_page,
                    "total_pages": aggregate_total_pages,
                },
                replace_fetched_pages=replace_fetched_pages,
            )

            if discovered_refs:
                _queue_cover_fetch(actress_id, refs=discovered_refs, silent=True)

            if not silent:
                page_label = f"page {pages[0]}" if len(pages) == 1 else f"{len(pages)} pages"
                detail_suffix = ""
                if page_state.get("total_pages"):
                    detail_suffix = f" · detected {page_state['total_pages']} page(s)"
                _notify(
                    f"{latest_name or actress_id}: {page_label} fetched, {total_added} new video(s){detail_suffix}",
                    color="positive",
                )

        except Exception as exc:
            cooldown_seconds = get_rate_limit_cooldown_seconds(exc)
            if cooldown_seconds is not None:
                _notify(
                    f"JAVLibrary cooling down for ~{cooldown_seconds}s. Page fetch queued in memory.",
                    color="warning",
                    timeout=5000,
                )
            else:
                _notify(f"Page fetch failed: {exc}", color="negative", timeout=8000)
        finally:
            _SCRAPING_IDS.discard(actress_id)
            # All UI updates MUST be gated on _client to avoid pushing DOM
            # mutations without a NiceGUI client context, which causes reconnects.
            if _client is not None:
                try:
                    with _client:
                        _refresh_actress_row(actress_id)
                        if selected_id_ref[0] == actress_id:
                            _refresh_right_panel()
                except Exception:
                    pass

    async def _scrape_actress(actress_id: str, first_add: bool = False) -> None:
        if first_add:
            await _fetch_pages_for_actress(
                actress_id,
                [1],
                replace_fetched_pages=True,
            )
            return

        pag = get_pagination(actress_id)
        pages = _normalize_fetched_pages(pag.get("fetched_pages"))
        if not pages:
            pages_loaded = int(pag.get("pages_loaded", 0) or 0)
            pages = list(range(1, pages_loaded + 1)) if pages_loaded > 0 else [1]
        await _fetch_pages_for_actress(actress_id, pages, silent=False)

    def _open_page_fetch_dialog(actress_id: str) -> None:
        data = load_tracker()
        actress = data["actresses"].get(actress_id)
        if not actress:
            return
        _deleted_for_actress = get_deleted_refs_for_actress(actress_id)
        _skip_deleted_ref: list[bool] = [True]
        selection: list[set[int]] = [set()]

        pag = get_pagination(actress_id)

        # Pre-select the suggested next page
        _next = pag.get("next_page")
        if _next:
            try:
                selection[0].add(max(1, int(_next)))
            except (TypeError, ValueError):
                pass

        def _selection_to_text(sel: set[int]) -> str:
            """Convert {2,4,5,6,8} → '2, 4-6, 8'."""
            if not sel:
                return ""
            pages = sorted(sel)
            ranges: list[str] = []
            start = end = pages[0]
            for p in pages[1:]:
                if p == end + 1:
                    end = p
                else:
                    ranges.append(str(start) if start == end else f"{start}-{end}")
                    start = end = p
            ranges.append(str(start) if start == end else f"{start}-{end}")
            return ", ".join(ranges)

        def _parse_page_text(raw: str) -> set[int]:
            """Parse '2, 4-6, 8' → {2, 4, 5, 6, 8}. Handles incomplete ranges like '2-'."""
            result: set[int] = set()
            raw = (
                str(raw or "")
                .replace("\u2010", "-")
                .replace("\u2011", "-")
                .replace("\u2012", "-")
                .replace("\u2013", "-")
                .replace("\u2014", "-")
                .replace("\u2212", "-")
            )
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    try:
                        a, b = part.split("-", 1)
                        a_int = max(1, int(a.strip()))
                        b = b.strip()
                        if not b:
                            # Incomplete range "2-" — keep start number so button stays active
                            result.add(a_int)
                        else:
                            b_int = min(500, max(1, int(b)))
                            lo = min(a_int, b_int)
                            hi = max(a_int, b_int)
                            for p in range(lo, hi + 1):
                                result.add(p)
                    except ValueError:
                        pass
                else:
                    try:
                        result.add(max(1, int(part)))
                    except ValueError:
                        pass
            return result

        def _get_btn_style(is_fetched: bool, is_selected: bool) -> str:
            if is_selected and is_fetched:
                return "background:#451a03;color:#fbbf24;border-width:2px;border-style:solid;border-color:#f59e0b"
            if is_selected:
                return "background:#78350f;color:#fbbf24;border-width:2px;border-style:solid;border-color:#d97706"
            if is_fetched:
                return "background:#1c1208;color:#7a4515;border-width:1px;border-style:solid;border-color:#3a2a10"
            return "background:#141419;color:#52525b;border-width:1px;border-style:solid;border-color:#27272a"

        headline, detail = _get_page_summary(pag)
        with (
            ui.dialog() as dlg,
            ui.card().style(
                "min-width:480px;max-width:640px;background:#0f0f13;border:1px solid #1a1a24"
            ),
        ):
            # ── Header ───────────────────────────────────────────────
            ui.label(f'Fetch Pages — "{actress.get("name") or actress_id}"').style(
                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:4px"
            )
            headline_lbl = ui.label(headline).classes("trk-page-dialog-title")
            detail_lbl = ui.label(detail).classes("trk-page-dialog-detail")
            hint_lbl = ui.label("").classes("trk-page-dialog-hint")

            def _refresh_dialog_state() -> tuple[dict, set[int], int]:
                latest_pag = get_pagination(actress_id)
                latest_headline, latest_detail = _get_page_summary(latest_pag)
                headline_lbl.set_text(latest_headline)
                detail_lbl.set_text(latest_detail)
                if latest_pag.get("has_more") and not latest_pag.get("total_pages"):
                    hint_lbl.set_text(
                        "Total page count not confirmed yet. Use the grid or type a higher number."
                    )
                else:
                    hint_lbl.set_text("")
                latest_fetched = set(_normalize_fetched_pages(latest_pag.get("fetched_pages")))
                latest_limit = _get_detected_page_limit(latest_pag)
                return latest_pag, latest_fetched, latest_limit

            # ── Page selection grid ───────────────────────────────────
            quick_pages_host = ui.element("div").classes("w-full").style("margin-top:8px")

            def _render_quick_pages(fetched: set[int], sel: set[int], limit: int) -> None:
                quick_pages_host.clear()
                quick_limit = min(limit, 80)
                with quick_pages_host:
                    if quick_limit > 0:
                        with ui.element("div").classes("trk-page-grid w-full"):
                            for page in range(1, quick_limit + 1):
                                is_fetched = page in fetched
                                is_selected = page in sel
                                style = _get_btn_style(is_fetched, is_selected)
                                with ui.element("div").classes("trk-page-btn").style(style).on(
                                    "click", lambda p=page: _toggle_page(p)
                                ):
                                    ui.label("✓" if is_fetched else "").classes("trk-page-btn__check")
                                    ui.label(str(page)).classes("trk-page-btn__num")
                    if limit > quick_limit:
                        ui.label(
                            f"Pages 1–{quick_limit} shown. Use the input for higher pages."
                        ).classes("trk-page-dialog-hint")
                    elif limit == 0:
                        ui.label("Use the input below to enter page numbers.").classes(
                            "trk-page-dialog-hint"
                        )

            # ── Legend ───────────────────────────────────────────────
            with ui.row().classes("gap-x-4 gap-y-1 items-center flex-wrap").style("margin:6px 0 2px"):
                for dot_color, lbl_text in (
                    ("#854d0e", "Fetched"),
                    ("#d97706", "To fetch"),
                    ("#f59e0b", "Re-fetch"),
                    ("#6b7280", "Available"),
                ):
                    with ui.row().classes("gap-1 items-center"):
                        ui.element("span").style(
                            f"width:8px;height:8px;border-radius:2px;"
                            f"background:{dot_color};display:inline-block;flex-shrink:0"
                        )
                        ui.label(lbl_text).style("font-size:0.7rem;color:#9ca3af")

            # ── Input row ────────────────────────────────────────────
            with ui.row().classes("gap-2 items-center w-full").style("margin-top:4px"):
                page_inp = (
                    ui.input(
                        value=_selection_to_text(selection[0]),
                        placeholder="e.g. 2, 4-6, 8",
                    )
                    .props("outlined dense")
                    .classes("flex-1")
                    .style("font-size:0.85rem")
                )
                ui.button("Clear", on_click=lambda: _clear_selection()).props(
                    "flat dense size=sm"
                ).style("color:#6b7280;white-space:nowrap")

            # ── Check total pages ─────────────────────────────────────
            async def _check_total_pages() -> None:
                try:
                    result = await fetch_actress_total_pages(actress["url"])
                except Exception as exc:
                    cooldown_seconds = get_rate_limit_cooldown_seconds(exc)
                    if cooldown_seconds is not None:
                        ui.notify(
                            f"JAVLibrary cooling down for ~{cooldown_seconds}s. Total-page check queued in memory.",
                            color="warning",
                        )
                    else:
                        ui.notify(f"Could not read JAVLibrary page count: {exc}", color="warning")
                    return

                total_pages = result.get("total_pages")
                latest_pag = get_pagination(actress_id)
                fetched_pages_now = _normalize_fetched_pages(latest_pag.get("fetched_pages"))
                pages_loaded_now = max(
                    int(latest_pag.get("pages_loaded", 0) or 0),
                    max(fetched_pages_now, default=0),
                )

                if total_pages is not None:
                    total_pages = max(1, int(total_pages))
                    remaining = [p for p in range(1, total_pages + 1) if p not in fetched_pages_now]
                    next_page = remaining[0] if remaining else None
                    has_more = bool(remaining)
                else:
                    total_pages = None
                    next_page = latest_pag.get("next_page")
                    has_more = latest_pag.get("has_more")

                set_pagination(
                    actress_id,
                    has_more=has_more,
                    next_page=next_page,
                    pages_scraped=int(latest_pag.get("pages_scraped", 0) or 0),
                    pages_loaded=pages_loaded_now,
                    total_pages=total_pages,
                    fetched_pages=fetched_pages_now,
                )
                save_pagination_state(
                    actress_id,
                    pages_loaded=pages_loaded_now,
                    next_page=next_page,
                    has_more=has_more,
                    total_pages=total_pages,
                    fetched_pages=fetched_pages_now,
                )

                latest_pag, latest_fetched, latest_limit = _refresh_dialog_state()
                if latest_pag.get("total_pages"):
                    if next_page and next_page not in selection[0]:
                        selection[0].add(next_page)
                        page_inp.value = _selection_to_text(selection[0])
                        _update_fetch_btn()
                    _render_quick_pages(latest_fetched, selection[0], latest_limit)
                    ui.notify(f"JAVLibrary shows {latest_pag['total_pages']} page(s)", color="positive")
                else:
                    _render_quick_pages(latest_fetched, selection[0], latest_limit)
                    ui.notify("JAVLibrary did not expose a page count for this actress", color="info")

            # ── Submit ────────────────────────────────────────────────
            async def _submit_pages() -> None:
                pages = sorted(selection[0])
                if not pages:
                    ui.notify("Select at least one page", color="warning")
                    return
                dlg.close()
                await _fetch_pages_for_actress(
                    actress_id, pages, silent=False, skip_deleted=_skip_deleted_ref[0]
                )

            # ── Skip deleted ──────────────────────────────────────────
            if _deleted_for_actress:
                _skip_cb = ui.checkbox(
                    f"Skip {len(_deleted_for_actress)} previously deleted video(s)",
                    value=True,
                ).style("margin-top:8px;font-size:0.8rem")

                def _on_skip_toggle(v):
                    _skip_deleted_ref[0] = v

                _skip_cb.on("update:model-value", _on_skip_toggle)

            # ── Action row ────────────────────────────────────────────
            with ui.row().classes("gap-2 items-center w-full").style("margin-top:12px"):
                ui.button(
                    "Check Total Pages", icon="rule", on_click=_check_total_pages
                ).props("flat size=sm").style("color:#f59e0b")
                ui.element("div").classes("flex-1")
                ui.button("Cancel", on_click=dlg.close).props("flat size=sm").style(
                    "color:#6b7280"
                )
                fetch_btn = (
                    ui.button("Fetch Pages", icon="travel_explore", on_click=_submit_pages)
                    .props("unelevated size=sm")
                    .style("background:#d97706;color:#fff")
                )

            # ── Interaction logic (defined after all UI elements) ─────
            def _update_fetch_btn() -> None:
                n = len(selection[0])
                if n == 0:
                    fetch_btn.set_text("Select Pages")
                    fetch_btn.disable()
                elif n == 1:
                    p = min(selection[0])
                    fetch_btn.set_text(f"Fetch Page {p}")
                    fetch_btn.enable()
                else:
                    fetch_btn.set_text(f"Fetch {n} Pages")
                    fetch_btn.enable()

            def _toggle_page(page: int) -> None:
                if page in selection[0]:
                    selection[0].discard(page)
                else:
                    selection[0].add(page)
                page_inp.value = _selection_to_text(selection[0])
                _, fetched, limit = _refresh_dialog_state()
                _render_quick_pages(fetched, selection[0], limit)
                _update_fetch_btn()

            def _clear_selection() -> None:
                selection[0].clear()
                page_inp.value = ""
                _, fetched, limit = _refresh_dialog_state()
                _render_quick_pages(fetched, selection[0], limit)
                _update_fetch_btn()

            def _coerce_input_value(event_or_value) -> str:
                value = getattr(event_or_value, "value", None)
                if value is None:
                    sender = getattr(event_or_value, "sender", None)
                    value = getattr(sender, "value", event_or_value)
                return str(value or "")

            def _on_input_change(v) -> None:
                raw = str(page_inp.value or "")
                if not raw:
                    raw = _coerce_input_value(v)
                selection[0] = _parse_page_text(raw)
                # Skip expensive grid rebuild while mid-typing a range/list
                if raw.endswith(("-", ",")):
                    _update_fetch_btn()
                    return
                _, fetched, limit = _refresh_dialog_state()
                _render_quick_pages(fetched, selection[0], limit)
                _update_fetch_btn()

            page_inp.on_value_change(_on_input_change)
            page_inp.on("input", _on_input_change)
            page_inp.on("keyup", _on_input_change)
            page_inp.on("change", _on_input_change)
            page_inp.on("update:model-value", _on_input_change)

            # ── Initial render ────────────────────────────────────────
            _, fetched_pages, detected_limit = _refresh_dialog_state()
            _render_quick_pages(fetched_pages, selection[0], detected_limit)
            _update_fetch_btn()

        dlg.open()

    async def _do_refresh_all(skip_deleted: bool) -> None:
        """Check page 1 of every tracked actress for new releases only."""
        data = load_tracker()
        ids = list(data["actresses"].keys())
        if not ids:
            ui.notify("No actresses to check", color="info")
            return

        worker_count = _cover_queue.worker_count_for_source("javlibrary", len(ids))
        total_new = 0
        progress_lbl.set_text(f"Checking 0 / {len(ids)} …")

        for actress_id in ids:
            _SCRAPING_IDS.add(actress_id)
            _refresh_actress_row(actress_id)

        sem = asyncio.Semaphore(worker_count)

        async def _run_probe(actress_id: str) -> tuple[str, dict | None, Exception | None]:
            async with sem:
                try:
                    snapshot = await _probe_new_release_page(
                        actress_id,
                        skip_deleted=skip_deleted,
                    )
                    return actress_id, snapshot, None
                except Exception as exc:
                    return actress_id, None, exc

        completed = 0
        tasks = [asyncio.create_task(_run_probe(actress_id)) for actress_id in ids]
        for task in asyncio.as_completed(tasks):
            actress_id, snapshot, error = await task
            completed += 1
            progress_lbl.set_text(f"Checking {completed} / {len(ids)} …")

            try:
                if error is not None:
                    cooldown_seconds = get_rate_limit_cooldown_seconds(error)
                    if cooldown_seconds is not None:
                        ui.notify(
                            f"JAVLibrary cooling down for ~{cooldown_seconds}s. New-release probe queued in memory.",
                            color="warning",
                            timeout=5000,
                        )
                    else:
                        ui.notify(f"Page fetch failed: {error}", color="negative", timeout=8000)
                    continue
                if snapshot is not None:
                    total_new += _apply_new_release_probe(snapshot)
            finally:
                _SCRAPING_IDS.discard(actress_id)
                _refresh_actress_row(actress_id)

        progress_lbl.set_text("")
        if total_new:
            ui.notify(f"Found {total_new} new release(s) across all actresses", color="positive")
        else:
            ui.notify("No new releases found", color="info")

    async def _refresh_all() -> None:
        """Prompt if deleted refs exist, then delegate to _do_refresh_all."""
        all_deleted = get_all_deleted_refs()
        if not all_deleted:
            await _do_refresh_all(skip_deleted=True)
            return

        skip_cb_ref: list[bool] = [True]
        javlibrary_slots = _cover_queue.worker_count_for_source(
            "javlibrary",
            len(load_tracker()["actresses"]),
        )
        with (
            ui.dialog() as dlg,
            ui.card().style(
                "min-width:340px;background:#0f0f13;border:1px solid #1a1a24"
            ),
        ):
            ui.label("Check New Releases").style(
                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:8px"
            )
            ui.label(
                f"You have {len(all_deleted)} previously deleted video(s) on record."
            ).style("font-size:0.82rem;color:#9ca3af;margin-bottom:4px")
            ui.label(
                f"This refresh will use up to {javlibrary_slots} JAVLibrary slot(s) from Downloader settings."
            ).style("font-size:0.76rem;color:#f59e0b;margin-bottom:8px")
            skip_cb = ui.checkbox("Skip previously deleted videos", value=True).style(
                "margin-bottom:12px"
            )
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button("Cancel", on_click=dlg.close).props("flat size=sm").style(
                    "color:#6b7280"
                )

                async def _run():
                    dlg.close()
                    await _do_refresh_all(skip_deleted=skip_cb.value)

                ui.button("Check", icon="new_releases", on_click=_run).props(
                    "unelevated size=sm"
                ).style("background:#d97706;color:#fff")
        dlg.open()

    def _confirm_remove_video(actress_id: str, ref: str) -> None:
        data = load_tracker()
        actress = data["actresses"].get(actress_id, {})
        video = next(
            (
                _vmerge(v, data.get("videos", {}))
                for v in actress.get("videos", [])
                if str(v.get("ref", "")).strip().upper() == str(ref).strip().upper()
            ),
            None,
        )
        ref_up = str(ref or "").strip().upper()
        title = str((video or {}).get("title", "") or "").strip()

        # Other tracker actresses that also have this ref
        other_actress_ids = [
            aid for aid, a in data["actresses"].items()
            if aid != actress_id
            and any(v.get("ref", "").upper() == ref_up for v in a.get("videos", []))
        ]
        is_shared = bool(other_actress_ids)

        # Is this ref alive in the downloader session?
        in_downloader = ref_up in get_downloader_refs(app.storage.user)

        # Full asset deletion is only safe when removing this ref leaves 0 total references.
        # "Total references" = tracker entries + downloader entry (if any).
        # Removing "this actress only" leaves (other tracker entries) + downloader.
        # Removing "all actresses" leaves 0 tracker entries + downloader.
        can_full_delete_single = (not is_shared) and (not in_downloader)
        can_full_delete_all = not in_downloader  # safe only when downloader won't need assets

        with (
            ui.dialog() as dlg,
            ui.card().style(
                "min-width:360px;background:#0f0f13;border:1px solid #1a1a24"
            ),
        ):
            ui.label(f"Remove {ref_up} from tracker?").style(
                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:4px"
            )
            if title:
                ui.label(title).style(
                    "font-size:0.78rem;color:#9ca3af;margin-bottom:4px"
                )

            # Context message
            if is_shared:
                shared_count = len(other_actress_ids)
                word = "actress" if shared_count == 1 else "actresses"
                msg = f"Also tracked by {shared_count} other {word}."
                if in_downloader:
                    msg += " Also in downloader queue — assets will be preserved."
                ui.label(msg).style("font-size:0.8rem;color:#fbbf24;margin-bottom:16px")
            elif in_downloader:
                ui.label(
                    "This ref is also in the downloader queue — cover and metadata will be preserved."
                ).style("font-size:0.8rem;color:#fbbf24;margin-bottom:16px")
            else:
                ui.label(
                    "This is the only reference to this video. "
                    "You can remove from tracker only, or also delete the cached assets."
                ).style("font-size:0.8rem;color:#6b7280;margin-bottom:16px")

            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button("Cancel", on_click=dlg.close).props("flat size=sm").style(
                    "color:#6b7280"
                )

                def _do_remove_this(*, _delete_assets: bool) -> None:
                    removed = delete_video_from_actress(actress_id, ref_up)
                    if not removed:
                        dlg.close()
                        ui.notify(f"{ref_up} is no longer in the tracker list", color="warning")
                        return
                    record_deleted_ref(actress_id, ref_up, globally=False)
                    if _delete_assets:
                        prune_orphaned_refs(app.storage.user, [ref_up])
                    if selected_video_ref[0] and selected_video_ref[0].upper() == ref_up:
                        selected_video_ref[0] = None
                    dlg.close()
                    _refresh_actress_row(actress_id)
                    if selected_id_ref[0] == actress_id:
                        _refresh_right_panel()

                if is_shared:
                    # Always offer "this actress only" (soft — other actresses still reference it)
                    ui.button("This actress only", on_click=lambda: _do_remove_this(_delete_assets=False)).props(
                        "flat size=sm"
                    ).style("color:#ef4444").tooltip(
                        "Removes from this actress only — assets kept"
                    )

                    _other_ids = list(other_actress_ids)

                    def _do_remove_all(*, _delete_assets: bool) -> None:
                        all_with_ref = [actress_id] + _other_ids
                        for aid in all_with_ref:
                            delete_video_from_actress(aid, ref_up)
                        record_deleted_ref(None, ref_up, globally=True)
                        if _delete_assets:
                            prune_orphaned_refs(app.storage.user, [ref_up])
                        if selected_video_ref[0] and selected_video_ref[0].upper() == ref_up:
                            selected_video_ref[0] = None
                        dlg.close()
                        _rebuild_left_list()
                        if selected_id_ref[0] in all_with_ref:
                            _refresh_right_panel()

                    if can_full_delete_all:
                        ui.button("All actresses + delete assets", on_click=lambda: _do_remove_all(_delete_assets=True)).props(
                            "flat size=sm"
                        ).style("color:#dc2626").tooltip(
                            "Removes from every actress and deletes the cached cover & metadata"
                        )
                    else:
                        # Downloader still has the ref — soft removal only
                        ui.button("All actresses", on_click=lambda: _do_remove_all(_delete_assets=False)).props(
                            "flat size=sm"
                        ).style("color:#ef4444").tooltip(
                            "Removes from every actress in Tracker — assets kept for downloader"
                        )
                else:
                    # Solo video
                    if can_full_delete_single:
                        # Last reference — offer both options
                        ui.button("Tracker only", on_click=lambda: _do_remove_this(_delete_assets=False)).props(
                            "flat size=sm"
                        ).style("color:#ef4444").tooltip("Keep cover and metadata on disk")
                        ui.button("Remove + delete assets", on_click=lambda: _do_remove_this(_delete_assets=True)).props(
                            "flat size=sm"
                        ).style("color:#dc2626").tooltip("Also deletes cached cover and metadata")
                    else:
                        # In downloader — soft remove only
                        ui.button("Remove from tracker", on_click=lambda: _do_remove_this(_delete_assets=False)).props(
                            "flat size=sm"
                        ).style("color:#ef4444")
        dlg.open()

    async def _queue_ref(ref: str, actress_id: str) -> None:
        # ── Pre-populate downloader JAV cache so it skips re-scraping ──
        # The tracker already has title, date, and optionally full metadata
        # (actresses, studio, genres) from a prior deep-fetch. Feed that into the
        # downloader JAV cache so _fetch_one() returns immediately without hitting
        # the scraper again.
        _tracker_data_q = load_tracker()
        _actress_entry_q = _tracker_data_q["actresses"].get(actress_id, {})
        _vd_q = _tracker_data_q.get("videos", {})
        _video_entry_q = next(
            (
                _vmerge(v, _vd_q)
                for v in _actress_entry_q.get("videos", [])
                if v["ref"].upper() == ref.upper()
            ),
            None,
        )
        if _video_entry_q:
            _vmeta = _video_entry_q.get("_meta") or {}
            # Determine actress list: prefer deep-fetched list, fall back to
            # the single tracked actress name.
            _actress_names = _vmeta.get("actresses") or (
                [_actress_entry_q["name"]] if _actress_entry_q.get("name") else []
            )
            _cached_jav = {
                "title": _vmeta.get("title") or _video_entry_q.get("title", ""),
                "cover_url": (
                    f"/api/cover?ref={ref.upper()}"
                    if cover_exists(ref)
                    else _video_entry_q.get("cover_url", "")
                ),
                "id": ref.upper(),
                "date": _video_entry_q.get("date", ""),
                "studio": _vmeta.get("studio", ""),
                "actresses": _actress_names,
                "genres": _vmeta.get("genres", []),
            }
            # Only cache if there is at least a title or an actress name —
            if _cached_jav["title"] or _cached_jav["actresses"]:
                upsert_downloader_cache_entry(ref, {"jav": _cached_jav})

            # If studio/genres are missing (no deep-fetch yet), kick one off in
            # the background. The fetch writes to tracker.json and jav_dl_cache,
            # so the downloader gets full data when it processes
            # the ref (or on the next inspector open if processing already ran).
            if not _vmeta.get("studio") and not _vmeta.get("genres"):
                asyncio.create_task(_fetch_and_cache_video_meta(ref, actress_id))
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post(
                    "http://localhost:8765/api/queue",
                    json={"refs": [ref]},
                    timeout=5.0,
                )
            if r.status_code == 200:
                ui.notify(f"{ref} added to queue", color="positive", timeout=2500)
                mark_seen(actress_id, [ref])
                # Optimistically insert into the shared session queue so the badge
                # renders immediately — the downloader will overwrite this entry with
                # full metadata when it next processes _ext_ref_queue.
                if not any(item["kw"].upper() == ref.upper() for item in load_downloader_queue()):
                    append_downloader_queue_stub(
                        ref,
                        downloaded=is_ref_downloaded_globally(ref),
                    )
                _rebuild_left_list()
                if actress_id in actress_row_els:
                    actress_row_els[actress_id].classes(add="active-row")
                _refresh_video_rows(
                    actress_id,
                    [ref],
                    allow_membership_change=filter_ref[0] == "unseen",
                )
            else:
                ui.notify(f"Queue API error {r.status_code}", color="warning")
        except Exception as exc:
            ui.notify(f"Failed to add {ref} to queue: {exc}", color="negative")

    async def _fetch_and_cache_video_meta(ref: str, actress_id: str) -> "dict | None":
        """
        Core metadata fetch: scrape ref, persist _meta to tracker.json, and write
        to jav_dl_cache so the downloader can use the
        result without re-scraping.

        Returns the metadata dict on success, None on failure.
        Silent — no UI notifications. The caller decides how to surface results.
        """
        source = resolve_metadata_source()

        meta = None
        _fetch_error: "Exception | None" = None
        try:
            meta = await fetch_jav_metadata(ref, source=source)
        except Exception as exc:
            _fetch_error = exc
            print(f"[TRACKER] fetch_jav_metadata failed for {ref} (source={source}): {exc!r}", flush=True)
            meta = None

        keep_latest_cover(ref)

        if not isinstance(meta, dict) or not meta:
            # Attach the original exception so callers can show a useful message
            raise RuntimeError(
                repr(_fetch_error) if _fetch_error else f"Empty result from {source}"
            ) from _fetch_error

        # Persist to tracker.json
        save_video_meta(actress_id, ref, meta)

        # Downloader cache so the downloader skips re-scraping
        upsert_downloader_cache_entry(
            ref,
            {
                "jav": meta,
            },
        )

        return meta

    async def _deep_fetch_video(ref: str, actress_id: str, btn) -> None:
        """
        Fetch full JAV metadata for a single video ref.
                Mirrors the downloader metadata fetch path exactly:
          - same shared SCRAPER_SEM (one request at a time, 2 s cooldown)
          - same proxy rotation (built into search_javdb via _load_proxies())
                    - same 403 sleep-and-retry for JavDB
        Result is persisted to tracker.json and cached in app.storage.user
        so the downloader can reuse it without re-scraping.
        """
        btn.props("loading=true disable=true")
        try:
            # Delete any existing cover so the scraper always writes a fresh one.
            delete_cover(ref)

            meta = await _fetch_and_cache_video_meta(ref, actress_id)

            actresses = meta.get("actresses", [])
            label = ", ".join(actresses) if actresses else "Solo"
            solo = len(actresses) <= 1
            with client:
                ui.notify(
                    f"{ref}: {label}"
                    + (" — solo" if solo else f" ({len(actresses)} actresses)"),
                    color="positive",
                    timeout=4000,
                )
                import time as _time

                _cover_busted[ref.upper()] = int(_time.time())
                _refresh_video_rows(actress_id, [ref], refresh_cover=True)
        except Exception as exc:
            print(f"[TRACKER] _deep_fetch_video failed for {ref}: {exc!r}", flush=True)
            try:
                with client:
                    ui.notify(
                        f"Could not fetch metadata for {ref}: {exc!r}",
                        color="negative",
                        timeout=6000,
                    )
            except Exception:
                pass
        finally:
            try:
                btn.props("loading=false disable=false")
            except Exception:
                pass  # btn deleted when panel rebuilt — that's fine

    def _confirm_delete(actress_id: str) -> None:
        data = load_tracker()
        name = data["actresses"].get(actress_id, {}).get("name") or actress_id
        with (
            ui.dialog() as dlg,
            ui.card().style(
                "min-width:340px;background:#0f0f13;border:1px solid #1a1a24"
            ),
        ):
            ui.label(f'Remove "{name}"?').style(
                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:4px"
            )
            ui.label("No files are deleted from disk.").style(
                "font-size:0.8rem;color:#6b7280;margin-bottom:16px"
            )
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button("Cancel", on_click=dlg.close).props("flat size=sm").style(
                    "color:#6b7280"
                )

                def _do_delete():
                    removed_refs = delete_actress(actress_id)
                    clear_pagination(actress_id)
                    prune_orphaned_refs(app.storage.user, removed_refs)
                    dlg.close()
                    if selected_id_ref[0] == actress_id:
                        selected_id_ref[0] = None
                        right_col.clear()
                        _build_empty_right()
                    actress_row_els.pop(actress_id, None)
                    _rebuild_left_list()

                ui.button("Remove", on_click=_do_delete).props("flat size=sm").style(
                    "color:#ef4444"
                )
        dlg.open()

    def _open_add_dialog() -> None:
        with (
            ui.dialog() as dlg,
            ui.card().style(
                "min-width:440px;background:#0f0f13;border:1px solid #1a1a24"
            ),
        ):
            ui.label("Add Actress").style(
                "font-size:0.95rem;font-weight:700;color:#f1f5f9;margin-bottom:4px"
            )
            ui.label(
                "Paste the JAVLibrary actress page URL\n"
                "e.g. https://www.javlibrary.com/tw/vl_star.php?s=aadd6"
            ).style(
                "font-size:0.75rem;color:#6b7280;white-space:pre-line;margin-bottom:12px"
            )
            url_inp = (
                ui.input(placeholder="https://www.javlibrary.com/tw/vl_star.php?s=…")
                .classes("w-full")
                .props("outlined dense")
            )

            async def _do_add():
                url = url_inp.value.strip()
                actress_id = actress_id_from_url(url)
                if not actress_id:
                    ui.notify(
                        "Invalid URL — must contain ?s= parameter", color="negative"
                    )
                    return
                add_actress(url)
                dlg.close()
                _rebuild_left_list()
                _select_actress(actress_id)
                # Scrape page 1 on first add, then let the user fetch/refetch specific pages.
                await _scrape_actress(actress_id, first_add=True)

            with ui.row().classes("gap-2 justify-end w-full").style("margin-top:12px"):
                ui.button("Cancel", on_click=dlg.close).props("flat size=sm").style(
                    "color:#6b7280"
                )
                ui.button(
                    "Add & Scrape",
                    icon="add",
                    on_click=lambda: _do_add(),
                ).props("unelevated size=sm").style("background:#d97706;color:#fff")
        dlg.open()

    def _on_save_tracker(
        cover_w: int,
        left_panel_w: int = _DEFAULT_LEFT_W,
        auto_inactive_enabled: bool = True,
        inactive_months: int = 6,
    ) -> None:
        panel_w_ref[0] = left_panel_w  # keep in sync for any future rebuilds
        set_tracker_left_panel_width(left_panel_w)
        recalculate_all_inactive_statuses()
        _rebuild_left_list()
        if selected_id_ref[0] and selected_id_ref[0] in actress_row_els:
            actress_row_els[selected_id_ref[0]].classes(add="active-row")
        _refresh_right_panel()

    settings_dialog = _build_settings_dialog(
        accent="#d97706",
        on_save_tracker=_on_save_tracker,
        save_state_key="tracker",
    )

    # ── Build layout ──────────────────────────────────────────────────────────

    # Header
    with ui.header().classes("trk-header text-white px-6 items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="home").props("flat round size=sm").style(
                "color:#fbbf24"
            ).tooltip("Back to Launchpad").on("click", lambda: ui.navigate.to("/"))
            ui.html(
                '<span class="trk-logo" style="cursor:pointer" '
                'onclick="window.location=\'/\'" title="Home">JAV Video System</span>'
            )
            build_save_state_badge("tracker", resolver=lambda: [TRACKER_FILE, TRACKER_UI_STATE_FILE, CONFIG_FILE])

        with ui.row().classes("items-center gap-4"):
            progress_lbl = ui.label("").classes("trk-progress")

            ui.button(
                "Check New Releases",
                icon="new_releases",
                on_click=lambda: _refresh_all(),
            ).props("flat size=sm").style("color:#fbbf24;font-size:0.78rem").tooltip(
                "Checks page 1 of every tracked actress for new releases. "
                "Fetches covers & metadata only for newly-found videos."
            )

            ui.button(
                icon="settings",
                on_click=settings_dialog.open,
            ).props("flat round size=sm").style("color:#fbbf24").tooltip("Settings")

            ui.button(
                "+ Add",
                icon="person_add",
                on_click=_open_add_dialog,
            ).props("unelevated size=sm").style(
                "background:#d97706;color:#fff;font-size:0.78rem"
            )

    # Body
    with (
        ui.row()
        .classes("trk-shell w-full gap-0 items-stretch")
        .style(
            "flex-wrap:nowrap;min-height:0;overflow:hidden;height:calc(100vh - 60px)"
        )
    ):
        # Left panel
        with (
            ui.element("div")
            .classes("trk-left trk-left-panel")
            .style(f"width:{panel_w_ref[0]}px")
        ):
            with ui.element("div").classes("trk-section-header"):
                ui.html("ACTRESSES")

            # ── Search + Sort bar ─────────────────────────────────────────────
            with ui.element("div").classes("trk-search-bar"):
                with (
                    ui.row()
                    .classes("items-center justify-between gap-1")
                    .style("margin-bottom:4px")
                ):
                    ui.label("Search").style("font-size:0.65rem;color:#6b7280")
                    # NiceGUI's ui.toggle with a dict can emit the numeric index
                    # (as int or str) rather than the key — map both forms.
                    _TOGGLE_MODE_MAP = {
                        "actress": "actress",
                        "ref": "ref",
                        0: "actress",
                        1: "ref",
                        "0": "actress",
                        "1": "ref",
                    }
                    _mode_toggle = (
                        ui.toggle(
                            {"actress": "Name", "ref": "Ref"},
                            value=search_mode_ref[0],
                        )
                        .props("dense color=amber")
                        .style("font-size:0.65rem")
                    )
                    _mode_toggle.on_value_change(
                        lambda e: _set_search_mode(
                            _TOGGLE_MODE_MAP.get(
                                e.value, _TOGGLE_MODE_MAP.get(str(e.value), "actress")
                            )
                        )
                    )

                def _on_search(e):
                    search_ref[0] = str(e.value).strip() if e.value else ""
                    print(
                        f"[SEARCH] value={e.value!r}  stored={search_ref[0]!r}  mode={search_mode_ref[0]!r}",
                        flush=True,
                    )
                    _rebuild_left_list()
                    if selected_id_ref[0] and selected_id_ref[0] in actress_row_els:
                        actress_row_els[selected_id_ref[0]].classes(add="active-row")

                search_inp = (
                    ui.input(
                        placeholder="Search actress…",
                        on_change=_on_search,
                    )
                    .props("outlined dense clearable autocomplete=off")
                    .style("width:100%")
                )
                search_inp_ref.append(search_inp)

                # Sort chips (hidden in ref search mode)
                _sort_opts = [
                    ("az", "A→Z"),
                    ("za", "Z→A"),
                    ("unseen", "Unseen"),
                    ("rating", "Rating"),
                    ("scraped", "Recent"),
                ]
                with ui.element("div").classes("trk-sort-row") as _sort_row_el:
                    for _sk, _sl in _sort_opts:
                        _active_cls = " active" if sort_ref[0] == _sk else ""
                        ui.html(
                            f'<span class="trk-sort-chip{_active_cls}">{_sl}</span>'
                        ).on(
                            "click",
                            lambda k=_sk: _set_sort(k),
                        )
                sort_row_ref.append(_sort_row_el)

            with ui.element("div").classes("trk-list-wrap") as trk_list_wrap:
                pass  # populated by _rebuild_left_list()

        # Right panel
        with ui.element("div").classes("trk-right") as right_col:
            pass  # populated by _refresh_right_panel()

    # Migrate old float star ratings to None (one-time, idempotent)
    migrate_ratings_to_score()
    recalculate_all_inactive_statuses()

    # Initial render
    _rebuild_left_list()
    _build_empty_right()

    def _apply_tracker_ref_jump(ref: str) -> bool:
        ref_up = str(ref or "").strip().upper()
        if not ref_up:
            return False

        search_mode_ref[0] = "ref"
        search_ref[0] = ref_up
        filter_ref[0] = "all"
        selected_video_ref[0] = None
        if search_inp_ref:
            search_inp_ref[0].value = ref_up
            search_inp_ref[0].props('placeholder="Search ref code… (e.g. SONE)"')
        if sort_row_ref:
            sort_row_ref[0].style("display:none")

        data = load_tracker()
        for actress_id, actress in data.get("actresses", {}).items():
            for video in actress.get("videos", []):
                if str(video.get("ref", "")).strip().upper() != ref_up:
                    continue
                _rebuild_left_list()
                _select_actress_video(actress_id, ref_up)
                return True

        _rebuild_left_list()
        _build_empty_right()
        return False

    # ── Jump-to-actress from downloader: if the downloader sent us here by
    # clicking an actress chip, that actress's ID is stored in session.
    # Select her now that actress_row_els is fully populated.
    _jump_ref = app.storage.user.get("_tracker_jump_ref")
    if _jump_ref:
        try:
            del app.storage.user["_tracker_jump_ref"]
        except Exception:
            pass
        _apply_tracker_ref_jump(_jump_ref)

    _jump_id = app.storage.user.get("_tracker_jump_actress_id")
    if _jump_id and not selected_id_ref[0]:
        try:
            del app.storage.user["_tracker_jump_actress_id"]
        except Exception:
            pass
        if _jump_id in actress_row_els:
            _select_actress(_jump_id)
    # Restore persisted page-fetch state after restart.
    _init_data = load_tracker()
    for _aid, _actress in _init_data.get("actresses", {}).items():
        _pl = _actress.get("pages_loaded", 0)
        _np = _actress.get("next_page")
        _hm = _actress.get("has_more", False)
        _tp = _actress.get("total_pages")
        _fp = _actress.get("fetched_pages") or []
        if not _fp and _pl:
            _fp = list(range(1, int(_pl) + 1))
        if _pl > 0 or _hm:
            set_pagination(
                _aid,
                has_more=_hm,
                next_page=_np,
                pages_scraped=_pl,
                pages_loaded=_pl,
                total_pages=_tp,
                fetched_pages=_fp,
            )
