"""I1 — input normalization. the speed bump, NOT the trust boundary.

Normalize untrusted external text BEFORE any scan or classification: strip
zero-width/control chars, NFKC-fold, map common confusables to canonical Latin,
and flag mixed-script tokens and base64/hex blobs.

LOAD-BEARING WALL NOTE: this reduces evasion VOLUME. it is not the defense. a
homoglyph this map misses must still fail safe — because I2 tags the source
untrusted and I3 wraps it as data regardless of the glyph. never rely on this
map being complete.
"""

from __future__ import annotations

import re
import unicodedata

# common cyrillic/greek lookalikes → canonical latin. deliberately partial —
# completeness is impossible, which is exactly why I2/I3 carry the real defense.
_CONFUSABLES = {
    # cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "ѕ": "s", "і": "i", "ј": "j", "к": "k", "н": "h", "т": "t", "в": "b", "м": "m",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Х": "X", "У": "Y",
    "К": "K", "Н": "H", "Т": "T", "В": "B", "М": "M",
    # greek
    "ο": "o", "α": "a", "ε": "e", "ρ": "p", "τ": "t", "υ": "u", "ι": "i",
    "κ": "k", "ν": "v", "Ο": "O", "Α": "A", "Ε": "E", "Ρ": "P", "Τ": "T",
}

_ZERO_WIDTH = "​‌‍⁠﻿­᠎‎‏"
_ZW_RE = re.compile(f"[{re.escape(_ZERO_WIDTH)}]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}\b")
_HEX_RE = re.compile(r"\b(?:0x)?[0-9a-fA-F]{32,}\b")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK", "ARABIC", "HEBREW", "HAN",
            "HIRAGANA", "KATAKANA", "HANGUL")


def _char_script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for s in _SCRIPTS:
        if name.startswith(s):
            return s
    return "OTHER"


def _has_mixed_script(text: str) -> bool:
    # a single word mixing scripts (e.g. cyrillic 'а' inside latin) is the classic
    # homoglyph tell — flag it even though we also fold it.
    for word in _WORD_RE.findall(text):
        scripts = {s for s in (_char_script(c) for c in word) if s}
        if len(scripts) > 1:
            return True
    return False


def normalize_text(text: str | None) -> tuple[str, list[str]]:
    """Return (normalized_text, flags). Flags name the evasions seen, not blocks."""
    flags: list[str] = []
    if not text:
        return "", flags

    if _ZW_RE.search(text):
        flags.append("zero_width_stripped")
    text = _ZW_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)

    text = unicodedata.normalize("NFKC", text)

    # detect mixed-script BEFORE folding — folding would erase the evidence.
    if _has_mixed_script(text):
        flags.append("mixed_script")
    if _BASE64_RE.search(text) or _HEX_RE.search(text):
        flags.append("base64_blob")

    folded = "".join(_CONFUSABLES.get(ch, ch) for ch in text)
    if folded != text:
        flags.append("homoglyph_mapped")

    return folded, flags
