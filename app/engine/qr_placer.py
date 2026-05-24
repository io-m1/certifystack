"""
QR code auto-placement engine: finds empty regions in SVG templates and
embeds QR codes at the optimal location.
"""

import io
import base64
from typing import Optional, List, Dict, NamedTuple, Tuple
from lxml import etree


class QRPlacement(NamedTuple):
    x: float
    y: float
    size: float              # Recommended QR code size in pixels
    confidence: float        # 0.0–1.0 — how suitable this location is
    location_desc: str       # "bottom-right" | "bottom-left" | "top-right" | "custom"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svg_dimensions(root: etree.Element) -> Tuple[float, float]:
    """Extract (width, height) from SVG root element or viewBox."""

    def _parse(attr: str, fallback: float) -> float:
        val = root.get(attr, "")
        try:
            return float(str(val).replace("px", "").strip())
        except (ValueError, AttributeError):
            pass
        vb = root.get("viewBox", "")
        parts = vb.split()
        if len(parts) == 4:
            return float(parts[2]) if attr == "width" else float(parts[3])
        return fallback

    return _parse("width", 842.0), _parse("height", 595.0)


def _collect_occupied_boxes(root: etree.Element) -> List[Dict]:
    """Return approximate bounding boxes for all text elements."""
    boxes: List[Dict] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag not in ("text", "rect", "image"):
            continue
        try:
            x = float(el.get("x", 0))
            y = float(el.get("y", 0))
            if tag == "text":
                txt = "".join(el.itertext())
                fs_str = (el.get("font-size") or "12").replace("px", "")
                try:
                    fs = float(fs_str)
                except ValueError:
                    fs = 12.0
                w = max(len(txt) * fs * 0.6, 40.0)
                h = fs * 1.6
            else:
                w_raw = el.get("width", "0")
                h_raw = el.get("height", "0")
                w = float(str(w_raw).replace("%", "").strip() or "0")
                h = float(str(h_raw).replace("%", "").strip() or "0")
                if w > 1000:   # percentage width like 100% on a 842px canvas
                    w = 0.0
                if h > 1000:
                    h = 0.0
            boxes.append({"x": x, "y": y - (h if tag == "text" else 0), "w": w, "h": h})
        except (ValueError, TypeError):
            pass
    return boxes


def _overlaps_any(
    x: float,
    y: float,
    size: float,
    boxes: List[Dict],
    margin: float = 10.0,
) -> bool:
    """Check whether a square zone (x, y, size×size) overlaps any occupied box."""
    for box in boxes:
        if not (
            x + size + margin <= box["x"]
            or x >= box["x"] + box["w"] + margin
            or y + size + margin <= box["y"]
            or y >= box["y"] + box["h"] + margin
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_qr_size(
    template_dims: Tuple[float, float],
    min_size: int = 80,
    max_size: int = 200,
) -> int:
    """Calculate appropriate QR size proportional to template dimensions."""
    w, h = template_dims
    proposed = int(min(w, h) * 0.14)  # ~14% of the shorter axis
    return max(min_size, min(max_size, proposed))


def find_qr_placement(
    svg_path: str,
    qr_size: int = 120,
) -> Optional[QRPlacement]:
    """
    Analyse *svg_path* and return the best QRPlacement.

    Preference order: bottom-right → bottom-left → top-right → top-left.
    If all corners are occupied, tries a grid scan for the first free zone.
    Returns None if no placement is found.
    """
    try:
        tree = etree.parse(svg_path)
    except Exception:
        return None

    root = tree.getroot()
    svg_w, svg_h = _svg_dimensions(root)
    qr_size = calculate_qr_size((svg_w, svg_h), min_size=80, max_size=200)
    boxes = _collect_occupied_boxes(root)
    margin = 20.0

    corners = [
        (svg_w - qr_size - margin, svg_h - qr_size - margin, "bottom-right", 1.0),
        (margin, svg_h - qr_size - margin, "bottom-left", 0.85),
        (svg_w - qr_size - margin, margin, "top-right", 0.70),
        (margin, margin, "top-left", 0.55),
    ]

    for cx, cy, desc, base_conf in corners:
        if not _overlaps_any(cx, cy, qr_size, boxes):
            return QRPlacement(
                x=round(cx, 1),
                y=round(cy, 1),
                size=float(qr_size),
                confidence=base_conf,
                location_desc=desc,
            )

    # Grid scan fallback
    step = qr_size + margin
    y = svg_h - qr_size - margin
    while y >= margin:
        x = svg_w - qr_size - margin
        while x >= margin:
            if not _overlaps_any(x, y, qr_size, boxes):
                return QRPlacement(
                    x=round(x, 1),
                    y=round(y, 1),
                    size=float(qr_size),
                    confidence=0.4,
                    location_desc="custom",
                )
            x -= step
        y -= step

    return None


def embed_qr_code(
    svg_path: str,
    qr_data: str,
    placement: QRPlacement,
) -> str:
    """
    Generate a QR code and embed it as a base64-encoded ``<image>`` element at
    *placement* coordinates.  Returns the modified SVG as a UTF-8 string.

    Requires the ``qrcode`` package with PIL backend.  Falls back to a
    placeholder ``<rect>`` if qrcode is unavailable.
    """
    try:
        tree = etree.parse(svg_path)
    except Exception as exc:
        raise ValueError(f"Cannot parse SVG at {svg_path}: {exc}") from exc

    root = tree.getroot()
    size = int(placement.size)

    # Attempt QR generation via qrcode library
    qr_image_b64: Optional[str] = None
    try:
        import qrcode  # type: ignore
        from PIL import Image  # type: ignore

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img: Image.Image = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        pass  # Will fall through to placeholder

    if qr_image_b64:
        # Embed as <image xlink:href="data:image/png;base64,...">
        img_el = etree.Element(
            "image",
            attrib={
                "id": "qr_code",
                "x": str(placement.x),
                "y": str(placement.y),
                "width": str(size),
                "height": str(size),
                "{http://www.w3.org/1999/xlink}href": f"data:image/png;base64,{qr_image_b64}",
                "preserveAspectRatio": "xMidYMid meet",
            },
        )
        root.append(img_el)
    else:
        # Placeholder rect so the UI can show something
        rect_el = etree.Element(
            "rect",
            attrib={
                "id": "qr_code_placeholder",
                "x": str(placement.x),
                "y": str(placement.y),
                "width": str(size),
                "height": str(size),
                "fill": "#ffffff",
                "stroke": "#000000",
                "stroke-width": "2",
                "stroke-dasharray": "6,3",
            },
        )
        label_el = etree.Element(
            "text",
            attrib={
                "x": str(placement.x + size / 2),
                "y": str(placement.y + size / 2),
                "text-anchor": "middle",
                "font-size": "10",
                "fill": "#666666",
            },
        )
        label_el.text = "QR"
        root.append(rect_el)
        root.append(label_el)

    return etree.tostring(tree, encoding="unicode", xml_declaration=False)
