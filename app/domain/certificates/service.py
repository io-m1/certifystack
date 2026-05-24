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


