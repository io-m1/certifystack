"""
Unified certificate rendering facade.

Every certificate in the system is produced through render_certificate_pdf(),
which dispatches on the gateway's render mode:

  - 'mlj'     -> the MedLocum designed certificate (app.engine.mlj_certificate),
                 ported from the proven medlocumjobs e-learning pipeline.
                 No template upload required.
  - 'overlay' -> the legacy engine that overlays text onto an uploaded
                 master PDF/PNG (app.engine.pdf_processor).
"""

from datetime import datetime


def build_verify_url(org, certificate_id: str) -> str:
    base = (getattr(org, 'verify_base_url', '') or '').rstrip('/')
    if base and certificate_id:
        return f'{base}/verify/{certificate_id}'
    return ''


def render_certificate_pdf(user, cert_type, org, issued_at=None) -> bytes:
    """Render the certificate PDF for a registrant. Returns PDF bytes."""
    issued_at = issued_at or user.sent_at or user.approved_at or datetime.utcnow()
    verify_url = build_verify_url(org, user.certificate_id)

    mode = getattr(cert_type, 'render_mode', None) or (
        'overlay' if cert_type.master_pdf_path else 'mlj'
    )

    # Any template-backed mode ('overlay' or 'svg' falling back here when the
    # SVG pipeline is unavailable) personalizes the uploaded master file.
    if mode != 'mlj' and cert_type.master_pdf_path:
        from app.engine.pdf_processor import generate_personalized_pdf

        return generate_personalized_pdf(
            master_pdf_path=cert_type.master_pdf_path,
            overlay_coords=cert_type.overlay_coords or {},
            full_name=user.full_name,
            certificate_id=user.certificate_id,
            issuance_date=issued_at.strftime('%d %B %Y'),
            include_qr=user.include_qr,
            cert_name=cert_type.name,
            master_file_type=cert_type.master_file_type or 'pdf',
            verify_url=verify_url,
        )

    from app.engine.mlj_certificate import render_mlj_certificate

    return render_mlj_certificate(
        full_name=user.full_name,
        course_title=cert_type.name,
        certificate_id=user.certificate_id,
        issued_at=issued_at,
        verify_url=verify_url,
        duration_hours=getattr(cert_type, 'duration_hours', 0) or 0,
        organisation=getattr(cert_type, 'organisation', '') or (getattr(org, 'org_name', '') or ''),
        website=getattr(cert_type, 'website', '') or '',
        signatory_name=getattr(cert_type, 'signatory_name', '') or '',
        signatory_title=getattr(cert_type, 'signatory_title', '') or '',
        include_qr=user.include_qr,
    )
