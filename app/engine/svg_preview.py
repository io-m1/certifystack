import io
import os
import logging
from PIL import Image
import cairosvg
from app.engine.exceptions import ConversionError

logger = logging.getLogger(__name__)


def svg_to_png_bytes(svg_path: str, width: int = 800) -> bytes:
    """Rasterize SVG to PNG at specified width, auto-scaling height."""
    if not os.path.exists(svg_path):
        raise ConversionError(f"SVG file not found: {svg_path}")
        
    try:
        png_data = cairosvg.svg2png(url=svg_path, output_width=width)
        if not png_data:
            raise ConversionError("CairoSVG rasterization returned empty bytes")
        return png_data
    except Exception as e:
        logger.error(f"Failed to rasterize SVG {svg_path}: {e}", exc_info=True)
        raise ConversionError(f"SVG to PNG rasterization failed: {e}")


def generate_preview_card(svg_path: str, output_path: str, size: tuple[int, int] = (400, 283)) -> str:
    """Create a white-padded, aspect-ratio preserved PNG preview card."""
    try:
        png_bytes = svg_to_png_bytes(svg_path, width=size[0])
        img = Image.open(io.BytesIO(png_bytes))
        img.thumbnail(size, Image.Resampling.LANCZOS)
        
        card = Image.new("RGBA", size, (255, 255, 255, 255))
        offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
        card.paste(img, offset, img if img.mode == "RGBA" else None)
        
        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
        card.convert("RGB").save(output_path, "PNG")
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate preview card at {output_path}: {e}", exc_info=True)
        raise ConversionError(f"Preview card generation failed: {e}")
