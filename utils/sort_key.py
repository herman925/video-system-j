"""Shared sort key utility for multilingual name lists (Latin / Japanese / Chinese).

Three independent buckets, sorted in this order:
  Bucket 0 — Latin/English  : A-Z alphabetical
  Bucket 1 — Japanese        : romaji A-Z  (kana present, or Japanese-only CJK symbols)
  Bucket 2 — Chinese         : stroke count ascending (pure CJK, no kana)
  Bucket ∞ — blank / '—'    : always last

Detection:
  • Has any ASCII letter                        → Latin  (bucket 0)
  • Has hiragana, katakana, or 々〆〇 (U+3005-7) → Japanese (bucket 1)
  • Pure CJK, no kana, no Latin                → Chinese (bucket 2)
  • Anything else                              → Latin bucket

Performance notes:
  • Stroke data loaded from a 20KB binary file (not a 20K-line Python source).
  • pykakasi is lazy-initialised on first use so imports are instant.
"""

import os
import re
import sys
from functools import lru_cache

SORT_DEBUG = False  # set True to enable logging

_kakasi_instance = None


def _kakasi():
    global _kakasi_instance
    if _kakasi_instance is None:
        import pykakasi as _mod
        _kakasi_instance = _mod.Kakasi()
    return _kakasi_instance


# ── Stroke data ────────────────────────────────────────────────────────────────
# Flat bytes array: index = (codepoint − 0x4E00), value = stroke count.
# 0 means unknown/not in table.
_BIN_PATH = os.path.join(os.path.dirname(__file__), 'cjk_strokes.bin')
_CJK_BASE = 0x4E00

with open(_BIN_PATH, 'rb') as _f:
    _STROKES: bytes = _f.read()


def _stroke_count(cp: int) -> int:
    idx = cp - _CJK_BASE
    if 0 <= idx < len(_STROKES):
        return _STROKES[idx] or 99  # 0 = unknown → sort to end of Chinese bucket
    return 99


# ── Detection regexes ──────────────────────────────────────────────────────────
# Japanese-exclusive characters:
#   hiragana   U+3040–U+309F
#   katakana   U+30A0–U+30FF
#   々  U+3005  (ideographic iteration mark, used in names like 八木奈々)
#   〆  U+3006  (ideographic closing mark)
#   〇  U+3007  (ideographic number zero)
_HAS_JAPANESE = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u3005-\u3007]')
_HAS_CJK      = re.compile(r'[\u4e00-\u9fff]')
_HAS_LATIN    = re.compile(r'[a-zA-Z]')


# ── Public API ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=4096)
def romaji_key(text: str) -> str:
    """Return a sort key placing names in bucket order: Latin → Japanese → Chinese.

    Results are cached so repeated sorts over the same actress list are instant.
    """
    if not text or text == '—':
        key = '\uffff'
        if SORT_DEBUG:
            print(f'[SORT] {text!r:30s}  bucket=∞  key={key!r}', file=sys.stderr, flush=True)
        return key

    has_latin    = bool(_HAS_LATIN.search(text))
    has_japanese = bool(_HAS_JAPANESE.search(text))
    has_cjk      = bool(_HAS_CJK.search(text))

    if has_latin or (not has_japanese and not has_cjk):
        # Bucket 0 — Latin / English
        result = _kakasi().convert(text)
        key = '0' + ''.join(item['hepburn'] for item in result).lower()
        if SORT_DEBUG:
            print(f'[SORT] {text!r:30s}  bucket=0(Latin)    key={key!r}', file=sys.stderr, flush=True)
        return key

    if has_japanese:
        # Bucket 1 — Japanese (kana or Japanese CJK symbols present)
        result = _kakasi().convert(text)
        key = '1' + ''.join(item['hepburn'] for item in result).lower()
        if SORT_DEBUG:
            print(f'[SORT] {text!r:30s}  bucket=1(Japanese) key={key!r}', file=sys.stderr, flush=True)
        return key

    # Bucket 2 — Chinese (pure CJK, no Japanese markers)
    parts = []
    stroke_detail = []
    for c in text:
        cp = ord(c)
        if 0x4E00 <= cp <= 0x9FFF:
            sc = _stroke_count(cp)
            parts.append(f'{sc:03d}{cp:06d}')
            stroke_detail.append(f'{c}={sc}(U+{cp:04X})')
        else:
            parts.append(f'000{cp:06d}')
            stroke_detail.append(f'{c}=?(U+{cp:04X})')
    key = '2' + ''.join(parts)
    if SORT_DEBUG:
        print(f'[SORT] {text!r:30s}  bucket=2(Chinese)  key={key!r}  strokes=[{", ".join(stroke_detail)}]', file=sys.stderr, flush=True)
    return key


def log_sorted_order(label: str, items: list, name_fn) -> None:
    """Print the final sorted order to stderr. name_fn(item) should return the display name."""
    if not SORT_DEBUG:
        return
    print(f'\n[SORT] ── {label} sorted order ──', file=sys.stderr, flush=True)
    for i, item in enumerate(items):
        name = name_fn(item)
        key = romaji_key(name)
        print(f'[SORT]   {i+1:3d}. {name!r:30s}  key={key!r}', file=sys.stderr, flush=True)
    print(f'[SORT] ── end ({len(items)} items) ──\n', file=sys.stderr, flush=True)
