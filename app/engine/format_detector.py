import os
import zipfile
from enum import Enum
from typing import NamedTuple, Optional, List
from lxml import etree
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from app.engine.exceptions import FormatDetectionError

MAX_FILE_SIZE_MB = 50


class DetectedFormat(Enum):
    SVG_TEXT = "svg_with_text"
    SVG_PATH = "svg_without_text"
    PDF_TEXT = "pdf_with_text"
    PDF_FLATTENED = "pdf_flattened"
    RASTER = "raster"
    UNSUPPORTED = "unsupported"


class FormatDetectionResult(NamedTuple):
    detected_format: DetectedFormat
    mime_type: str
    claimed_extension: str
    confidence: float
    details: str


def has_selectable_text(pdf_path: str) -> bool:
    """Check if the first page of PDF has selectable text using pdfminer.six."""
    try:
        pages = list(extract_pages(pdf_path, page_numbers=[0]))
        if not pages:
            raise FormatDetectionError("PDF is empty (0 pages).")
        
        # Check elements recursively or iteratively for text
        for element in pages[0]:
            cls_name = element.__class__.__name__
            if ("LTTextContainer" in cls_name or "LTTextBox" in cls_name or hasattr(element, "get_text")):
                try:
                    txt = getattr(element, "get_text")()
                    if txt and txt.strip():
                        return True
                except Exception:
                    pass
        return False
    except Exception as e:
        if "encrypted" in str(e).lower() or "password" in str(e).lower():
            raise FormatDetectionError("Encrypted PDF detected. Please decrypt the PDF first.")
        if isinstance(e, FormatDetectionError):
            raise
        raise FormatDetectionError(f"Failed to check PDF text selectability: {e}")


def _detect_svg_format(file_path: str) -> DetectedFormat:
    """Parse SVG to check if it contains any <text> element with an ID."""
    try:
        tree = etree.parse(file_path)
        # Search for any <text> tags with an 'id' attribute
        for element in tree.iter():
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag == "text" and element.get("id"):
                return DetectedFormat.SVG_TEXT
        return DetectedFormat.SVG_PATH
    except Exception:
        return DetectedFormat.SVG_PATH


def _detect_zip_type(file_path: str, ext: str) -> DetectedFormat:
    """Check inside ZIP archives to reject DOCX/PPTX formats."""
    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            names = z.namelist()
            if any(name.startswith("word/") for name in names) or ext == ".docx":
                return DetectedFormat.UNSUPPORTED
            if any(name.startswith("ppt/") for name in names) or ext == ".pptx":
                return DetectedFormat.UNSUPPORTED
    except Exception:
        pass
    return DetectedFormat.UNSUPPORTED


def detect_format(file_path: str) -> FormatDetectionResult:
    """Inspect magic bytes and content of file to determine its format."""
    if not os.path.exists(file_path):
        raise FormatDetectionError("File does not exist.")
        
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FormatDetectionError(f"File size {size_mb:.1f}MB exceeds limit of {MAX_FILE_SIZE_MB}MB.")
        
    ext = os.path.splitext(file_path)[1].lower()
    
    with open(file_path, "rb") as f:
        header = f.read(2048)
        
    # Analyze magic bytes
    if header.startswith(b"%PDF"):
        is_selectable = has_selectable_text(file_path)
        df = DetectedFormat.PDF_TEXT if is_selectable else DetectedFormat.PDF_FLATTENED
        return FormatDetectionResult(df, "application/pdf", ext, 1.0, "Valid PDF detected.")
        
    if header.startswith(b"<?xml") or header.startswith(b"<svg") or b"<svg" in header:
        df = _detect_svg_format(file_path)
        return FormatDetectionResult(df, "image/svg+xml", ext, 1.0, "SVG image template detected.")
        
    if header.startswith(b"\x89PNG"):
        return FormatDetectionResult(DetectedFormat.RASTER, "image/png", ext, 1.0, "PNG image detected.")
        
    if header.startswith(b"\xff\xd8\xff"):
        return FormatDetectionResult(DetectedFormat.RASTER, "image/jpeg", ext, 1.0, "JPEG image detected.")
        
    if header.startswith(b"RIFF") and b"WEBP" in header[8:16]:
        return FormatDetectionResult(DetectedFormat.RASTER, "image/webp", ext, 1.0, "WebP image detected.")
        
    if header.startswith(b"PK\x03\x04"):
        df = _detect_zip_type(file_path, ext)
        msg = "Office document (DOCX/PPTX) is not supported. Export as PDF first."
        return FormatDetectionResult(df, "application/zip", ext, 0.9, msg)
        
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return FormatDetectionResult(DetectedFormat.UNSUPPORTED, "image/tiff", ext, 1.0, "TIFF image is not supported.")
        
    if b"ftypheic" in header or b"ftypheix" in header or ext in (".heic", ".heif"):
        return FormatDetectionResult(DetectedFormat.UNSUPPORTED, "image/heic", ext, 0.8, "HEIC format is not supported.")
        
    return FormatDetectionResult(DetectedFormat.UNSUPPORTED, "application/octet-stream", ext, 0.5, "Unsupported format.")
