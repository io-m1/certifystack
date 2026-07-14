"""
MedLocum Jobs designed certificate renderer.

A faithful ReportLab port of the proven MedLocum e-learning certificate
(Laravel: resources/views/pdf/certificate.blade.php, rendered by DomPDF).
It reproduces the same A4 portrait design programmatically so no master
template upload, overlay coordinates or OCR are needed:

  - cream page with dark/bright green side bars
  - gold corner brackets (top-left, bottom-right)
  - white MLJ roundel with navy pill (top-right)
  - "{COURSE} CERTIFICATION" title, "This is to certify that:"
  - italic serif recipient name over a gold rule
  - completion statement, "Date Issued: {Month, Year}.", learning hours
  - footer: signature over gold rule, gold/green seal, training
    organisation block with QR code and certificate number
  - verification URL line at the very bottom

Colours and geometry are transcribed 1:1 from the source template
(mm positions, px font sizes at the CSS 96dpi -> pt ratio of 0.75).
"""

import io
import os
import logging

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

MM = 72.0 / 25.4          # millimetres -> points
PX = 0.75                 # CSS px (96dpi) -> points
PAGE_W = 210 * MM
PAGE_H = 297 * MM

# ── Palette (verbatim from the MedLocum template) ─────────────────
CREAM = HexColor('#f5f3ec')
GREEN_DARK = HexColor('#0d3b22')
GREEN_BRIGHT = HexColor('#3aa62c')
GREEN_DEEP = HexColor('#14532d')
GREEN_TEXT = HexColor('#166534')
GREEN_LINK = HexColor('#15803d')
GOLD = HexColor('#c9a227')
GOLD_TEXT = HexColor('#8a6d1d')
NAVY = HexColor('#1a2f5e')
INK = HexColor('#123524')
GREY_BODY = HexColor('#4b5563')
GREY_DARK = HexColor('#1f2937')
GREY_FAINT = HexColor('#9ca3af')
WHITE = HexColor('#ffffff')

FONT = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_SERIF_ITALIC = 'Times-Italic'

DEFAULTS = {
    'organisation': 'Medical Locum Jobs',
    'website': 'www.medlocumjobs.com',
    'signatory_name': 'Abiola Oloye',
    'signatory_title': 'Training Director',
}

_SIGNATURE_CANDIDATES = (
    os.environ.get('CERT_SIGNATURE_PATH') or '',
    os.path.join('uploads', 'signature.png'),
    os.path.join('static', 'signature.png'),
)


def _y_top(mm_from_top: float) -> float:
    """Convert a distance from the top edge (mm) to a ReportLab y coordinate."""
    return PAGE_H - mm_from_top * MM


def _find_signature_path() -> str | None:
    for candidate in _SIGNATURE_CANDIDATES:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _qr_image(url: str) -> ImageReader:
    qr = qrcode.QRCode(
        version=None, box_size=6, border=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ImageReader(buf)


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word-wrap for centred blocks."""
    words = (text or '').split()
    lines, current = [], ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if stringWidth(trial, font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or ['']


def _draw_spaced_centred(c, x_center, y, text, font, size, char_space):
    """Centred text with letter-spacing (ReportLab centres without it)."""
    width = stringWidth(text, font, size) + char_space * max(len(text) - 1, 0)
    obj = c.beginText()
    obj.setTextOrigin(x_center - width / 2, y)
    obj.setFont(font, size)
    obj.setCharSpace(char_space)
    obj.textOut(text)
    # Character spacing is part of the persistent PDF text state — reset it
    # so later text (footer, verify line) is not letter-spaced too.
    obj.setCharSpace(0)
    c.drawText(obj)


def render_mlj_certificate(
    full_name: str,
    course_title: str,
    certificate_id: str,
    issued_at=None,
    verify_url: str = '',
    duration_hours: float = 0,
    organisation: str = '',
    website: str = '',
    signatory_name: str = '',
    signatory_title: str = '',
    include_qr: bool = True,
    signature_path: str = None,
) -> bytes:
    """Render the MedLocum designed certificate and return PDF bytes."""
    from datetime import datetime

    issued_at = issued_at or datetime.utcnow()
    organisation = organisation or DEFAULTS['organisation']
    website = website or DEFAULTS['website']
    signatory_name = signatory_name or DEFAULTS['signatory_name']
    signatory_title = signatory_title or DEFAULTS['signatory_title']

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f'Certificate — {certificate_id}')

    # ── Cream page ────────────────────────────────────────────────
    c.setFillColor(CREAM)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # ── Green side bars ───────────────────────────────────────────
    c.setFillColor(GREEN_DARK)
    c.rect(9 * MM, _y_top(42 + 118), 2 * MM, 118 * MM, stroke=0, fill=1)
    c.rect(PAGE_W - (9 + 2) * MM, _y_top(176 + 82), 2 * MM, 82 * MM, stroke=0, fill=1)
    c.setFillColor(GREEN_BRIGHT)
    c.rect(12 * MM, _y_top(42 + 118), 3 * MM, 118 * MM, stroke=0, fill=1)
    c.rect(PAGE_W - (12 + 3) * MM, _y_top(176 + 82), 3 * MM, 82 * MM, stroke=0, fill=1)

    # ── Gold corner brackets ──────────────────────────────────────
    c.setStrokeColor(GOLD)

    def _bracket(x, y_top_mm, w, h, top, left, bottom, right, weight):
        c.setLineWidth(weight)
        y0 = _y_top(y_top_mm + h)
        if top:
            c.line(x, _y_top(y_top_mm), x + w * MM, _y_top(y_top_mm))
        if left:
            c.line(x, y0, x, _y_top(y_top_mm))
        if bottom:
            c.line(x, y0, x + w * MM, y0)
        if right:
            c.line(x + w * MM, y0, x + w * MM, _y_top(y_top_mm))

    _bracket(12 * MM, 12, 28, 30, True, True, False, False, 2.5)
    _bracket(15 * MM, 15, 8, 20, True, True, False, False, 4)
    # Bottom-right brackets are specified from the bottom edge in the source.
    br_top = 297 - 12 - 30
    _bracket(PAGE_W - (12 + 28) * MM, br_top, 28, 30, False, False, True, True, 2.5)
    br_inner_top = 297 - 15 - 20
    _bracket(PAGE_W - (15 + 8) * MM, br_inner_top, 8, 20, False, False, True, True, 4)

    # ── Logo roundel (top-right) ──────────────────────────────────
    roundel_r = 17 * MM
    cx = PAGE_W - 18 * MM - roundel_r
    cy = _y_top(14) - roundel_r
    c.setFillColor(WHITE)
    c.setStrokeColor(GREEN_BRIGHT)
    c.setLineWidth(2.5)
    c.circle(cx, cy, roundel_r, stroke=1, fill=1)

    c.setFillColor(INK)
    line_h = 9.5 * PX * 1.35
    text_y = cy + roundel_r - 7.5 * MM - 9.5 * PX
    for word in ('MEDICAL', 'LOCUM', 'JOBS'):
        _draw_spaced_centred(c, cx, text_y, word, FONT_BOLD, 9.5 * PX, 1 * PX)
        text_y -= line_h

    pill_text, pill_size, pill_space = 'M L J', 8 * PX, 2 * PX
    pill_text_w = stringWidth(pill_text, FONT_BOLD, pill_size) + pill_space * (len(pill_text) - 1)
    pill_w = pill_text_w + 2 * 7 * PX
    pill_h = pill_size + 2 * 1.5 * PX + 2
    pill_y = text_y + line_h - 1.5 * MM - pill_h
    c.setFillColor(NAVY)
    c.roundRect(cx - pill_w / 2, pill_y, pill_w, pill_h, 6 * PX, stroke=0, fill=1)
    c.setFillColor(WHITE)
    _draw_spaced_centred(c, cx, pill_y + (pill_h - pill_size) / 2 + 1, pill_text, FONT_BOLD, pill_size, pill_space)

    # ── Main content (centred column) ─────────────────────────────
    content_center = PAGE_W / 2
    content_width = PAGE_W - 2 * 26 * MM

    title_size = 24 * PX
    title_lh = title_size * 1.35
    title_lines = _wrap((course_title or '').upper(), FONT_BOLD, title_size, content_width)
    title_lines.append('CERTIFICATION')

    y = _y_top(56) - title_size
    c.setFillColor(GREEN_DEEP)
    for line in title_lines:
        _draw_spaced_centred(c, content_center, y, line, FONT_BOLD, title_size, 1.5 * PX)
        y -= title_lh

    y -= 22 * MM - title_lh
    c.setFillColor(GREY_BODY)
    c.setFont(FONT, 14 * PX)
    c.drawCentredString(content_center, y, 'This is to certify that:')

    recipient_size = 38 * PX
    y -= 8 * MM + recipient_size * 0.35
    c.setFillColor(GREEN_DEEP)
    c.setFont(FONT_SERIF_ITALIC, recipient_size)
    c.drawCentredString(content_center, y, full_name)

    y -= 4 * MM
    c.setFillColor(GOLD)
    c.rect(content_center - 55 * MM, y, 110 * MM, 1.2, stroke=0, fill=1)

    completion_size = 14 * PX
    completion_lh = completion_size * 1.55
    y -= 10 * MM
    c.setFillColor(GREEN_TEXT)
    for line in _wrap(
        f'has successfully completed training in {course_title}',
        FONT_BOLD, completion_size, 150 * MM,
    ):
        c.setFont(FONT_BOLD, completion_size)
        c.drawCentredString(content_center, y, line)
        y -= completion_lh

    y -= 8 * MM - completion_lh
    c.setFont(FONT_BOLD, 13 * PX)
    c.drawCentredString(content_center, y, f"Date Issued: {issued_at.strftime('%B, %Y')}.")

    if duration_hours and float(duration_hours) > 0:
        y -= 3 * MM + 10 * PX
        c.setFillColor(GOLD_TEXT)
        _draw_spaced_centred(
            c, content_center, y,
            f'{float(duration_hours):.1f} LEARNING HOURS',
            FONT_BOLD, 10 * PX, 1 * PX,
        )

    # ── Footer: signature / seal / organisation + QR ──────────────
    footer_bottom = 46 * MM
    footer_left = 20 * MM
    footer_width = PAGE_W - 2 * 20 * MM

    # Column 1 — signature stack (bottom-aligned: org, title, name, rule, image)
    col1_center = footer_left + footer_width * 0.16
    line = footer_bottom
    c.setFillColor(GREEN_DEEP)
    c.setFont(FONT_BOLD, 11 * PX)
    c.drawCentredString(col1_center, line, organisation)
    line += 11 * PX * 1.35
    c.drawCentredString(col1_center, line, signatory_title)
    line += 13 * PX * 1.3
    c.setFont(FONT_BOLD, 13 * PX)
    c.drawCentredString(col1_center, line, signatory_name)
    line += 13 * PX + 1.5 * MM
    c.setFillColor(GOLD)
    c.rect(col1_center - 22 * MM, line, 44 * MM, 1, stroke=0, fill=1)

    sig_path = signature_path or _find_signature_path()
    if sig_path:
        try:
            sig = ImageReader(sig_path)
            iw, ih = sig.getSize()
            sig_h = 15 * MM
            sig_w = sig_h * iw / ih
            c.drawImage(
                sig, col1_center - sig_w / 2, line + 1.5 * MM,
                width=sig_w, height=sig_h,
                preserveAspectRatio=True, mask='auto',
            )
        except Exception as exc:  # pragma: no cover — malformed image only
            logger.warning('Signature image skipped: %s', exc)

    # Column 2 — gold/green seal
    col2_center = footer_left + footer_width * 0.43
    seal_cy = footer_bottom + 13.5 * MM
    c.setFillColor(GOLD)
    c.circle(col2_center, seal_cy, 13.5 * MM, stroke=0, fill=1)
    c.setFillColor(GREEN_DEEP)
    c.setStrokeColor(WHITE)
    c.setLineWidth(1.5)
    c.circle(col2_center, seal_cy, 10 * MM, stroke=1, fill=1)

    # Column 3 — organisation block + QR + certificate number
    col3_right = footer_left + footer_width
    cert_no_y = footer_bottom
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 12 * PX)
    c.drawRightString(col3_right, cert_no_y, f'CERTIFICATE NO: {certificate_id}')

    qr_size = 20 * MM
    block_bottom = cert_no_y + 12 * PX + 1.5 * MM
    text_right = col3_right
    if include_qr and verify_url:
        try:
            c.drawImage(
                _qr_image(verify_url),
                col3_right - qr_size, block_bottom,
                width=qr_size, height=qr_size,
            )
            text_right = col3_right - qr_size - 4 * MM
        except Exception as exc:  # pragma: no cover — qr lib failure only
            logger.warning('QR code skipped: %s', exc)

    org_y = block_bottom
    c.setFillColor(GREEN_LINK)
    c.setFont(FONT, 12 * PX)
    c.drawRightString(text_right, org_y, website)
    org_y += 12 * PX * 1.35
    c.setFillColor(GREY_DARK)
    c.drawRightString(text_right, org_y, organisation)
    org_y += 12 * PX * 1.35 + 1 * MM
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 12 * PX)
    c.drawRightString(text_right, org_y, 'Training Organisation:')

    # ── Verification line ─────────────────────────────────────────
    if verify_url:
        prefix = 'Verify this certificate at '
        size = 8 * PX
        total = stringWidth(prefix, FONT, size) + stringWidth(verify_url, FONT, size)
        x = (PAGE_W - total) / 2
        vy = 8 * MM
        c.setFont(FONT, size)
        c.setFillColor(GREY_FAINT)
        c.drawString(x, vy, prefix)
        c.setFillColor(GREEN_LINK)
        c.drawString(x + stringWidth(prefix, FONT, size), vy, verify_url)

    c.save()
    return buf.getvalue()
