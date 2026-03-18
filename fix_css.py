import pathlib
import sys

p_theme = pathlib.Path('assets/theme.css')
css_lines = p_theme.read_text(encoding='utf-8')

# We want to replace the aura classes in theme.css with em-based text-shadows 
# so they scale perfectly for the large Title font AND the tiny list font!

new_css = """
/* ---- Aura Tiers ---- */
@keyframes auraPulseGod {
  0% { text-shadow: 0 0 0.2em #a5f3fc, 0 0 0.8em #6366f1, 0 -0.4em 1em rgba(99,102,241,0.8); color: #fff; }
  50% { text-shadow: 0 0 0.4em #cffafe, 0 0 1.2em #818cf8, 0 -0.8em 1.5em rgba(165,243,252,0.9); color: #e0e7ff; }
  100% { text-shadow: 0 0 0.2em #a5f3fc, 0 0 0.8em #6366f1, 0 -0.4em 1em rgba(99,102,241,0.8); color: #fff; }
}
.aura-god { animation: auraPulseGod 2s ease-in-out infinite; font-weight: bold; }

@keyframes auraPulseRuby {
  0% { text-shadow: 0 0 0.2em #fb7185, 0 0 0.8em #e11d48, 0 -0.3em 0.8em rgba(225,29,72,0.8); color: #fff0f3; }
  50% { text-shadow: 0 0 0.4em #fda4af, 0 0 1.2em #be123c, 0 -0.6em 1.2em rgba(251,113,133,0.9); color: #ffe4e6; }
  100% { text-shadow: 0 0 0.2em #fb7185, 0 0 0.8em #e11d48, 0 -0.3em 0.8em rgba(225,29,72,0.8); color: #fff0f3; }
}
.aura-ruby { animation: auraPulseRuby 2s ease-in-out infinite; font-weight: bold; }

@keyframes auraPulseSapphire {
  0% { text-shadow: 0 0 0.2em #60a5fa, 0 0 0.8em #2563eb, 0 -0.3em 0.8em rgba(37,99,235,0.8); color: #eff6ff; }
  50% { text-shadow: 0 0 0.4em #93c5fd, 0 0 1.2em #1d4ed8, 0 -0.6em 1.2em rgba(96,165,250,0.9); color: #dbeafe; }
  100% { text-shadow: 0 0 0.2em #60a5fa, 0 0 0.8em #2563eb, 0 -0.3em 0.8em rgba(37,99,235,0.8); color: #eff6ff; }
}
.aura-sapphire { animation: auraPulseSapphire 2.2s ease-in-out infinite; font-weight: bold; }

@keyframes auraPulseAmethyst {
  0% { text-shadow: 0 0 0.2em #c084fc, 0 0 0.8em #9333ea, 0 -0.3em 0.8em rgba(147,51,234,0.8); color: #faf5ff; }
  50% { text-shadow: 0 0 0.4em #d8b4fe, 0 0 1.2em #7e22ce, 0 -0.6em 1.2em rgba(192,132,252,0.9); color: #f3e8ff; }
  100% { text-shadow: 0 0 0.2em #c084fc, 0 0 0.8em #9333ea, 0 -0.3em 0.8em rgba(147,51,234,0.8); color: #faf5ff; }
}
.aura-amethyst { animation: auraPulseAmethyst 2.5s ease-in-out infinite; font-weight: bold; }

@keyframes auraPulseEmerald {
  0% { text-shadow: 0 0 0.2em #34d399, 0 0 0.8em #059669, 0 -0.3em 0.8em rgba(5,150,105,0.8); color: #ecfdf5; }
  50% { text-shadow: 0 0 0.4em #6ee7b7, 0 0 1.2em #047857, 0 -0.6em 1.2em rgba(52,211,153,0.9); color: #d1fae5; }
  100% { text-shadow: 0 0 0.2em #34d399, 0 0 0.8em #059669, 0 -0.3em 0.8em rgba(5,150,105,0.8); color: #ecfdf5; }
}
.aura-emerald { animation: auraPulseEmerald 2.5s ease-in-out infinite; font-weight: bold; }

@keyframes auraPulseGold {
  0% { text-shadow: 0 0 0.2em #fbbf24, 0 0 0.6em #d97706; color: #fffbeb; }
  50% { text-shadow: 0 0 0.3em #fde68a, 0 0 0.8em #b45309; color: #fef3c7; }
  100% { text-shadow: 0 0 0.2em #fbbf24, 0 0 0.6em #d97706; color: #fffbeb; }
}
.aura-gold { animation: auraPulseGold 3s ease-in-out infinite; }

@keyframes auraPulseTopaz {
  0% { text-shadow: 0 0 0.2em #fcd34d, 0 0 0.6em #b45309; color: #fffbeb; }
  50% { text-shadow: 0 0 0.3em #fef3c7, 0 0 0.8em #92400e; color: #fef3c7; }
  100% { text-shadow: 0 0 0.2em #fcd34d, 0 0 0.6em #b45309; color: #fffbeb; }
}
.aura-topaz { animation: auraPulseTopaz 3s ease-in-out infinite; }

@keyframes auraPulseSilver {
  0% { text-shadow: 0 0 0.2em #cbd5e1, 0 0 0.6em #64748b; color: #f8fafc; }
  50% { text-shadow: 0 0 0.3em #f1f5f9, 0 0 0.8em #475569; color: #ffffff; }
  100% { text-shadow: 0 0 0.2em #cbd5e1, 0 0 0.6em #64748b; color: #f8fafc; }
}
.aura-silver { animation: auraPulseSilver 3.5s ease-in-out infinite; }

@keyframes auraPulseAqua {
  0% { text-shadow: 0 0 0.2em #22d3ee, 0 0 0.6em #0891b2; color: #ecfeff; }
  50% { text-shadow: 0 0 0.3em #a5f3fc, 0 0 0.8em #0e7490; color: #cffafe; }
  100% { text-shadow: 0 0 0.2em #22d3ee, 0 0 0.6em #0891b2; color: #ecfeff; }
}
.aura-aqua { animation: auraPulseAqua 3.5s ease-in-out infinite; }

@keyframes auraPulseJade {
  0% { text-shadow: 0 0 0.15em #b5c4a1, 0 0 0.5em #4a7c40; color: #f0fdf4; }
  50% { text-shadow: 0 0 0.25em #dcfce7, 0 0 0.7em #2d4a24; color: #ffffff; }
  100% { text-shadow: 0 0 0.15em #b5c4a1, 0 0 0.5em #4a7c40; color: #f0fdf4; }
}
.aura-jade { animation: auraPulseJade 4s ease-in-out infinite; }

@keyframes auraPulseGarnet {
  0% { text-shadow: 0 0 0.15em #f87171, 0 0 0.5em #991b1b; color: #fef2f2; }
  50% { text-shadow: 0 0 0.25em #fee2e2, 0 0 0.7em #7f1d1d; color: #ffffff; }
  100% { text-shadow: 0 0 0.15em #f87171, 0 0 0.5em #991b1b; color: #fef2f2; }
}
.aura-garnet { animation: auraPulseGarnet 4s ease-in-out infinite; }
.aura-onyx { color: #a1a1aa; text-shadow: 0 0 0.2em rgba(255,255,255,0.2); }
"""

import re
# Strip everything from /* ---- Aura Tiers ---- */ to EOF
if "/* ---- Aura Tiers ---- */" in css_lines:
    css_base = css_lines[:css_lines.index("/* ---- Aura Tiers ---- */")]
else:
    css_base = css_lines

p_theme.write_text(css_base + new_css, encoding='utf-8')
print("Updated theme.css with em-based keyframes")
