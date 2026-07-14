"""
Background worker tasks.
All heavy operations: cert generation, email dispatch, campaign processing.
"""
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


# NOTE: certificate generation now happens at approval time
# (app.services.certgen.generate_certificates_job) and dispatch goes through
# app.services.email — the old combined generate_and_send path was removed.


def send_nudge_email(user_id: int):
    from app import create_app
    from app.models import db, User, CertificateType
    from app.engine.email_sender import send_nudge

    app = create_app()
    with app.app_context():
        user = db.session.get(User, user_id)
        cert_type = db.session.get(CertificateType, user.certificate_type_id)
        org = _get_org_settings(None)
        send_nudge(user.email, user.first_name, cert_type.name, org.org_name)


def process_campaign(campaign_id: int, user_ids: list, draft_id: int):
    from app import create_app
    from app.models import db, Campaign, User, EmailDraft
    from app.services.email.sender import dispatch
    from app.services.email.templates import render, build_context

    app = create_app()
    with app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        draft    = db.session.get(EmailDraft, draft_id)
        org      = _get_org_settings(None)
        base_url = (org.verify_base_url or '').rstrip('/')

        if not campaign or not draft:
            logger.error(f"process_campaign: missing campaign={campaign_id} or draft={draft_id}")
            return

        sent = failed = 0
        for uid in user_ids:
            user = db.session.get(User, uid)
            if not user or user.unsubscribed:
                continue
            try:
                ctx = build_context(user, user.certificate_type, org, base_url, base_url)
                subject = render(draft.subject, ctx)
                body    = render(draft.body,    ctx)
                result  = dispatch(
                    to_email=user.email,
                    subject=subject,
                    body=body,
                    from_name=org.sender_name or 'Medical Locum Jobs',
                    from_email=app.config.get('MAIL_USERNAME', ''),
                    reply_to=org.reply_to_email or '',
                )
                if result['success']:
                    sent += 1
                else:
                    logger.error(f"Campaign email failed uid={uid}: {result['error']}")
                    failed += 1
            except Exception as e:
                logger.error(f"Campaign email exception uid={uid}: {e}")
                failed += 1

        campaign.sent_count   = sent
        campaign.failed_count = failed
        campaign.status       = 'sent'
        campaign.sent_at      = datetime.utcnow()
        db.session.commit()

