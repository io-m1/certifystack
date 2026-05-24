import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Insert app to path to import engine packages directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock packages that might not be installed or need C-libraries locally
sys.modules['pdfminer'] = MagicMock()
sys.modules['pdfminer.high_level'] = MagicMock()
sys.modules['pdfminer.layout'] = MagicMock()
sys.modules['pdf2image'] = MagicMock()
sys.modules['pytesseract'] = MagicMock()
sys.modules['vtracer'] = MagicMock()
sys.modules['cairosvg'] = MagicMock()
sys.modules['cairocffi'] = MagicMock()

from app.engine.exceptions import FormatDetectionError, ConversionError
from app.engine.format_detector import detect_format, DetectedFormat, has_selectable_text
from app.engine.ocr_engine import suggest_field_type, extract_text_regions, OCRRegion
from app.engine.format_converter import convert_to_svg, ConversionPath


class TestNormalizationPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_pdf = "temp_test.pdf"
        self.temp_svg = "temp_test.svg"
        self.temp_png = "temp_test.png"
        self.temp_pptx = "temp_test.pptx"

        # Create dummy files
        with open(self.temp_pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%...\n")
        with open(self.temp_svg, "wb") as f:
            f.write(b"<svg xmlns=\"http://www.w3.org/2000/svg\"><text id=\"name\">John</text></svg>")
        with open(self.temp_png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
        with open(self.temp_pptx, "wb") as f:
            f.write(b"PK\x03\x04...ppt/presentation.xml")

    def tearDown(self):
        for path in [self.temp_pdf, self.temp_svg, self.temp_png, self.temp_pptx]:
            if os.path.exists(path):
                os.remove(path)

    @patch('app.engine.format_detector.has_selectable_text')
    def test_detect_format_pdf(self, mock_selectable):
        mock_selectable.return_value = True
        res = detect_format(self.temp_pdf)
        self.assertEqual(res.detected_format, DetectedFormat.PDF_TEXT)

        mock_selectable.return_value = False
        res = detect_format(self.temp_pdf)
        self.assertEqual(res.detected_format, DetectedFormat.PDF_FLATTENED)

    def test_detect_format_svg(self):
        res = detect_format(self.temp_svg)
        self.assertEqual(res.detected_format, DetectedFormat.SVG_TEXT)

    def test_detect_format_raster(self):
        res = detect_format(self.temp_png)
        self.assertEqual(res.detected_format, DetectedFormat.RASTER)

    def test_detect_format_unsupported(self):
        res = detect_format(self.temp_pptx)
        self.assertEqual(res.detected_format, DetectedFormat.UNSUPPORTED)

    @patch('app.engine.format_detector.extract_pages')
    def test_has_selectable_text(self, mock_extract):
        # Define a local dummy class to use as a spec instead of the mocked module
        class DummyLTTextContainer:
            def get_text(self) -> str:
                return "Awarded to John"

        mock_el = MagicMock(spec=DummyLTTextContainer)
        mock_el.get_text.return_value = "Awarded to John"
        
        mock_page = [mock_el]
        mock_extract.return_value = [mock_page]

        self.assertTrue(has_selectable_text(self.temp_pdf))

    def test_suggest_field_type(self):
        # Test Date matching
        self.assertEqual(suggest_field_type("May 24, 2026", {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}), "date")
        self.assertEqual(suggest_field_type("24/05/2026", {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}), "date")

        # Test ID matching
        self.assertEqual(suggest_field_type("Certificate ID: 12345", {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}), "certificate_id")
        self.assertEqual(suggest_field_type("cert-obs-999", {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}), "certificate_id")

        # Test Name matching (centered, height > 0.025, multiple words)
        self.assertEqual(suggest_field_type("Jane Smith", {"x": 0.4, "y": 0.5, "w": 0.2, "h": 0.04}), "name")

        # Test Unknown
        self.assertEqual(suggest_field_type("Some random description text", {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.01}), "unknown")

    @patch('pytesseract.image_to_data')
    def test_extract_text_regions_normalization(self, mock_tesseract):
        mock_tesseract.return_value = {
            "text": ["Awarded", "to", "John Doe"],
            "conf": [80, 90, 95],
            "left": [100, 200, 300],
            "top": [150, 150, 150],
            "width": [50, 20, 100],
            "height": [20, 20, 20]
        }
        
        # Mock PIL image size to 1000x800
        mock_img = MagicMock()
        mock_img.size = (1000, 800)
        
        with patch('PIL.Image.open', return_value=mock_img):
            regions = extract_text_regions(self.temp_png)
            self.assertEqual(len(regions), 3)
            # Verify x is normalized correctly: 100 / 1000 = 0.1
            self.assertAlmostEqual(regions[0].bbox["x"], 0.1)
            # Verify y is normalized correctly: 150 / 800 = 0.1875
            self.assertAlmostEqual(regions[0].bbox["y"], 0.1875)

    def test_max_file_size_error(self):
        # Mock filesize check by patching os.path.getsize
        with patch('os.path.getsize', return_value=60 * 1024 * 1024):
            with self.assertRaises(FormatDetectionError):
                detect_format(self.temp_pdf)


if __name__ == "__main__":
    unittest.main()
