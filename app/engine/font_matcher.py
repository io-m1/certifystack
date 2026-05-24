"""
Font matching engine: maps fonts found in SVG templates to the platform's
curated open-source font library, with fallback by category similarity.
"""

import re
from typing import List, Dict, Optional, NamedTuple
from enum import Enum


class FontCategory(Enum):
    SERIF = "serif"
    SANS_SERIF = "sans-serif"
    SCRIPT = "script"
    DISPLAY = "display"
    MONOSPACE = "monospace"


class FontMatch(NamedTuple):
    requested_font: str       # What the template asked for
    matched_font: str         # Best match in the platform library
    category: FontCategory
    confidence: float         # 0.0–1.0 match quality
    is_exact: bool            # True if name matched exactly (case-insensitive)
    alternatives: List[str]   # Other close matches from same category


# ---------------------------------------------------------------------------
# Platform font library
# ---------------------------------------------------------------------------

PLATFORM_FONTS: Dict[str, Dict] = {
    # --- Serif ---
    "Playfair Display": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "black"],
        "aliases": ["playfair"],
    },
    "Cormorant Garamond": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "italic"],
        "aliases": ["cormorant", "garamond"],
    },
    "Lora": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "italic"],
        "aliases": [],
    },
    "Merriweather": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": [],
    },
    "EB Garamond": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold"],
        "aliases": ["garamond", "eb garamond"],
    },
    "Libre Baskerville": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "italic"],
        "aliases": ["baskerville"],
    },
    "Crimson Text": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "italic"],
        "aliases": ["crimson"],
    },
    "Spectral": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": [],
    },
    "Source Serif Pro": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold"],
        "aliases": ["source serif"],
    },
    "Noto Serif": {
        "category": FontCategory.SERIF,
        "weights": ["regular", "bold"],
        "aliases": [],
    },
    # --- Sans-Serif ---
    "Montserrat": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "black"],
        "aliases": [],
    },
    "Roboto": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "medium"],
        "aliases": [],
    },
    "Josefin Sans": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": ["josefin"],
    },
    "Raleway": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "black"],
        "aliases": [],
    },
    "Open Sans": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "semibold"],
        "aliases": ["opensans"],
    },
    "Lato": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "black"],
        "aliases": [],
    },
    "Nunito": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "black"],
        "aliases": [],
    },
    "Poppins": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "medium"],
        "aliases": [],
    },
    "Inter": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light", "medium"],
        "aliases": [],
    },
    "Source Sans Pro": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": ["source sans"],
    },
    "Work Sans": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": [],
    },
    "Fira Sans": {
        "category": FontCategory.SANS_SERIF,
        "weights": ["regular", "bold", "light"],
        "aliases": ["fira"],
    },
    # --- Script ---
    "Great Vibes": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": [],
    },
    "Alex Brush": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": ["alex"],
    },
    "Dancing Script": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular", "bold"],
        "aliases": ["dancing"],
    },
    "Pacifico": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": [],
    },
    "Sacramento": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": [],
    },
    "Satisfy": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": [],
    },
    "Allura": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": [],
    },
    "Pinyon Script": {
        "category": FontCategory.SCRIPT,
        "weights": ["regular"],
        "aliases": ["pinyon"],
    },
    # --- Display ---
    "Cinzel": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular", "bold", "black"],
        "aliases": [],
    },
    "Cinzel Decorative": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular", "bold", "black"],
        "aliases": ["cinzel decorative"],
    },
    "Abril Fatface": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular"],
        "aliases": ["abril"],
    },
    "Playfair Display SC": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular", "bold"],
        "aliases": ["playfair sc"],
    },
    "Fjalla One": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular"],
        "aliases": ["fjalla"],
    },
    "Oswald": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular", "bold", "light"],
        "aliases": [],
    },
    "Bebas Neue": {
        "category": FontCategory.DISPLAY,
        "weights": ["regular"],
        "aliases": ["bebas"],
    },
    # --- Monospace ---
    "Source Code Pro": {
        "category": FontCategory.MONOSPACE,
        "weights": ["regular", "bold"],
        "aliases": ["source code"],
    },
    "JetBrains Mono": {
        "category": FontCategory.MONOSPACE,
        "weights": ["regular", "bold"],
        "aliases": ["jetbrains"],
    },
    "Fira Code": {
        "category": FontCategory.MONOSPACE,
        "weights": ["regular", "bold", "light"],
        "aliases": ["fira code"],
    },
    "Roboto Mono": {
        "category": FontCategory.MONOSPACE,
        "weights": ["regular", "bold"],
        "aliases": [],
    },
    "Courier Prime": {
        "category": FontCategory.MONOSPACE,
        "weights": ["regular", "bold", "italic"],
        "aliases": ["courier"],
    },
}


# ---------------------------------------------------------------------------
# Heuristic category detection for unknown fonts
# ---------------------------------------------------------------------------

_SERIF_HINTS = re.compile(
    r"\b(serif|times|garamond|georgia|palatino|baskerville|caslon|"
    r"didot|bodoni|century|charter|constantia|cambria|bookman)\b",
    re.IGNORECASE,
)
_SANS_HINTS = re.compile(
    r"\b(sans|gothic|grotesk|helvetica|arial|verdana|futura|gill|"
    r"myriad|calibri|tahoma|optima|trebuchet|avenir)\b",
    re.IGNORECASE,
)
_SCRIPT_HINTS = re.compile(
    r"\b(script|cursive|handwriting|brush|calligraph|pen|ink|"
    r"italic|vibes|allura|sacramento)\b",
    re.IGNORECASE,
)
_DISPLAY_HINTS = re.compile(
    r"\b(display|decorative|heading|title|poster|impact|block|"
    r"black|ultra|condensed|wide)\b",
    re.IGNORECASE,
)
_MONO_HINTS = re.compile(
    r"\b(mono|code|typewriter|courier|terminal|console|fixed)\b",
    re.IGNORECASE,
)


def _guess_category(font_name: str) -> FontCategory:
    """Heuristically guess the FontCategory from a font name string."""
    if _SCRIPT_HINTS.search(font_name):
        return FontCategory.SCRIPT
    if _DISPLAY_HINTS.search(font_name):
        return FontCategory.DISPLAY
    if _MONO_HINTS.search(font_name):
        return FontCategory.MONOSPACE
    if _SERIF_HINTS.search(font_name):
        return FontCategory.SERIF
    if _SANS_HINTS.search(font_name):
        return FontCategory.SANS_SERIF
    return FontCategory.SANS_SERIF  # safe default


def _string_similarity(a: str, b: str) -> float:
    """
    Very lightweight similarity: fraction of characters in common after
    lowercasing and stripping punctuation.
    """
    a_clean = re.sub(r"[^a-z0-9]", "", a.lower())
    b_clean = re.sub(r"[^a-z0-9]", "", b.lower())
    if not a_clean or not b_clean:
        return 0.0
    common = sum(c in b_clean for c in a_clean)
    return common / max(len(a_clean), len(b_clean))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_font(requested_font: str, requested_weight: str = "regular") -> FontMatch:
    """
    Find the closest platform font for *requested_font*.

    Strategy:
    1. Exact case-insensitive name match in PLATFORM_FONTS.
    2. Alias match.
    3. Category-based match using name-similarity scoring.
    4. Fallback to category-default font.

    Returns FontMatch with confidence and alternatives.
    """
    normalised = requested_font.strip()
    normalised_lower = normalised.lower()

    # 1. Exact match
    for name, meta in PLATFORM_FONTS.items():
        if name.lower() == normalised_lower:
            alts = suggest_font_alternatives(name, meta["category"], limit=3)
            return FontMatch(
                requested_font=requested_font,
                matched_font=name,
                category=meta["category"],
                confidence=1.0,
                is_exact=True,
                alternatives=alts,
            )

    # 2. Alias match
    for name, meta in PLATFORM_FONTS.items():
        for alias in meta.get("aliases", []):
            if alias.lower() == normalised_lower:
                alts = suggest_font_alternatives(name, meta["category"], limit=3)
                return FontMatch(
                    requested_font=requested_font,
                    matched_font=name,
                    category=meta["category"],
                    confidence=0.9,
                    is_exact=True,
                    alternatives=alts,
                )

    # 3. Similarity scoring within guessed category
    guessed_cat = _guess_category(normalised)
    candidates = [
        (name, meta)
        for name, meta in PLATFORM_FONTS.items()
        if meta["category"] == guessed_cat
    ]

    if not candidates:
        candidates = list(PLATFORM_FONTS.items())

    scored = sorted(
        candidates,
        key=lambda nm: _string_similarity(normalised, nm[0]),
        reverse=True,
    )
    best_name, best_meta = scored[0]
    best_sim = _string_similarity(normalised, best_name)

    # Confidence: at most 0.85 for non-exact; floor at 0.3
    confidence = max(0.3, min(0.85, best_sim * 0.9 + 0.2 if best_sim > 0 else 0.3))

    alts = [n for n, _ in scored[1:4]]

    return FontMatch(
        requested_font=requested_font,
        matched_font=best_name,
        category=guessed_cat,
        confidence=round(confidence, 3),
        is_exact=False,
        alternatives=alts,
    )


def get_installed_fonts() -> List[str]:
    """Return all font names registered in the platform library."""
    return sorted(PLATFORM_FONTS.keys())


def suggest_font_alternatives(
    font_name: str,
    category: FontCategory,
    limit: int = 3,
) -> List[str]:
    """
    Return up to *limit* alternative font names from the same *category*,
    excluding *font_name* itself.
    """
    return [
        name
        for name, meta in PLATFORM_FONTS.items()
        if meta["category"] == category and name != font_name
    ][:limit]
