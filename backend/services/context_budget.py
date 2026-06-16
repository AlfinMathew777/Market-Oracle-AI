"""
Context budgeting helpers — defensive truncation of free-text before it enters an
LLM prompt.

Context engineering principle (reduction): more source text does not produce better
output, it just inflates the window and dilutes signal. A single unusually long news
headline or source excerpt would otherwise bloat all ~30 agent prompts at once, so we
cap every piece of free text at a known budget before assembly.

Pure, stateless, immutable — returns new strings, never mutates input.
"""

from __future__ import annotations

# Default per-item budget for headlines/short source text. Headlines are usually well
# under this; the cap only fires on pathological inputs (e.g. a "headline" that is an
# entire paragraph). 200 chars keeps a full real headline intact.
DEFAULT_HEADLINE_CHARS = 200

# Ellipsis marker appended to truncated text so the model can tell it was cut.
_SUFFIX = "…"


def truncate_text(text: str | None, max_chars: int = DEFAULT_HEADLINE_CHARS) -> str:
    """
    Return ``text`` shortened to at most ``max_chars`` characters (suffix included).

    Args:
        text:      The string to bound. ``None`` is treated as empty.
        max_chars: Hard upper bound on the returned length. Values <= 0 yield "".

    Returns:
        A new string no longer than ``max_chars``. Whole words are preserved where
        possible — truncation snaps back to the last space before the limit when one
        exists in the final quarter of the budget, otherwise it hard-cuts.
    """
    if not text:
        return ""
    if max_chars <= 0:
        return ""

    text = text.strip()
    if len(text) <= max_chars:
        return text

    # Reserve room for the suffix.
    budget = max_chars - len(_SUFFIX)
    if budget <= 0:
        return _SUFFIX[:max_chars]

    cut = text[:budget]
    # Prefer a clean word boundary if one sits reasonably close to the end of the cut,
    # so we don't slice a word in half when a nearby space is available.
    last_space = cut.rfind(" ")
    if last_space >= budget * 0.75:
        cut = cut[:last_space]

    return cut.rstrip() + _SUFFIX


def total_chars(*parts: str | None) -> int:
    """Sum the character lengths of the given parts, treating ``None`` as empty.

    A coarse, dependency-free proxy for prompt size — useful for budget assertions and
    logging without pulling in a tokenizer.
    """
    return sum(len(p) for p in parts if p)
