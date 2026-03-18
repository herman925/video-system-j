import textwrap

def format_tooltip(text: str, max_len: int = 60) -> str:
    res = []
    for line in text.split('\n'):
        if not line.strip():
            res.append('')
        else:
            res.extend(textwrap.wrap(line, max_len))
    return '&#10;'.join(res)
