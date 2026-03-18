import pathlib
import re

p = pathlib.Path('tracker/page.py')
text = p.read_text(encoding='utf-8')

# Fix unpacking to 4 items
text = re.sub(r'return\s+nc,\s*ns,\s*bh,\s*locals\(\)\.get\(\"aura\",\s*\"\"\),\s*locals\(\)\.get\(\"aura\",\s*\"\"\)', 'return nc, ns, bh, locals().get("aura", "")', text)

text = re.sub(r'return\s+"#6b7280",\s*"",\s*"",\s*"",\s*""', 'return "#6b7280", "", "", ""', text)

p.write_text(text, encoding='utf-8')
print('Fixed with regex')
