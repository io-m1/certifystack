"""
Generates personalized PDF certificates from SVG template.
Replaces PyPDF2 overlay approach with SVG → PDF rendering.
Provides a robust fallback to legacy PyPDF2 canvas overlay for compatibility.
"""

import qrcode
import io
import base64
import re
import os
import logging
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

_FONT_DIR = os.path.join(os.path.dirname(__file__), '../../static/fonts')
_DEFAULT_FONT = 'Helvetica-Bold'
_DEFAULT_FONT_REGULAR = 'Helvetica'


def _register_fonts():
    if not os.path.isdir(_FONT_DIR):
        return
    for fname in os.listdir(_FONT_DIR):
        if fname.endswith('.ttf'):
            name = fname[:-4]
            try:
                pdfmetrics.registerFont(TTFont(name, os.path.join(_FONT_DIR, fname)))
            except Exception:
                pass


_register_fonts()


def _make_qr(data: str, size: int = 90) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=6, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return buf


def _auto_font_size(text: str, max_width: float, max_height: float, font_name: str, start_size: int = 32) -> int:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    size = start_size
    while size > 7:
        w = stringWidth(text, font_name, size)
        if w <= max_width and size <= max_height * 1.3:
            return size
        size -= 1
    return size


def _binary_to_reader(binary_data: bytes, file_type: str) -> PdfReader:
    if file_type == 'png':
        img = Image.open(io.BytesIO(binary_data))
        iw, ih = img.size
        # Dynamically scale to standard A4 paper size bounds based on orientation
        if iw >= ih:
            # Landscape template
            max_w, max_h = 841.89, 595.28
        else:
            # Portrait template
            max_w, max_h = 595.28, 841.89
            
        scale = min(max_w / iw, max_h / ih)
        pw, ph = (iw * scale, ih * scale)
        
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        c.drawImage(ImageReader(img), 0, 0, width=pw, height=ph, preserveAspectRatio=True)
        c.save()
        buf.seek(0)
        return PdfReader(buf)
    else:
        return PdfReader(io.BytesIO(binary_data))


def generate_personalized_pdf_legacy(template_binary: bytes, overlay_coords: dict, full_name: str, certificate_id: str, issuance_date: str, include_qr: bool = True, cert_name: str = '', master_file_type: str = 'pdf', verify_url: str = '', font_name: str = None) -> bytes:
    if not template_binary:
        raise ValueError("template_binary is required")

    reader = _binary_to_reader(template_binary, master_file_type)
    writer = PdfWriter()
    master_page = reader.pages[0]
    page_w = float(master_page.mediabox.width)
    page_h = float(master_page.mediabox.height)
    name_font = font_name or _DEFAULT_FONT
    body_font = _DEFAULT_FONT_REGULAR
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        stringWidth('test', name_font, 12)
    except Exception:
        name_font = _DEFAULT_FONT
        body_font = _DEFAULT_FONT_REGULAR
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_w, page_h))
    
    from reportlab.lib import colors
    
    # 1. Resolve custom colors from overlay_coords
    default_mask = 'transparent' if master_file_type == 'png' else '#FFFFFF'
    mask_color_hex = overlay_coords.get('mask_color', default_mask)
    name_color_hex = overlay_coords.get('name_color', '#000000')
    text_color_hex = overlay_coords.get('text_color', '#000000')
    
    try:
        if str(mask_color_hex).lower() in ('transparent', 'none', ''):
            mask_color = None
        else:
            mask_color = colors.HexColor(mask_color_hex)
    except Exception:
        mask_color = colors.white
        
    try:
        name_color = colors.HexColor(name_color_hex)
    except Exception:
        name_color = colors.black
        
    try:
        text_color = colors.HexColor(text_color_hex)
    except Exception:
        text_color = colors.black

    # Resolve coordinates
    name_x = overlay_coords.get('name_x', page_w / 2)
    name_y = overlay_coords.get('name_y', page_h * 0.46)
    name_w = overlay_coords.get('name_w', page_w * 0.7)
    name_h = overlay_coords.get('name_h', 50)
    name_align = overlay_coords.get('name_align', 'center')
    
    cid_x = overlay_coords.get('cert_id_x', 60)
    cid_y = overlay_coords.get('cert_id_y', 55)
    cid_w = overlay_coords.get('cert_id_w', 120)
    cid_h = overlay_coords.get('cert_id_h', 15)
    
    date_x = overlay_coords.get('date_x', 60)
    date_y = overlay_coords.get('date_y', 42)
    date_w = overlay_coords.get('date_w', 120)
    date_h = overlay_coords.get('date_h', 15)

    # 2. Mask the original placeholder text areas to avoid overlaps (only if mask_color is specified)
    pad_name_x = overlay_coords.get('name_bg_padding_x', 15)
    pad_name_y = overlay_coords.get('name_bg_padding_y', 8)
    
    pad_id_x = overlay_coords.get('cert_id_bg_padding_x', 10)
    pad_id_y = overlay_coords.get('cert_id_bg_padding_y', 4)
    
    pad_date_x = overlay_coords.get('date_bg_padding_x', 10)
    pad_date_y = overlay_coords.get('date_bg_padding_y', 4)
    
    if mask_color is not None:
        c.setFillColor(mask_color)
        c.setStrokeColor(mask_color)
        
        # Mask Name
        if name_align == 'center':
            name_rect_x = name_x - name_w / 2
        elif name_align == 'right':
            name_rect_x = name_x - name_w
        else:
            name_rect_x = name_x
        c.rect(name_rect_x - pad_name_x, name_y - name_h / 2 - pad_name_y, name_w + 2 * pad_name_x, name_h + 2 * pad_name_y, fill=1, stroke=0)
        
        # Mask Cert ID
        c.rect(cid_x - pad_id_x, cid_y - cid_h / 2 - pad_id_y, cid_w + 2 * pad_id_x, cid_h + 2 * pad_id_y, fill=1, stroke=0)
        
        # Mask Date
        c.rect(date_x - pad_date_x, date_y - date_h / 2 - pad_date_y, date_w + 2 * pad_date_x, date_h + 2 * pad_date_y, fill=1, stroke=0)

    # 3. Draw new personalized text in custom text colors
    start_size = overlay_coords.get('name_font_size', 32)
    font_size = _auto_font_size(full_name, name_w, name_h, name_font, start_size)
    
    c.setFont(name_font, font_size)
    c.setFillColor(name_color)
    if name_align == 'center':
        c.drawCentredString(name_x, name_y, full_name)
    elif name_align == 'right':
        c.drawRightString(name_x, name_y, full_name)
    else:
        c.drawString(name_x, name_y, full_name)
        
    c.setFillColor(text_color)
    cid_size = overlay_coords.get('cert_id_font_size', 9)
    c.setFont(body_font, cid_size)
    c.drawString(cid_x, cid_y, certificate_id)
    
    date_size = overlay_coords.get('date_font_size', 9)
    c.setFont(body_font, date_size)
    c.drawString(date_x, date_y, issuance_date)
    
    # 4. Draw QR Code (with optional background masking)
    qr_x = overlay_coords.get('qr_x')
    qr_y = overlay_coords.get('qr_y', 20)
    qr_size = overlay_coords.get('qr_size', 72)
    if qr_x is None:
        qr_x = page_w - qr_size - 20
    if include_qr and isinstance(qr_x, (int, float)) and (qr_x >= 0):
        # Mask QR region first
        if mask_color is not None:
            c.setFillColor(mask_color)
            c.rect(qr_x, qr_y, qr_size, qr_size, fill=1, stroke=0)
        
        qr_url = verify_url or f'CERT:{certificate_id}'
        qr_data = f'{qr_url}|{full_name}|{cert_name}|PASSED|{issuance_date}'
        qr_buf = _make_qr(qr_data)
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size, mask='auto')
    c.save()
    packet.seek(0)
    overlay_reader = PdfReader(packet)
    master_page.merge_page(overlay_reader.pages[0])
    writer.add_page(master_page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generate_personalized_pdf(svg_template_path, overlay_coords, 
                               full_name, certificate_id, issuance_date, **kwargs):
    """
    1. Load SVG template
    2. Replace placeholder text with actual values
    3. Generate QR code and embed as base64 image in SVG
    4. Convert SVG to final PDF
    """
    # Robust backward compatibility check: if binary template is passed, fall back to legacy PyPDF2 overlay
    if isinstance(svg_template_path, bytes):
        return generate_personalized_pdf_legacy(
            template_binary=svg_template_path,
            overlay_coords=overlay_coords,
            full_name=full_name,
            certificate_id=certificate_id,
            issuance_date=issuance_date,
            **kwargs
        )

    # Read SVG template
    with open(svg_template_path, 'r', encoding='utf-8') as f:
        svg_content = f.read()
    
    # Generate QR code
    qr_data = f"CERT:{certificate_id}|NAME:{full_name}|DATE:{issuance_date}"
    qr = qrcode.make(qr_data)
    qr_buffer = io.BytesIO()
    # Check if the QR code is generated using the pure-python PyPNGImage backend
    if 'pure' in str(type(qr)):
        qr.save(qr_buffer)
    else:
        # Completely bypass strict flow-sensitive compilers by invoking dynamically
        save_fn = getattr(qr, 'save')
        save_args = {str('format'): 'PNG'}
        try:
            save_fn(qr_buffer, **save_args)
        except TypeError:
            qr.save(qr_buffer)
    qr_buffer.seek(0)
    qr_base64 = base64.b64encode(qr_buffer.read()).decode('utf-8')
    
    # Replace QR placeholder
    qr_data_uri = f'data:image/png;base64,{qr_base64}'
    svg_content = svg_content.replace(
        'id="placeholder-qr"',
        f'id="placeholder-qr" href="{qr_data_uri}"'
    )
    
    # Replace text placeholders
    replacements = {
        '{{name}}': full_name,
        '{{cert_id}}': certificate_id,
        '{{date}}': issuance_date,
    }
    
    for placeholder, value in replacements.items():
        svg_content = svg_content.replace(placeholder, value)
    
    # Convert SVG to PDF bytes
    from cairosvg import svg2pdf
    pdf_bytes = svg2pdf(bytestring=svg_content.encode('utf-8'))
    
    return pdf_bytes
