import io
import logging
from typing import List, Dict
logger = logging.getLogger(__name__)
NAME_KEYWORDS = ['name', 'recipient', 'awarded', 'presented to', 'this certifies']
DATE_KEYWORDS = ['date', 'issued', 'awarded on', 'day of', 'completed']
ID_KEYWORDS = ['certificate no', 'cert id', 'id:', 'number', 'reference']


def _pil_from_pdf(pdf_path: str):
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes('png')
        from PIL import Image
        return Image.open(io.BytesIO(img_bytes))
    except ImportError:
        pass
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=1)
        return pages[0] if pages else None
    except Exception:
        return None


def _pil_from_png(png_path: str):
    from PIL import Image
    return Image.open(png_path)


def analyze_template(file_path: str, file_type: str = 'pdf') -> Dict:
    result = {'width': 842, 'height': 595, 'regions': [], 'ocr_available': False,
              'message': 'OCR not available — use manual field placement'}
    try:
        import pytesseract
        from PIL import Image
        img = _pil_from_pdf(file_path) if file_type == 'pdf' else _pil_from_png(file_path)
        if img is None:
            result['regions'] = _default_regions()
            return result
        img_w, img_h = img.size
        result['ocr_available'] = True
        result['message'] = 'OCR complete'
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        regions = []
        n = len(data['text'])
        for i in range(n):
            word = (data['text'][i] or '').strip()
            conf = int(data['conf'][i]) if str(data['conf'][i]).lstrip('-').isdigit() else 0
            if not word or conf < 40:
                continue
            x = data['left'][i]
            y = data['top'][i]
            w = data['width'][i]
            h = data['height'][i]
            word_lower = word.lower()
            region_type = None
            for kw in NAME_KEYWORDS:
                if kw in word_lower:
                    region_type = 'name'
                    break
            if not region_type:
                for kw in DATE_KEYWORDS:
                    if kw in word_lower:
                        region_type = 'date'
                        break
            if not region_type:
                for kw in ID_KEYWORDS:
                    if kw in word_lower:
                        region_type = 'cert_id'
                        break
            if region_type:
                norm_x = round(x * 842 / img_w)
                norm_y = round((img_h - y - h) * 595 / img_h)
                norm_w = round(w * 842 / img_w)
                norm_h = round(h * 595 / img_h)
                regions.append({'type': region_type, 'x': norm_x, 'y': norm_y, 'w': max(norm_w, 120),
                               'h': max(norm_h, 20), 'text': word, 'confidence': conf, 'source': 'ocr'})
        seen = {}
        for r in sorted(regions, key=lambda x: x['confidence'], reverse=True):
            if r['type'] not in seen:
                seen[r['type']] = r
        result['regions'] = list(seen.values())
        if not result['regions']:
            result['regions'] = _default_regions()
            result['message'] = 'OCR ran but no editable fields detected — defaults applied'
        return result
    except ImportError:
        result['regions'] = _default_regions()
        return result
    except Exception as e:
        logger.warning(f'OCR analysis failed: {e}')
        result['regions'] = _default_regions()
        result['message'] = f'OCR error: {str(e)} — defaults applied'
        return result


def _default_regions() -> List[Dict]:
    return [{'type': 'name', 'x': 100, 'y': 280, 'w': 400, 'h': 40, 'text': 'PARTICIPANT NAME', 'confidence': 0, 'source': 'default'}, {'type': 'date', 'x': 100, 'y': 160, 'w': 200, 'h': 24, 'text': 'DATE', 'confidence': 0, 'source': 'default'}, {'type': 'cert_id', 'x': 100, 'y': 80, 'w': 250, 'h': 20, 'text': 'CERT ID', 'confidence': 0, 'source': 'default'}]
