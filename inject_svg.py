import pathlib
import sys

p = pathlib.Path('tracker/page.py')
text = p.read_text(encoding='utf-8')

# Find start and end of _svg_score_badge
lines = text.split('\n')
start = next(i for i, l in enumerate(lines) if 'def _svg_score_badge' in l)
end = next((i for i in range(start+1, len(lines)) if lines[i].startswith('    def ')), len(lines))

new_svg_func = """    def _svg_score_badge(score: "Optional[int]", size=48) -> str:
        \"\"\"Returns complex SVG string for right panel profile picture style.\"\"\"
        s = score
        if s is None:
            return f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:pointer;opacity:0.9;transition:all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0" onmouseover="this.style.transform='scale(1.1) rotate(2deg)'" onmouseout="this.style.transform='scale(1) rotate(0)'"><title>Unrated = haven\\'t beaten off to her enough to judge.</title><circle cx="24" cy="24" r="22" fill="#1f2937" stroke="#374151" stroke-width="1"/><text x="24" y="24" fill="#9ca3af" font-size="10" font-family="sans-serif" font-weight="600" text-anchor="middle" dominant-baseline="central">N/A</text></svg>'''
        
        s = max(0, min(100, int(s)))

        # Determine colors and shapes
        glow_opacity = "0.6"
        aura_xml = ""
        tt = "Unrated"

        if s >= 96:
            c1, c2, border, text_col = "#1e1b4b", "#06b6d4", "#a5f3fc", "#ffffff"
            shape = "diamond"
            glow = "#3b82f6"
            tt = "💎 Diamond — Guaranteed nut every single time. Her face, body, moans, and the way she takes dick are all exactly your type. You cum to her scenes without fail — 100% success rate. You'd actually pay for her content. New release? Already downloading before checking the cover. She's in your permanent rotation."
            aura_xml = f'''
                <g opacity="0.6">
                    <path d="M 24,-10 L 26,16 L 58,24 L 26,32 L 24,58 L 22,32 L -10,24 L 22,16 Z" fill="url(#grad_sq_{s})" opacity="0.8"/>
                    <path d="M 5,5 L 20,20 L 43,5 L 28,28 L 43,43 L 20,28 L 5,43 L 15,24 Z" fill="{glow}" opacity="0.6" filter="url(#shadow)"/>
                    <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="4s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
                </g>
                <circle cx="24" cy="24" r="26" fill="none" stroke="{border}" stroke-width="1" opacity="0.5">
                    <animate attributeName="r" values="18;34" dur="1.5s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.8;0" dur="1.5s" repeatCount="indefinite" />
                </circle>
            '''
        elif s >= 94:
            c1, c2, border, text_col = "#4c0519", "#e11d48", "#fb7185", "#fff0f3"
            shape = "gem"
            glow = "#be123c"
            tt = "♦ Ruby — Near-guaranteed orgasm. Her face and body get you hard instantly, and her performance keeps you there. You finish to her 90%+ of the time. New releases go straight to queue — maybe a quick cover glance, but you're watching regardless. The kind of girl you edge to because you don't want it to end."
            aura_xml = f'''
                <g opacity="0.7">
                    <path d="M 24,-5 L 28,15 L 50,15 L 32,26 L 40,48 L 24,34 L 8,48 L 16,26 L -2,15 L 20,15 Z" fill="{glow}" filter="url(#shadow)"/>
                    <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="8s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.5;0.9;0.5" dur="1.5s" repeatCount="indefinite" />
                </g>
            '''
        elif s >= 90:
            c1, c2, border, text_col = "#172554", "#3b82f6", "#60a5fa", "#eff6ff"
            shape = "gem"
            glow = "#2563eb"
            tt = "✦ Sapphire — Reliable go-to fap material. Her look hits your preferences and she fucks with genuine energy. You cum to her 80%+ of the time. New releases are instant shortlist — you might peek at tags but you're already sold. One of your regulars when you need to get off without gambling on quality."
            aura_xml = f'''
                <circle cx="24" cy="24" r="24" fill="none" stroke="{border}" stroke-width="2" opacity="0.8" stroke-dasharray="4,6">
                    <animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="10s" repeatCount="indefinite"/>
                </circle>
                <circle cx="24" cy="24" r="28" fill="none" stroke="{glow}" stroke-width="1.5">
                    <animate attributeName="r" values="20;32" dur="2s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.7;0" dur="2s" repeatCount="indefinite" />
                </circle>
            '''
        elif s >= 86:
            c1, c2, border, text_col = "#2e1065", "#7e22ce", "#c084fc", "#faf5ff"
            shape = "hex"
            glow = "#9333ea"
            tt = "✦ Amethyst — Specific fetish goldmine. Something about her hits different — her face, her body type, how she moans, or she does exactly the genres you're into. When the scene concept aligns, you bust hard. 70%+ nut rate when the theme is right. Not an auto-queue but when she matches your fetish, she delivers."
            aura_xml = f'''
                <polygon points="24,0 45,12 45,36 24,48 3,36 3,12" fill="none" stroke="{glow}" stroke-width="2" opacity="0.6">
                    <animate attributeName="opacity" values="0.2;0.8;0.2" dur="2s" repeatCount="indefinite" />
                </polygon>
                <polygon points="24,-4 49,10 49,38 24,52 -1,38 -1,10" fill="none" stroke="{glow}" stroke-width="1">
                    <animate attributeName="opacity" values="0.6;0" dur="1.5s" repeatCount="indefinite" />
                </polygon>
            '''
        elif s >= 81:
            c1, c2, border, text_col = "#022c22", "#10b981", "#34d399", "#ecfdf5"
            shape = "hex"
            glow = "#059669"
            tt = "◆ Emerald — Solid nut when the stars align. Her baseline is attractive enough, and with the right studio, outfit, or co-star she gets you off consistently. Maybe 60-70% success rate depending on the scene. Worth tracking because when she hits, she really hits. You check covers before committing but she's on your radar."
            aura_xml = f'''
                 <circle cx="24" cy="24" r="26" fill="none" stroke="{glow}" stroke-width="2" stroke-dasharray="10,4">
                    <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="6s" repeatCount="indefinite"/>
                 </circle>
            '''
        elif s >= 76:
            c1, c2, border, text_col = "#78350f", "#f59e0b", "#fde68a", "#ffffff"
            shape = "medal"
            glow = "#d97706"
            tt = "🥇 Gold — Decent fap but conditional. She's attractive and watchable, but you need the right setup — specific tags, a costume you like, or a scenario that clicks. Maybe 50-60% nut rate. She won't ruin a scene but she's not the reason you're hard. You definitely preview before downloading."
        elif s >= 71:
            c1, c2, border, text_col = "#451a03", "#d97706", "#fef3c7", "#ffffff"
            shape = "medal"
            glow = "#b45309"
            tt = "◈ Topaz — Only for the fetish. There's a narrow scenario where she works — maybe it's the costume, the specific genre, or a position she does well. Maybe 40-50% nut rate if the theme is exactly your thing. You're not here for her, you're here for the concept. She's a bonus if the rest of the scene is hot, never the main draw."
        elif s >= 66:
            c1, c2, border, text_col = "#334155", "#94a3b8", "#f1f5f9", "#ffffff"
            shape = "medal"
            glow = "#64748b"
            tt = "🥈 Silver — Barely gets you there. Watchable but no real sexual pull on her own. Maybe 30-40% nut rate, and that's when the studio, scenario, or a hotter co-star does the heavy lifting. You preview everything and skip more than you download. She's filler at best."
        elif s >= 61:
            c1, c2, border, text_col = "#083344", "#06b6d4", "#cffafe", "#ffffff"
            shape = "shield"
            glow = "#0e7490"
            tt = "◇ Aquamarine — Rarely worth the effort. Maybe one or two scenes where something clicked — a specific angle, a moment where she looked hot, or a fetish done right. 20-30% nut rate at best. You need screenshots, tags, and a trusted studio before even considering it. Most of her stuff is a pass. Only here for that one scene."
        elif s >= 56:
            c1, c2, border, text_col = "#1a2416", "#4a7c40", "#dcfce7", "#ffffff"
            shape = "shield"
            glow = "#166534"
            tt = "◈ Jade — Neutral, maybe even a turn-off. No strong physical appeal, her performance feels phoned in, or something about her just doesn't work for you. 10-20% nut rate, and that's being generous. Only worth a look if you're collecting a specific series or the niche is impossible to find elsewhere. Usually leave you soft or clicking away mid-scene."
        elif s >= 50:
            c1, c2, border, text_col = "#3b0000", "#b91c1c", "#fee2e2", "#ffffff"
            shape = "shield"
            glow = "#991b1b"
            tt = "🥉 Garnet — Why am I even watching this? Her look, energy, or on-screen presence actively turns you off. Under 10% nut rate — you mostly click away frustrated or bored. The rare orgasm is despite her, not because of her. Only here if you're desperate or the surrounding content somehow carries the scene. Skip almost everything."
        elif s >= 40:
            t = (s - 40) / 9.0
            r2, g2, b2 = (180 + int(t * 30), 100 + int(t * 20), 10 + int(t * 20))
            hex_c = f"#{r2:02x}{g2:02x}{b2:02x}"
            c1, c2, border, text_col = "#09090b", "#27272a", hex_c, "#ffffff"
            shape = "shield"
            glow = "#27272a"
            tt = "◼ Onyx — Hard pass. You almost never cum to her. The only reason to even consider is extreme desperation, completionism, or a very specific fetish that no one else does. Zero sexual appeal — she actively kills your boner."
        else:
            rt, gt, bt = _lerp_rgb(s)
            c1 = f"rgba({rt//6},{gt//6},{bt//6},1)"
            c2 = f"rgba({rt//2},{gt//2},{bt//2},1)"
            border = f"rgba({rt},{gt},{bt},0.8)"
            text_col = f"rgba({rt},{gt},{bt},1)"
            shape = "pill"
            glow = f"rgba({rt},{gt},{bt},1)"
            glow_opacity = "0.3"
            if s >= 20:
                tt = "Low priority. She doesn't do it for you — face, body, or energy, pick one. Only worth queue space if the concept around her is extremely specific."
            else:
                tt = "Hard pass. Reserved for actresses you actively avoid regardless of what's around them. Don't waste queue space."

        rId = f"grad_sq_{s}"
        
        layers = ""
        txt_y = "25"
        font_size = "15"
        
        if shape == "diamond":
            d_path = "M 24,0 L 48,22 L 24,48 L 0,22 Z"
            txt_y = "24"
            font_size = "16"
            layers = f'''
                <path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <path d="M 24,4 L 43,22 L 24,44 L 5,22 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.6" />
                <path d="M 24,2 L 34,22 L 24,46 L 14,22 Z" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.5" />
                <polygon points="24,2 14,22 24,4" fill="#ffffff" opacity="0.5" />
                <polygon points="24,2 2,22 14,22" fill="#ffffff" opacity="0.2" />
                <polygon points="24,22 34,22 24,46" fill="#000000" opacity="0.3" />
            '''
        elif shape == "gem":
            d_path = "M 12,2 L 36,2 L 48,16 L 48,32 L 36,46 L 12,46 L 0,32 L 0,16 Z"
            txt_y = "25"
            font_size = "15"
            layers = f'''
                <path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <path d="M 14,4 L 34,4 L 45,17 L 45,31 L 34,44 L 14,44 L 3,31 L 3,17 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.5" />
                <polygon points="12,2 36,2 24,18" fill="#ffffff" opacity="0.4" />
                <polygon points="0,16 12,2 24,18 10,24" fill="#ffffff" opacity="0.2" />
                <polygon points="24,18 48,32 36,46" fill="#000000" opacity="0.25" />
                <path d="M 24,18 L 48,16 M 24,18 L 48,32 M 24,18 L 36,46 M 24,18 L 12,46 M 24,18 L 0,32 M 24,18 L 0,16 M 24,18 L 12,2 M 24,18 L 36,2" stroke="#ffffff" stroke-width="1" opacity="0.4"/>
            '''
        elif shape == "hex":
            d_path = "M 24,2 L 45,14 L 45,34 L 24,46 L 3,34 L 3,14 Z"
            layers = f'''
                <path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <path d="M 24,6 L 41,16 L 41,32 L 24,42 L 7,32 L 7,16 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" />
                <polygon points="24,2 45,14 24,24" fill="#ffffff" opacity="0.2" />
                <polygon points="3,14 24,2 24,24" fill="#ffffff" opacity="0.3" />
            '''
        elif shape == "medal":
            layers = f'''
                <circle cx="24" cy="24" r="22" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <circle cx="24" cy="24" r="18" fill="none" stroke="{border}" stroke-width="2" opacity="0.8" stroke-dasharray="2,2" />
                <circle cx="24" cy="24" r="14" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" />
                <circle cx="24" cy="24" r="22" fill="none" stroke="#ffffff" stroke-width="1" opacity="0.4" />
                <path d="M 6,10 Q 24,-2 42,10" fill="none" stroke="#ffffff" stroke-width="5" opacity="0.2" filter="blur(1px)"/>
                <path d="M 12,38 Q 24,46 36,38" fill="none" stroke="#000000" stroke-width="4" opacity="0.3" filter="blur(1px)"/>
            '''
        elif shape == "shield":
            d_path = "M 4,4 L 44,4 L 44,22 C 44,36 24,46 24,46 C 24,46 4,36 4,22 Z"
            txt_y = "24"
            layers = f'''
                <path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <path d="M 8,7 L 40,7 L 40,21 C 40,32 24,41 24,41 C 24,41 8,32 8,21 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4" />
                <path d="M 4,4 L 24,18 L 44,4" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.4"/>
                <rect x="10" y="6" width="28" height="6" fill="#ffffff" opacity="0.2" rx="2"/>
                <path d="M 16,0 L 20,24 L 42,14 L 24,46" fill="#ffffff" opacity="0.1" />
            '''
        else:
            d_path = "M 8,4 L 40,4 A 6,6 0 0 1 46,10 L 46,38 A 6,6 0 0 1 40,44 L 8,44 A 6,6 0 0 1 2,38 L 2,10 A 6,6 0 0 1 8,4 Z"
            layers = f'''
                <path d="{d_path}" fill="url(#{rId})" stroke="{border}" stroke-width="2" filter="url(#shadow)" />
                <path d="M 10,6.5 L 38,6.5 A 3.5,3.5 0 0 1 43.5,10 L 43.5,38 A 3.5,3.5 0 0 1 38,41.5 L 10,41.5 A 3.5,3.5 0 0 1 4.5,38 L 4.5,10 A 3.5,3.5 0 0 1 10,6.5 Z" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.3" />
                <rect x="4" y="4" width="40" height="20" fill="#ffffff" opacity="0.1" rx="4"/>
                <path d="M 6,12 L 42,12" stroke="#ffffff" stroke-width="1" opacity="0.3"/>
            '''

        return f'''<svg width="{size}" height="{size}" viewBox="-12 -12 72 72" xmlns="http://www.w3.org/2000/svg" style="display:block;cursor:pointer;transition:transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);flex-shrink:0" onmouseover="this.style.transform='scale(1.15) rotate(3deg)'" onmouseout="this.style.transform='scale(1) rotate(0deg)'">
    <title>{tt}</title>
    <defs>
        <linearGradient id="{rId}" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="{c1}" />
            <stop offset="40%" stop-color="{c1}" />
            <stop offset="100%" stop-color="{c2}" />
        </linearGradient>
        <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="{glow}" flood-opacity="{glow_opacity}"/>
            <feDropShadow dx="0" dy="6" stdDeviation="4" flood-color="#000000" flood-opacity="0.6"/>
        </filter>
        <filter id="text-glow">
            <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000000" flood-opacity="0.8"/>
            <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="{glow}" flood-opacity="0.6"/>
        </filter>
    </defs>
    {aura_xml}
    {layers}
    <!-- Top-left rim highlight for gloss -->
    <path d="M 12,6 A 16,16 0 0 1 20,4" fill="none" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" opacity="0.8" style="mix-blend-mode: overlay;"/>
    <text x="24" y="{txt_y}" fill="{text_col}" font-size="{font_size}" font-family="system-ui, -apple-system, sans-serif, 'Segoe UI Emoji'" font-weight="900" text-anchor="middle" dominant-baseline="central" alignment-baseline="middle" filter="url(#text-glow)" letter-spacing="0.5">{s}</text>
</svg>'''
"""

new_text = "\n".join(lines[:start]) + "\n" + new_svg_func + "\n" + "\n".join(lines[end:])
p.write_text(new_text, encoding='utf-8')
print("Injected enhanced SVG badge generator.")
