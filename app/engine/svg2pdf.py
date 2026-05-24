import os
import logging
from lxml import etree
import cairosvg
from app.engine.exceptions import ConversionError

logger = logging.getLogger(__name__)


def svg_to_pdf_bytes(svg_path: str, dpi: int = 300) -> bytes:
    """Convert SVG file to high-fidelity print-ready PDF bytes, ensuring white background."""
    if not os.path.exists(svg_path):
        raise ConversionError(f"SVG file not found at: {svg_path}")
        
    try:
        tree = etree.parse(svg_path)
        root = tree.getroot()
        
        has_bg = False
        for child in root:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "rect" and child.get("width") in ("100%", "100") and child.get("height") in ("100%", "100"):
                has_bg = True
                break
                
        if not has_bg:
            bg_rect = etree.Element("rect", width="100%", height="100%", fill="#FFFFFF")
            root.insert(0, bg_rect)
            
        svg_bytes = etree.tostring(tree, encoding="utf-8")
        pdf_data = cairosvg.svg2pdf(bytestring=svg_bytes, dpi=dpi)
        
        if not pdf_data:
            raise ConversionError("CairoSVG conversion returned empty bytes")
            
        return pdf_data
    except Exception as e:
        logger.error(f"CairoSVG conversion error for {svg_path}: {e}", exc_info=True)
        raise ConversionError(f"SVG to PDF conversion failed: {e}")


def svg_to_pdf_file(svg_path: str, pdf_path: str, dpi: int = 300) -> str:
    """Convert SVG file to PDF file on disk, auto-creating parent directories."""
    pdf_bytes = svg_to_pdf_bytes(svg_path, dpi=dpi)
    
    try:
        if os.path.dirname(pdf_path):
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
    except Exception as e:
        logger.error(f"Failed to write PDF to disk at {pdf_path}: {e}")
        raise ConversionError(f"Could not save PDF to {pdf_path}: {e}")
        
    return pdf_path
