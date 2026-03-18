import re
content = open('tracker/page.py', encoding='utf-8').read()
for m in re.findall(r'_span\(\s*\"(.*?)\"\s*,', content, re.DOTALL):
    print(m[:40].replace('\n', ' '))
