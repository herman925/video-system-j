import pathlib

p = pathlib.Path('tracker/page.py')
text = p.read_text(encoding='utf-8')
text = text.replace('return "#6b7280", "", "", "", ""', 'return "#6b7280", "", "", ""')
text = text.replace('return nc, ns, bh, locals().get("aura", ""), locals().get("aura", "")', 'return nc, ns, bh, locals().get("aura", "")')
p.write_text(text, encoding='utf-8')
print("Fixed tuple unpacking!")
