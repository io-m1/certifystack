import os
import tempfile
from flask import Blueprint, request, jsonify
from flask_login import login_required
from app.models import db, CertificateType
from app.engine.format_detector import detect_format
from app.engine.format_converter import convert_to_svg
from app.engine.svg_template_loader import load_template
from app.engine.exceptions import CertificateEngineError

bp = Blueprint('template_upload', __name__)


@bp.route('/admin/templates/upload', methods=['POST'])
@login_required
def upload_template():
    """Endpoint for uploading raw design files and normalizing them to SVG."""
    if not request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = next(iter(request.files.values()))
    cert_type_id = request.form.get('cert_type_id')
    if not cert_type_id:
        return jsonify({'error': 'cert_type_id required'}), 400
        
    cert_type = CertificateType.query.get(cert_type_id)
    if not cert_type:
        return jsonify({'error': 'CertificateType not found'}), 404
        
    # Save the uploaded file to a temporary location for pipeline processing
    temp_dir = tempfile.gettempdir()
    suffix = os.path.splitext(file.filename)[1]
    temp_input_path = os.path.join(temp_dir, f"upload_{cert_type_id}{suffix}")
    file.save(temp_input_path)
    
    try:
        detection = detect_format(temp_input_path)
        result = convert_to_svg(temp_input_path, "uploads")
        fields = load_template(result.output_svg_path)
        
        # Populate new normalization fields on model
        cert_type.original_format = detection.detected_format.value
        cert_type.conversion_path = result.conversion_path
        cert_type.quality_level = result.quality_level
        cert_type.master_svg_path = result.output_svg_path
        cert_type.detected_fields = [f._asdict() for f in fields]
        db.session.commit()
        
        detected_fields_resp = [{
            "field_id": f.field_id,
            "suggested_type": f.field_type,
            "display_text": f.display_text,
            "font_family": f.font_family,
            "font_size": f.font_size,
            "text_color": f.text_color,
            "confidence": "high"
        } for f in fields]
        
        return jsonify({
            "success": True,
            "template_id": cert_type.id,
            "template_format": "svg",
            "conversion_path": result.conversion_path,
            "quality_level": result.quality_level,
            "text_preserved": result.text_preserved,
            "detected_fields": detected_fields_resp,
            "warnings": result.warnings,
            "next_steps": result.admin_next_steps
        })
    except CertificateEngineError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f"Processing failed: {e}"}), 500
    finally:
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
