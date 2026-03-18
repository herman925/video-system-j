import pathlib

css_file = pathlib.Path('assets/theme.css')
content = css_file.read_text(encoding='utf-8')

aura_css = """
/* ---- Aura Tiers ---- */
@keyframes auraPulseGod {
  0% { text-shadow: 0 0 10px #a5f3fc, 0 0 20px #6366f1, 0 0 30px #6366f1; transform: scale(1); }
  50% { text-shadow: 0 0 15px #ffffff, 0 0 25px #818cf8, 0 0 40px #4f46e5; transform: scale(1.02); }
  100% { text-shadow: 0 0 10px #a5f3fc, 0 0 20px #6366f1, 0 0 30px #6366f1; transform: scale(1); }
}
.aura-god {
  animation: auraPulseGod 3s ease-in-out infinite;
  letter-spacing: 1px;
}

@keyframes auraPulseRuby {
  0% { text-shadow: 0 0 10px #fb7185, 0 0 20px #e11d48; transform: scale(1); }
  50% { text-shadow: 0 0 15px #ffe4e6, 0 0 30px #be123c; transform: scale(1.015); }
  100% { text-shadow: 0 0 10px #fb7185, 0 0 20px #e11d48; transform: scale(1); }
}
.aura-ruby {
  animation: auraPulseRuby 3s ease-in-out infinite;
}

@keyframes auraPulseSapphire {
  0% { text-shadow: 0 0 8px #60a5fa, 0 0 15px #2563eb; }
  50% { text-shadow: 0 0 12px #bfdbfe, 0 0 25px #1d4ed8; }
  100% { text-shadow: 0 0 8px #60a5fa, 0 0 15px #2563eb; }
}
.aura-sapphire {
  animation: auraPulseSapphire 3.5s ease-in-out infinite;
}

@keyframes auraPulseAmethyst {
  0% { text-shadow: 0 0 8px #c084fc, 0 0 15px #9333ea; }
  50% { text-shadow: 0 0 12px #e9d5ff, 0 0 25px #7e22ce; }
  100% { text-shadow: 0 0 8px #c084fc, 0 0 15px #9333ea; }
}
.aura-amethyst {
  animation: auraPulseAmethyst 3.5s ease-in-out infinite;
}

@keyframes auraPulseEmerald {
  0% { text-shadow: 0 0 8px #34d399, 0 0 15px #059669; }
  50% { text-shadow: 0 0 12px #a7f3d0, 0 0 25px #047857; }
  100% { text-shadow: 0 0 8px #34d399, 0 0 15px #059669; }
}
.aura-emerald {
  animation: auraPulseEmerald 4s ease-in-out infinite;
}

@keyframes auraPulseGold {
  0% { text-shadow: 0 0 8px #fde68a, 0 0 15px #d97706; }
  50% { text-shadow: 0 0 12px #fef3c7, 0 0 25px #b45309; }
  100% { text-shadow: 0 0 8px #fde68a, 0 0 15px #d97706; }
}
.aura-gold {
  animation: auraPulseGold 4s ease-in-out infinite;
  display: inline-block;
}
.aura-god, .aura-ruby, .aura-sapphire, .aura-amethyst, .aura-emerald {
  display: inline-block;
}
"""

if '/* ---- Aura Tiers ---- */' not in content:
    content += "\n" + aura_css
    css_file.write_text(content, encoding='utf-8')
    print("CSS updated!")
else:
    print("CSS already contains Aura Tiers")
