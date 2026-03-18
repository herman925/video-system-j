import pathlib

# 1. Update theme.css
css_path = pathlib.Path('assets/theme.css')
css = css_path.read_text(encoding='utf-8')
if 'animeBeam' not in css:
    anim_css = """
/* --- DBZ Aura SVG Animations (CSS-based to bypass Vue sanitization) --- */
@keyframes animeBeam1 { 0% { transform: translateY(60px); opacity: 0; } 50% { opacity: 0.8; } 100% { transform: translateY(-40px); opacity: 0; } }
@keyframes animeBeam2 { 0% { transform: translateY(60px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translateY(-50px); opacity: 0; } }
@keyframes animeBeam3 { 0% { transform: translateY(60px); opacity: 0; } 50% { opacity: 0.5; } 100% { transform: translateY(-20px); opacity: 0; } }
@keyframes animeBeam4 { 0% { transform: translateY(60px); opacity: 0; } 50% { opacity: 0.9; } 100% { transform: translateY(-30px); opacity: 0; } }

.anime-beam-1 { animation: animeBeam1 0.8s linear infinite; }
.anime-beam-2 { animation: animeBeam2 0.6s linear infinite; }
.anime-beam-3 { animation: animeBeam3 1.0s linear infinite; }
.anime-beam-4 { animation: animeBeam4 0.7s linear infinite; }

@keyframes animeParticle1 { 0% { transform: translateY(50px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translateY(-20px); opacity: 0; } }
@keyframes animeParticle2 { 0% { transform: translateY(55px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translateY(-30px); opacity: 0; } }
@keyframes animeParticle3 { 0% { transform: translateY(45px); opacity: 0; } 50% { opacity: 0.8; } 100% { transform: translateY(-10px); opacity: 0; } }

.anime-particle-1 { animation: animeParticle1 1.5s linear infinite; }
.anime-particle-2 { animation: animeParticle2 1.2s linear infinite; }
.anime-particle-3 { animation: animeParticle3 1.8s linear infinite; }

@keyframes animeSpinFW { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
@keyframes animeSpinBW { 0% { transform: rotate(360deg); } 100% { transform: rotate(0deg); } }

/* For transform origin center in 48x48 svg */
.anime-spin-fw { animation: animeSpinFW 15s linear infinite; transform-origin: 24px 24px; }
.anime-spin-bw { animation: animeSpinBW 15s linear infinite; transform-origin: 24px 24px; }
.anime-spin-fw-fast { animation: animeSpinFW 2s linear infinite; transform-origin: 24px 24px; }
.anime-spin-bw-fast { animation: animeSpinBW 1.5s linear infinite; transform-origin: 24px 24px; }
.anime-spin-fw-med { animation: animeSpinFW 4s linear infinite; transform-origin: 24px 24px; }
.anime-spin-bw-med { animation: animeSpinBW 6s linear infinite; transform-origin: 24px 24px; }
.anime-spin-fw-slow { animation: animeSpinFW 10s linear infinite; transform-origin: 24px 24px; }
.anime-spin-bw-slow { animation: animeSpinBW 12s linear infinite; transform-origin: 24px 24px; }

/* Scale and opacity pulses */
@keyframes animePulseOpa1 { 0% { opacity: 0.2; } 50% { opacity: 0.8; } 100% { opacity: 0.2; } }
@keyframes animePulseOpa2 { 0% { opacity: 0.6; } 50% { opacity: 1; } 100% { opacity: 0.6; } }
@keyframes animePulseOpa3 { 0% { opacity: 0.3; } 50% { opacity: 0.9; } 100% { opacity: 0.3; } }
@keyframes animePulseOpa4 { 0% { opacity: 0.1; } 50% { opacity: 0.4; } 100% { opacity: 0.1; } }

/* Complex multi-animations */
.anime-burst-1 { animation: animeSpinFW 2s linear infinite, animePulseOpa1 0.5s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-2 { animation: animeSpinBW 1.5s linear infinite, animePulseOpa2 0.3s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-3 { animation: animeSpinFW 3s linear infinite, animePulseOpa3 0.8s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-4 { animation: animeSpinFW 4s linear infinite, animePulseOpa3 1.2s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-5 { animation: animeSpinBW 5s linear infinite, animePulseOpa1 1.5s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-6 { animation: animeSpinFW 5s linear infinite, animePulseOpa3 1s ease-in-out infinite; transform-origin: 24px 24px; }
.anime-burst-7 { animation: animeSpinFW 15s linear infinite, animePulseOpa4 3s ease-in-out infinite; transform-origin: 24px 24px; }

@keyframes animeRipple { 0% { transform: scale(1); opacity: 1; } 100% { transform: scale(1.5); opacity: 0; } }
.anime-ripple { animation: animeRipple 1s ease-out infinite; transform-origin: 24px 24px; }
.anime-ripple-slow { animation: animeRipple 1.2s ease-out infinite; transform-origin: 24px 24px; }
.anime-ripple-med { animation: animeRipple 1.5s ease-out infinite; transform-origin: 24px 24px; }
.anime-ripple-aqua { animation: animeRipple 2.5s ease-out infinite; transform-origin: 24px 24px; }
"""
    css_path.write_text(css + "\n" + anim_css, encoding='utf-8')


# 2. Rewrite tracker/page.py function to use classes, not <animate> tags!
p_tracker = pathlib.Path('tracker/page.py')
lines_tracker = p_tracker.read_text(encoding='utf-8').splitlines()

start_svg = next(i for i, l in enumerate(lines_tracker) if 'def _svg_score_badge' in l)
end_svg = next((i for i in range(start_svg+1, len(lines_tracker)) if lines_tracker[i].startswith('    def ')), len(lines_tracker))

new_badge_code = """    def _svg_score_badge(score: "Optional[int]", size=48) -> str:
        \"\"\"Returns complex SVG string for right panel profile picture style.\"\"\"
        s = score
        if s is None:
            return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:pointer;opacity:0.9;transition:all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0" onmouseover="this.style.transform='scale(1.1) rotate(2deg)'" onmouseout="this.style.transform='scale(1) rotate(0)'"><title>Unrated = haven\\'t beaten off to her enough to judge.</title><circle cx="24" cy="24" r="22" fill="#1f2937" stroke="#374151" stroke-width="1"/><text x="24" y="24" fill="#9ca3af" font-size="10" font-family="sans-serif" font-weight="600" text-anchor="middle" dominant-baseline="central">N/A</text></svg>'''

        s = max(0, min(100, int(s)))

        cfg = AURA_CONFIG.copy()
        if hasattr(Page, '_user_cfg_cache'):
            cfg.update(Page._user_cfg_cache)
        elif '_user_cfg_cache' in globals():
            cfg.update(globals().get('_user_cfg_cache', {}))
        
        scale = cfg["emission_scale"]
        
        glow_opacity = "0.7"
        aura_xml = ""
        tt = "Unrated"

        def _beams(col):
            if not cfg["vertical_beams"]: return ""
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
            if not cfg["particles"]: return ""
            return f'''
            <g fill="{col}">
                <circle cx="12" r="1.5" class="anime-particle-1" />
                <circle cx="24" r="2" class="anime-particle-2" />
                <circle cx="36" r="1" class="anime-particle-3" />
            </g>
            '''

        def _god_rays(col):
            if not cfg["god_light"]: return ""
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
                pts.append(f"{24 + math.cos(angle)*r},{24 + math.sin(angle)*r}")
            return " ".join(pts)

        if s >= 96:
            c1, c2, border, text_col = "#1e1b4b", "#06b6d4", "#a5f3fc", "#ffffff"
            shape = "diamond"; glow = "#3b82f6"; tt = "💎 Diamond — Guaranteed nut every single time."
            aura_class = ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ''
            
            aura_xml = f'''
                {_god_rays('#a5f3fc')}
                {_beams('#3b82f6')}
                {_particles('#67e8f9')}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#60a5fa', 28, 14, 20)}" fill="#60a5fa" class="anime-burst-1" />
                    <polygon points="{make_spiky_burst('#a5f3fc', 22, 12, 12)}" fill="#a5f3fc" class="anime-burst-2" />
                </g>
                <circle cx="24" cy="24" r="24" fill="none" stroke="#fff" stroke-width="2.5" class="anime-ripple" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 94:
            c1, c2, border, text_col = "#4c0519", "#e11d48", "#fb7185", "#fff0f3"
            shape = "gem"; glow = "#be123c"; tt = "♦ Ruby — Near-guaranteed orgasm."
            aura_class = ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ''
            
            aura_xml = f'''
                {_beams('#e11d48')}
                {_particles('#fda4af')}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#e11d48', 26, 12, 16)}" fill="#e11d48" class="anime-burst-3" />
                </g>
                <circle cx="24" cy="24" r="24" fill="none" stroke="{border}" stroke-width="1.5" class="anime-ripple-slow" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 90:
            c1, c2, border, text_col = "#172554", "#3b82f6", "#60a5fa", "#eff6ff"
            shape = "gem"; glow = "#2563eb"; tt = "✦ Sapphire — Reliable go-to fap material."
            aura_class = ' filter="url(#glow-filter)"' if cfg["use_blur_filters"] else ''
            aura_xml = f'''
                {_particles('#93c5fd')}
                <g{aura_class} style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#2563eb', 24, 14, 14)}" fill="#2563eb" class="anime-burst-4" />
                </g>
                <circle cx="24" cy="24" r="28" fill="none" stroke="{border}" stroke-width="2" stroke-dasharray="12,6" class="anime-spin-fw-med" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 86:
            c1, c2, border, text_col = "#2e1065", "#7e22ce", "#c084fc", "#faf5ff"
            shape = "hex"; glow = "#9333ea"; tt = "✦ Amethyst — Specific fetish goldmine."
            aura_xml = f'''
                {_god_rays('#a855f7')}
                <polygon points="{make_spiky_burst('#9333ea', 25, 14, 12)}" fill="#9333ea" class="anime-burst-5" />
                <polygon points="24,-12 60,8 60,40 24,60 -12,40 -12,8" fill="none" stroke="{border}" stroke-width="1.5" opacity="0.5" class="anime-spin-bw-med" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 81:
            c1, c2, border, text_col = "#022c22", "#10b981", "#34d399", "#ecfdf5"
            shape = "hex"; glow = "#059669"; tt = "◆ Emerald — Solid nut when the stars align."
            aura_xml = f'''
                 {_particles('#6ee7b7')}
                 <circle cx="24" cy="24" r="28" fill="none" stroke="{border}" stroke-width="2" stroke-dasharray="10,12" class="anime-spin-bw-med" />
                 <circle cx="24" cy="24" r="24" fill="none" stroke="{glow}" stroke-width="1.5" class="anime-ripple-med" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 76:
            c1, c2, border, text_col = "#78350f", "#f59e0b", "#fde68a", "#ffffff"
            shape = "medal"; glow = "#d97706"; tt = "🥇 Gold — Decent fap but conditional."
            aura_xml = f'''
                {_beams('#fef3c7')}
                <polygon points="{make_spiky_burst('#f59e0b', 21, 14, 10)}" fill="#fde68a" class="anime-burst-6" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 71:
            c1, c2, border, text_col = "#451a03", "#d97706", "#fef3c7", "#ffffff"
            shape = "medal"; glow = "#b45309"; tt = "◈ Topaz — Only for the fetish."
            aura_xml = f'''
                <rect x="0" y="0" width="48" height="48" fill="none" stroke="{glow}" stroke-width="1.5" opacity="0.5" class="anime-spin-fw-slow" />
                <rect x="4" y="4" width="40" height="40" fill="none" stroke="{border}" stroke-width="1" opacity="0.4" class="anime-spin-bw-slow" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 66:
            c1, c2, border, text_col = "#334155", "#94a3b8", "#f1f5f9", "#ffffff"
            shape = "medal"; glow = "#64748b"; tt = "🥈 Silver — Barely gets you there."
            aura_xml = f'''
                <polygon points="{make_spiky_burst('#cbd5e1', 24, 14, 4)}" fill="#e2e8f0" opacity="0.3" class="anime-spin-fw-slow" />
                <polygon points="{make_spiky_burst('#94a3b8', 24, 14, 4)}" fill="none" stroke="#f1f5f9" stroke-width="1.5" opacity="0.5" transform="rotate(45 24 24)" class="anime-spin-bw-slow" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 61:
            c1, c2, border, text_col = "#083344", "#06b6d4", "#cffafe", "#ffffff"
            shape = "shield"; glow = "#0e7490"; tt = "◇ Aquamarine — Rarely worth the effort."
            aura_xml = f'''
                <circle cx="24" cy="24" r="22" fill="none" stroke="{border}" stroke-width="1" class="anime-ripple-aqua" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 56:
            c1, c2, border, text_col = "#1a2416", "#4a7c40", "#dcfce7", "#ffffff"
            shape = "shield"; glow = "#166534"; tt = "◈ Jade — Neutral, maybe even a turn-off."
            aura_xml = f'''
                <circle cx="24" cy="24" r="26" fill="none" stroke="{glow}" stroke-width="1.5" stroke-dasharray="8,16" class="anime-spin-fw-med" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 50:
            c1, c2, border, text_col = "#3b0000", "#b91c1c", "#fee2e2", "#ffffff"
            shape = "shield"; glow = "#991b1b"; tt = "🥉 Garnet — Why am I even watching this?"
            p_c = '#f87171'
            aura_xml = f'''
                {_particles(p_c)}
                <polygon points="{make_spiky_burst('#b91c1c', 16, 12, 6)}" fill="#f87171" class="anime-burst-7" />
            ''' if cfg["enabled"] else ""
            
        elif s >= 40:
            t = (s - 40) / 9.0; r2, g2, b2 = (180 + int(t * 30), 100 + int(t * 20), 10 + int(t * 20)); hex_c = f"#{r2:02x}{g2:02x}{b2:02x}"
            c1, c2, border, text_col = "#09090b", "#27272a", hex_c, "#ffffff"
            shape = "shield"; glow = "#27272a"; tt = "◼ Onyx — Hard pass."
        else:
            rt, gt, bt = _lerp_rgb(s)
            c1, c2, border, text_col, shape, glow, glow_opacity = f"rgba({rt//6},{gt//6},{bt//6},1)", f"rgba({rt//2},{gt//2},{bt//2},1)", f"rgba({rt},{gt},{bt},0.8)", f"rgba({rt},{gt},{bt},1)", "pill", f"rgba({rt},{gt},{bt},1)", "0.3"
            tt = "Low rank" if s >= 20 else "Hard pass"

        rId = f"grad_sq_{s}"
        layers = ""; txt_y = "25"; font_size = "15"
        
        # Dropshadow config
        shadow_xml = f'<feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="{glow}" flood-opacity="{glow_opacity}"/><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#000000" flood-opacity="0.8"/>' if cfg["use_blur_filters"] else f'<feDropShadow dx="0" dy="4" stdDeviation="2" flood-color="#000000" flood-opacity="0.8"/>'
        
        if shape == "diamond":
            d_path = "M 24,0 L 48,22 L 24,52 L 0,22 Z"; txt_y = "24"; font_size = "16"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 24,4 L 43,22 L 24,48 L 5,22 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.6" /><path d="M 24,2 L 34,22 L 24,50 L 14,22 Z" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.5" /><polygon points="24,2 14,22 24,4" fill="#ffffff" opacity="0.5" /><polygon points="24,2 2,22 14,22" fill="#ffffff" opacity="0.2" /><polygon points="24,22 34,22 24,50" fill="#000000" opacity="0.3" />'
        elif shape == "gem":
            d_path = "M 12,2 L 36,2 L 50,16 L 50,32 L 36,48 L 12,48 L -2,32 L -2,16 Z"; txt_y = "25"; font_size = "15"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 14,4 L 34,4 L 47,17 L 47,31 L 34,46 L 14,46 L 1,31 L 1,17 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.5" /><polygon points="12,2 36,2 24,18" fill="#ffffff" opacity="0.4" /><polygon points="-2,16 12,2 24,18 10,24" fill="#ffffff" opacity="0.2" /><polygon points="24,18 50,32 36,48" fill="#000000" opacity="0.25" /><path d="M 24,18 L 50,16 M 24,18 L 50,32 M 24,18 L 36,48 M 24,18 L 12,48 M 24,18 L -2,32 M 24,18 L -2,16 M 24,18 L 12,2 M 24,18 L 36,2" stroke="#ffffff" stroke-width="1" opacity="0.4"/>'
        elif shape == "hex":
            d_path = "M 24,2 L 46,14 L 46,36 L 24,48 L 2,36 L 2,14 Z"
            layers = f'<path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><path d="M 24,6 L 42,16 L 42,34 L 24,44 L 6,34 L 6,16 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" /><polygon points="24,2 46,14 24,24" fill="#ffffff" opacity="0.2" /><polygon points="2,14 24,2 24,24" fill="#ffffff" opacity="0.3" />'
        elif shape == "medal":
            layers = f'<circle cx="24" cy="24" r="22" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" /><circle cx="24" cy="24" r="18" fill="none" stroke="{border}" stroke-width="2" opacity="0.8" stroke-dasharray="2,2" /><circle cx="24" cy="24" r="14" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" /><circle cx="24" cy="24" r="22" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.4" /><path d="M 6,10 Q 24,-2 42,10" fill="none" stroke="#ffffff" stroke-width="5" opacity="0.2" filter="blur(1px)"/><path d="M 12,38 Q 24,46 36,38" fill="none" stroke="#000000" stroke-width="4" opacity="0.3" filter="blur(1px)"/>'
        elif shape == "shield":
            d_path = "M 4,4 L 44,4 L 44,22 C 44,36 24,46 24,46 C 24,46 4,36 4,22 Z"; txt_y = "24"
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
"""

new_lines_t = lines_tracker[:start_svg] + new_badge_code.splitlines() + lines_tracker[end_svg:]
p_tracker.write_text('\n'.join(new_lines_t), encoding='utf-8')
print("Successfully shifted from SVG <animate> to global CSS classes")
