"""
Certificate generation service.

Mirrors the MedLocum pipeline's separation of concerns:
approval creates/records the certificate (generate), dispatch is a later,
admin-triggered step (see app.services.email). Generated PDFs are stored
permanently in CertArchive.pdf_binary so the exact bytes a registrant was
approved with are what later gets emailed and what /verify vouches for.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_for_user(user, cert_type, org) -> bytes:
    """Render the registrant's certificate and persist it to the archive.
    Caller is responsible for committing the session."""
    from app.models import db, CertArchive
    from app.engine.renderer import render_certificate_pdf

    issued_at = user.approved_at or datetime.utcnow()
    pdf_bytes = render_certificate_pdf(user, cert_type, org, issued_at=issued_at)
    issued_date = issued_at.strftime('%d %B %Y')

    archive = CertArchive.query.filter_by(certificate_id=user.certificate_id).first()
    if archive:
        archive.pdf_binary = pdf_bytes
        archive.full_name = user.full_name
        archive.issued_date = issued_date
        archive.status = 'generated'
    else:
        db.session.add(CertArchive(
            certificate_id=user.certificate_id,
            full_name=user.full_name,
            cert_name=cert_type.name,
            course_code=cert_type.course_code,
            issued_date=issued_date,
            email=user.email,
            status='generated',
            pdf_binary=pdf_bytes,
            raw_binary=json.dumps({
                'email': user.email,
                'cert_type_id': cert_type.id,
                'include_qr': user.include_qr,
            }).encode('utf-8'),
        ))

    user.generated_at = datetime.utcnow()
    return pdf_bytes


def generate_certificates_job(user_ids: list):
    """Background job: generate certificates for freshly approved
    registrants. Runs in the worker thread with its own app context."""
    from app import create_app
    from app.models import db, User, CertificateType, OrgSettings, AuditLog

    app = create_app()
    with app.app_context():
        org = OrgSettings.query.first() or OrgSettings()
        generated = failed = 0

        for uid in user_ids:
            user = db.session.get(User, uid)
            if not user or user.status != 'approved':
                continue
            cert_type = db.session.get(CertificateType, user.certificate_type_id)
            if not cert_type:
                continue
            try:
                generate_for_user(user, cert_type, org)
                db.session.commit()
                generated += 1
            except Exception as exc:
                db.session.rollback()
                logger.error('Certificate generation failed user_id=%s: %s', uid, exc)
                try:
                    db.session.add(AuditLog(
                        user_id=uid, action='generate_failed', performed_by='system',
                        details={'error': str(exc)},
                    ))
                    db.session.commit()
                except Exception:
                    pass
                failed += 1

        if generated or failed:
            try:
                db.session.add(AuditLog(
                    action='certificates_generated', performed_by='system',
                    details={'generated': generated, 'failed': failed},
                ))
                db.session.commit()
            except Exception:
                pass
        logger.info('Certificate generation batch: %s generated, %s failed', generated, failed)
