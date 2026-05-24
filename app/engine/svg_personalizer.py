import re
import logging
from typing import Dict, Optional
from lxml import etree
from app.engine.exceptions import MissingFieldError, TemplateValidationError
from app.engine.svg_template_loader import resolve_style_inheritance, parse_font_size

logger = logging.getLogger(__name__)


def calculate_text_width(text: str, font_family: str, font_size: float) -> float:
    """Approximate rendered text width in pixels using serif vs sans-serif tables."""
    is_serif = any(s in font_family.lower() for s in ["serif", "playfair", "times", "georgia"])
    width_sum = 0.0
    for char in text:
        if ord(char) > 0x2000:
            width_sum += 1.0
        elif char.isupper():
            width_sum += 0.75 if is_serif else 0.7
        elif char.isnumeric():
            width_sum += 0.55 if is_serif else 0.5
        elif char in "mwMW":
            width_sum += 0.8
        elif char in "iIlt., !:;()[]{}":
            width_sum += 0.25 if is_serif else 0.2
        else:
            width_sum += 0.52 if is_serif else 0.48
    return width_sum * font_size


def _update_font_size(element: etree.Element, new_size: float) -> None:
    """Update font-size either inside inline CSS style attribute or XML attribute."""
    style_attr = element.get("style")
    if style_attr:
        if re.search(r"font-size\s*:[^;]+", style_attr):
            new_style = re.sub(r"font-size\s*:[^;]+", f"font-size: {new_size}px", style_attr)
        else:
            new_style = style_attr.rstrip(";") + f"; font-size: {new_size}px;"
        element.set("style", new_style)
    else:
        element.set("font-size", f"{new_size}px")


def _apply_shrink(el: etree.Element, original_text: str, new_text: str, min_size: float) -> None:
    """Iteratively reduce font size if replacement text is wider than placeholder."""
    font_fam = resolve_style_inheritance(el, "font-family") or "Helvetica"
    font_family = re.sub(r"['\"]", "", font_fam.split(",")[0]).strip()
    
    font_size_str = resolve_style_inheritance(el, "font-size") or "16px"
    font_size = parse_font_size(font_size_str)
    
    orig_w = calculate_text_width(original_text, font_family, font_size)
    new_w = calculate_text_width(new_text, font_family, font_size)
    
    if new_w > orig_w:
        curr_size = font_size
        while curr_size > min_size:
            curr_size -= 0.5
            if calculate_text_width(new_text, font_family, curr_size) <= orig_w:
                break
        _update_font_size(el, curr_size)


def personalize(
    template_path: str,
    field_data: Dict[str, str],
    output_path: str,
    options: Optional[Dict] = None
) -> str:
    """Read template SVG, personalize field values while preserving styles, save output."""
    try:
        tree = etree.parse(template_path)
    except Exception as e:
        raise TemplateValidationError(f"Failed to parse template SVG: {e}")
        
    id_to_el = {el.get("id"): el for el in tree.iter() if el.get("id")}
    
    for key, val in field_data.items():
        if key not in id_to_el:
            raise MissingFieldError(f"Required field ID '{key}' not found in the SVG template")
            
        el = id_to_el[key]
        orig_txt = "".join(el.itertext()).strip()
        
        if any(ord(c) > 0x2000 for c in val):
            logger.warning(f"Field '{key}' has non-standard chars. Check font compatibility.")
            
        if options and options.get("auto_shrink"):
            _apply_shrink(el, orig_txt, val, float(options.get("min_font_size", 8.0)))
            
        tspans = el.findall(".//{*}tspan")
        if tspans:
            tspans[0].text = val
            logger.warning(f"Field '{key}' contains nested tspans. Replaced first child text.")
        else:
            el.text = val
            for child in list(el):
                el.remove(child)
                
    try:
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
    except Exception as e:
        raise TemplateValidationError(f"Failed to save personalized SVG: {e}")
        
    return output_path
