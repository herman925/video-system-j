import pathlib

p_tracker = pathlib.Path('tracker/page.py')
lines_tracker = p_tracker.read_text(encoding='utf-8').splitlines()

start_info = next(i for i, l in enumerate(lines_tracker) if 'def _score_info' in l)
start_svg = next(i for i, l in enumerate(lines_tracker) if 'def _svg_score_badge' in l)
end_svg = next((i for i in range(start_svg+1, len(lines_tracker)) if lines_tracker[i].startswith('    def ')), len(lines_tracker))

new_score_info = """    def _score_info(score: "Optional[int]"):
        if score is None:
            return "#6b7280", "", "", ""
        s = max(0, min(100, int(score)))

        def _span(tip, css, icon, val):
            return (
                f'<span title="{tip}" style="{_B}{css}">'
                f'<span style="font-size:1.25em;line-height:1;">{icon}</span>'
                f'<span style="font-size:1em;line-height:1;">{val}</span>'
                f"</span>"
            )

        aura = ""
        # We omit inline text-shadows (ns="") so the CSS em-based keyframes can apply cleanly
        if s >= 96:
            nc, ns, aura = "#a5f3fc", "", "aura-god"
            bh = _span("💎 Diamond", "background:linear-gradient(135deg,#312e81,#6366f1,#06b6d4,#10b981,#6366f1);animation:trk-hue-spin 3s linear infinite;color:#fff;border:1px solid #818cf8;text-shadow:0 0 8px #fff,0 0 18px #a5f3fc;box-shadow:0 0 14px rgba(99,102,241,0.9),0 0 28px rgba(6,182,212,0.5);", "💎", s)
        elif s >= 94:
            nc, ns, aura = "#fb7185", "", "aura-ruby"
            bh = _span("♦ Ruby", "background:linear-gradient(135deg,#4c0519,#be123c,#fb7185,#fda4af,#e11d48);color:#fff0f3;border:1px solid #fb7185;text-shadow:0 0 8px rgba(253,164,175,0.8),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(225,29,72,0.8),0 0 22px rgba(251,113,133,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "♦", s)
        elif s >= 90:
            nc, ns, aura = "#60a5fa", "", "aura-sapphire"
            bh = _span("✦ Sapphire", "background:linear-gradient(135deg,#1e3a8a,#1d4ed8,#60a5fa,#bfdbfe,#3b82f6);color:#eff6ff;border:1px solid #60a5fa;text-shadow:0 0 8px rgba(191,219,254,0.7),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(29,78,216,0.8),0 0 22px rgba(96,165,250,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "✦", s)
        elif s >= 86:
            nc, ns, aura = "#c084fc", "", "aura-amethyst"
            bh = _span("✦ Amethyst", "background:linear-gradient(135deg,#2e1065,#7e22ce,#c084fc,#e9d5ff,#a855f7);color:#faf5ff;border:1px solid #a855f7;text-shadow:0 0 8px rgba(233,213,255,0.7),0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 12px rgba(126,34,206,0.8),0 0 22px rgba(192,132,252,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "✦", s)
        elif s >= 81:
            nc, ns, aura = "#34d399", "", "aura-emerald"
            bh = _span("◆ Emerald", "background:linear-gradient(135deg,#022c22,#065f46,#34d399,#a7f3d0,#10b981);color:#ecfdf5;border:1px solid #34d399;text-shadow:0 0 8px rgba(167,243,208,0.7),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(5,150,105,0.8),0 0 22px rgba(52,211,153,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "◆", s)
        elif s >= 76:
            nc, ns, aura = "#fbbf24", "", "aura-gold"
            bh = _span("🥇 Gold", "background:linear-gradient(135deg,#78350f,#d97706,#fbbf24,#fde68a,#f59e0b,#92400e);color:#1c1917;border:1px solid #f59e0b;text-shadow:0 1px 2px rgba(0,0,0,0.3);box-shadow:0 0 10px rgba(251,191,36,0.8),0 0 22px rgba(217,119,6,0.4),inset 0 1px 0 rgba(255,255,255,0.35);", "🥇", s)
        elif s >= 71:
            nc, ns, aura = "#fcd34d", "", "aura-topaz"
            bh = _span("◈ Topaz", "background:linear-gradient(135deg,#451a03,#b45309,#fcd34d,#fef3c7,#d97706);color:#1c1917;border:1px solid #fbbf24;text-shadow:0 1px 2px rgba(0,0,0,0.25);box-shadow:0 0 8px rgba(252,211,77,0.6),inset 0 1px 0 rgba(255,255,255,0.3);", "◈", s)
        elif s >= 66:
            nc, ns, aura = "#cbd5e1", "", "aura-silver"
            bh = _span("🥈 Silver", "background:linear-gradient(135deg,#475569,#94a3b8,#e2e8f0,#cbd5e1,#64748b);color:#0f172a;border:1px solid #94a3b8;text-shadow:0 1px 2px rgba(255,255,255,0.5);box-shadow:0 0 8px rgba(148,163,184,0.6),inset 0 1px 0 rgba(255,255,255,0.4);", "🥈", s)
        elif s >= 61:
            nc, ns, aura = "#22d3ee", "", "aura-aqua"
            bh = _span("◇ Aquamarine", "background:linear-gradient(135deg,#083344,#0e7490,#22d3ee,#a5f3fc,#06b6d4);color:#ecfeff;border:1px solid #22d3ee;text-shadow:0 0 7px rgba(165,243,252,0.7),0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 10px rgba(8,145,178,0.7),0 0 18px rgba(34,211,238,0.35),inset 0 1px 0 rgba(255,255,255,0.2);", "◇", s)
        elif s >= 56:
            nc, ns, aura = "#b5c4a1", "", "aura-jade"
            bh = _span("◈ Jade", "background:linear-gradient(135deg,#1a2416,#2d4a24,#4a7c40,#b5c4a1,#7aab6a);color:#e8f0e4;border:1px solid #7aab6a;text-shadow:0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 6px rgba(74,124,64,0.5),inset 0 1px 0 rgba(255,255,255,0.12);", "◈", s)
        elif s >= 50:
            nc, ns, aura = "#f87171", "", "aura-garnet"
            bh = _span("🥉 Garnet", "background:linear-gradient(135deg,#3b0000,#7f1d1d,#b91c1c,#f87171,#991b1b);color:#fef2f2;border:1px solid #dc2626;text-shadow:0 1px 3px rgba(0,0,0,0.6);box-shadow:0 0 8px rgba(127,29,29,0.7),inset 0 1px 0 rgba(255,255,255,0.1);", "🥉", s)
        elif s >= 40:
            t = (s - 40) / 9.0
            r2, g2, b2 = (180 + int(t * 30), 100 + int(t * 20), 10 + int(t * 20))
            nc = f"#{r2:02x}{g2:02x}{b2:02x}"
            ns = ""
            aura = "aura-onyx"
            bh = f'<span title="◼ Onyx" style="{_B}background:linear-gradient(135deg,#09090b,#18181b,#27272a,#{r2:02x}{g2:02x}{b2:02x}44);color:#{r2:02x}{g2:02x}{b2:02x};border:1px solid rgba({r2},{g2},{b2},0.5);box-shadow:0 0 6px rgba({r2},{g2},{b2},0.4);"><span style="font-size:1.25em;line-height:1;">◼</span><span style="font-size:1em;line-height:1;">{s}</span></span>'
        else:
            r, g, b = _lerp_rgb(s)
            hex_col = f"#{r:02x}{g:02x}{b:02x}"
            bg_a = 0.10 + s / 400
            bdr_a = 0.25 + s / 200
            glow_str = f"box-shadow:0 0 {3 + s//10}px rgba({r},{g},{b},{0.15 + s/220:.2f});" if s >= 15 else ""
            nc, ns, aura = hex_col, ("" if s < 20 else f"0 0 3px rgba({r},{g},{b},{s/120:.2f})"), ""
            bh = f'<span title="Low rank" style="{_B}background:rgba({r},{g},{b},{bg_a:.2f});color:{hex_col};border:1px solid rgba({r},{g},{b},{bdr_a:.2f});{glow_str}"><span style="font-size:1em;line-height:1;">{s}</span></span>'
        return nc, ns, bh, aura
"""

new_svg_func = """    def _svg_score_badge(score: "Optional[int]", size=48) -> str:
        \"\"\"Returns complex SVG string for right panel profile picture style.\"\"\"
        s = score
        if s is None:
            return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:pointer;opacity:0.9;transition:all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0" onmouseover="this.style.transform='scale(1.1) rotate(2deg)'" onmouseout="this.style.transform='scale(1) rotate(0)'"><title>Unrated = haven\\'t beaten off to her enough to judge.</title><circle cx="24" cy="24" r="22" fill="#1f2937" stroke="#374151" stroke-width="1"/><text x="24" y="24" fill="#9ca3af" font-size="10" font-family="sans-serif" font-weight="600" text-anchor="middle" dominant-baseline="central">N/A</text></svg>'''
        
        s = max(0, min(100, int(s)))

        # Determine colors and shapes
        glow_opacity = "0.7"
        aura_xml = ""
        tt = "Unrated"
        
        def make_spiky_burst(color, outer, inner, points=12):
            import math
            pts = []
            for i in range(points * 2):
                angle = i * math.pi / points
                r = outer if i % 2 == 0 else inner
                pts.append(f"{24 + math.cos(angle)*r},{24 + math.sin(angle)*r}")
            return " ".join(pts)

        if s >= 96:
            c1, c2, border, text_col = "#1e1b4b", "#06b6d4", "#a5f3fc", "#ffffff"
            shape = "diamond"; glow = "#3b82f6"; tt = "💎 Diamond — Guaranteed nut every single time."
            aura_xml = f'''
                <!-- Explosive UI God Aura out to 60px -->
                <g filter="url(#glow-filter)" style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#60a5fa', 58, 26, 20)}" fill="#60a5fa" opacity="0.6"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="3s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.3;0.9;0.3" dur="0.8s" repeatCount="indefinite"/></polygon>
                    <polygon points="{make_spiky_burst('#a5f3fc', 48, 22, 16)}" fill="#a5f3fc" opacity="0.8"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.9;0.6;0.9" dur="0.5s" repeatCount="indefinite"/></polygon>
                </g>
                <circle cx="24" cy="24" r="28" fill="none" stroke="#fff" stroke-width="2"><animate attributeName="r" values="24;55" dur="1.2s" repeatCount="indefinite" /><animate attributeName="opacity" values="1;0" dur="1.2s" repeatCount="indefinite" /></circle>
            '''
        elif s >= 94:
            c1, c2, border, text_col = "#4c0519", "#e11d48", "#fb7185", "#fff0f3"
            shape = "gem"; glow = "#be123c"; tt = "♦ Ruby — Near-guaranteed orgasm."
            aura_xml = f'''
                <!-- Blazing Ruby Flame -->
                <g filter="url(#glow-filter)" style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#e11d48', 52, 24, 16)}" fill="#e11d48" opacity="0.7"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="4s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.4;1;0.4" dur="1s" repeatCount="indefinite"/></polygon>
                    <polygon points="{make_spiky_burst('#fb7185', 42, 20, 10)}" fill="#fb7185" opacity="0.9"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="2.5s" repeatCount="indefinite"/></polygon>
                </g>
                <circle cx="24" cy="24" r="24" fill="none" stroke="{border}" stroke-width="1.5"><animate attributeName="r" values="24;45" dur="1.5s" repeatCount="indefinite" /><animate attributeName="opacity" values="0.8;0" dur="1.5s" repeatCount="indefinite" /></circle>
            '''
        elif s >= 90:
            c1, c2, border, text_col = "#172554", "#3b82f6", "#60a5fa", "#eff6ff"
            shape = "gem"; glow = "#2563eb"; tt = "✦ Sapphire — Reliable go-to fap material."
            aura_xml = f'''
                <g filter="url(#glow-filter)" style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#2563eb', 46, 26, 14)}" fill="#2563eb" opacity="0.7"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="5s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.4;0.9;0.4" dur="1.5s" repeatCount="indefinite"/></polygon>
                    <circle cx="24" cy="24" r="32" fill="none" stroke="{border}" stroke-width="3" opacity="0.9" stroke-dasharray="12,8"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="4s" repeatCount="indefinite"/></circle>
                </g>
                <circle cx="24" cy="24" r="28" fill="none" stroke="{border}" stroke-width="1.5"><animate attributeName="r" values="24;42" dur="2s" repeatCount="indefinite" /><animate attributeName="opacity" values="0.7;0" dur="2s" repeatCount="indefinite" /></circle>
            '''
        elif s >= 86:
            c1, c2, border, text_col = "#2e1065", "#7e22ce", "#c084fc", "#faf5ff"
            shape = "hex"; glow = "#9333ea"; tt = "✦ Amethyst — Specific fetish goldmine."
            aura_xml = f'''
                <g filter="url(#glow-filter)">
                    <polygon points="{make_spiky_burst('#9333ea', 44, 25, 12)}" fill="#9333ea" opacity="0.5"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="6s" repeatCount="indefinite" /><animate attributeName="opacity" values="0.3;0.8;0.3" dur="2s" repeatCount="indefinite" /></polygon>
                    <polygon points="24,-12 60,8 60,40 24,60 -12,40 -12,8" fill="none" stroke="{border}" stroke-width="2" opacity="0.6"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="8s" repeatCount="indefinite" /></polygon>
                </g>
            '''
        elif s >= 81:
            c1, c2, border, text_col = "#022c22", "#10b981", "#34d399", "#ecfdf5"
            shape = "hex"; glow = "#059669"; tt = "◆ Emerald — Solid nut when the stars align."
            aura_xml = f'''
                 <g filter="url(#glow-filter)" style="mix-blend-mode: screen;">
                     <polygon points="{make_spiky_burst('#10b981', 42, 26, 10)}" fill="#10b981" opacity="0.5"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="7s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.3;0.8;0.3" dur="2s" repeatCount="indefinite"/></polygon>
                     <circle cx="24" cy="24" r="34" fill="none" stroke="{border}" stroke-width="2" stroke-dasharray="15,10"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="6s" repeatCount="indefinite"/></circle>
                 </g>
            '''
        elif s >= 76:
            c1, c2, border, text_col = "#78350f", "#f59e0b", "#fde68a", "#ffffff"
            shape = "medal"; glow = "#d97706"; tt = "🥇 Gold — Decent fap but conditional."
            aura_xml = f'''
                <!-- Super Saiyan 1 Golden Aura -->
                <g filter="url(#glow-filter)" style="mix-blend-mode: screen;">
                    <polygon points="{make_spiky_burst('#f59e0b', 38, 26, 10)}" fill="#fde68a" opacity="0.6"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="5s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.4;1;0.4" dur="1.5s" repeatCount="indefinite"/></polygon>
                    <circle cx="24" cy="24" r="30" fill="none" stroke="{glow}" stroke-width="2" stroke-dasharray="8,6"><animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="4s" repeatCount="indefinite"/></circle>
                </g>
            '''
        elif s >= 71:
            c1, c2, border, text_col = "#451a03", "#d97706", "#fef3c7", "#ffffff"
            shape = "medal"; glow = "#b45309"; tt = "◈ Topaz — Only for the fetish."
            aura_xml = f'''
                <!-- Geo / Earth rings -->
                <g filter="url(#glow-filter)">
                    <rect x="-8" y="-8" width="64" height="64" fill="none" stroke="{glow}" stroke-width="1.5" transform="rotate(45 24 24)" opacity="0.6"><animateTransform attributeName="transform" type="rotate" from="45 24 24" to="225 24 24" dur="10s" repeatCount="indefinite"/></rect>
                    <rect x="-2" y="-2" width="52" height="52" fill="none" stroke="{border}" stroke-width="1" transform="rotate(15 24 24)" opacity="0.5"><animateTransform attributeName="transform" type="rotate" from="15 24 24" to="-165 24 24" dur="8s" repeatCount="indefinite"/></rect>
                </g>
            '''
        elif s >= 66:
            c1, c2, border, text_col = "#334155", "#94a3b8", "#f1f5f9", "#ffffff"
            shape = "medal"; glow = "#64748b"; tt = "🥈 Silver — Barely gets you there."
            aura_xml = f'''
                <!-- Chrome Starburst -->
                <g filter="url(#glow-filter)">
                    <polygon points="{make_spiky_burst('#cbd5e1', 40, 26, 4)}" fill="#e2e8f0" opacity="0.4"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="12s" repeatCount="indefinite"/></polygon>
                    <polygon points="{make_spiky_burst('#94a3b8', 40, 26, 4)}" fill="none" stroke="#f1f5f9" stroke-width="1.5" opacity="0.6" transform="rotate(45 24 24)"><animateTransform attributeName="transform" type="rotate" from="45 24 24" to="-315 24 24" dur="12s" repeatCount="indefinite"/></polygon>
                </g>
            '''
        elif s >= 61:
            c1, c2, border, text_col = "#083344", "#06b6d4", "#cffafe", "#ffffff"
            shape = "shield"; glow = "#0e7490"; tt = "◇ Aquamarine — Rarely worth the effort."
            aura_xml = f'''
                <!-- Water ripples -->
                <circle cx="24" cy="24" r="24" fill="none" stroke="{border}" stroke-width="1.5"><animate attributeName="r" values="24;38" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.8;0" dur="2s" repeatCount="indefinite"/></circle>
                <circle cx="24" cy="24" r="24" fill="none" stroke="{glow}" stroke-width="1.5" begin="1s"><animate attributeName="r" values="24;38" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.8;0" dur="2s" repeatCount="indefinite"/></circle>
            '''
        elif s >= 56:
            c1, c2, border, text_col = "#1a2416", "#4a7c40", "#dcfce7", "#ffffff"
            shape = "shield"; glow = "#166534"; tt = "◈ Jade — Neutral, maybe even a turn-off."
            aura_xml = f'''
                <!-- Wind leaves swirling -->
                <circle cx="24" cy="24" r="30" fill="none" stroke="{glow}" stroke-width="2" stroke-dasharray="16,24"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="3s" repeatCount="indefinite"/></circle>
            '''
        elif s >= 50:
            c1, c2, border, text_col = "#3b0000", "#b91c1c", "#fee2e2", "#ffffff"
            shape = "shield"; glow = "#991b1b"; tt = "🥉 Garnet — Why am I even watching this?"
            aura_xml = f'''
                <!-- Embers pulsing -->
                <polygon points="{make_spiky_burst('#b91c1c', 32, 24, 6)}" fill="#f87171" opacity="0.4"><animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="15s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.2;0.6;0.2" dur="2s" repeatCount="indefinite"/></polygon>
            '''
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

        # Notice overflow:visible and viewBox 0 0 48 48! This prevents scaling and lets effects bleed!
        return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:help;transform-origin:center;transition:transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0;overflow:visible;z-index:99;" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform='scale(1)'">
    <title>{tt}</title>
    <defs>
        <linearGradient id="{rId}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="{c1}" /><stop offset="40%" stop-color="{c1}" /><stop offset="100%" stop-color="{c2}" /></linearGradient>
        <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="{glow}" flood-opacity="{glow_opacity}"/><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#000000" flood-opacity="0.8"/></filter>
        <filter id="glow-filter" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="blur" /><feComposite in="SourceGraphic" in2="blur" operator="over" /></filter>
        <filter id="text-glow"><feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000000" flood-opacity="0.8"/><feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="{glow}" flood-opacity="0.8"/></filter>
    </defs>
    {aura_xml}
    {layers}
    <!-- Top-left rim highlight for gloss -->
    <path d="M 12,6 A 16,16 0 0 1 20,4" fill="none" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" opacity="0.8" style="mix-blend-mode: overlay;"/>
    <text x="24" y="{txt_y}" fill="{text_col}" font-size="{font_size}" font-family="system-ui, -apple-system, sans-serif" font-weight="900" text-anchor="middle" dominant-baseline="central" alignment-baseline="middle" filter="url(#text-glow)" letter-spacing="0.5">{s}</text>
</svg>'''
"""

idx2_start = next(i for i, l in enumerate(lines_tracker) if 'def _score_html' in l)
new_lines_t = lines_tracker[:start_info] + new_score_info.splitlines() + lines_tracker[idx2_start:start_svg] + new_svg_func.splitlines() + lines_tracker[end_svg:]
p_tracker.write_text('\n'.join(new_lines_t), encoding='utf-8')
print("Successfully updated tracker/page.py with inline ns override and obvious UI effects.")
