"""
Field scoring algorithm: assigns FieldType labels and confidence scores to
detected SVG template fields using evidence-weighted heuristics.
"""

import re
from typing import List, Dict, Tuple, Optional
from enum import Enum
from lxml import etree


class FieldType(Enum):
    RECIPIENT_NAME = "recipient_name"
    CERTIFICATE_ID = "certificate_id"
    ISSUANCE_DATE = "issuance_date"
    COURSE_TITLE = "course_title"
    QR_CODE_ZONE = "qr_code_zone"
    CUSTOM_TEXT = "custom_text"
    UNKNOWN = "unknown"


class ScoredField:
    """Result of scoring a single detected field."""

    def __init__(
        self,
        field_id: str,
        field_type: FieldType,
        confidence: float,
        evidence: List[str],
        suggested_action: str,
    ) -> None:
        self.field_id = field_id
        self.field_type = field_type
        self.confidence = confidence          # 0.0–1.0
        self.evidence = evidence              # Human-readable reasons
        self.suggested_action = suggested_action  # "auto_map"|"review_recommended"|"manual_required"

    def _asdict(self) -> Dict:
        return {
            "field_id": self.field_id,
            "field_type": self.field_type.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
        }

    def __repr__(self) -> str:
        return (
            f"ScoredField(field_id={self.field_id!r}, "
            f"field_type={self.field_type.value!r}, "
            f"confidence={self.confidence:.2f})"
        )


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(
    r"""
    (
        \d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}  # 01/02/2024
      | \d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}    # 2024-01-02
      | \b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?
            |Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?
            |Nov(?:ember)?|Dec(?:ember)?)\b      # month names
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CERT_ID_PATTERN = re.compile(
    r"""
    (
        \bCERT[-_\s]?\d+\b
      | \b[A-Z]{2,6}[-_]\d{4}[-_]\d+\b          # MLJ-2026-000001
      | \b#\d{4,}\b
      | \b[A-Z0-9]{8,}\b                          # generic alphanumeric ID
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NAME_PLACEHOLDER_PATTERN = re.compile(
    r"\b(name|full[_\s]?name|recipient|student|participant|learner|nominee)\b",
    re.IGNORECASE,
)

_COURSE_PATTERN = re.compile(
    r"\b(course|certification|programme|program|training|workshop|diploma|award)\b",
    re.IGNORECASE,
)

_MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}


# ---------------------------------------------------------------------------
# Per-type scorers
# ---------------------------------------------------------------------------

def _score_as_name(field: Dict, dims: Tuple[float, float]) -> Tuple[float, List[str]]:
    """Return (raw_score, evidence_list) for RECIPIENT_NAME."""
    score = 0.0
    evidence: List[str] = []
    w, h = dims

    font_size: float = field.get("font_size") or 0.0
    text: str = (field.get("display_text") or "").strip()
    x: float = field.get("x") or 0.0
    y: float = field.get("y") or 0.0
    text_anchor: str = (field.get("text_anchor") or "start").lower()
    field_id: str = (field.get("field_id") or "").lower()

    if font_size > 24:
        score += 0.3
        evidence.append(f"Large font size ({font_size:.0f}px > 24px suggests name field)")

    if _NAME_PLACEHOLDER_PATTERN.search(text) or _NAME_PLACEHOLDER_PATTERN.search(field_id):
        score += 0.4
        evidence.append("Text or field ID contains name-related keyword")

    if text_anchor == "middle" or (w > 0 and 0.35 * w <= x <= 0.65 * w):
        score += 0.2
        evidence.append("Field is horizontally centered (typical for name)")

    if h > 0 and y < 0.6 * h:
        score += 0.1
        evidence.append("Field is in the upper 60% of the template")

    return score, evidence


def _score_as_certificate_id(field: Dict, dims: Tuple[float, float]) -> Tuple[float, List[str]]:
    """Return (raw_score, evidence_list) for CERTIFICATE_ID."""
    score = 0.0
    evidence: List[str] = []
    w, h = dims

    font_size: float = field.get("font_size") or 0.0
    text: str = (field.get("display_text") or "").strip()
    y: float = field.get("y") or 0.0
    field_id: str = (field.get("field_id") or "").lower()

    id_keywords = re.compile(r"\b(cert|id|num|number|ref|serial|code)\b", re.IGNORECASE)
    if id_keywords.search(text) or id_keywords.search(field_id):
        score += 0.4
        evidence.append("Text or field ID contains cert/ID/number keyword")

    if _CERT_ID_PATTERN.search(text):
        score += 0.3
        evidence.append("Text matches alphanumeric certificate ID pattern")

    if h > 0 and y > 0.7 * h:
        score += 0.2
        evidence.append("Field is in the bottom 30% of the template")

    if 0 < font_size < 18:
        score += 0.1
        evidence.append(f"Small font size ({font_size:.0f}px < 18px typical for IDs)")

    return score, evidence


def _score_as_date(field: Dict, dims: Tuple[float, float]) -> Tuple[float, List[str]]:
    """Return (raw_score, evidence_list) for ISSUANCE_DATE."""
    score = 0.0
    evidence: List[str] = []
    w, h = dims

    text: str = (field.get("display_text") or "").strip()
    y: float = field.get("y") or 0.0
    field_id: str = (field.get("field_id") or "").lower()

    if _DATE_PATTERN.search(text):
        score += 0.5
        evidence.append("Text matches date pattern")

    text_lower = text.lower()
    if any(m in text_lower for m in _MONTH_NAMES):
        score += 0.3
        evidence.append("Text contains a month name")

    date_kw = re.compile(r"\b(date|issued|awarded|completed|day|month|year)\b", re.IGNORECASE)
    if date_kw.search(field_id) or date_kw.search(text):
        score += 0.15
        evidence.append("Field ID or text contains date-related keyword")

    if h > 0 and y > 0.7 * h:
        score += 0.2
        evidence.append("Field is in the bottom 30% (typical for dates)")

    return score, evidence


def _score_as_course_title(field: Dict, dims: Tuple[float, float]) -> Tuple[float, List[str]]:
    """Return (raw_score, evidence_list) for COURSE_TITLE."""
    score = 0.0
    evidence: List[str] = []
    w, h = dims

    font_size: float = field.get("font_size") or 0.0
    text: str = (field.get("display_text") or "").strip()
    y: float = field.get("y") or 0.0
    field_id: str = (field.get("field_id") or "").lower()

    if _COURSE_PATTERN.search(text) or _COURSE_PATTERN.search(field_id):
        score += 0.3
        evidence.append("Text or field ID contains course/certification keyword")

    if h > 0 and y < 0.3 * h:
        score += 0.2
        evidence.append("Field is in the upper 30% (typical for titles)")

    if font_size > 18:
        score += 0.15
        evidence.append(f"Medium-large font ({font_size:.0f}px) consistent with a title")

    return score, evidence


def _normalize_confidence(raw_scores: Dict[FieldType, float]) -> float:
    """
    Normalise the winning raw score to a 0-1 confidence value.
    Uses ratio of winning score to sum of all scores; clamps to [0, 1].
    """
    total = sum(raw_scores.values())
    if total == 0:
        return 0.0
    best = max(raw_scores.values())
    raw_conf = best / total
    return min(1.0, max(0.0, raw_conf))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_fields(
    detected_fields: List[Dict],
    template_width: float,
    template_height: float,
) -> List[ScoredField]:
    """
    Score each detected field and assign a FieldType with confidence.

    Parameters
    ----------
    detected_fields:
        List of field dicts as produced by load_template() (CertificateField._asdict()).
    template_width, template_height:
        SVG canvas dimensions in pixels (used for positional scoring).

    Returns
    -------
    List[ScoredField] sorted by confidence descending.
    """
    dims: Tuple[float, float] = (template_width, template_height)
    results: List[ScoredField] = []

    for field in detected_fields:
        scorers = {
            FieldType.RECIPIENT_NAME: _score_as_name(field, dims),
            FieldType.CERTIFICATE_ID: _score_as_certificate_id(field, dims),
            FieldType.ISSUANCE_DATE: _score_as_date(field, dims),
            FieldType.COURSE_TITLE: _score_as_course_title(field, dims),
        }

        raw_scores: Dict[FieldType, float] = {ft: s for ft, (s, _) in scorers.items()}
        best_type = max(raw_scores, key=lambda ft: raw_scores[ft])
        best_score = raw_scores[best_type]
        best_evidence = scorers[best_type][1]

        if best_score == 0:
            best_type = FieldType.UNKNOWN
            confidence = 0.0
            suggested_action = "manual_required"
        else:
            confidence = _normalize_confidence(raw_scores)
            if confidence >= 0.6:
                suggested_action = "auto_map"
            elif confidence >= 0.4:
                suggested_action = "review_recommended"
            else:
                suggested_action = "manual_required"

        results.append(
            ScoredField(
                field_id=field.get("field_id", ""),
                field_type=best_type,
                confidence=round(confidence, 3),
                evidence=best_evidence or ["No strong evidence; manual review required"],
                suggested_action=suggested_action,
            )
        )

    return sorted(results, key=lambda sf: sf.confidence, reverse=True)


def detect_empty_zones(
    svg_path: str,
    min_width: int = 100,
    min_height: int = 100,
) -> List[Dict]:
    """
    Analyse an SVG file for rectangular regions containing no text or graphic
    elements, suitable for QR code placement.

    Returns list of candidate zones sorted by preference:
    bottom-right → bottom-left → top-right.
    """
    try:
        tree = etree.parse(svg_path)
    except Exception:
        return []

    root = tree.getroot()
    ns = root.nsmap.get(None, "")

    def _dim(attr: str, fallback: float) -> float:
        val = root.get(attr, "")
        try:
            return float(val.replace("px", "").strip())
        except (ValueError, AttributeError):
            vb = root.get("viewBox", "")
            parts = vb.split()
            if len(parts) == 4:
                return float(parts[2]) if attr == "width" else float(parts[3])
            return fallback

    svg_w = _dim("width", 842.0)
    svg_h = _dim("height", 595.0)

    # Collect occupied bounding boxes from text elements
    occupied: List[Dict] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "text":
            try:
                x = float(el.get("x", 0))
                y = float(el.get("y", 0))
                # Rough estimate: 0.6 * font_size * char_count wide
                text = "".join(el.itertext())
                fs_str = el.get("font-size", "12px").replace("px", "")
                try:
                    fs = float(fs_str)
                except ValueError:
                    fs = 12.0
                w = len(text) * fs * 0.6
                occupied.append({"x": x, "y": y - fs, "w": w, "h": fs * 1.5})
            except (ValueError, TypeError):
                pass

    def _overlaps(x: float, y: float, w: float, h: float) -> bool:
        for occ in occupied:
            if not (
                x + w <= occ["x"]
                or x >= occ["x"] + occ["w"]
                or y + h <= occ["y"]
                or y >= occ["y"] + occ["h"]
            ):
                return True
        return False

    # Candidate corners in preference order
    qr_w = max(min_width, 120)
    qr_h = max(min_height, 120)
    margin = 20.0

    candidates = [
        {
            "x": svg_w - qr_w - margin,
            "y": svg_h - qr_h - margin,
            "width": qr_w,
            "height": qr_h,
            "location": "bottom-right",
            "preference": 1,
        },
        {
            "x": margin,
            "y": svg_h - qr_h - margin,
            "width": qr_w,
            "height": qr_h,
            "location": "bottom-left",
            "preference": 2,
        },
        {
            "x": svg_w - qr_w - margin,
            "y": margin,
            "width": qr_w,
            "height": qr_h,
            "location": "top-right",
            "preference": 3,
        },
        {
            "x": margin,
            "y": margin,
            "width": qr_w,
            "height": qr_h,
            "location": "top-left",
            "preference": 4,
        },
    ]

    zones = [c for c in candidates if not _overlaps(c["x"], c["y"], c["width"], c["height"])]
    return zones


def generate_field_mapping(scored_fields: List[ScoredField]) -> Dict[str, str]:
    """
    Produce a final field_id → FieldType.value mapping, resolving conflicts by
    confidence.  Fields with confidence < 0.4 are flagged as UNKNOWN.
    """
    # Resolve conflicts: each FieldType can only win once
    claimed: Dict[FieldType, ScoredField] = {}
    for sf in scored_fields:  # already sorted by confidence desc
        if sf.field_type in (FieldType.UNKNOWN, FieldType.CUSTOM_TEXT):
            continue
        if sf.field_type not in claimed:
            claimed[sf.field_type] = sf

    mapping: Dict[str, str] = {}
    claimed_ids = {sf.field_id for sf in claimed.values()}

    for sf in scored_fields:
        if sf.field_id in claimed_ids and sf == claimed.get(sf.field_type):
            mapping[sf.field_id] = sf.field_type.value
        elif sf.field_id not in claimed_ids:
            if sf.confidence < 0.4:
                mapping[sf.field_id] = FieldType.UNKNOWN.value
            else:
                mapping[sf.field_id] = FieldType.CUSTOM_TEXT.value

    # Fill any remaining scored fields not yet mapped
    for sf in scored_fields:
        if sf.field_id not in mapping:
            mapping[sf.field_id] = FieldType.UNKNOWN.value

    return mapping
