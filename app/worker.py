import logging
import json
from datetime import datetime
logger = logging.getLogger(__name__)


def _get_org_settings(app_context):
    from app.models import OrgSettings
    settings = OrgSettings.query.first()
    if not settings:
        settings = OrgSettings()
    return settings


def generate_certificate(job_id: int, certificate_id: str, draft_id: int = None, **kwargs):
    from app import create_app
    from app.models import db, User, CertificateType, Certificate, JobQueue, CertificateStatus
    from app.engine.pdf_processor import generate_personalized_pdf
    from app.domain.certificates.service import resolve_certificate_asset, ensure_svg_template
    from datetime import datetime

    app = create_app()
    with app.app_context():
        job = db.session.get(JobQueue, job_id)
        cert = db.session.get(Certificate, certificate_id)
        
        if not cert:
            logger.error(f"Certificate {certificate_id} not found")
            return

        # IDEMPOTENCY CHECK: If already READY_FOR_DISPATCH or beyond, skip generation
        if cert.status in [CertificateStatus.READY_FOR_DISPATCH, CertificateStatus.QUEUED_FOR_DISPATCH, CertificateStatus.SENDING, CertificateStatus.SENT]:
            logger.info(f"Certificate {certificate_id} already generated. Skipping.")
            # If it was supposed to be queued but isn't SENT, ensure it moves forward
            if cert.status == CertificateStatus.READY_FOR_DISPATCH:
                cert.transition_to_queued()
                db.session.commit()
                _enqueue_dispatch(cert, job.payload.get('draft_id'))
            return

        try:
            cert.transition_to_generating()
            db.session.commit()

            user = cert.user
            cert_type = cert.cert_type
            org = _get_org_settings(None)

            issue_date = (user.sent_at or datetime.utcnow()).strftime('%d %B %Y')
            base_url = org.verify_base_url or ''
            verify_url = f'{base_url}/verify/{cert.id}' if base_url else ''

            if cert_type.master_svg_path:
                template_source = ensure_svg_template(cert_type) or resolve_certificate_asset(cert_type)
            else:
                template_source = resolve_certificate_asset(cert_type)

            pdf_bytes = generate_personalized_pdf(
                template_source, 
                overlay_coords=cert_type.overlay_coords, 
                full_name=user.full_name, 
                certificate_id=cert.id,
                issuance_date=issue_date, 
                include_qr=user.include_qr, 
                cert_name=cert_type.name, 
                master_file_type=cert_type.master_file_type or 'pdf', 
                verify_url=verify_url
            )

            import hashlib
            pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
            cert.transition_to_generated(pdf_bytes, pdf_hash)
            
            import os
            os.makedirs('archive', exist_ok=True)
            archive_path = f"archive/{cert.id}.pdf"
            with open(archive_path, 'wb') as f:
                f.write(pdf_bytes)
            logger.info(f"Certificate saved to archive: {archive_path}")

            cert.transition_to_ready()
            cert.transition_to_queued()
            db.session.commit()

            _enqueue_dispatch(cert, job.payload.get('draft_id'))
            logger.info(f"Certificate {certificate_id} generated and queued for dispatch")

        except Exception as e:
            logger.error(f"Generation failed for {certificate_id}: {e}", exc_info=True)
            db.session.rollback()
            cert = db.session.get(Certificate, certificate_id)
            if cert:
                cert.fail_generation(e)
                db.session.commit()
            raise


def dispatch_certificate(job_id: int, certificate_id: str, draft_id: int = None):
    from app import create_app
    from app.models import db, User, CertificateType, Certificate, EmailDraft, AuditLog, JobQueue, CertificateStatus
    from app.engine.email_sender import send_certificate_email
    from datetime import datetime

    app = create_app()
    with app.app_context():
        cert = db.session.get(Certificate, certificate_id)
        if not cert:
            logger.error(f"Certificate {certificate_id} not found for dispatch")
            return

        # IDEMPOTENCY CHECK
        if cert.status == CertificateStatus.SENT:
            logger.info(f"Certificate {certificate_id} already sent. Skipping.")
            return

        try:
            cert.transition_to_dispatching()
            db.session.commit()

            user = cert.user
            cert_type = cert.cert_type
            org = _get_org_settings(None)
            issue_date = (user.sent_at or datetime.utcnow()).strftime('%d %B %Y')
            base_url = org.verify_base_url or ''
            verify_url = f'{base_url}/verify/{cert.id}' if base_url else ''

            subject_tpl = body_tpl = None
            if draft_id:
                draft = db.session.get(EmailDraft, draft_id)
                if draft:
                    subject_tpl = draft.subject
                    body_tpl = draft.body
            elif cert_type.email_message:
                body_tpl = cert_type.email_message
            if cert_type.email_subject:
                subject_tpl = cert_type.email_subject

            # Send email - SendGrid accepted message -> SENT
            message_id = send_certificate_email(
                to_email=user.email, 
                first_name=user.first_name, 
                full_name=user.full_name, 
                course_name=cert_type.name, 
                pdf_bytes=cert.pdf_artifact, 
                certificate_id=cert.id,
                issue_date=issue_date, 
                verify_url=verify_url, 
                org_name=org.org_name, 
                sender_name=org.sender_name, 
                reply_to=org.reply_to_email, 
                subject_tpl=subject_tpl, 
                body_tpl=body_tpl, 
                include_attachment=True
            )

            cert.transition_to_sent(message_id)
            user.status = 'sent'
            user.sent_at = datetime.utcnow()
            db.session.add(AuditLog(user_id=user.id, action='sent', performed_by='system', details={'cert_id': cert.id, 'email': user.email}))
            db.session.commit()
            logger.info(f"Certificate {certificate_id} dispatched to {user.email}")

        except Exception as e:
            logger.error(f"Dispatch failed for {certificate_id}: {e}", exc_info=True)
            db.session.rollback()
            cert = db.session.get(Certificate, certificate_id)
            if cert:
                cert.fail_dispatch(e)
                db.session.commit()
            raise


def _enqueue_dispatch(cert, draft_id):
    from flask import current_app
    current_app.task_queue.enqueue(
        'dispatch_certificate', 
        idempotency_key=f"cert_{cert.id}_dispatch", 
        certificate_id=cert.id,
        draft_id=draft_id
    )


def send_nudge_email(job_id: int, user_id: int):
    from app import create_app
    from app.models import db, User, CertificateType, JobQueue
    from app.engine.email_sender import send_nudge
    app = create_app()
    with app.app_context():
        job = db.session.get(JobQueue, job_id)
        if job and job.checkpoint == "EMAIL_SENT":
            return
            
        user = db.session.get(User, user_id)
        cert_type = db.session.get(CertificateType, user.certificate_type_id)
        org = _get_org_settings(None)
        send_nudge(user.email, user.first_name, cert_type.name, org.org_name)
        
        if job:
            job.checkpoint = "EMAIL_SENT"
            db.session.commit()


def process_campaign(job_id: int, campaign_id: int, user_ids: list, draft_id: int):
    from app import create_app
    from app.models import db, Campaign, User, EmailDraft, JobQueue
    from app.engine.email_sender import send_generic_email
    from app.utils.templates import render
    app = create_app()
    with app.app_context():
        job = db.session.get(JobQueue, job_id)
        if job and job.checkpoint == "COMPLETED":
            return
            
        campaign = db.session.get(Campaign, campaign_id)
        draft = db.session.get(EmailDraft, draft_id)
        org = _get_org_settings(None)
        base_url = (org.verify_base_url or '').rstrip('/')
        if not campaign or not draft:
            logger.error(f'process_campaign: missing campaign={campaign_id} or draft={draft_id}')
            return
            
        sent = failed = 0
        for uid in user_ids:
            user = db.session.get(User, uid)
            if not user or user.unsubscribed:
                continue
            try:
                ctx = {
                    'first_name': user.first_name,
                    'full_name': user.full_name,
                    'organization_name': org.org_name,
                    'verification_link': f"{base_url}/verify/{user.certificate_id}" if user.certificate_id else "",
                    'certificate_id': user.certificate_id or "",
                }
                subject = render(draft.subject, ctx)
                body = render(draft.body, ctx)
                send_generic_email(
                    to_email=user.email,
                    subject=subject,
                    body=body,
                    reply_to=org.reply_to_email
                )
                sent += 1
            except Exception as e:
                logger.error(f'Campaign email exception uid={uid}: {e}')
                failed += 1
                
        campaign.sent_count = sent
        campaign.failed_count = failed
        campaign.status = 'sent'
        campaign.sent_at = datetime.utcnow()
        if job:
            job.checkpoint = "COMPLETED"
        db.session.commit()


def process_bulk_certificates(job_id: int, user_ids: list, certificate_type_id: int, draft_id: int = None):
    from app import create_app
    from app.models import db, User, CertificateType, Certificate, CertificateStatus
    from app.engine.cert_id import assign_certificate_id
    from flask import current_app

    app = create_app()
    with app.app_context():
        cert_type = db.session.get(CertificateType, certificate_type_id)
        if not cert_type:
            logger.error(f"CertificateType {certificate_type_id} not found")
            return

        for uid in user_ids:
            user = db.session.get(User, uid)
            if not user:
                continue

            # 1. Ensure certificate record exists (IDEMPOTENT)
            if not user.certificate_id:
                assign_certificate_id(user)
                db.session.commit()

            cert = db.session.get(Certificate, user.certificate_id)
            if not cert:
                try:
                    with db.session.begin_nested():
                        cert = Certificate(
                            id=user.certificate_id,
                            user_id=user.id,
                            cert_type_id=cert_type.id,
                            asset_id=cert_type.asset_id,
                            status=CertificateStatus.DRAFT
                        )
                        db.session.add(cert)
                except Exception:
                    # Roll back savepoint and fetch the record created concurrently by another worker
                    db.session.rollback()
                    cert = db.session.get(Certificate, user.certificate_id)
                    if not cert:
                        raise
                db.session.commit()

            # 2. Transition to APPROVED_FOR_GENERATION
            if cert.status == CertificateStatus.DRAFT:
                cert.transition_to_approved()
                db.session.commit()

            # 3. Enqueue generation job (idempotent key: cert_{user_id}_{cert_type_id})
            if cert.status == CertificateStatus.APPROVED_FOR_GENERATION:
                current_app.task_queue.enqueue(
                    'generate_certificate',
                    idempotency_key=f"cert_{user.id}_{cert_type.id}",
                    certificate_id=cert.id,
                    draft_id=draft_id
                )

        logger.info(f"Bulk certificates processed for {len(user_ids)} users")


__all__ = ["process_bulk_certificates", "generate_certificate", "dispatch_certificate", "process_campaign", "send_nudge_email"]
