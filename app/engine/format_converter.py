import os
import re
import tempfile
import subprocess
from typing import List, NamedTuple, Optional, Dict
from lxml import etree
from PIL import Image, ImageEnhance
import pdf2image
from app.engine.exceptions import ConversionError
from app.engine.format_detector import detect_format, DetectedFormat
from app.engine.ocr_engine import extract_text_regions, suggest_field_type

class ConversionPath(str):
    PASS_THROUGH = "pass_through"
    PDF_TEXT_TO_SVG = "pdf_text_to_svg"
    PDF_FLAT_TO_SVG = "pdf_flat_to_svg"
    RASTER_TO_SVG = "raster_to_svg"
    UNSUPPORTED = "unsupported"


class ConversionResult(NamedTuple):
    output_svg_path: str
    conversion_path: str
    text_preserved: bool
    quality_level: str
    warnings: List[str]
    detected_text_regions: List[Dict]
    admin_next_steps: str


def _clean_inkscape_svg(svg_path: str) -> None:
    """Post-process Inkscape SVG to strip proprietary namespaces and attributes."""
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(svg_path, parser)
        root = tree.getroot()
        
        # Remove inkscape and sodipodi metadata attributes
        etree.strip_attributes(root, "{http://www.inkscape.org/namespaces/inkscape}*", "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}*")
        tree.write(svg_path, encoding="utf-8", xml_declaration=True, pretty_print=True)
    except Exception:
        pass


def pdf_text_to_svg(pdf_path: str, output_path: str) -> ConversionResult:
    """Convert a vector PDF containing text into SVG using Inkscape CLI."""
    warnings: List[str] = []
    try:
        subprocess.run([
            "inkscape", "--pdf-poppler", "--export-type=svg",
            f"--export-filename={output_path}", pdf_path
        ], check=True, capture_output=True, timeout=60)
    except FileNotFoundError:
        msg = "Inkscape not installed. Please install Inkscape and ensure it is in the PATH."
        raise ConversionError(msg)
    except Exception as e:
        raise ConversionError(f"Inkscape conversion failed: {e}")
        
    _clean_inkscape_svg(output_path)
    
    # Check if text elements are actually present in output
    tree = etree.parse(output_path)
    has_text = any(el.tag.split("}")[-1] == "text" for el in tree.iter())
    if not has_text:
         warnings.append("No text elements found in converted SVG. High risk of missing fields.")
         
    return ConversionResult(
        output_svg_path=output_path,
        conversion_path=ConversionPath.PDF_TEXT_TO_SVG,
        text_preserved=has_text,
        quality_level="good",
        warnings=warnings,
        detected_text_regions=[],
        admin_next_steps="Review the output template. Map text element IDs to certificate placeholders."
    )


def _preprocess_raster(image_path: str) -> str:
    """Enhance contrast and deskew the input raster image for optimal vectorization."""
    try:
        img = Image.open(image_path)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        temp_img = tempfile.NamedTuple = tempfile.mktemp(suffix=".png")
        img.save(temp_img)
        return temp_img
    except Exception:
        return image_path


def _vectorize_raster(input_path: str, output_path: str, warnings: List[str]) -> None:
    """Vectorize a raster image to SVG using vtracer or potrace fallback."""
    try:
        import vtracer
        vtracer.convert_image_to_svg_py(input_path, output_path, colormode="color")
    except Exception as e:
        warnings.append(f"vtracer failed or not compiled ({e}). Falling back to potrace (B&W).")
        try:
            img = Image.open(input_path).convert("1")
            temp_bmp = tempfile.mktemp(suffix=".bmp")
            img.save(temp_bmp)
            subprocess.run(["potrace", "-s", "-o", output_path, temp_bmp], check=True)
            if os.path.exists(temp_bmp):
                os.remove(temp_bmp)
        except Exception as pe:
            raise ConversionError(f"Vectorization fallback to potrace failed: {pe}. Ensure potrace is installed.")


def _embed_ocr_elements(svg_path: str, image_path: str) -> List[Dict]:
    """Extract text from the original raster and embed it as selectable <text> tags."""
    regions = extract_text_regions(image_path)
    if not regions:
        return []
        
    tree = etree.parse(svg_path)
    root = tree.getroot()
    
    viewbox = root.get("viewBox")
    width = float(root.get("width", "842").replace("px", ""))
    height = float(root.get("height", "595").replace("px", ""))
    if viewbox:
        parts = viewbox.split()
        if len(parts) == 4:
            width, height = float(parts[2]), float(parts[3])
            
    for idx, reg in enumerate(regions):
        txt_el = etree.Element("text", {
            "id": f"ocr-{idx}",
            "x": str(reg.bbox["x"] * width),
            "y": str((reg.bbox["y"] + reg.bbox["h"]) * height),
            "font-size": f"{max(reg.bbox['h'] * height, 10.0):.1f}px",
            "font-family": "Helvetica, Arial, sans-serif",
            "fill": "#000000",
            "text-anchor": "start"
        })
        txt_el.text = reg.text
        root.append(txt_el)
        
    tree.write(svg_path, encoding="utf-8", xml_declaration=True, pretty_print=True)
    return [{"text": r.text, "bbox": r.bbox, "confidence": r.confidence, "suggested_type": r.suggested_field_type} for r in regions]


def raster_to_svg(image_path: str, output_path: str) -> ConversionResult:
    """Preprocess, vectorize, and overlay OCR text onto a raster image template."""
    warnings: List[str] = []
    preprocessed_path = _preprocess_raster(image_path)
    
    try:
        _vectorize_raster(preprocessed_path, output_path, warnings)
    finally:
        if preprocessed_path != image_path and os.path.exists(preprocessed_path):
            os.remove(preprocessed_path)
            
    ocr_regions = _embed_ocr_elements(output_path, image_path)
    if not ocr_regions:
        warnings.append("No text could be extracted from image via OCR.")
        
    low_conf = any(r["confidence"] < 60.0 for r in ocr_regions)
    quality = "requires_review" if (low_conf or not ocr_regions) else "degraded"
    
    return ConversionResult(
        output_svg_path=output_path,
        conversion_path=ConversionPath.RASTER_TO_SVG,
        text_preserved=len(ocr_regions) > 0,
        quality_level=quality,
        warnings=warnings,
        detected_text_regions=ocr_regions,
        admin_next_steps="Review OCR-extracted fields. Map them to certificate placeholders."
    )


def pdf_flattened_to_svg(pdf_path: str, output_path: str) -> ConversionResult:
    """Convert a flattened/outlined PDF to SVG by rasterizing first, then run raster_to_svg."""
    warnings: List[str] = []
    try:
        pages = pdf2image.convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
        if not pages:
            raise ConversionError("PDF has no pages.")
        if len(pdf2image.pdfinfo_from_path(pdf_path).get("Pages", 1)) > 1:
            warnings.append("PDF contains multiple pages. Only the first page was converted.")
    except Exception as e:
        raise ConversionError(f"Failed to rasterize PDF: {e}")
        
    temp_png = tempfile.mktemp(suffix=".png")
    pages[0].save(temp_png, "PNG")
    
    try:
        res = raster_to_svg(temp_png, output_path)
        return ConversionResult(
            output_svg_path=output_path,
            conversion_path=ConversionPath.PDF_FLAT_TO_SVG,
            text_preserved=res.text_preserved,
            quality_level="degraded" if res.quality_level == "requires_review" else res.quality_level,
            warnings=warnings + res.warnings,
            detected_text_regions=res.detected_text_regions,
            admin_next_steps="Flattened PDF design converted. Verify field alignments and maps."
        )
    finally:
        if os.path.exists(temp_png):
            os.remove(temp_png)


def convert_to_svg(input_path: str, output_dir: str) -> ConversionResult:
    """Universal entry point for all format to SVG conversion paths."""
    detection = detect_format(input_path)
    if detection.detected_format == DetectedFormat.UNSUPPORTED:
        raise ConversionError(f"Unsupported format: {detection.details}")
        
    os.makedirs(output_dir, exist_ok=True)
    out_filename = os.path.splitext(os.path.basename(input_path))[0] + ".svg"
    output_path = os.path.join(output_dir, out_filename)
    
    if detection.detected_format == DetectedFormat.SVG_TEXT:
        import shutil
        shutil.copy(input_path, output_path)
        return ConversionResult(output_path, ConversionPath.PASS_THROUGH, True, "perfect", [], [], "Template ready for direct use.")
        
    if detection.detected_format == DetectedFormat.SVG_PATH:
        import shutil
        shutil.copy(input_path, output_path)
        warnings = ["SVG template contains vector paths but no selectable text fields."]
        return ConversionResult(output_path, ConversionPath.PASS_THROUGH, False, "requires_review", warnings, [], "Add text elements manually.")
        
    if detection.detected_format == DetectedFormat.PDF_TEXT:
        return pdf_text_to_svg(input_path, output_path)
        
    if detection.detected_format == DetectedFormat.PDF_FLATTENED:
        return pdf_flattened_to_svg(input_path, output_path)
        
    return raster_to_svg(input_path, output_path)
