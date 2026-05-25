from app.engine.exceptions import (
    CertificateEngineError,
    TemplateValidationError,
    MissingFieldError,
    ConversionError,
    FontError,
)
from app.engine.svg_template_loader import (
    CertificateField,
    load_template,
    resolve_style_inheritance,
    parse_font_size,
)
from app.engine.svg_personalizer import personalize, calculate_text_width
from app.engine.svg2pdf import svg_to_pdf_bytes, svg_to_pdf_file
from app.engine.svg_preview import svg_to_png_bytes, generate_preview_card

# Wave 3: Template Intelligence
from app.engine.field_scorer import score_fields, ScoredField, FieldType, generate_field_mapping
from app.engine.font_matcher import match_font, FontMatch, FontCategory, PLATFORM_FONTS
from app.engine.qr_placer import find_qr_placement, embed_qr_code, QRPlacement

__all__ = [
    # Exceptions
    "CertificateEngineError",
    "TemplateValidationError",
    "MissingFieldError",
    "ConversionError",
    "FontError",
    # Template loading
    "CertificateField",
    "load_template",
    "resolve_style_inheritance",
    "parse_font_size",
    # Personalisation
    "personalize",
    "calculate_text_width",
    # PDF/PNG output
    "svg_to_pdf_bytes",
    "svg_to_pdf_file",
    "svg_to_png_bytes",
    "generate_preview_card",
    # Wave 3 — Field scoring
    "score_fields",
    "ScoredField",
    "FieldType",
    "generate_field_mapping",
    # Wave 3 — Font matching
    "match_font",
    "FontMatch",
    "FontCategory",
    "PLATFORM_FONTS",
    # Wave 3 — QR placement
    "find_qr_placement",
    "embed_qr_code",
    "QRPlacement",
]
