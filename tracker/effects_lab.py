import json
from pathlib import Path

from nicegui import Client, ui

from tracker.pixi_badges import pixi_badge_host, pixi_badge_runtime_html
from utils.ui_ratings import DEFAULT_RATING_THRESHOLDS, TIER_LABELS, TIER_ORDER


RANK_META = {
        'diamond': {
                'theme': 'God-tier cosmic charge with a white-hot center and deep indigo falloff.',
                'shape': 'Faceted diamond core with long tapered rays and celestial framing.',
                'motion': 'Slow rotational authority plus intermittent surge pulses.',
                'emission': 'Layered radial glow, lens-flare streaks, and airy plasma drift.',
        },
        'ruby': {
                'theme': 'Violent heat and blood-red pressure.',
                'shape': 'Sharp crown silhouette with hostile spike logic.',
                'motion': 'Aggressive pulse and short pressure bursts.',
                'emission': 'Hot bloom and jagged flame petals rather than noble rays.',
        },
        'sapphire': {
                'theme': 'Stable cold power with controlled intensity.',
                'shape': 'Clean shard geometry with disciplined edge clarity.',
                'motion': 'Steady orbit with occasional bright flash moments.',
                'emission': 'Crystalline ribbons and cold rings instead of flames.',
        },
        'amethyst': {
                'theme': 'Occult resonance and ritual charge.',
                'shape': 'Hex-seal medallion with subtle rune spokes.',
                'motion': 'Trance-like rotation and echo ripples.',
                'emission': 'Smoky translucent gradients with interference rings.',
        },
        'emerald': {
                'theme': 'Living force, more cultivated than explosive.',
                'shape': 'Circular seal with leaf-like slivers and soft perimeter life.',
                'motion': 'Breathing expansion with disciplined ripple response.',
                'emission': 'Smooth aura shell with rising motes.',
        },
        'gold': {
                'theme': 'Medal energy with solar authority.',
                'shape': 'Round medallion with restrained sunburst logic.',
                'motion': 'Measured pulse and shimmer sweep.',
                'emission': 'Gilded halo with limited sparkles.',
        },
        'topaz': {
                'theme': 'Narrow spark and situational warning energy.',
                'shape': 'Beveled square seal with cut edges.',
                'motion': 'Slow flicker with intermittent edge sweep.',
                'emission': 'Thin electric seams, not a full aura bloom.',
        },
        'silver': {
                'theme': 'Low-heat metallic drift.',
                'shape': 'Circular plate with reflective restraint.',
                'motion': 'Subtle shimmer only.',
                'emission': 'Reflective glints and sparse aura mass.',
        },
        'aquamarine': {
                'theme': 'Weak current and waterline tension.',
                'shape': 'Shield geometry with gentle concentric contours.',
                'motion': 'Small ripple cycles and current drift.',
                'emission': 'Translucent wave contours instead of sparks.',
        },
        'jade': {
                'theme': 'Dull static life with low urgency.',
                'shape': 'Restrained shield with soft perimeter haze.',
                'motion': 'Barely-there pulse.',
                'emission': 'Thin fog halo only.',
        },
        'garnet': {
                'theme': 'Hostile pressure and unstable collapse.',
                'shape': 'Cracked shield with broken fragments.',
                'motion': 'Twitch, surge, and collapse recoil.',
                'emission': 'Short-lived spark spits, no grandeur.',
        },
        'onyx': {
                'theme': 'Dead zone, heavy and unwelcoming.',
                'shape': 'Dense slab with no ornamental optimism.',
                'motion': 'Almost none.',
                'emission': 'Weak murky shadow by design.',
        },
        'low': {
                'theme': 'Failure / void.',
                'shape': 'Flat scarred plate that feels intentionally defeated.',
                'motion': 'None.',
                'emission': 'Absent by design.',
        },
}

DEFAULT_CONTROLS = {
    'diamond': {'energy': 1.18, 'motion': 1.08, 'particles': 0.94, 'contrast': 1.12},
    'ruby': {'energy': 1.08, 'motion': 1.28, 'particles': 0.82, 'contrast': 1.06},
    'sapphire': {'energy': 0.98, 'motion': 0.84, 'particles': 0.54, 'contrast': 1.04},
        'amethyst': {'energy': 0.9, 'motion': 0.78, 'particles': 0.64, 'contrast': 0.98},
        'emerald': {'energy': 0.88, 'motion': 0.74, 'particles': 0.58, 'contrast': 0.98},
        'gold': {'energy': 0.84, 'motion': 0.68, 'particles': 0.48, 'contrast': 0.96},
        'topaz': {'energy': 0.76, 'motion': 0.62, 'particles': 0.32, 'contrast': 0.94},
        'silver': {'energy': 0.68, 'motion': 0.48, 'particles': 0.2, 'contrast': 0.92},
        'aquamarine': {'energy': 0.72, 'motion': 0.56, 'particles': 0.3, 'contrast': 0.94},
        'jade': {'energy': 0.58, 'motion': 0.38, 'particles': 0.14, 'contrast': 0.9},
        'garnet': {'energy': 0.7, 'motion': 0.82, 'particles': 0.36, 'contrast': 0.96},
        'onyx': {'energy': 0.36, 'motion': 0.22, 'particles': 0.04, 'contrast': 0.88},
        'low': {'energy': 0.18, 'motion': 0.0, 'particles': 0.0, 'contrast': 0.86},
}

DEFAULT_SCORES = {**DEFAULT_RATING_THRESHOLDS, 'low': 24}
TOP_TIER_RANKS = ('diamond', 'ruby', 'sapphire')


def _focus_card(rank: str) -> str:
        label = TIER_LABELS[rank]
        controls = {'controls': DEFAULT_CONTROLS[rank]}
        meta = RANK_META[rank]
        return f'''
        <button class="fxlab-focus-card" type="button" data-focus-rank="{rank}">
            <div class="fxlab-focus-badge">{pixi_badge_host(DEFAULT_SCORES[rank], size=136, variant=rank, options=controls, extra_classes='fxlab-focus-host')}</div>
            <div class="fxlab-focus-name">{label}</div>
            <div class="fxlab-focus-copy">{meta['motion']}</div>
            <div class="fxlab-focus-copy">{meta['emission']}</div>
        </button>
        '''


def _gallery_card(rank: str) -> str:
        label = TIER_LABELS[rank]
        controls = {'controls': DEFAULT_CONTROLS[rank]}
        return f'''
        <button class="fxlab-rank-card" type="button" data-rank-card="{rank}">
            <div class="fxlab-rank-badge">{pixi_badge_host(DEFAULT_SCORES[rank], size=104, variant=rank, options=controls, extra_classes='fxlab-gallery-host')}</div>
            <div class="fxlab-rank-name">{label}</div>
            <div class="fxlab-rank-theme">{RANK_META[rank]['theme']}</div>
        </button>
        '''


@ui.page('/tracker-effects-lab')
async def tracker_effects_lab(client: Client) -> None:
    ui.add_head_html('<meta charset="utf-8">')
    ui.add_head_html(f"<style>{Path('assets/theme.css').read_text(encoding='utf-8')}</style>")
    ui.add_head_html(pixi_badge_runtime_html())
    ui.add_head_html('''
        <style>
            .fxlab-root {
                min-height: 100vh;
                padding: 28px;
                color: #ecf6ff;
                background:
                    radial-gradient(circle at top left, rgba(56, 189, 248, 0.14), transparent 26%),
                    radial-gradient(circle at 80% 0%, rgba(244, 114, 182, 0.12), transparent 24%),
                    linear-gradient(180deg, #04070d 0%, #08101c 52%, #05070c 100%);
            }
            .fxlab-shell { max-width: 1440px; margin: 0 auto; }
            .fxlab-top {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 18px;
                margin-bottom: 22px;
            }
            .fxlab-kicker {
                color: #7dd3fc;
                font-size: 0.72rem;
                letter-spacing: 0.18em;
                text-transform: uppercase;
                font-weight: 800;
                margin-bottom: 10px;
            }
            .fxlab-title {
                margin: 0;
                font-size: clamp(1.6rem, 2.4vw, 2.4rem);
                line-height: 1.03;
                letter-spacing: -0.03em;
                font-weight: 900;
                max-width: 10ch;
            }
            .fxlab-sub {
                margin-top: 10px;
                max-width: 840px;
                color: #93a9c3;
                line-height: 1.6;
                font-size: 0.95rem;
            }
            .fxlab-back {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                padding: 11px 16px;
                border-radius: 999px;
                text-decoration: none;
                color: #eaf4ff;
                border: 1px solid rgba(125, 211, 252, 0.22);
                background: rgba(10, 17, 31, 0.72);
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
            }
            .fxlab-layout {
                display: grid;
                grid-template-columns: 330px minmax(0, 1fr);
                gap: 20px;
                align-items: start;
            }
            .fxlab-card {
                background: linear-gradient(180deg, rgba(10, 16, 29, 0.92), rgba(6, 10, 20, 0.98));
                border: 1px solid rgba(134, 168, 214, 0.14);
                border-radius: 24px;
                box-shadow: 0 26px 90px rgba(0, 0, 0, 0.32);
            }
            .fxlab-controls {
                padding: 22px;
                position: sticky;
                top: 20px;
            }
            .fxlab-controls h2, .fxlab-preview-pane h2, .fxlab-lower h2 {
                margin: 0 0 10px 0;
                font-size: 1.08rem;
            }
            .fxlab-section-copy {
                margin: 0 0 18px 0;
                color: #89a0bb;
                line-height: 1.55;
                font-size: 0.88rem;
            }
            .fxlab-group {
                margin-bottom: 18px;
                padding-bottom: 18px;
                border-bottom: 1px solid rgba(148, 163, 184, 0.1);
            }
            .fxlab-group:last-child {
                border-bottom: 0;
                margin-bottom: 0;
                padding-bottom: 0;
            }
            .fxlab-label-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                margin-bottom: 8px;
            }
            .fxlab-label-row label {
                font-size: 0.84rem;
                color: #dce9f8;
                font-weight: 700;
            }
            .fxlab-value {
                color: #7dd3fc;
                font-size: 0.8rem;
                font-weight: 700;
            }
            .fxlab-select,
            .fxlab-range {
                width: 100%;
            }
            .fxlab-select {
                border-radius: 14px;
                border: 1px solid rgba(148, 163, 184, 0.14);
                background: rgba(8, 13, 24, 0.95);
                color: #eef6ff;
                padding: 12px 14px;
                font-size: 0.9rem;
            }
            .fxlab-range {
                accent-color: #38bdf8;
            }
            .fxlab-preview-pane {
                padding: 22px;
                display: grid;
                gap: 18px;
            }
            .fxlab-hero {
                display: grid;
                grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
                gap: 18px;
            }
            .fxlab-preview-stage {
                min-height: 430px;
                border-radius: 22px;
                border: 1px solid rgba(148, 163, 184, 0.12);
                position: relative;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                background:
                    radial-gradient(circle at 50% 34%, rgba(255, 255, 255, 0.12), transparent 20%),
                    radial-gradient(circle at 50% 24%, rgba(56, 189, 248, 0.12), transparent 26%),
                    linear-gradient(180deg, #08111f 0%, #040811 100%);
            }
            .fxlab-preview-stage[data-scene="studio"] {
                background:
                    radial-gradient(circle at 50% 24%, rgba(255, 244, 214, 0.14), transparent 22%),
                    linear-gradient(180deg, #111722 0%, #090d14 100%);
            }
            .fxlab-preview-stage[data-scene="clear"] {
                background:
                    radial-gradient(circle at 50% 22%, rgba(255, 255, 255, 0.1), transparent 16%),
                    linear-gradient(180deg, #0b1220 0%, #050812 100%);
            }
            .fxlab-preview-stage::after {
                content: '';
                position: absolute;
                inset: auto 16% 8% 16%;
                height: 18%;
                background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.1), transparent 70%);
                filter: blur(20px);
                pointer-events: none;
            }
            .fxlab-preview-mount {
                width: 100%;
                min-height: 380px;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                z-index: 1;
            }
            .fxlab-spec {
                display: grid;
                gap: 14px;
                align-content: start;
            }
            .fxlab-rank-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }
            .fxlab-rank-title {
                margin: 0;
                font-size: clamp(1.5rem, 2vw, 2rem);
                font-weight: 900;
                letter-spacing: -0.03em;
            }
            .fxlab-pill {
                display: inline-flex;
                align-items: center;
                padding: 7px 12px;
                border-radius: 999px;
                background: rgba(56, 189, 248, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.18);
                color: #d8f4ff;
                font-size: 0.78rem;
                font-weight: 700;
            }
            .fxlab-summary {
                margin: 0;
                color: #95abc4;
                line-height: 1.6;
                font-size: 0.92rem;
            }
            .fxlab-spec-list {
                display: grid;
                gap: 10px;
            }
            .fxlab-spec-item {
                padding: 14px 15px;
                border-radius: 16px;
                background: rgba(8, 13, 24, 0.7);
                border: 1px solid rgba(148, 163, 184, 0.09);
            }
            .fxlab-spec-label {
                color: #7dd3fc;
                font-size: 0.72rem;
                font-weight: 800;
                letter-spacing: 0.13em;
                text-transform: uppercase;
                margin-bottom: 6px;
            }
            .fxlab-spec-text {
                color: #e7f1fb;
                line-height: 1.5;
                font-size: 0.9rem;
            }
            .fxlab-lower {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 18px;
            }
            .fxlab-focus {
                padding: 22px;
            }
            .fxlab-focus-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 14px;
            }
            .fxlab-focus-card {
                appearance: none;
                text-align: left;
                border-radius: 20px;
                border: 1px solid rgba(148, 163, 184, 0.12);
                background:
                    radial-gradient(circle at top, rgba(255, 255, 255, 0.08), transparent 32%),
                    linear-gradient(180deg, rgba(8, 13, 24, 0.96), rgba(5, 9, 18, 0.98));
                padding: 16px;
                color: inherit;
                cursor: pointer;
                transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
            }
            .fxlab-focus-card:hover {
                transform: translateY(-2px);
                border-color: rgba(125, 211, 252, 0.24);
            }
            .fxlab-focus-card.is-active {
                border-color: rgba(125, 211, 252, 0.42);
                box-shadow: 0 0 0 1px rgba(125, 211, 252, 0.12), 0 18px 44px rgba(0, 0, 0, 0.24);
            }
            .fxlab-focus-badge {
                min-height: 156px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 8px;
            }
            .fxlab-focus-name {
                font-size: 1rem;
                font-weight: 900;
                margin-bottom: 8px;
            }
            .fxlab-focus-copy {
                color: #98afc8;
                line-height: 1.5;
                font-size: 0.82rem;
                margin-top: 5px;
            }
            .fxlab-prompt {
                padding: 22px;
            }
            .fxlab-prompt-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 12px;
            }
            .fxlab-copy {
                border: 1px solid rgba(125, 211, 252, 0.18);
                background: rgba(10, 17, 31, 0.82);
                color: #eaf5ff;
                border-radius: 999px;
                padding: 10px 14px;
                cursor: pointer;
            }
            .fxlab-copy:hover,
            .fxlab-rank-card:hover {
                border-color: rgba(125, 211, 252, 0.34);
            }
            .fxlab-output {
                width: 100%;
                min-height: 150px;
                resize: vertical;
                border-radius: 16px;
                border: 1px solid rgba(148, 163, 184, 0.14);
                background: rgba(5, 8, 14, 0.96);
                color: #eef6ff;
                padding: 14px 16px;
                line-height: 1.55;
                font-size: 0.92rem;
            }
            .fxlab-gallery {
                padding: 22px;
            }
            .fxlab-gallery-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 14px;
            }
            .fxlab-rank-card {
                appearance: none;
                text-align: left;
                border-radius: 18px;
                border: 1px solid rgba(148, 163, 184, 0.12);
                background: rgba(8, 13, 24, 0.82);
                padding: 14px;
                color: inherit;
                cursor: pointer;
                transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
            }
            .fxlab-rank-card.is-active {
                border-color: rgba(125, 211, 252, 0.42);
                box-shadow: 0 0 0 1px rgba(125, 211, 252, 0.12), 0 18px 44px rgba(0, 0, 0, 0.24);
                transform: translateY(-2px);
            }
            .fxlab-rank-badge {
                min-height: 124px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .fxlab-rank-name {
                font-size: 0.95rem;
                font-weight: 800;
                margin-top: 6px;
            }
            .fxlab-rank-theme {
                margin-top: 6px;
                color: #8ba2bc;
                font-size: 0.8rem;
                line-height: 1.45;
            }
            canvas.trk-pixi-canvas {
                width: 100% !important;
                height: 100% !important;
                display: block;
            }
            @media (max-width: 1180px) {
                .fxlab-layout { grid-template-columns: 1fr; }
                .fxlab-controls { position: static; }
            }
            @media (max-width: 980px) {
                .fxlab-hero { grid-template-columns: 1fr; }
                .fxlab-focus-grid { grid-template-columns: 1fr; }
            }
            @media (max-width: 720px) {
                .fxlab-root { padding: 18px; }
                .fxlab-top { flex-direction: column; }
            }
        </style>
        ''')

        rank_options = ''.join(
                f'<option value="{rank}">{TIER_LABELS[rank]}</option>' for rank in TIER_ORDER
        )
        focus_html = ''.join(_focus_card(rank) for rank in TOP_TIER_RANKS)
        gallery_html = ''.join(_gallery_card(rank) for rank in TIER_ORDER)
        preview_host = pixi_badge_host(
                DEFAULT_SCORES['diamond'],
                size=272,
                variant='diamond',
                host_id='fxlab-preview-host',
                extra_classes='fxlab-live-badge',
                options={'controls': DEFAULT_CONTROLS['diamond']},
        )

        ui.html(f'''
        <div class="fxlab-root">
            <div class="fxlab-shell">
                <div class="fxlab-top">
                    <div>
                        <div class="fxlab-kicker">PixiJS Playground</div>
                        <h1 class="fxlab-title">Tracker Rank Effects Lab</h1>
                        <p class="fxlab-sub">Design the entire rank ladder in one place before touching production. This lab is now a PixiJS-first playground: tune a focused hero badge, inspect the per-rank mood system, and keep a prompt-style output for whichever variant is ready to graduate into the live tracker.</p>
                    </div>
                    <a class="fxlab-back" href="/tracker">Back to Tracker</a>
                </div>

                <div class="fxlab-layout">
                    <aside class="fxlab-card fxlab-controls">
                        <h2>Controls</h2>
                        <p class="fxlab-section-copy">Use Diamond as the ceiling, then drag the whole ladder into place. The controls here tune procedural intensity, not just color swaps.</p>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-rank">Rank</label>
                            </div>
                            <select id="fxlab-rank" class="fxlab-select">{rank_options}</select>
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-score">Score</label>
                                <span class="fxlab-value" id="fxlab-score-value">99</span>
                            </div>
                            <input id="fxlab-score" class="fxlab-range" type="range" min="0" max="100" step="1" value="99">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-size">Preview Size</label>
                                <span class="fxlab-value" id="fxlab-size-value">272 px</span>
                            </div>
                            <input id="fxlab-size" class="fxlab-range" type="range" min="140" max="320" step="2" value="272">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-energy">Energy</label>
                                <span class="fxlab-value" id="fxlab-energy-value">1.12</span>
                            </div>
                            <input id="fxlab-energy" class="fxlab-range" type="range" min="0" max="2" step="0.02" value="1.12">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-motion">Motion</label>
                                <span class="fxlab-value" id="fxlab-motion-value">1.00</span>
                            </div>
                            <input id="fxlab-motion" class="fxlab-range" type="range" min="0" max="2" step="0.02" value="1.00">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-particles">Particle Density</label>
                                <span class="fxlab-value" id="fxlab-particles-value">1.00</span>
                            </div>
                            <input id="fxlab-particles" class="fxlab-range" type="range" min="0" max="2" step="0.02" value="1.00">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-contrast">Core Contrast</label>
                                <span class="fxlab-value" id="fxlab-contrast-value">1.08</span>
                            </div>
                            <input id="fxlab-contrast" class="fxlab-range" type="range" min="0.7" max="1.5" step="0.02" value="1.08">
                        </div>

                        <div class="fxlab-group">
                            <div class="fxlab-label-row">
                                <label for="fxlab-scene">Scene Context</label>
                            </div>
                            <select id="fxlab-scene" class="fxlab-select">
                                <option value="nebula">Nebula Stage</option>
                                <option value="studio">Studio Darkness</option>
                                <option value="clear">Clear Contrast</option>
                            </select>
                        </div>
                    </aside>

                    <section class="fxlab-card fxlab-preview-pane">
                        <div class="fxlab-hero">
                            <div class="fxlab-preview-stage" id="fxlab-preview-stage" data-scene="nebula">
                                <div class="fxlab-preview-mount" id="fxlab-preview-mount">{preview_host}</div>
                            </div>
                            <div class="fxlab-spec">
                                <div class="fxlab-rank-head">
                                    <h2 class="fxlab-rank-title" id="fxlab-rank-title">Diamond</h2>
                                    <span class="fxlab-pill" id="fxlab-rank-score">Score 99</span>
                                </div>
                                <p class="fxlab-summary" id="fxlab-summary">Diamond is the reference ceiling: a faceted god-tier badge with real value falloff, deliberate motion, and enough internal structure to hold together when it shrinks.</p>
                                <div class="fxlab-spec-list">
                                    <div class="fxlab-spec-item">
                                        <div class="fxlab-spec-label">Theme</div>
                                        <div class="fxlab-spec-text" id="fxlab-theme"></div>
                                    </div>
                                    <div class="fxlab-spec-item">
                                        <div class="fxlab-spec-label">Shape</div>
                                        <div class="fxlab-spec-text" id="fxlab-shape"></div>
                                    </div>
                                    <div class="fxlab-spec-item">
                                        <div class="fxlab-spec-label">Motion</div>
                                        <div class="fxlab-spec-text" id="fxlab-motion-copy"></div>
                                    </div>
                                    <div class="fxlab-spec-item">
                                        <div class="fxlab-spec-label">Emission</div>
                                        <div class="fxlab-spec-text" id="fxlab-emission"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="fxlab-lower">
                            <div class="fxlab-card fxlab-focus">
                                <h2>Top Tier Focus</h2>
                                <p class="fxlab-section-copy">Diamond, Ruby, and Sapphire are the current design frontier. Use these three panels to compare power grammar directly before you worry about the rest of the ladder.</p>
                                <div class="fxlab-focus-grid">{focus_html}</div>
                            </div>

                            <div class="fxlab-card fxlab-prompt">
                                <div class="fxlab-prompt-top">
                                    <div>
                                        <h2>Prompt Output</h2>
                                        <p class="fxlab-section-copy">This stays written like a direction to the next implementation pass, not a raw dump of sliders.</p>
                                    </div>
                                    <button class="fxlab-copy" id="fxlab-copy" type="button">Copy Prompt</button>
                                </div>
                                <textarea class="fxlab-output" id="fxlab-output" readonly></textarea>
                            </div>

                            <div class="fxlab-card fxlab-gallery">
                                <h2>Rank Gallery</h2>
                                <p class="fxlab-section-copy">Click any rank to pull it into the hero preview. The gallery stays on default tuning so you can read the ladder as a system instead of a stack of unrelated experiments.</p>
                                <div class="fxlab-gallery-grid">{gallery_html}</div>
                            </div>
                        </div>
                    </section>
                </div>
            </div>
        </div>
        ''')

        meta_json = json.dumps(RANK_META)
        controls_json = json.dumps(DEFAULT_CONTROLS)
        scores_json = json.dumps(DEFAULT_SCORES)

        ui.add_body_html(f'''
        <script>
        (() => {{
            const rankMeta = {meta_json};
            const defaultControls = {controls_json};
            const defaultScores = {scores_json};

            function q(id) {{
                return document.getElementById(id);
            }}

            function formatNumber(value) {{
                return Number(value).toFixed(2);
            }}

            function buildSummary(rank, score) {{
                const label = rankMeta[rank] ? rank.charAt(0).toUpperCase() + rank.slice(1) : rank;
                if (rank === 'diamond') {{
                    return `Diamond is still the quality bar: the badge needs a bright core, softer mid-glow, and a readable silhouette at 48 px before anything else in the ladder deserves polish.`;
                }}
                return `${{label}} sits at score ${{score}} in the lab. The job here is not to make it louder than Diamond; it is to make its mood legible, specific, and proportional to the rest of the ladder.`;
            }}

            function buildPrompt(state) {{
                const meta = rankMeta[state.rank];
                const label = q('fxlab-rank').selectedOptions[0].textContent;
                return [
                    `Design the ${{label}} tracker rank badge as a live PixiJS effect.`,
                    `Theme: ${{meta.theme}}`,
                    `Shape language: ${{meta.shape}}`,
                    `Motion intent: ${{meta.motion}}`,
                    `Emission grammar: ${{meta.emission}}`,
                    `Current lab tuning: size ${{state.size}} px, score ${{state.score}}, energy ${{formatNumber(state.energy)}}, motion ${{formatNumber(state.motion)}}, particle density ${{formatNumber(state.particles)}}, core contrast ${{formatNumber(state.contrast)}}.`,
                    `Keep the badge readable at 48 px, preserve a bright core with softer falloff, and do not let lower tiers visually compete with Diamond unless the rank is meant to feel equally dominant.`
                ].join(' ');
            }}

            function getState() {{
                return {{
                    rank: q('fxlab-rank').value,
                    score: Number(q('fxlab-score').value),
                    size: Number(q('fxlab-size').value),
                    energy: Number(q('fxlab-energy').value),
                    motion: Number(q('fxlab-motion').value),
                    particles: Number(q('fxlab-particles').value),
                    contrast: Number(q('fxlab-contrast').value),
                    scene: q('fxlab-scene').value,
                }};
            }}

            function setSliderValues(rank) {{
                const controls = defaultControls[rank];
                q('fxlab-score').value = defaultScores[rank];
                q('fxlab-energy').value = controls.energy;
                q('fxlab-motion').value = controls.motion;
                q('fxlab-particles').value = controls.particles;
                q('fxlab-contrast').value = controls.contrast;
            }}

            function updateValueDisplays(state) {{
                q('fxlab-score-value').textContent = state.score;
                q('fxlab-size-value').textContent = `${{state.size}} px`;
                q('fxlab-energy-value').textContent = formatNumber(state.energy);
                q('fxlab-motion-value').textContent = formatNumber(state.motion);
                q('fxlab-particles-value').textContent = formatNumber(state.particles);
                q('fxlab-contrast-value').textContent = formatNumber(state.contrast);
            }}

            function updateSpec(state) {{
                const meta = rankMeta[state.rank];
                const label = q('fxlab-rank').selectedOptions[0].textContent;
                q('fxlab-rank-title').textContent = label;
                q('fxlab-rank-score').textContent = `Score ${{state.score}}`;
                q('fxlab-summary').textContent = buildSummary(state.rank, state.score);
                q('fxlab-theme').textContent = meta.theme;
                q('fxlab-shape').textContent = meta.shape;
                q('fxlab-motion-copy').textContent = meta.motion;
                q('fxlab-emission').textContent = meta.emission;
                q('fxlab-output').value = buildPrompt(state);
                q('fxlab-preview-stage').dataset.scene = state.scene;
            }}

            function updateGallerySelection(state) {{
                document.querySelectorAll('[data-rank-card]').forEach((card) => {{
                    card.classList.toggle('is-active', card.dataset.rankCard === state.rank);
                }});
                document.querySelectorAll('[data-focus-rank]').forEach((card) => {{
                    card.classList.toggle('is-active', card.dataset.focusRank === state.rank);
                }});
            }}

            function mountPreview(state) {{
                const mount = q('fxlab-preview-mount');
                const existing = mount.querySelector('.trk-pixi-badge');
                if (existing && window.__destroyTrackerPixiBadge) {{
                    window.__destroyTrackerPixiBadge(existing);
                }}
                mount.innerHTML = '';
                const host = document.createElement('div');
                host.id = 'fxlab-preview-host';
                host.className = 'trk-pixi-badge fxlab-live-badge';
                host.dataset.score = String(state.score);
                host.dataset.variant = state.rank;
                host.dataset.options = JSON.stringify({{
                    controls: {{
                        energy: state.energy,
                        motion: state.motion,
                        particles: state.particles,
                        contrast: state.contrast,
                    }},
                    scene: state.scene,
                }});
                host.style.width = `${{state.size}}px`;
                host.style.height = `${{state.size}}px`;
                host.style.display = 'flex';
                host.style.alignItems = 'center';
                host.style.justifyContent = 'center';
                mount.appendChild(host);
                window.__renderTrackerPixiBadges && window.__renderTrackerPixiBadges(mount);
            }}

            function render() {{
                const state = getState();
                updateValueDisplays(state);
                updateSpec(state);
                updateGallerySelection(state);
                mountPreview(state);
            }}

            function bindInputs() {{
                ['fxlab-score', 'fxlab-size', 'fxlab-energy', 'fxlab-motion', 'fxlab-particles', 'fxlab-contrast', 'fxlab-scene'].forEach((id) => {{
                    q(id).addEventListener('input', render);
                    q(id).addEventListener('change', render);
                }});
                q('fxlab-rank').addEventListener('change', () => {{
                    setSliderValues(q('fxlab-rank').value);
                    render();
                }});
                document.querySelectorAll('[data-rank-card]').forEach((card) => {{
                    card.addEventListener('click', () => {{
                        q('fxlab-rank').value = card.dataset.rankCard;
                        setSliderValues(card.dataset.rankCard);
                        render();
                    }});
                }});
                document.querySelectorAll('[data-focus-rank]').forEach((card) => {{
                    card.addEventListener('click', () => {{
                        q('fxlab-rank').value = card.dataset.focusRank;
                        setSliderValues(card.dataset.focusRank);
                        render();
                    }});
                }});
                q('fxlab-copy').addEventListener('click', async () => {{
                    try {{
                        await navigator.clipboard.writeText(q('fxlab-output').value);
                        q('fxlab-copy').textContent = 'Copied';
                        setTimeout(() => {{ q('fxlab-copy').textContent = 'Copy Prompt'; }}, 1400);
                    }} catch (_) {{
                        q('fxlab-copy').textContent = 'Copy failed';
                        setTimeout(() => {{ q('fxlab-copy').textContent = 'Copy Prompt'; }}, 1400);
                    }}
                }});
            }}

            window.addEventListener('load', () => {{
                bindInputs();
                setSliderValues('diamond');
                render();
            }}, {{ once: true }});
        }})();
        </script>
        ''')
