from typing import Optional
import textwrap
from translator.llm import load_config

TIER_ORDER = [
    "diamond",
    "ruby",
    "sapphire",
    "amethyst",
    "emerald",
    "gold",
    "topaz",
    "silver",
    "aquamarine",
    "jade",
    "garnet",
    "onyx",
    "low",
]

TIER_LABELS = {
    "diamond": "Diamond",
    "ruby": "Ruby",
    "sapphire": "Sapphire",
    "amethyst": "Amethyst",
    "emerald": "Emerald",
    "gold": "Gold",
    "topaz": "Topaz",
    "silver": "Silver",
    "aquamarine": "Aquamarine",
    "jade": "Jade",
    "garnet": "Garnet",
    "onyx": "Onyx",
    "low": "Low Rank",
}

TIER_ICONS = {
    "diamond": "💎",
    "ruby": "♦",
    "sapphire": "✦",
    "amethyst": "✦",
    "emerald": "◆",
    "gold": "🥇",
    "topaz": "◈",
    "silver": "🥈",
    "aquamarine": "◇",
    "jade": "◈",
    "garnet": "🥉",
    "onyx": "◼",
    "low": "",
}

DEFAULT_RATING_THRESHOLDS = {
    "diamond": 96,
    "ruby": 94,
    "sapphire": 90,
    "amethyst": 86,
    "emerald": 81,
    "gold": 76,
    "topaz": 71,
    "silver": 66,
    "aquamarine": 61,
    "jade": 56,
    "garnet": 50,
    "onyx": 40,
}

DEFAULT_RATING_TOOLTIPS = {
    "diamond": (
        "💎 Diamond — Guaranteed nut every time, zero exceptions.\n\n"
        "Her face during sex — the expressions, the eye contact, the way she looks overwhelmed — is exactly your type. "
        "Her body is peak for your preferences. She moans like she means it, moves her hips like she wants it, and covers your core fetishes.\n\n"
        "100% success rate. You edge on purpose because finishing feels like a waste. She is the benchmark."
    ),
    "ruby": (
        "♦ Ruby — Near-guaranteed orgasm.\n\n"
        "Her face gets you hard in the thumbnail. Her body is top tier for your type. She fucking performs — active, vocal, convincing moans, pushes back, looks at the camera at exactly the right moment.\n\n"
        "Covers your key fetishes. 90%+ nut rate. You edge through her scenes because finishing too fast feels wasteful. Instant queue."
    ),
    "sapphire": (
        "✦ Sapphire — Reliable go-to material.\n\n"
        "Her face is genuinely attractive and holds up in close-up. She fucks with real energy — active hips, convincing moans, doesn't just lie there. Her genres overlap well with yours.\n\n"
        "80%+ nut rate. Automatic shortlist. One of your regulars when you want to get off without gambling."
    ),
    "amethyst": (
        "✦ Amethyst — Specific fetish goldmine.\n\n"
        "Her face, body, or the way she moans hits a specific nerve that's hard to explain. She commits properly to the genres and acts you're wired for.\n\n"
        "When theme alignment is right — exact outfit, exact scenario, exact dynamic — you bust hard and fast. 70%+ nut rate when matched. Not auto-queue, but dominant when conditions are met."
    ),
    "emerald": (
        "◆ Emerald — Solid nut when the stars align.\n\n"
        "Her face has moments — specific expressions or angles where she looks genuinely hot. Her performance has real energy in the right scenes. With the right studio, outfit, co-star, or scenario, she delivers.\n\n"
        "60-70% nut rate. Worth tracking — when she hits, she really hits. Check cover and tags before committing."
    ),
    "gold": (
        "🥇 Gold — Conditional fap.\n\n"
        "Her face is passable with occasional good moments. Her performance is adequate but inconsistent — the scenario or co-star usually carries the weight. You need specific tags or a scene concept you already know works before committing.\n\n"
        "50-60% nut rate. Always preview. She's not the reason you're hard."
    ),
    "topaz": (
        "◈ Topaz — Only for the fetish.\n\n"
        "In a very narrow scenario — specific costume, specific act, exact fetish executed right — she's passable. Outside that band, forgettable. Her face and body don't do it for you generally but one particular setup makes her usable.\n\n"
        "40-50% nut rate when conditions are exact. You're here for the concept, not her."
    ),
    "silver": (
        "🥈 Silver — Barely gets you there.\n\n"
        "Her face and body are neutral-to-off for your preferences. Her moans are mechanical, her performance goes through the motions without heat.\n\n"
        "30-40% nut rate, and the studio or a hotter co-star is doing the heavy lifting when you do finish. You preview everything and skip most of it. Pure filler."
    ),
    "aquamarine": (
        "◇ Aquamarine — Rarely worth the effort.\n\n"
        "Her face has little appeal and her expressions during sex are unconvincing. Her performance is flat — moans on cue without any energy behind them. Maybe one or two scenes in her catalog where something accidentally clicked.\n\n"
        "20-30% nut rate at best. Full preview plus specific tags from a trusted studio required. Most releases are an immediate pass."
    ),
    "jade": (
        "◈ Jade — Neutral to mild turn-off.\n\n"
        "Her face during sex is indifferent or unsexy — nothing about her expressions pulls you in. Her body doesn't match your preferences and her performance is robotic.\n\n"
        "10-20% nut rate, being generous. Only worth loading for a rare niche or specific series. Will usually leave you soft or clicking away before it ends."
    ),
    "garnet": (
        "🥉 Garnet — Why am I even watching this?\n\n"
        "Her face, body, and performance actively work against you finishing. Her expressions are off-putting, her moans break immersion, and her presence in the scene is a net negative.\n\n"
        "Under 10% nut rate. On the rare occasion you finish, it's despite her. Only here out of desperation or the surrounding production somehow carries the entire load. Consider removing her."
    ),
    "onyx": (
        "◼ Onyx — Hard pass.\n\n"
        "Her face does nothing for you, her body fails your physical preferences, her performance is grating or absent. Near-zero nut rate — and when you do finish it required mentally removing her from the scene.\n\n"
        "She actively kills the erection. Only reason to look: extreme desperation, completionism, or a fetish niche literally no one else covers."
    ),
    "low": (
        "Bottom tier — Zero appeal.\n\n"
        "Her face, body, and performance combine into an active turn-off. Zero nut rate. She makes you close the tab.\n\n"
        "Why is she here?"
    ),
}

LEGACY_PLACEHOLDER_TOOLTIPS = {
    "diamond": "💎 Diamond",
    "ruby": "♦ Ruby",
    "sapphire": "✦ Sapphire",
    "amethyst": "✦ Amethyst",
    "emerald": "◆ Emerald",
    "gold": "🥇 Gold",
    "topaz": "◈ Topaz",
    "silver": "🥈 Silver",
    "aquamarine": "◇ Aquamarine",
    "jade": "◈ Jade",
    "garnet": "🥉 Garnet",
    "onyx": "◼ Onyx",
    "low": "Low rank",
}


def get_rating_thresholds(config: Optional[dict] = None) -> dict:
    cfg = config or load_config()
    raw = cfg.get("rating_thresholds", {})
    thresholds = {
        key: int(raw.get(key, DEFAULT_RATING_THRESHOLDS[key]))
        for key in DEFAULT_RATING_THRESHOLDS
    }
    thresholds = {key: max(0, min(100, value)) for key, value in thresholds.items()}

    ordered = TIER_ORDER[:-1]
    for idx in range(len(ordered) - 1):
        current_key = ordered[idx]
        next_key = ordered[idx + 1]
        if thresholds[current_key] <= thresholds[next_key]:
            return DEFAULT_RATING_THRESHOLDS.copy()

    return thresholds


def get_rating_tooltips(config: Optional[dict] = None) -> dict:
    cfg = config or load_config()
    raw = cfg.get("rating_tooltips", {})
    normalized = {}
    for key in TIER_ORDER:
        value = raw.get(key)
        if value is None:
            normalized[key] = DEFAULT_RATING_TOOLTIPS[key]
            continue

        value = str(value)
        if value.strip() == LEGACY_PLACEHOLDER_TOOLTIPS[key]:
            normalized[key] = DEFAULT_RATING_TOOLTIPS[key]
            continue

        normalized[key] = value

    return normalized


def get_rating_tier(score: Optional[int], config: Optional[dict] = None) -> str | None:
    if score is None:
        return None

    s = max(0, min(100, int(score)))
    thr = get_rating_thresholds(config)

    if s >= thr["diamond"]:
        return "diamond"
    if s >= thr["ruby"]:
        return "ruby"
    if s >= thr["sapphire"]:
        return "sapphire"
    if s >= thr["amethyst"]:
        return "amethyst"
    if s >= thr["emerald"]:
        return "emerald"
    if s >= thr["gold"]:
        return "gold"
    if s >= thr["topaz"]:
        return "topaz"
    if s >= thr["silver"]:
        return "silver"
    if s >= thr["aquamarine"]:
        return "aquamarine"
    if s >= thr["jade"]:
        return "jade"
    if s >= thr["garnet"]:
        return "garnet"
    if s >= thr["onyx"]:
        return "onyx"
    return "low"

def _format_tooltip(text: str, max_len: int = 60) -> str:
    res = []
    for line in text.split('\n'):
        if not line.strip():
            res.append('')
        else:
            res.extend(textwrap.wrap(line, max_len))
    return '&#10;'.join(res)

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

def get_score_info(score: Optional[int]):
    if score is None:
        return "#6b7280", "", "", ""
    s = max(0, min(100, int(score)))

    def _span(tip, css, icon, val):
        tip = _format_tooltip(tip)
        return (
            f'<span title="{tip}" style="{_B}{css}">'
            f'<span style="font-size:1.25em;line-height:1;">{icon}</span>'
            f'<span style="font-size:1em;line-height:1;">{val}</span>'
            f"</span>"
        )

    cfg = load_config()
    tts = get_rating_tooltips(cfg)
    thr = get_rating_thresholds(cfg)

    aura = ""
    # We omit inline text-shadows (ns="") so the CSS em-based keyframes can apply cleanly
    if s >= int(thr.get("diamond", 96)):
        nc, ns, aura = "#a5f3fc", "", "aura-god"
        bh = _span(tts.get("diamond", "💎 Diamond"), "background:linear-gradient(135deg,#312e81,#6366f1,#06b6d4,#10b981,#6366f1);animation:trk-hue-spin 3s linear infinite;color:#fff;border:1px solid #818cf8;text-shadow:0 0 8px #fff,0 0 18px #a5f3fc;box-shadow:0 0 14px rgba(99,102,241,0.9),0 0 28px rgba(6,182,212,0.5);", "💎", s)
    elif s >= int(thr.get("ruby", 94)):
        nc, ns, aura = "#fb7185", "", "aura-ruby"
        bh = _span(tts.get("ruby", "♦ Ruby"), "background:linear-gradient(135deg,#4c0519,#be123c,#fb7185,#fda4af,#e11d48);color:#fff0f3;border:1px solid #fb7185;text-shadow:0 0 8px rgba(253,164,175,0.8),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(225,29,72,0.8),0 0 22px rgba(251,113,133,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "♦", s)
    elif s >= int(thr.get("sapphire", 90)):
        nc, ns, aura = "#60a5fa", "", "aura-sapphire"
        bh = _span(tts.get("sapphire", "✦ Sapphire"), "background:linear-gradient(135deg,#1e3a8a,#1d4ed8,#60a5fa,#bfdbfe,#3b82f6);color:#eff6ff;border:1px solid #60a5fa;text-shadow:0 0 8px rgba(191,219,254,0.7),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(29,78,216,0.8),0 0 22px rgba(96,165,250,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "✦", s)
    elif s >= int(thr.get("amethyst", 86)):
        nc, ns, aura = "#c084fc", "", "aura-amethyst"
        bh = _span(tts.get("amethyst", "✦ Amethyst"), "background:linear-gradient(135deg,#2e1065,#7e22ce,#c084fc,#e9d5ff,#a855f7);color:#faf5ff;border:1px solid #a855f7;text-shadow:0 0 8px rgba(233,213,255,0.7),0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 12px rgba(126,34,206,0.8),0 0 22px rgba(192,132,252,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "✦", s)
    elif s >= int(thr.get("emerald", 81)):
        nc, ns, aura = "#34d399", "", "aura-emerald"
        bh = _span(tts.get("emerald", "◆ Emerald"), "background:linear-gradient(135deg,#022c22,#065f46,#34d399,#a7f3d0,#10b981);color:#ecfdf5;border:1px solid #34d399;text-shadow:0 0 8px rgba(167,243,208,0.7),0 1px 2px rgba(0,0,0,0.5);box-shadow:0 0 12px rgba(5,150,105,0.8),0 0 22px rgba(52,211,153,0.4),inset 0 1px 0 rgba(255,255,255,0.2);", "◆", s)
    elif s >= int(thr.get("gold", 76)):
        nc, ns, aura = "#fbbf24", "", "aura-gold"
        bh = _span(tts.get("gold", "🥇 Gold"), "background:linear-gradient(135deg,#78350f,#d97706,#fbbf24,#fde68a,#f59e0b,#92400e);color:#1c1917;border:1px solid #f59e0b;text-shadow:0 1px 2px rgba(0,0,0,0.3);box-shadow:0 0 10px rgba(251,191,36,0.8),0 0 22px rgba(217,119,6,0.4),inset 0 1px 0 rgba(255,255,255,0.35);", "🥇", s)
    elif s >= int(thr.get("topaz", 71)):
        nc, ns, aura = "#fcd34d", "", "aura-topaz"
        bh = _span(tts.get("topaz", "◈ Topaz"), "background:linear-gradient(135deg,#451a03,#b45309,#fcd34d,#fef3c7,#d97706);color:#1c1917;border:1px solid #fbbf24;text-shadow:0 1px 2px rgba(0,0,0,0.25);box-shadow:0 0 8px rgba(252,211,77,0.6),inset 0 1px 0 rgba(255,255,255,0.3);", "◈", s)
    elif s >= int(thr.get("silver", 66)):
        nc, ns, aura = "#cbd5e1", "", "aura-silver"
        bh = _span(tts.get("silver", "🥈 Silver"), "background:linear-gradient(135deg,#475569,#94a3b8,#e2e8f0,#cbd5e1,#64748b);color:#0f172a;border:1px solid #94a3b8;text-shadow:0 1px 2px rgba(255,255,255,0.5);box-shadow:0 0 8px rgba(148,163,184,0.6),inset 0 1px 0 rgba(255,255,255,0.4);", "🥈", s)
    elif s >= int(thr.get("aquamarine", 61)):
        nc, ns, aura = "#22d3ee", "", "aura-aqua"
        bh = _span(tts.get("aquamarine", "◇ Aquamarine"), "background:linear-gradient(135deg,#083344,#0e7490,#22d3ee,#a5f3fc,#06b6d4);color:#ecfeff;border:1px solid #22d3ee;text-shadow:0 0 7px rgba(165,243,252,0.7),0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 10px rgba(8,145,178,0.7),0 0 18px rgba(34,211,238,0.35),inset 0 1px 0 rgba(255,255,255,0.2);", "◇", s)
    elif s >= int(thr.get("jade", 56)):
        nc, ns, aura = "#b5c4a1", "", "aura-jade"
        bh = _span(tts.get("jade", "◈ Jade"), "background:linear-gradient(135deg,#1a2416,#2d4a24,#4a7c40,#b5c4a1,#7aab6a);color:#e8f0e4;border:1px solid #7aab6a;text-shadow:0 1px 2px rgba(0,0,0,0.4);box-shadow:0 0 6px rgba(74,124,64,0.5),inset 0 1px 0 rgba(255,255,255,0.12);", "◈", s)
    elif s >= int(thr.get("garnet", 50)):
        nc, ns, aura = "#f87171", "", "aura-garnet"
        bh = _span(tts.get("garnet", "🥉 Garnet"), "background:linear-gradient(135deg,#3b0000,#7f1d1d,#b91c1c,#f87171,#991b1b);color:#fef2f2;border:1px solid #dc2626;text-shadow:0 1px 3px rgba(0,0,0,0.6);box-shadow:0 0 8px rgba(127,29,29,0.7),inset 0 1px 0 rgba(255,255,255,0.1);", "🥉", s)
    elif s >= int(thr.get("onyx", 40)):
        t = (s - 40) / 9.0
        r2, g2, b2 = (180 + int(t * 30), 100 + int(t * 20), 10 + int(t * 20))
        nc = f"#{r2:02x}{g2:02x}{b2:02x}"
        ns = ""
        aura = "aura-onyx"
        tip = _format_tooltip(tts.get("onyx", "◼ Onyx"))
        bh = f'<span title="{tip}" style="{_B}background:linear-gradient(135deg,#09090b,#18181b,#27272a,#{r2:02x}{g2:02x}{b2:02x}44);color:#{r2:02x}{g2:02x}{b2:02x};border:1px solid rgba({r2},{g2},{b2},0.5);box-shadow:0 0 6px rgba({r2},{g2},{b2},0.4);"><span style="font-size:1.25em;line-height:1;">◼</span><span style="font-size:1em;line-height:1;">{s}</span></span>'
    else:
        r, g, b = _lerp_rgb(s)
        hex_col = f"#{r:02x}{g:02x}{b:02x}"
        bg_a = 0.10 + s / 400
        bdr_a = 0.25 + s / 200
        glow_str = f"box-shadow:0 0 {3 + s//10}px rgba({r},{g},{b},{0.15 + s/220:.2f});" if s >= 15 else ""
        nc, ns, aura = hex_col, ("" if s < 20 else f"0 0 3px rgba({r},{g},{b},{s/120:.2f})"), ""
        tip = _format_tooltip(tts.get("low", "Low rank"))
        bh = f'<span title="{tip}" style="{_B}background:rgba({r},{g},{b},{bg_a:.2f});color:{hex_col};border:1px solid rgba({r},{g},{b},{bdr_a:.2f});{glow_str}"><span style="font-size:1em;line-height:1;">{s}</span></span>'
    
    return nc, ns, bh, aura

def get_score_html(rating: Optional[int]) -> str:
    if rating is None:
        return ""
    return get_score_info(int(rating))[2]

def get_actor_rank_html_span(actor_name: str, name_to_rating: dict) -> str:
    r = name_to_rating.get(actor_name)
    c, s, _, aura = get_score_info(r)
    style = f"color:{c};" + (f"text-shadow:{s};" if s else "")
    return f'<span class="{aura}" style="{style}">{actor_name}</span>'
