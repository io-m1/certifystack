"""
Converts uploaded PDF certificate master to editable SVG template.
Uses pdf2image for rasterization + potrace for vectorization,
or cairosvg for direct PDF-to-SVG conversion.
"""

import subprocess
import os
from pdf2image import convert_from_path
from PIL import Image
import xml.etree.ElementTree as ET

def pdf_to_svg(pdf_path, output_svg_path):
    """
    Convert uploaded PDF to SVG template.
    Uses Inkscape command-line if available (best quality),
    falls back to pdf2image + potrace.
    """
    # Try Inkscape first (highest quality vector conversion)
    try:
        subprocess.run([
            'inkscape',
            '--without-gui',
            '--file=' + pdf_path,
            '--export-plain-svg=' + output_svg_path
        ], check=True, timeout=30)
        return output_svg_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    
    # Fallback: pdf2image → PNG → potrace → SVG
    images = convert_from_path(pdf_path, dpi=300)
    png_path = pdf_path.replace('.pdf', '.png')
    images[0].save(png_path, 'PNG')
    
    subprocess.run([
        'potrace',
        '-s',  # SVG output
        '-o', output_svg_path,
        png_path
    ], check=True)
    
    os.remove(png_path)
    return output_svg_path


def add_placeholders_to_svg(svg_path, placeholders):
    """
    Insert text placeholders into SVG template at specified coordinates.
    Accepts either structured placeholders format or maps flat overlay_coords directly.
    """
    # Map flat database overlay_coords if they are passed directly
    if 'name_x' in placeholders or 'cert_id_x' in placeholders:
        coords = placeholders
        placeholders = {
            'name': {
                'x': coords.get('name_x', 300),
                'y': coords.get('name_y', 400),
                'font_size': coords.get('name_font_size', 24)
            },
            'cert_id': {
                'x': coords.get('cert_id_x', 50),
                'y': coords.get('cert_id_y', 50),
                'font_size': coords.get('cert_id_font_size', 12)
            },
            'qr': {
                'x': coords.get('qr_x', 450),
                'y': coords.get('qr_y', 50),
                'size': coords.get('qr_size', 100)
            },
            'date': {
                'x': coords.get('date_x', 50),
                'y': coords.get('date_y', 30),
                'font_size': coords.get('date_font_size', 10)
            }
        }

    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    tree = ET.parse(svg_path)
    root = tree.getroot()
    
    ns = 'http://www.w3.org/2000/svg'
    
    for key, coords in placeholders.items():
        if key == 'qr':
            # QR code placeholder
            image = ET.SubElement(root, 'image')
            image.set('id', 'placeholder-qr')
            image.set('x', str(coords['x']))
            image.set('y', str(coords['y']))
            image.set('width', str(coords.get('size', 100)))
            image.set('height', str(coords.get('size', 100)))
            image.set('preserveAspectRatio', 'xMidYMid meet')
        else:
            # Text placeholder
            text = ET.SubElement(root, 'text')
            text.set('id', f'placeholder-{key}')
            text.set('x', str(coords['x']))
            text.set('y', str(coords['y']))
            text.set('font-size', str(coords.get('font_size', 24)))
            text.set('font-family', 'Helvetica, Arial, sans-serif')
            text.set('fill', '#000000')
            text.set('text-anchor', 'middle')
            text.text = f'{{{{{key}}}}}'  # Template variable: {{name}}, {{cert_id}}, {{date}}
    
    tree.write(svg_path, encoding='utf-8', xml_declaration=True)
    return svg_path
