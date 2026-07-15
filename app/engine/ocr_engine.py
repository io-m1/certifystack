import re
from typing import List, Dict, NamedTuple
import pytesseract
from PIL import Image
from app.engine.exceptions import ConversionError

class OCRRegion(NamedTuple):
    text: str
    bbox: Dict[str, float]  # Normalized 0.0-1.0
    confidence: float       # 0-100
    suggested_field_type: str  # "name" | "date" | "certificate_id" | "unknown"


def suggest_field_type(text: str, bbox: Dict[str, float]) -> str:
    """Guess field type based on regex patterns and bounding box heuristics."""
    text_lower = text.lower()
    
    # Identify date patterns
    date_patterns = [
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b"
    ]
    if any(re.search(pat, text_lower) for pat in date_patterns):
        return "date"
        
    # Identify certificate reference ID patterns
    id_patterns = [
        r"\bcert\b", r"\bid\b", r"\bno\b", r"^[a-z0-9-]{8,25}$"
    ]
    if any(re.search(pat, text_lower) for pat in id_patterns):
        return "certificate_id"
        
    # Identify recipient name by central position and size threshold
    x_center = bbox["x"] + bbox["w"] / 2.0
    if abs(x_center - 0.5) < 0.15 and bbox["h"] > 0.025 and len(text.split()) >= 2:
        return "name"
        
    return "unknown"


def extract_text_regions(image_path: str, language: str = 'eng') -> List[OCRRegion]:
    """Run pytesseract OCR to extract words, filter noise, and normalize bounding boxes."""
    try:
        img = Image.open(image_path)
    except Exception as e:
        raise ConversionError(f"Failed to open image for OCR: {e}")
        
    w, h = img.size
    
    try:
        data = pytesseract.image_to_data(img, lang=language, output_type=pytesseract.Output.DICT)
    except FileNotFoundError:
        raise ConversionError("Tesseract-OCR binary not found. Please install tesseract-ocr.")
    except Exception as e:
        raise ConversionError(f"Tesseract OCR execution failed: {e}")
        
    regions: List[OCRRegion] = []
    for i in range(len(data.get("text", []))):
        text = (data["text"][i] or "").strip()
        conf_val = data["conf"][i]
        
        # Check standard integer/float compatibility for confidence score
        try:
            conf = float(conf_val)
        except (ValueError, TypeError):
            conf = 0.0
            
        if not text or conf < 30.0:
            continue
            
        bbox = {
            "x": float(data["left"][i]) / w,
            "y": float(data["top"][i]) / h,
            "w": float(data["width"][i]) / w,
            "h": float(data["height"][i]) / h
        }
        
        regions.append(OCRRegion(
            text=text,
            bbox=bbox,
            confidence=conf,
            suggested_field_type=suggest_field_type(text, bbox)
        ))
        
    return regions
