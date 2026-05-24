from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import db, User, CertificateType, EmailLog, Campaign, OrgSettings, CertArchive
from datetime import datetime
import json
from sqlalchemy import func

bp = Blueprint('email_routes', __name__)

def summary_stats(cert_type_id=None):
    q = db.session.query(EmailLog.status, func.count(EmailLog.id)).group_by(EmailLog.status)
    if cert_type_id:
        q = q.join(User).filter(User.certificate_type_id == cert_type_id)
    return {status: count for status, count in q.all()}

def failed_logs(limit=100):
    logs = EmailLog.query.filter_by(status='failed').order_by(EmailLog.created_at.desc()).limit(limit).all()
    return [{'id': l.id, 'recipient_email': l.recipient_email, 'failed_reason': l.failed_reason, 'sent_at': l.sent_at} for l in logs]

def campaign_stats(cid):
    c = db.session.get(Campaign, cid)
    if not c: return {}
    return {'sent': c.sent_count, 'failed': c.failed_count, 'total': c.recipient_count}



@bp.route('/api/email/send', methods=['POST'])
@login_required
def send_emails():
    data = request.json or {}
    user_ids = data.get('user_ids', [])
    cert_type_id = data.get('cert_type_id')
    draft_id = data.get('draft_id')
    confirmed = data.get('confirmed', False)
    send_rate = int(data.get('send_rate', 15))
    ct = CertificateType.query.get_or_404(cert_type_id)
    org = OrgSettings.query.first() or OrgSettings()
    eligible = User.query.filter(User.id.in_(user_ids), User.status == 'approved').all() if user_ids else []
    if not confirmed:
        return jsonify({'needs_confirmation': True, 'recipient_count': len(eligible), 'course': ct.name, 'period': ct.period, 'sender': f"{org.sender_name} <{org.sender_email or current_app.config.get('MAIL_USERNAME', '')}>", 'cert_count': len(eligible), 'send_rate': send_rate, 'est_minutes': round(len(eligible) / max(send_rate, 1), 1)})
    # No longer setting user.status = 'sending' here
    db.session.flush()

    current_app.task_queue.enqueue('process_bulk_certificates', idempotency_key=f"bulk_{cert_type_id}_{datetime.utcnow().strftime('%Y%m%d%H%M')}", user_ids=[
                                   u.id for u in eligible], certificate_type_id=cert_type_id, draft_id=draft_id)
    queued = len(eligible)
    db.session.commit()
    return jsonify({'message': f'{queued} certificates queued', 'queued': queued})


@bp.route('/api/email/send-all-approved', methods=['POST'])
@login_required
def send_all_approved():
    data = request.json or {}
    cert_type_id = data.get('cert_type_id')
    draft_id = data.get('draft_id')
    confirmed = data.get('confirmed', False)
    send_rate = int(data.get('send_rate', 15))
    ct = CertificateType.query.get_or_404(cert_type_id)
    org = OrgSettings.query.first() or OrgSettings()
    eligible = User.query.filter_by(certificate_type_id=cert_type_id, status='approved').all()
    if not confirmed:
        return jsonify({'needs_confirmation': True, 'recipient_count': len(eligible), 'course': ct.name, 'period': ct.period, 'sender': f"{org.sender_name} <{org.sender_email or current_app.config.get('MAIL_USERNAME', '')}>", 'cert_count': len(eligible), 'send_rate': send_rate, 'est_minutes': round(len(eligible) / max(send_rate, 1), 1)})
    if not eligible:
        return jsonify({'message': 'No approved participants found', 'queued': 0})
    # No longer setting user.status = 'sending' here
    db.session.flush()

    current_app.task_queue.enqueue('process_bulk_certificates', idempotency_key=f"bulk_all_{cert_type_id}_{datetime.utcnow().strftime('%Y%m%d%H%M')}", user_ids=[
                                   u.id for u in eligible], certificate_type_id=cert_type_id, draft_id=draft_id)
    queued = len(eligible)
    db.session.commit()
    return jsonify({'message': f'{queued} certificates queued', 'queued': queued})


@bp.route('/api/email/logs')
@login_required
def get_logs():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    status = request.args.get('status')
    email_type = request.args.get('type')
    q = EmailLog.query
    if status:
        q = q.filter_by(status=status)
    if email_type:
        q = q.filter_by(email_type=email_type)
    logs = q.order_by(EmailLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({'logs': [{'id': l.id, 'recipient_email': l.recipient_email, 'recipient_name': l.recipient_name, 'email_type': l.email_type, 'status': l.status, 'failed_reason': l.failed_reason or '', 'retry_count': l.retry_count or 0, 'sent_at': l.sent_at.strftime('%d/%m/%Y %H:%M') if l.sent_at else '', 'created_at': l.created_at.strftime('%d/%m/%Y %H:%M') if l.created_at else ''} for l in logs.items], 'total': logs.total, 'pages': logs.pages, 'page': page})


@bp.route('/api/email/logs/<int:log_id>')
@login_required
def get_log_detail(log_id):
    log = EmailLog.query.get_or_404(log_id)
    archive = None
    if log.user_id:
        user = db.session.get(User, log.user_id)
        if user and user.certificate_id:
            archive = CertArchive.query.filter_by(certificate_id=user.certificate_id).first()
    return jsonify({'id': log.id, 'recipient_email': log.recipient_email, 'recipient_name': log.recipient_name, 'status': log.status, 'failed_reason': log.failed_reason, 'sent_at': log.sent_at.strftime('%d/%m/%Y %H:%M') if log.sent_at else None, 'has_archive': archive is not None, 'certificate_id': archive.certificate_id if archive else None, 'email_type': log.email_type})


@bp.route('/api/email/stats')
@login_required
def get_stats():
    ct_id = request.args.get('cert_type_id', type=int)
    return jsonify(summary_stats(ct_id))


@bp.route('/api/email/failed')
@login_required
def get_failed():
    return jsonify(failed_logs(100))


@bp.route('/api/email/retry', methods=['POST'])
@login_required
def retry_emails():
    log_ids = request.json.get('log_ids', [])
    if not log_ids:
        return (jsonify({'error': 'No log IDs provided'}), 400)
    from app.models import Certificate, CertificateStatus
    for log_id in log_ids:
        log = db.session.get(EmailLog, log_id)
        if log and log.user_id:
            user = log.user
            cert = Certificate.query.get(user.certificate_id) if user.certificate_id else None
            
            if cert and cert.status in [CertificateStatus.READY_FOR_DISPATCH, CertificateStatus.DISPATCH_FAILED]:
                # If generation was successful, just retry dispatch
                current_app.task_queue.enqueue(
                    'dispatch_certificate', 
                    idempotency_key=f"cert_{cert.id}_dispatch_{datetime.utcnow().strftime('%Y%m%d%H%M')}", 
                    certificate_id=cert.id
                )
            else:
                # Otherwise restart from generation
                current_app.task_queue.enqueue(
                    'process_bulk_certificates', 
                    idempotency_key=f"retry_{user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M')}", 
                    user_ids=[user.id], 
                    certificate_type_id=user.certificate_type_id
                )
    return jsonify({'message': f'{len(log_ids)} emails queued for retry'})


@bp.route('/api/email/campaigns', methods=['GET'])
@login_required
def list_campaigns():
    camps = Campaign.query.order_by(Campaign.created_at.desc()).all()
    return jsonify([{'id': c.id, 'name': c.name, 'status': c.status, 'recipient_count': c.recipient_count, 'sent_count': c.sent_count, 'failed_count': c.failed_count, 'include_attachment': c.include_attachment, 'scheduled_at': c.scheduled_at.strftime('%d/%m/%Y %H:%M') if c.scheduled_at else '', 'sent_at': c.sent_at.strftime('%d/%m/%Y %H:%M') if c.sent_at else '', 'created_at': c.created_at.strftime('%d/%m/%Y') if c.created_at else ''} for c in camps])


@bp.route('/api/email/campaigns', methods=['POST'])
@login_required
def create_campaign():
    data = request.json or {}
    cert_type_id = data.get('cert_type_id')
    draft_id = data.get('draft_id')
    send_now = data.get('send_now', False)
    send_rate = int(data.get('send_rate', 15))
    scheduled_at_str = data.get('scheduled_at')
    audience_filter = data.get('audience_filter', 'sent')
    if not draft_id:
        return (jsonify({'error': 'Draft required'}), 400)
    q = User.query.filter_by(unsubscribed=False)
    if cert_type_id:
        q = q.filter_by(certificate_type_id=cert_type_id)
    if audience_filter == 'sent':
        q = q.filter_by(status='sent')
    elif audience_filter == 'archived':
        q = q.filter_by(status='archived')
    users = q.all()
    scheduled_at = None
    if scheduled_at_str:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str)
        except ValueError:
            return (jsonify({'error': 'Invalid scheduled_at format (use ISO 8601)'}), 400)
    camp = Campaign(name=data.get('name', f"Campaign {datetime.utcnow().strftime('%d/%m/%Y')}"), cert_type_id=cert_type_id, draft_id=draft_id, include_attachment=False, recipient_count=len(
        users), status='scheduled' if scheduled_at else 'draft' if not send_now else 'sending', scheduled_at=scheduled_at, created_by=current_user.email)
    db.session.add(camp)
    db.session.commit()
    if send_now or scheduled_at:
        current_app.task_queue.enqueue('process_campaign', idempotency_key=f"campaign_{camp.id}", campaign_id=camp.id, user_ids=[u.id for u in users], draft_id=draft_id)
        camp.recipient_count = len(users)
        db.session.commit()
    return jsonify({'id': camp.id, 'message': f'Campaign created ({len(users)} recipients)'})


@bp.route('/api/email/campaigns/<int:cid>/stats')
@login_required
def get_campaign_stats(cid):
    return jsonify(campaign_stats(cid))


@bp.route('/api/email/campaigns/<int:cid>/resend', methods=['POST'])
@login_required
def resend_campaign(cid):
    failed = EmailLog.query.filter_by(campaign_id=cid, status='failed').all()
    log_ids = [l.id for l in failed]
    from app.models import Certificate, CertificateStatus
    for log_id in log_ids:
        log = db.session.get(EmailLog, log_id)
        if log and log.user_id:
            user = log.user
            cert = Certificate.query.get(user.certificate_id) if user.certificate_id else None
            
            if cert and cert.status in [CertificateStatus.READY_FOR_DISPATCH, CertificateStatus.DISPATCH_FAILED]:
                current_app.task_queue.enqueue(
                    'dispatch_certificate', 
                    idempotency_key=f"cert_{cert.id}_dispatch_{datetime.utcnow().strftime('%Y%m%d%H%M')}", 
                    certificate_id=cert.id
                )
            else:
                current_app.task_queue.enqueue(
                    'process_bulk_certificates', 
                    idempotency_key=f"resend_{user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M')}", 
                    user_ids=[user.id], 
                    certificate_type_id=user.certificate_type_id
                )
    return jsonify({'message': f'{len(log_ids)} emails re-queued'})


@bp.route('/unsubscribe/<int:user_id>', methods=['GET', 'POST'])
def unsubscribe(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.unsubscribed = True
        db.session.commit()
    return '<html><body style="font-family:-apple-system,sans-serif;text-align:center;padding:60px;color:#374151"><h2 style="color:#1a7a3c">✓ Unsubscribed</h2><p style="margin-top:12px">You have been removed from our mailing list.</p><p style="font-size:12px;color:#9ca3af;margin-top:20px">You will still receive operational emails such as certificate dispatch.</p></body></html>'


@bp.route('/api/email/dns-guide')
@login_required
def dns_guide():
    org = OrgSettings.query.first() or OrgSettings()
    domain = (org.sender_email or '').split('@')[-1] or 'yourdomain.com'
    return jsonify({'domain': domain, 'records': [{'type': 'SPF', 'name': domain, 'value': f'v=spf1 include:_spf.google.com include:{domain} ~all', 'ttl': 3600, 'description': 'Authorises your mail server to send on behalf of this domain.'}, {'type': 'DMARC', 'name': f'_dmarc.{domain}', 'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}; pct=100', 'ttl': 3600, 'description': 'Policy for handling unauthenticated mail. Start with p=none for monitoring.'}, {'type': 'DKIM', 'name': f'mail._domainkey.{domain}', 'value': 'Generated by your SMTP provider (Gmail, Mailgun, SendGrid, etc.)', 'ttl': 3600, 'description': 'DKIM signing key — obtain from your SMTP provider dashboard.'}], 'notes': ['Configure these records in your domain DNS panel (Cloudflare, Route53, etc.)', 'SPF + DKIM together dramatically reduce spam placement.', 'DMARC should be set to p=none first for monitoring, then p=quarantine.', 'Gmail App Passwords work with smtp.gmail.com port 587.', 'For higher volumes use SendGrid, Mailgun or AWS SES as SMTP relay.']})
