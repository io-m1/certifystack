import re
from typing import Dict, List, Optional, NamedTuple
from lxml import etree
from app.engine.exceptions import TemplateValidationError

class CertificateField(NamedTuple):
    field_id: str
    field_type: str
    display_text: str
    font_family: str
    font_size: float
    font_weight: str
    font_style: str
    text_color: str
    text_anchor: str
    x: float
    y: float
    bounding_box: Dict[str, float]


_COLOR_MAP: Dict[str, str] = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "blue": "#0000ff", "gold": "#ffd700", "rebeccapurple": "#663399",
    "gray": "#808080", "grey": "#808080", "yellow": "#ffff00", "silver": "#c0c0c0",
}


def _parse_coordinate(val: Optional[str]) -> float:
    """Extract first float value from coordinate attribute string."""
    if not val:
        return 0.0
    match = re.search(r"[\d.-]+", val)
    return float(match.group(0)) if match else 0.0


def _normalize_color(val: str) -> str:
    """Normalize color strings (rgb, named colors, hex) to uppercase hex."""
    val = val.strip().lower()
    if val.startswith("#"):
        return val.upper()
    if val.startswith("rgb"):
        match = re.search(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", val)
        if match:
            return f"#{int(match.group(1)):02X}{int(match.group(2)):02X}{int(match.group(3)):02X}"
    return _COLOR_MAP.get(val, "#000000").upper()


def parse_font_size(size_str: str) -> float:
    """Convert absolute and relative SVG font size values to pixels."""
    match = re.match(r"^([\d.]+)\s*([a-zA-Z%]*)$", size_str.strip())
    if not match:
        raise ValueError(f"Invalid font size: {size_str}")
    val = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("", "px"):
        return val
    if unit == "pt":
        return val * 1.333
    if unit in ("em", "rem"):
        return val * 16.0
    if unit == "%":
        return (val / 100.0) * 16.0
    raise ValueError(f"Unsupported unit: {unit}")


def resolve_style_inheritance(element: etree.Element, attribute: str) -> Optional[str]:
    """Traverse up XML tree to resolve element styles or presentation attributes."""
    curr = element
    while curr is not None:
        style_attr = curr.get("style")
        if style_attr:
            styles = dict(re.findall(r"([\w-]+)\s*:\s*([^;]+)", style_attr))
            if attribute in styles:
                return styles[attribute].strip()
        val = curr.get(attribute)
        if val is not None:
            return val.strip()
        curr = curr.getparent()
    return None


def _build_field(el: etree.Element, field_id: str) -> CertificateField:
    """Construct CertificateField object from element styles and position."""
    display_text = "".join(el.itertext()).strip()
    font_fam = resolve_style_inheritance(el, "font-family") or "Helvetica"
    font_family = re.sub(r"['\"]", "", font_fam.split(",")[0]).strip()
    
    font_size_str = resolve_style_inheritance(el, "font-size") or "16px"
    font_size = parse_font_size(font_size_str)
    
    x = _parse_coordinate(el.get("x"))
    y = _parse_coordinate(el.get("y"))
    text_anchor = resolve_style_inheritance(el, "text-anchor") or "start"
    
    approx_w = len(display_text) * (font_size * 0.6)
    bbox_x = x - (approx_w / 2 if text_anchor == "middle" else approx_w if text_anchor == "end" else 0.0)
    
    fid_lower = field_id.lower()
    ftype = "name" if "name" in fid_lower else "date" if "date" in fid_lower else "certificate_id" if "id" in fid_lower else "qr_code" if "qr" in fid_lower else "custom"
    
    return CertificateField(
        field_id=field_id,
        field_type=ftype,
        display_text=display_text,
        font_family=font_family,
        font_size=font_size,
        font_weight=resolve_style_inheritance(el, "font-weight") or "normal",
        font_style=resolve_style_inheritance(el, "font-style") or "normal",
        text_color=_normalize_color(resolve_style_inheritance(el, "fill") or "#000000"),
        text_anchor=text_anchor,
        x=x,
        y=y,
        bounding_box={"x": bbox_x, "y": y - font_size, "width": approx_w, "height": font_size}
    )


def load_template(svg_path: str) -> List[CertificateField]:
    """Parse SVG template, resolving text element style profiles."""
    try:
        tree = etree.parse(svg_path)
    except Exception as e:
        raise TemplateValidationError(f"Failed to parse SVG: {e}")
        
    elements: List[CertificateField] = []
    seen: Dict[str, etree.Element] = {}
    
    for el in tree.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "text":
            fid = el.get("id")
            if fid:
                if fid in seen:
                    raise TemplateValidationError(
                        f"Duplicate field ID '{fid}' at line {seen[fid].sourceline} and {el.sourceline}"
                    )
                seen[fid] = el
                if "".join(el.itertext()).strip():
                    elements.append(_build_field(el, fid))
                    
    if not elements:
        raise TemplateValidationError("No text fields with valid IDs found in SVG template")
        
    return sorted(elements, key=lambda f: f.y)
