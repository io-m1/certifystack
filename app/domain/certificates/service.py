def resolve_certificate_asset(cert_type):
    from app.models import db, CertificateAsset
    if cert_type.asset_id:
        asset = db.session.get(CertificateAsset, cert_type.asset_id)
        if asset and asset.file_binary:
            return asset.file_binary

    raise RuntimeError("CERT_ASSET_MISSING")


def ensure_svg_template(cert_type):
    """
    Ensures that the SVG template exists on disk.
    If it is missing (e.g. after a deployment or container restart),
    it automatically regenerates the SVG using the database asset.
    """
    import os
    import logging
    logger = logging.getLogger(__name__)

    if not cert_type.master_svg_path:
        return None

    if os.path.exists(cert_type.master_svg_path):
        return cert_type.master_svg_path

    logger.warning(f"SVG template {cert_type.master_svg_path} missing from disk. Attempting to regenerate...")
    try:
        os.makedirs("uploads", exist_ok=True)
        pdf_bytes = resolve_certificate_asset(cert_type)
        
        pdf_path = f"uploads/{cert_type.id}_master.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        
        from app.engine.template_converter import pdf_to_svg, add_placeholders_to_svg
        pdf_to_svg(pdf_path, cert_type.master_svg_path)
        add_placeholders_to_svg(cert_type.master_svg_path, cert_type.overlay_coords)
        
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            
        logger.info(f"Successfully regenerated SVG template at {cert_type.master_svg_path}")
        return cert_type.master_svg_path
    except Exception as e:
        logger.error(f"Failed to regenerate SVG template: {e}", exc_info=True)
        return None



def render_certificate_bytes(user, cert_type, org=None, issued_at=None):
    """The single seam every generation path goes through.

    - Gateways with an uploaded template use the SVG personalization
      pipeline (with the legacy PDF-overlay engine as fallback).
    - Gateways created without a template ('mlj' mode) render the branded
      MedLocum designed certificate ported from the medlocumjobs
      e-learning platform. No template upload is required for these.

    Returns PDF bytes; raises on failure.
    """
    import os
    from datetime import datetime

    issued_at = issued_at or user.sent_at or user.approved_at or datetime.utcnow()

    render_mode = getattr(cert_type, 'render_mode', None) or 'mlj'
    has_template = bool(
        cert_type.asset_id or cert_type.master_svg_path
        or cert_type.master_pdf_binary or cert_type.master_pdf_path
    )

    if has_template and render_mode != 'mlj':
        svg_path = ensure_svg_template(cert_type)
        if svg_path:
            from app.engine.svg2pdf import svg_to_pdf_bytes
            from app.engine.svg_personalizer import personalize

            field_data = {
                'name': user.full_name,
                'cert_id': user.certificate_id,
                'date': issued_at.strftime('%d %B %Y'),
            }
            os.makedirs('uploads', exist_ok=True)
            temp_svg = f'uploads/{user.certificate_id}_personalized.svg'
            personalize(
                template_path=svg_path,
                field_data=field_data,
                output_path=temp_svg,
                options={'auto_shrink': True},
            )
            try:
                pdf_bytes = svg_to_pdf_bytes(temp_svg)
            finally:
                if os.path.exists(temp_svg):
                    os.remove(temp_svg)
            if pdf_bytes:
                return pdf_bytes

        # Fall back to the legacy overlay engine (masking-capable) when the
        # SVG path is unavailable (e.g. inkscape missing on the host).
        if cert_type.master_pdf_path and os.path.exists(cert_type.master_pdf_path):
            from app.engine.renderer import render_certificate_pdf
            return render_certificate_pdf(user, cert_type, org, issued_at=issued_at)

        raise RuntimeError('Template could not be personalized (no usable SVG or master PDF)')

    from app.engine.renderer import render_certificate_pdf
    return render_certificate_pdf(user, cert_type, org, issued_at=issued_at)
