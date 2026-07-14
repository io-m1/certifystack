import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


def send_certificate_job(log_id: int, user_id: int, cert_type_id: int,
                          draft_id: int = None):
    from app import create_app
    from app.models import db, User, CertificateType, EmailLog, CertArchive, OrgSettings, EmailDraft
    from app.engine.renderer import render_certificate_pdf
    from app.services.email.sender import dispatch
    from app.services.email.templates import render, build_context, DEFAULT_CERT_SUBJECT, DEFAULT_CERT_BODY

    app = create_app()
    with app.app_context():
        log = db.session.get(EmailLog, log_id)
        user = db.session.get(User, user_id)
        cert_type = db.session.get(CertificateType, cert_type_id)
        org = OrgSettings.query.first() or OrgSettings()

        if not log or not user or not cert_type:
            logger.error(f"Missing record: log={log_id} user={user_id} ct={cert_type_id}")
            return

        log.status = 'processing'
        log.started_at = datetime.utcnow()
        db.session.commit()

        try:
            issue_date = (user.sent_at or datetime.utcnow()).strftime('%d %B %Y')
            base_url = (org.verify_base_url or '').rstrip('/')
            verify_url = f"{base_url}/verify/{user.certificate_id}" if base_url and user.certificate_id else ''

            archive = CertArchive.query.filter_by(
                certificate_id=user.certificate_id).first()

            if archive and archive.pdf_binary:
                pdf_bytes = archive.pdf_binary
                logger.info(f"Using archived PDF for {user.certificate_id}")
            else:
                pdf_bytes = render_certificate_pdf(user, cert_type, org)
                if archive:
                    archive.pdf_binary = pdf_bytes
                else:
                    db.session.add(CertArchive(
                        certificate_id=user.certificate_id,
                        full_name=user.full_name,
                        cert_name=cert_type.name,
                        course_code=cert_type.course_code,
                        issued_date=issue_date,
                        email=user.email,
                        status='issued',
                        pdf_binary=pdf_bytes,
                        raw_binary=json.dumps({
                            'email': user.email,
                            'cert_type_id': cert_type_id,
                            'include_qr': user.include_qr,
                        }).encode('utf-8')
                    ))
                db.session.flush()

            ctx = build_context(user, cert_type, org, base_url, base_url)
            draft = db.session.get(EmailDraft, draft_id) if draft_id else None
            subject_tpl = (draft.subject if draft else None) or cert_type.email_subject or DEFAULT_CERT_SUBJECT
            body_tpl    = (draft.body    if draft else None) or cert_type.email_message  or DEFAULT_CERT_BODY

            subject = render(subject_tpl, ctx)
            body    = render(body_tpl, ctx)

            result = dispatch(
                to_email=user.email,
                subject=subject,
                body=body,
                from_name=org.sender_name or 'Medical Locum Jobs Academy',
                from_email=org.sender_email or app.config.get('MAIL_USERNAME', ''),
                reply_to=org.reply_to_email or '',
                attachments=[{
                    'data': pdf_bytes,
                    'filename': f"{user.certificate_id}.pdf"
                }],
            )

            if result['success']:
                log.status = 'sent'
                log.sent_at = datetime.utcnow()
                user.status = 'sent'
            else:
                log.status = 'failed'
                log.failed_reason = result['error']
                log.retry_count = (log.retry_count or 0) + result['attempts'] - 1
                user.status = 'approved'  # revert so admin can retry

            db.session.commit()

        except Exception as e:
            logger.error(f"Certificate job failed log={log_id}: {e}")
            try:
                db.session.rollback()
                log.status = 'failed'
                log.failed_reason = str(e)
                if user:
                    user.status = 'approved'
                db.session.commit()
            except Exception:
                pass
            raise


def send_campaign_job(log_id: int, user_id: int, draft_id: int,
                       campaign_id: int = None):
    from app import create_app
    from app.models import db, User, EmailLog, EmailDraft, Campaign, OrgSettings
    from app.services.email.sender import dispatch
    from app.services.email.templates import render, build_context

    app = create_app()
    with app.app_context():
        log  = db.session.get(EmailLog, log_id)
        user = db.session.get(User, user_id)
        draft = db.session.get(EmailDraft, draft_id)
        org  = OrgSettings.query.first() or OrgSettings()

        if not log or not user or not draft:
            return

        if user.unsubscribed:
            log.status = 'cancelled'
            log.failed_reason = 'unsubscribed'
            db.session.commit()
            return

        log.status = 'processing'
        log.started_at = datetime.utcnow()
        db.session.commit()

        try:
            base_url = (org.verify_base_url or '').rstrip('/')
            ctx = build_context(user, None, org, base_url, base_url)
            subject = render(draft.subject, ctx)
            body    = render(draft.body,    ctx)

            result = dispatch(
                to_email=user.email,
                subject=subject,
                body=body,
                from_name=org.sender_name or 'Medical Locum Jobs',
                from_email=org.sender_email or app.config.get('MAIL_USERNAME', ''),
                reply_to=org.reply_to_email or '',
                attachments=None,
            )

            if result['success']:
                log.status = 'sent'
                log.sent_at = datetime.utcnow()
            else:
                log.status = 'failed'
                log.failed_reason = result['error']

            if campaign_id:
                camp = db.session.get(Campaign, campaign_id)
                if camp:
                    if result['success']:
                        camp.sent_count = (camp.sent_count or 0) + 1
                    else:
                        camp.failed_count = (camp.failed_count or 0) + 1

            db.session.commit()

        except Exception as e:
            logger.error(f"Campaign job failed log={log_id}: {e}")
            try:
                db.session.rollback()
                log.status = 'failed'
                log.failed_reason = str(e)
                db.session.commit()
            except Exception:
                pass
            raise
