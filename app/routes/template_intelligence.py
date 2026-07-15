"""
Template Intelligence API — Wave 3 endpoints.

Provides field scoring, font matching, QR placement, and mapping
persistence for the WYSIWYG template mapper admin UI.
"""

import os
import json
import tempfile
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required

from app.models import db, CertificateType

bp = Blueprint("template_intelligence", __name__)


# ---------------------------------------------------------------------------
# Helper: load cert_type or 404
# ---------------------------------------------------------------------------

def _get_cert_type(cert_type_id: int) -> CertificateType:
    ct = db.session.get(CertificateType, cert_type_id)
    if ct is None:
        from flask import abort
        abort(404, description=f"CertificateType {cert_type_id} not found")
    return ct


def _svg_path(ct: CertificateType) -> Optional[str]:
    """Return the best available SVG path for *ct*, or None."""
    for attr in ("template_svg_path", "master_svg_path"):
        p = getattr(ct, attr, None)
        if p and os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# POST /api/cert-types/<id>/analyze
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/analyze", methods=["POST"])
@login_required
def analyze_template(cert_type_id: int):
    """
    Run field scoring on the template's detected_fields JSON.

    Returns scored fields with confidence levels, suggested mappings, and
    font match results.  Every field with confidence < 0.6 is flagged for
    review.
    """
    ct = _get_cert_type(cert_type_id)

    raw_fields: List[Dict[str, Any]] = ct.detected_fields or []
    if not raw_fields:
        return jsonify({
            "success": False,
            "error": "No detected fields available. Upload a template first.",
            "scored_fields": [],
        }), 400

    # Derive SVG dimensions for positional scoring
    svg_w, svg_h = 842.0, 595.0
    svg_p = _svg_path(ct)
    if svg_p:
        try:
            from lxml import etree
            root = etree.parse(svg_p).getroot()
            def _d(attr: str, fallback: float) -> float:
                v = root.get(attr, "")
                try:
                    return float(str(v).replace("px", "").strip())
                except (ValueError, AttributeError):
                    vb = root.get("viewBox", "")
                    parts = vb.split()
                    if len(parts) == 4:
                        return float(parts[2]) if attr == "width" else float(parts[3])
                    return fallback
            svg_w = _d("width", 842.0)
            svg_h = _d("height", 595.0)
        except Exception:
            pass

    from app.engine.field_scorer import score_fields, generate_field_mapping

    scored = score_fields(raw_fields, svg_w, svg_h)
    mapping = generate_field_mapping(scored)

    # Persist analysis results
    ct.field_mapping = mapping
    ct.mapping_status = "in_review"
    db.session.commit()

    scored_dicts = [sf._asdict() for sf in scored]
    low_conf = [sf for sf in scored if sf.confidence < 0.6]
    warnings = [
        f"Field '{sf.field_id}' has low confidence ({sf.confidence:.0%}) — manual review required"
        for sf in low_conf
    ]

    return jsonify({
        "success": True,
        "cert_type_id": cert_type_id,
        "template_width": svg_w,
        "template_height": svg_h,
        "scored_fields": scored_dicts,
        "suggested_mapping": mapping,
        "warnings": warnings,
        "review_required": len(low_conf) > 0,
    })


# ---------------------------------------------------------------------------
# GET /api/cert-types/<id>/mapping
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/mapping", methods=["GET"])
@login_required
def get_field_mapping(cert_type_id: int):
    """
    Return the current confirmed field mapping and per-field geometry.
    """
    ct = _get_cert_type(cert_type_id)
    detected: List[Dict] = ct.detected_fields or []
    confirmed: Dict     = ct.field_mapping or {}

    fields_out: List[Dict] = []
    for f in detected:
        fid = f.get("field_id", "")
        fields_out.append({
            **f,
            "field_type":       confirmed.get(fid, f.get("field_type", "unknown")),
            "suggested_action": "auto_map" if confirmed.get(fid) else "manual_required",
        })

    return jsonify({
        "cert_type_id":   cert_type_id,
        "mapping_status": ct.mapping_status or "pending",
        "fields":         fields_out,
        "confirmed_map":  confirmed,
    })


# ---------------------------------------------------------------------------
# PUT /api/cert-types/<id>/mapping
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/mapping", methods=["PUT"])
@login_required
def update_field_mapping(cert_type_id: int):
    """
    Persist admin-confirmed field mapping.

    Request body::

        {
          "fields": [
            { "field_id": "name", "field_type": "recipient_name",
              "x": 421, "y": 380, "font_family": "Playfair Display",
              "font_size": 32, "text_color": "#000000" },
            ...
          ]
        }
    """
    ct = _get_cert_type(cert_type_id)
    data: Dict = request.get_json(force=True) or {}

    incoming_fields: List[Dict] = data.get("fields", [])
    if not incoming_fields:
        return jsonify({"error": "No fields provided"}), 400

    # Build mapping dict and merge geometry back into detected_fields
    new_mapping: Dict[str, str] = {}
    field_index: Dict[str, Dict] = {
        f["field_id"]: f for f in (ct.detected_fields or []) if f.get("field_id")
    }

    for incoming in incoming_fields:
        fid = incoming.get("field_id")
        if not fid:
            continue
        ftype = incoming.get("field_type", "unknown")
        new_mapping[fid] = ftype

        # Merge position / style updates
        if fid in field_index:
            for key in ("x", "y", "font_family", "font_size", "text_color", "bounding_box"):
                if key in incoming:
                    field_index[fid][key] = incoming[key]

    ct.field_mapping     = new_mapping
    ct.detected_fields   = list(field_index.values())
    ct.mapping_status    = "confirmed"
    db.session.commit()

    return jsonify({
        "success":        True,
        "mapping_status": "confirmed",
        "confirmed_map":  new_mapping,
    })


# ---------------------------------------------------------------------------
# POST /api/cert-types/<id>/match-fonts
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/match-fonts", methods=["POST"])
@login_required
def match_template_fonts(cert_type_id: int):
    """
    Match all fonts used in the template to the platform font library.

    Returns one FontMatch result per unique font family, plus a list of all
    available platform fonts.
    """
    ct = _get_cert_type(cert_type_id)

    from app.engine.font_matcher import match_font, get_installed_fonts

    detected: List[Dict] = ct.detected_fields or []
    seen_fonts: Dict[str, str] = {}  # font_family → weight
    for f in detected:
        ff = (f.get("font_family") or "").strip()
        fw = (f.get("font_weight") or "regular").strip()
        if ff:
            seen_fonts[ff] = fw

    matches = []
    no_close_match: List[str] = []

    for ff, fw in seen_fonts.items():
        fm = match_font(ff, fw)
        match_dict = {
            "requested_font": fm.requested_font,
            "matched_font":   fm.matched_font,
            "category":       fm.category.value,
            "confidence":     fm.confidence,
            "is_exact":       fm.is_exact,
            "alternatives":   fm.alternatives,
            "action_required": not fm.is_exact and fm.confidence < 0.6,
        }
        matches.append(match_dict)
        if not fm.is_exact and fm.confidence < 0.6:
            no_close_match.append(ff)

    # Persist
    ct.font_matches = matches
    db.session.commit()

    warnings = [
        f"Font '{f}' has no close match in the platform library — admin selection required"
        for f in no_close_match
    ]

    return jsonify({
        "success":          True,
        "cert_type_id":     cert_type_id,
        "font_matches":     matches,
        "platform_fonts":   get_installed_fonts(),
        "warnings":         warnings,
        "fonts":            matches,  # alias used by JS _populateFontList
    })


# ---------------------------------------------------------------------------
# POST /api/cert-types/<id>/qr-placement
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/qr-placement", methods=["POST"])
@login_required
def suggest_qr_placement(cert_type_id: int):
    """
    Analyse the template and suggest the best QR code placement zone.
    """
    ct = _get_cert_type(cert_type_id)
    svg_p = _svg_path(ct)

    if not svg_p:
        return jsonify({
            "success": False,
            "error":   "No SVG template available for this certificate type.",
        }), 400

    from app.engine.qr_placer import find_qr_placement

    placement = find_qr_placement(svg_p)
    if not placement:
        return jsonify({
            "success":    False,
            "error":      "Could not find a suitable QR placement zone.",
            "placement":  None,
        }), 200

    pl_dict = placement._asdict()

    # Persist
    ct.qr_placement = pl_dict
    db.session.commit()

    return jsonify({
        "success":   True,
        "placement": pl_dict,
        "message": (
            f"QR code placement suggested at {placement.location_desc} "
            f"({placement.confidence:.0%} confidence)."
        ),
    })


# ---------------------------------------------------------------------------
# POST /api/cert-types/<id>/test-preview
# ---------------------------------------------------------------------------

@bp.route("/api/cert-types/<int:cert_type_id>/test-preview", methods=["POST"])
@login_required
def generate_test_preview(cert_type_id: int):
    """
    Generate a certificate preview rendered with sample data.

    Accepts optional ``sample_data`` override in the request body; falls back
    to built-in defaults.  Returns a PDF (application/pdf).
    """
    import io as _io
    import uuid

    ct = _get_cert_type(cert_type_id)
    svg_p = _svg_path(ct)
    if not svg_p:
        return jsonify({"error": "No SVG template available."}), 400

    data: Dict = request.get_json(force=True, silent=True) or {}
    sample_data: Dict[str, str] = data.get("sample_data") or {}

    # Build field_data from confirmed mapping, filling in sample values
    from app.engine.field_scorer import FieldType
    _SAMPLE_DEFAULTS: Dict[str, str] = {
        FieldType.RECIPIENT_NAME.value:  sample_data.get("recipient_name", "John Doe"),
        FieldType.CERTIFICATE_ID.value:  sample_data.get("certificate_id", "CERT-000001"),
        FieldType.ISSUANCE_DATE.value:   sample_data.get("issuance_date",  "January 1, 2026"),
        FieldType.COURSE_TITLE.value:    sample_data.get("course_title",   "Advanced Professional Development"),
        FieldType.CUSTOM_TEXT.value:     sample_data.get("custom_text",    "Sample Text"),
    }

    confirmed_map: Dict[str, str] = ct.field_mapping or {}
    detected: List[Dict] = ct.detected_fields or []

    field_data: Dict[str, str] = {}
    for f in detected:
        fid   = f.get("field_id", "")
        ftype = confirmed_map.get(fid) or f.get("field_type", "")
        if fid and ftype:
            field_data[fid] = _SAMPLE_DEFAULTS.get(ftype, "Sample")

    if not field_data:
        # Fallback: use hardcoded common field IDs
        field_data = {"name": "John Doe", "cert_id": "CERT-000001", "date": "January 1, 2026"}

    tmp_svg = os.path.join(tempfile.gettempdir(), f"preview_{cert_type_id}_{uuid.uuid4().hex[:8]}.svg")

    try:
        from app.engine.svg_personalizer import personalize
        from app.engine.svg2pdf import svg_to_pdf_bytes

        personalize(
            template_path=svg_p,
            field_data=field_data,
            output_path=tmp_svg,
            options={"auto_shrink": True},
        )
        pdf_bytes = svg_to_pdf_bytes(tmp_svg)
    except Exception as exc:
        return jsonify({"error": f"Preview generation failed: {exc}"}), 500
    finally:
        if os.path.exists(tmp_svg):
            os.remove(tmp_svg)

    return send_file(
        _io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"preview_cert_type_{cert_type_id}.pdf",
    )
